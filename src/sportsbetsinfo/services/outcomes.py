"""Outcome ingestion service for ground truth results.

Fetches completed game results and creates Outcome objects
to enable evaluation of analyses against actual outcomes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sportsbetsinfo.clients.odds_api import OddsAPIClient
from sportsbetsinfo.config.settings import Settings
from sportsbetsinfo.core.exceptions import DuplicateEntityError
from sportsbetsinfo.core.models import FinalScore, Outcome
from sportsbetsinfo.db.connection import get_connection
from sportsbetsinfo.db.repositories.outcome import OutcomeRepository
from sportsbetsinfo.db.repositories.snapshot import SnapshotRepository


class OutcomeService:
    """Service for ingesting game outcomes (ground truth).

    Fetches final scores from The Odds API and creates
    immutable Outcome records for completed games.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize with settings.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._odds_api: OddsAPIClient | None = None

    async def __aenter__(self) -> OutcomeService:
        """Enter async context, initialize API client."""
        if self.settings.odds_api_configured:
            self._odds_api = OddsAPIClient(
                api_key=self.settings.odds_api_key,
                rate_limit=self.settings.odds_api_rate_limit,
            )
            await self._odds_api.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context, cleanup client."""
        if self._odds_api:
            await self._odds_api.__aexit__(*args)

    async def ingest_outcomes(
        self,
        sport: str = "basketball_nba",
        days_from: int = 3,
    ) -> list[Outcome]:
        """Ingest outcomes for completed games.

        Fetches scores from Odds API and creates Outcome objects
        for games that have snapshots but no outcome yet.

        Args:
            sport: Sport key for The Odds API
            days_from: Days back to fetch scores (1-3)

        Returns:
            List of created Outcome objects
        """
        if not self._odds_api:
            return []

        # Get scores from API
        scores_data = await self._odds_api.get_scores(sport, days_from=days_from)

        # Filter to completed games only
        completed_games = [
            game for game in scores_data
            if game.get("completed", False)
        ]

        if not completed_games:
            return []

        # Get game IDs that have snapshots
        with get_connection(self.settings.db_path) as conn:
            snapshot_repo = SnapshotRepository(conn)
            outcome_repo = OutcomeRepository(conn)

            # Get all game IDs from completed games
            completed_ids = [g.get("id") for g in completed_games if g.get("id")]

            # Find which ones need outcomes (have snapshots but no outcome)
            all_snapshots = snapshot_repo.get_all(limit=1000)
            snapshot_game_ids = {s.game_id for s in all_snapshots}

            # Filter to games we have snapshots for
            games_with_snapshots = [
                g for g in completed_games
                if g.get("id") in snapshot_game_ids
            ]

            # Check which don't have outcomes yet
            pending_ids = outcome_repo.get_pending_games(
                [g.get("id") for g in games_with_snapshots if g.get("id")]
            )

        # Create outcomes for pending games
        outcomes = []
        for game in completed_games:
            game_id = game.get("id")
            if game_id not in pending_ids:
                continue

            outcome = self._create_outcome_from_scores(game)
            if outcome:
                try:
                    with get_connection(self.settings.db_path) as conn:
                        repo = OutcomeRepository(conn)
                        saved = repo.insert(outcome)
                        outcomes.append(saved)
                except DuplicateEntityError:
                    # Already exists, skip
                    pass

        return outcomes

    async def ingest_outcome_for_game(
        self,
        game_id: str,
        sport: str = "basketball_nba",
        days_from: int = 3,
    ) -> Outcome | None:
        """Ingest outcome for a specific game.

        Args:
            game_id: Game identifier
            sport: Sport key
            days_from: Days back to search

        Returns:
            Created Outcome or None if not found/completed
        """
        if not self._odds_api:
            return None

        # Check if outcome already exists
        with get_connection(self.settings.db_path) as conn:
            repo = OutcomeRepository(conn)
            existing = repo.get_by_game_id(game_id)
            if existing:
                return existing

        # Fetch scores
        scores_data = await self._odds_api.get_scores(sport, days_from=days_from)

        # Find the game
        game = next(
            (g for g in scores_data if g.get("id") == game_id),
            None
        )

        if not game or not game.get("completed"):
            return None

        outcome = self._create_outcome_from_scores(game)
        if not outcome:
            return None

        try:
            with get_connection(self.settings.db_path) as conn:
                repo = OutcomeRepository(conn)
                return repo.insert(outcome)
        except DuplicateEntityError:
            # Race condition - return existing
            with get_connection(self.settings.db_path) as conn:
                repo = OutcomeRepository(conn)
                return repo.get_by_game_id(game_id)

    def _create_outcome_from_scores(
        self,
        game: dict[str, Any],
    ) -> Outcome | None:
        """Create Outcome object from Odds API scores data.

        Args:
            game: Game data from get_scores()

        Returns:
            Outcome object or None if invalid data
        """
        game_id = game.get("id")
        if not game_id:
            return None

        scores = game.get("scores")
        if not scores:
            return None

        home_team = game.get("home_team")
        away_team = game.get("away_team")

        # Extract scores
        home_score: int | None = None
        away_score: int | None = None

        for score_entry in scores:
            name = score_entry.get("name")
            score_str = score_entry.get("score")
            if score_str is not None:
                try:
                    score_val = int(score_str)
                    if name == home_team:
                        home_score = score_val
                    elif name == away_team:
                        away_score = score_val
                except (ValueError, TypeError):
                    pass

        if home_score is None or away_score is None:
            return None

        # Determine winner
        if home_score > away_score:
            winner = home_team
        elif away_score > home_score:
            winner = away_team
        else:
            winner = "tie"

        # Parse completion time
        commence_time = game.get("commence_time")
        if commence_time:
            try:
                occurred_at = datetime.fromisoformat(
                    commence_time.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                occurred_at = datetime.now(timezone.utc)
        else:
            occurred_at = datetime.now(timezone.utc)

        # Build stats summary
        stats_summary = {
            "home_team": home_team,
            "away_team": away_team,
            "sport_key": game.get("sport_key"),
            "sport_title": game.get("sport_title"),
            "last_update": game.get("last_update"),
        }

        return Outcome.create(
            game_id=game_id,
            occurred_at=occurred_at,
            final_score=FinalScore(home=home_score, away=away_score),
            winner=winner,
            stats_summary=stats_summary,
            source="odds_api",
        )

    def get_games_needing_outcomes(self) -> list[str]:
        """Get game IDs that have snapshots but no outcomes.

        Returns:
            List of game IDs needing outcome ingestion
        """
        with get_connection(self.settings.db_path) as conn:
            snapshot_repo = SnapshotRepository(conn)
            outcome_repo = OutcomeRepository(conn)

            # Get unique game IDs from snapshots
            snapshots = snapshot_repo.get_all(limit=1000)
            game_ids = list({s.game_id for s in snapshots})

            # Find pending
            return outcome_repo.get_pending_games(game_ids)
