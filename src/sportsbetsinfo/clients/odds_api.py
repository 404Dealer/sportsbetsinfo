"""The Odds API client for sports betting odds.

Documentation: https://the-odds-api.com/liveapi/guides/v4/
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sportsbetsinfo.clients.base import BaseAPIClient


class OddsAPIClient(BaseAPIClient):
    """Client for The Odds API.

    Provides real-time odds from multiple bookmakers for
    various sports. Free tier allows 500 requests/month.
    """

    API_VERSION = "v4"
    BASE_URL = "https://api.the-odds-api.com/v4"

    # Common sport keys
    SPORTS = {
        "nba": "basketball_nba",
        "nfl": "americanfootball_nfl",
        "mlb": "baseball_mlb",
        "nhl": "icehockey_nhl",
        "ncaab": "basketball_ncaab",
        "ncaaf": "americanfootball_ncaaf",
    }

    def __init__(
        self,
        api_key: str,
        rate_limit: float = 1.0,
    ) -> None:
        """Initialize The Odds API client.

        Args:
            api_key: API key from the-odds-api.com
            rate_limit: Requests per second (be conservative to stay in quota)
        """
        super().__init__(
            base_url=self.BASE_URL,
            rate_limit=rate_limit,
        )
        self.api_key = api_key
        self._requests_remaining: int | None = None
        self._requests_used: int | None = None

    def _update_quota(self, headers: dict[str, Any]) -> None:
        """Update request quota from response headers."""
        if "x-requests-remaining" in headers:
            self._requests_remaining = int(headers["x-requests-remaining"])
        if "x-requests-used" in headers:
            self._requests_used = int(headers["x-requests-used"])

    @property
    def requests_remaining(self) -> int | None:
        """Get remaining API requests for the month."""
        return self._requests_remaining

    async def get_sports(self) -> list[dict[str, Any]]:
        """Get list of available sports.

        Returns:
            List of sport dictionaries with keys and titles
        """
        response = await self.get(
            "/sports",
            params={"apiKey": self.api_key},
        )
        self._update_quota(dict(response.headers))
        return response.json()

    async def get_markets(self, **kwargs: Any) -> dict[str, Any]:
        """Get available events with odds.

        Kwargs:
            sport: Sport key (e.g., "basketball_nba")
            regions: Comma-separated regions (default "us")
            markets: Comma-separated market types (default "h2h")
            odds_format: "american" or "decimal" (default "american")

        Returns:
            Dictionary with events and remaining quota
        """
        sport = kwargs.get("sport", "upcoming")
        response = await self.get(
            f"/sports/{sport}/odds",
            params={
                "apiKey": self.api_key,
                "regions": kwargs.get("regions", "us"),
                "markets": kwargs.get("markets", "h2h"),
                "oddsFormat": kwargs.get("odds_format", "american"),
            },
        )
        self._update_quota(dict(response.headers))
        return {
            "events": response.json(),
            "requests_remaining": self._requests_remaining,
        }

    async def get_odds(self, event_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get detailed odds for a specific event.

        Args:
            event_id: The Odds API event ID
            **kwargs: Additional parameters (regions, markets, etc.)

        Returns:
            Dictionary with detailed odds from all bookmakers
        """
        sport = kwargs.get("sport", "upcoming")
        response = await self.get(
            f"/sports/{sport}/events/{event_id}/odds",
            params={
                "apiKey": self.api_key,
                "regions": kwargs.get("regions", "us"),
                "markets": kwargs.get("markets", "h2h,spreads,totals"),
                "oddsFormat": kwargs.get("odds_format", "american"),
            },
        )
        self._update_quota(dict(response.headers))
        return response.json()

    async def get_scores(
        self, sport: str, days_from: int = 1
    ) -> list[dict[str, Any]]:
        """Get recent scores/results.

        Args:
            sport: Sport key
            days_from: Days back to fetch (1-3)

        Returns:
            List of completed events with scores
        """
        response = await self.get(
            f"/sports/{sport}/scores",
            params={
                "apiKey": self.api_key,
                "daysFrom": days_from,
            },
        )
        self._update_quota(dict(response.headers))
        return response.json()

    def get_version(self) -> str:
        """Get API version string."""
        return f"odds_api_{self.API_VERSION}"

    def american_to_probability(self, american_odds: int) -> float:
        """Convert American odds to implied probability.

        Args:
            american_odds: Odds in American format (+150, -200, etc.)

        Returns:
            Implied probability (0-1)
        """
        if american_odds > 0:
            return 100 / (american_odds + 100)
        else:
            return abs(american_odds) / (abs(american_odds) + 100)

    def calculate_no_vig_probability(
        self,
        home_odds: int,
        away_odds: int,
    ) -> tuple[float, float]:
        """Calculate no-vig (fair) probabilities from odds.

        Removes the bookmaker's edge to get true implied probabilities.

        Args:
            home_odds: American odds for home team
            away_odds: American odds for away team

        Returns:
            Tuple of (home_prob, away_prob) summing to ~1.0
        """
        home_implied = self.american_to_probability(home_odds)
        away_implied = self.american_to_probability(away_odds)

        # Total probability includes vig (overround)
        total = home_implied + away_implied

        # Remove vig by normalizing
        return home_implied / total, away_implied / total

    def normalize_event_data(self, event: dict[str, Any]) -> dict[str, Any]:
        """Normalize The Odds API event data to standard format.

        Args:
            event: Raw API event data

        Returns:
            Normalized dictionary with standard fields
        """
        # Extract best odds from bookmakers
        best_home_odds: int | None = None
        best_away_odds: int | None = None
        bookmaker_count = 0

        for bookmaker in event.get("bookmakers", []):
            bookmaker_count += 1
            for market in bookmaker.get("markets", []):
                if market.get("key") == "h2h":
                    for outcome in market.get("outcomes", []):
                        price = outcome.get("price")
                        if outcome.get("name") == event.get("home_team"):
                            if best_home_odds is None or price > best_home_odds:
                                best_home_odds = price
                        elif outcome.get("name") == event.get("away_team"):
                            if best_away_odds is None or price > best_away_odds:
                                best_away_odds = price

        # Calculate no-vig probabilities if we have both odds
        home_prob: float | None = None
        away_prob: float | None = None
        if best_home_odds is not None and best_away_odds is not None:
            home_prob, away_prob = self.calculate_no_vig_probability(
                best_home_odds, best_away_odds
            )

        return {
            "source": "odds_api",
            "event_id": event.get("id"),
            "sport_key": event.get("sport_key"),
            "sport_title": event.get("sport_title"),
            "commence_time": event.get("commence_time"),
            "home_team": event.get("home_team"),
            "away_team": event.get("away_team"),
            "best_home_odds": best_home_odds,
            "best_away_odds": best_away_odds,
            "home_no_vig_prob": home_prob,
            "away_no_vig_prob": away_prob,
            "bookmaker_count": bookmaker_count,
        }

    def filter_events_by_date(
        self,
        events: list[dict[str, Any]],
        target_date: date,
    ) -> list[dict[str, Any]]:
        """Filter events to those starting on target date (UTC).

        Args:
            events: List of event dictionaries from get_markets()
            target_date: Date to filter by (UTC)

        Returns:
            Events with commence_time on the target date
        """
        filtered = []
        for event in events:
            commence_time_str = event.get("commence_time")
            if commence_time_str:
                # Parse ISO 8601 format (e.g., "2025-01-05T00:30:00Z")
                commence_dt = datetime.fromisoformat(
                    commence_time_str.replace("Z", "+00:00")
                )
                if commence_dt.date() == target_date:
                    filtered.append(event)
        return filtered

    async def get_events_with_scores(
        self,
        sport: str,
        target_date: date | None = None,
        days_from: int = 1,
    ) -> list[dict[str, Any]]:
        """Get events with both odds and scores, properly categorized by game state.

        Combines data from odds and scores endpoints to provide complete
        game information including pre-game, in-progress, and final states.

        Args:
            sport: Sport key (e.g., "basketball_nba")
            target_date: Optional date to filter by (UTC)
            days_from: Days back to fetch scores (1-3)

        Returns:
            List of events with game_status: "pre_game", "in_progress", or "completed"
        """
        # Get upcoming/live odds
        odds_data = await self.get_markets(
            sport=sport,
            markets="h2h,spreads,totals",
        )
        odds_events = odds_data.get("events", [])

        # Get recent scores
        scores_data = await self.get_scores(sport, days_from=days_from)

        # Build a lookup of scores by event ID
        scores_by_id: dict[str, dict[str, Any]] = {}
        for score_event in scores_data:
            event_id = score_event.get("id")
            if event_id:
                scores_by_id[event_id] = score_event

        # Combine and categorize events
        combined_events: dict[str, dict[str, Any]] = {}

        # Process odds events (upcoming/live)
        for event in odds_events:
            event_id = event.get("id")
            if not event_id:
                continue

            # Check if we have score data for this event
            score_data = scores_by_id.get(event_id, {})
            completed = score_data.get("completed", False)

            if completed:
                game_status = "completed"
            elif score_data.get("scores"):
                game_status = "in_progress"
            else:
                game_status = "pre_game"

            combined_events[event_id] = {
                **event,
                "game_status": game_status,
                "scores": score_data.get("scores"),
                "completed": completed,
            }

        # Add any scored events not in odds (completed games)
        for event_id, score_event in scores_by_id.items():
            if event_id not in combined_events:
                combined_events[event_id] = {
                    **score_event,
                    "game_status": "completed" if score_event.get("completed") else "in_progress",
                    "bookmakers": [],  # No odds for completed games
                }

        # Filter by date if specified
        result = list(combined_events.values())
        if target_date:
            result = self.filter_events_by_date(result, target_date)

        return result

    def normalize_event_with_status(self, event: dict[str, Any]) -> dict[str, Any]:
        """Normalize event data including game status and scores.

        Args:
            event: Event data (may include scores)

        Returns:
            Normalized dictionary with game_status and scores
        """
        # Get base normalized data
        normalized = self.normalize_event_data(event)

        # Add game status
        normalized["game_status"] = event.get("game_status", "pre_game")
        normalized["completed"] = event.get("completed", False)

        # Add scores if available
        scores = event.get("scores")
        if scores:
            home_team = event.get("home_team")
            away_team = event.get("away_team")
            home_score = next(
                (int(s["score"]) for s in scores if s["name"] == home_team),
                None
            )
            away_score = next(
                (int(s["score"]) for s in scores if s["name"] == away_team),
                None
            )
            normalized["home_score"] = home_score
            normalized["away_score"] = away_score

            # Determine winner if completed
            if normalized["completed"] and home_score is not None and away_score is not None:
                if home_score > away_score:
                    normalized["winner"] = home_team
                elif away_score > home_score:
                    normalized["winner"] = away_team
                else:
                    normalized["winner"] = "tie"
        else:
            normalized["home_score"] = None
            normalized["away_score"] = None
            normalized["winner"] = None

        return normalized
