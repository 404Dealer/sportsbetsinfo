"""Data collection service for creating InfoSnapshots.

Orchestrates fetching data from multiple sources and creating
immutable snapshots with proper versioning.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sportsbetsinfo.clients.kalshi import KalshiClient
from sportsbetsinfo.clients.odds_api import OddsAPIClient
from sportsbetsinfo.config.settings import Settings
from sportsbetsinfo.core.models import InfoSnapshot, SourceVersions
from sportsbetsinfo.db.connection import get_connection
from sportsbetsinfo.db.repositories.snapshot import SnapshotRepository


class DataCollector:
    """Service for collecting market data and creating snapshots.

    Fetches data from configured sources (Kalshi, The Odds API) and
    creates immutable InfoSnapshots with full provenance tracking.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize collector with settings.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._kalshi: KalshiClient | None = None
        self._odds_api: OddsAPIClient | None = None

    async def __aenter__(self) -> DataCollector:
        """Enter async context, initialize API clients."""
        if self.settings.kalshi_configured:
            try:
                self._kalshi = KalshiClient(
                    api_key=self.settings.kalshi_api_key,
                    private_key_path=self.settings.kalshi_private_key_path,
                    rate_limit=self.settings.kalshi_rate_limit,
                )
                await self._kalshi.__aenter__()
                await self._kalshi.authenticate()
            except Exception:
                # Kalshi auth failed - continue without it
                if self._kalshi:
                    await self._kalshi.__aexit__(None, None, None)
                self._kalshi = None

        if self.settings.odds_api_configured:
            self._odds_api = OddsAPIClient(
                api_key=self.settings.odds_api_key,
                rate_limit=self.settings.odds_api_rate_limit,
            )
            await self._odds_api.__aenter__()

        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context, cleanup clients."""
        if self._kalshi:
            await self._kalshi.__aexit__(*args)
        if self._odds_api:
            await self._odds_api.__aexit__(*args)

    async def collect_snapshot(
        self,
        game_id: str,
        sport: str = "basketball_nba",
    ) -> InfoSnapshot:
        """Collect data and create a snapshot for a game.

        Args:
            game_id: Unique game identifier
            sport: Sport key for The Odds API

        Returns:
            Created InfoSnapshot

        Note:
            The snapshot is immediately persisted to the database.
        """
        collected_at = datetime.now(timezone.utc)

        # Collect raw data from each source
        raw_payloads: dict[str, Any] = {}
        normalized_fields: dict[str, Any] = {}

        # Kalshi data
        if self._kalshi:
            try:
                kalshi_data = await self._kalshi.get_markets(
                    series_ticker=sport.upper().split("_")[-1]
                )
                raw_payloads["kalshi"] = kalshi_data

                # Normalize Kalshi markets
                kalshi_normalized = []
                for market in kalshi_data.get("markets", []):
                    kalshi_normalized.append(
                        self._kalshi.normalize_market_data(market)
                    )
                normalized_fields["kalshi_markets"] = kalshi_normalized
            except Exception as e:
                raw_payloads["kalshi_error"] = str(e)

        # The Odds API data
        if self._odds_api:
            try:
                odds_data = await self._odds_api.get_markets(
                    sport=sport,
                    markets="h2h,spreads,totals",
                )
                raw_payloads["odds_api"] = odds_data

                # Normalize events
                odds_normalized = []
                for event in odds_data.get("events", []):
                    odds_normalized.append(
                        self._odds_api.normalize_event_data(event)
                    )
                normalized_fields["odds_api_events"] = odds_normalized
                normalized_fields["odds_api_requests_remaining"] = (
                    self._odds_api.requests_remaining
                )
            except Exception as e:
                raw_payloads["odds_api_error"] = str(e)

        # Create source versions
        source_versions = SourceVersions(
            kalshi=self._kalshi.get_version() if self._kalshi else "",
            odds_api=self._odds_api.get_version() if self._odds_api else "",
        )

        # Create and save snapshot
        snapshot = InfoSnapshot.create(
            game_id=game_id,
            collected_at=collected_at,
            schema_version=self.settings.schema_version,
            source_versions=source_versions,
            raw_payloads=raw_payloads,
            normalized_fields=normalized_fields,
        )

        # Persist to database
        with get_connection(self.settings.db_path) as conn:
            repo = SnapshotRepository(conn)
            return repo.insert(snapshot)

    async def collect_bulk_snapshots(
        self,
        sport: str = "basketball_nba",
    ) -> list[InfoSnapshot]:
        """Collect snapshots for all upcoming events in a sport.

        Creates one snapshot per event found.

        Args:
            sport: Sport key for The Odds API

        Returns:
            List of created snapshots
        """
        if not self._odds_api:
            return []

        # Get all upcoming events
        odds_data = await self._odds_api.get_markets(
            sport=sport,
            markets="h2h,spreads,totals",
        )

        snapshots = []
        for event in odds_data.get("events", []):
            event_id = event.get("id")
            if event_id:
                snapshot = await self.collect_snapshot(
                    game_id=event_id,
                    sport=sport,
                )
                snapshots.append(snapshot)

        return snapshots

    async def collect_day_snapshots(
        self,
        target_date: date | None = None,
        sport: str = "basketball_nba",
    ) -> list[InfoSnapshot]:
        """Collect snapshots for all games on a specific date.

        Fetches events from The Odds API and creates a snapshot for
        each game scheduled on the target date (UTC).

        Args:
            target_date: Date to collect games for (UTC). Defaults to today.
            sport: Sport key for The Odds API

        Returns:
            List of created snapshots for games on that date
        """
        if not self._odds_api:
            return []

        # Default to today (UTC)
        if target_date is None:
            target_date = datetime.now(timezone.utc).date()

        # Get all upcoming events
        odds_data = await self._odds_api.get_markets(
            sport=sport,
            markets="h2h,spreads,totals",
        )

        # Filter to target date
        events = odds_data.get("events", [])
        day_events = self._odds_api.filter_events_by_date(events, target_date)

        # Create snapshot for each game
        snapshots = []
        for event in day_events:
            event_id = event.get("id")
            if event_id:
                snapshot = await self.collect_snapshot(
                    game_id=event_id,
                    sport=sport,
                )
                snapshots.append(snapshot)

        return snapshots

    def get_latest_snapshot(self, game_id: str) -> InfoSnapshot | None:
        """Get the most recent snapshot for a game.

        Args:
            game_id: Game identifier

        Returns:
            Most recent snapshot or None
        """
        with get_connection(self.settings.db_path) as conn:
            repo = SnapshotRepository(conn)
            return repo.get_latest_by_game_id(game_id)

    def get_snapshot_timeline(self, game_id: str) -> list[InfoSnapshot]:
        """Get all snapshots for a game in chronological order.

        This represents the "timeline of belief states" - what we
        knew at each point in time.

        Args:
            game_id: Game identifier

        Returns:
            List of snapshots ordered by collected_at
        """
        with get_connection(self.settings.db_path) as conn:
            repo = SnapshotRepository(conn)
            return repo.get_by_game_id(game_id)

    def compute_deltas(
        self,
        older_snapshot: InfoSnapshot,
        newer_snapshot: InfoSnapshot,
    ) -> dict[str, Any]:
        """Compute changes between two snapshots.

        This is the "what changed" computation that makes the
        tool useful beyond a simple odds scraper.

        Args:
            older_snapshot: Earlier snapshot
            newer_snapshot: Later snapshot

        Returns:
            Dictionary describing what changed
        """
        deltas: dict[str, Any] = {
            "time_delta_seconds": (
                newer_snapshot.collected_at - older_snapshot.collected_at
            ).total_seconds(),
            "odds_changes": [],
            "probability_changes": [],
        }

        # Compare Odds API normalized events
        older_events = {
            e["event_id"]: e
            for e in older_snapshot.normalized_fields.get("odds_api_events", [])
        }
        newer_events = {
            e["event_id"]: e
            for e in newer_snapshot.normalized_fields.get("odds_api_events", [])
        }

        for event_id, newer_event in newer_events.items():
            if event_id in older_events:
                older_event = older_events[event_id]

                # Check for odds changes
                if (
                    older_event.get("best_home_odds")
                    != newer_event.get("best_home_odds")
                    or older_event.get("best_away_odds")
                    != newer_event.get("best_away_odds")
                ):
                    deltas["odds_changes"].append({
                        "event_id": event_id,
                        "home_team": newer_event.get("home_team"),
                        "away_team": newer_event.get("away_team"),
                        "old_home_odds": older_event.get("best_home_odds"),
                        "new_home_odds": newer_event.get("best_home_odds"),
                        "old_away_odds": older_event.get("best_away_odds"),
                        "new_away_odds": newer_event.get("best_away_odds"),
                    })

                # Check for probability changes
                old_prob = older_event.get("home_no_vig_prob")
                new_prob = newer_event.get("home_no_vig_prob")
                if old_prob is not None and new_prob is not None:
                    prob_delta = new_prob - old_prob
                    if abs(prob_delta) > 0.01:  # >1% change
                        deltas["probability_changes"].append({
                            "event_id": event_id,
                            "home_team": newer_event.get("home_team"),
                            "old_probability": old_prob,
                            "new_probability": new_prob,
                            "delta": prob_delta,
                            "delta_percent": prob_delta * 100,
                        })

        return deltas
