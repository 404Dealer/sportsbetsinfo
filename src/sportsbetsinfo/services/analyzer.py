"""Analysis service for comparing Kalshi vs Vegas probabilities.

Computes edge metrics by comparing Kalshi prediction market prices
against Vegas sportsbook implied probabilities (with vig included).
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Any

from sportsbetsinfo.config.settings import Settings
from sportsbetsinfo.core.models import Analysis, InfoSnapshot
from sportsbetsinfo.db.connection import get_connection
from sportsbetsinfo.db.repositories.analysis import AnalysisRepository
from sportsbetsinfo.db.repositories.snapshot import SnapshotRepository


# Analysis version - bump when logic changes
ANALYSIS_VERSION = "1.0.0"


def get_git_commit() -> str:
    """Get current git commit hash for code versioning."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"


def american_to_probability(american_odds: int) -> float:
    """Convert American odds to implied probability (WITH vig).

    This gives the raw implied probability including bookmaker edge.

    Args:
        american_odds: Odds in American format (+150, -200, etc.)

    Returns:
        Implied probability (0-1), includes vig
    """
    if american_odds > 0:
        return 100 / (american_odds + 100)
    else:
        return abs(american_odds) / (abs(american_odds) + 100)


class AnalysisService:
    """Service for creating analyses comparing Kalshi vs Vegas.

    Compares prediction market prices against sportsbook odds
    to identify potential edges/mispricings.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize with settings.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._code_version = get_git_commit()

    def analyze_snapshot(
        self,
        snapshot: InfoSnapshot,
        parent_analysis_id: str | None = None,
    ) -> Analysis | None:
        """Create analysis from a single snapshot.

        Compares Kalshi prices vs Vegas implied probabilities (with vig)
        for all matchable games in the snapshot.

        Args:
            snapshot: InfoSnapshot to analyze
            parent_analysis_id: Optional parent for DAG lineage

        Returns:
            Analysis object if any comparisons possible, None otherwise
        """
        # Extract normalized data
        odds_events = snapshot.normalized_fields.get("odds_api_events", [])
        kalshi_markets = snapshot.normalized_fields.get("kalshi_markets", [])

        if not odds_events:
            return None

        # Build derived features for each game
        comparisons = []
        edges_found = []

        for event in odds_events:
            comparison = self._compare_event_to_kalshi(event, kalshi_markets)
            if comparison:
                comparisons.append(comparison)

                # Track significant edges (> 3% delta)
                if comparison.get("edge_magnitude", 0) > 0.03:
                    edges_found.append(comparison)

        if not comparisons:
            return None

        # Build derived features
        derived_features = {
            "analysis_type": "kalshi_vs_vegas_with_vig",
            "snapshot_collected_at": snapshot.collected_at.isoformat(),
            "game_count": len(odds_events),
            "matched_count": len(comparisons),
            "comparisons": comparisons,
            "edge_threshold": 0.03,
            "edges_above_threshold": len(edges_found),
        }

        # Build conclusions
        conclusions = self._build_conclusions(comparisons, edges_found)

        # Build recommended actions
        recommended_actions = self._build_recommendations(edges_found)

        # Create analysis
        analysis = Analysis.create(
            analysis_version=ANALYSIS_VERSION,
            code_version=self._code_version,
            input_snapshot_ids=[snapshot.snapshot_id],
            derived_features=derived_features,
            conclusions=conclusions,
            recommended_actions=recommended_actions,
            parent_analysis_id=parent_analysis_id,
        )

        # Persist
        with get_connection(self.settings.db_path) as conn:
            repo = AnalysisRepository(conn)
            return repo.insert(analysis)

    def analyze_game(
        self,
        game_id: str,
        parent_analysis_id: str | None = None,
    ) -> Analysis | None:
        """Analyze latest snapshot for a specific game.

        Args:
            game_id: Game identifier
            parent_analysis_id: Optional parent for DAG lineage

        Returns:
            Analysis object if snapshot exists, None otherwise
        """
        with get_connection(self.settings.db_path) as conn:
            repo = SnapshotRepository(conn)
            snapshot = repo.get_latest_by_game_id(game_id)

        if not snapshot:
            return None

        return self.analyze_snapshot(snapshot, parent_analysis_id)

    def analyze_all_games(
        self,
        limit: int = 100,
    ) -> list[Analysis]:
        """Analyze latest snapshots for all games.

        Creates one analysis per game with the most recent snapshot.

        Args:
            limit: Maximum number of games to analyze

        Returns:
            List of created analyses
        """
        with get_connection(self.settings.db_path) as conn:
            repo = SnapshotRepository(conn)
            snapshots = repo.get_all(limit=limit)

        # Group by game_id, keep only latest
        latest_by_game: dict[str, InfoSnapshot] = {}
        for snapshot in snapshots:
            game_id = snapshot.game_id
            if game_id not in latest_by_game:
                latest_by_game[game_id] = snapshot
            elif snapshot.collected_at > latest_by_game[game_id].collected_at:
                latest_by_game[game_id] = snapshot

        # Analyze each
        analyses = []
        for snapshot in latest_by_game.values():
            analysis = self.analyze_snapshot(snapshot)
            if analysis:
                analyses.append(analysis)

        return analyses

    def _compare_event_to_kalshi(
        self,
        event: dict[str, Any],
        kalshi_markets: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Compare a single odds event to Kalshi markets.

        Matches by team names and computes probability deltas.

        Args:
            event: Normalized odds API event
            kalshi_markets: List of normalized Kalshi markets

        Returns:
            Comparison dict or None if no match
        """
        home_team = event.get("home_team", "")
        away_team = event.get("away_team", "")
        best_home_odds = event.get("best_home_odds")
        best_away_odds = event.get("best_away_odds")

        if not home_team or not best_home_odds or not best_away_odds:
            return None

        # Vegas implied probabilities WITH vig (raw)
        vegas_home_prob = american_to_probability(best_home_odds)
        vegas_away_prob = american_to_probability(best_away_odds)
        vegas_total = vegas_home_prob + vegas_away_prob  # Should be > 1 (vig)
        vegas_vig = vegas_total - 1.0

        # Try to find matching Kalshi market
        kalshi_match = self._find_kalshi_match(home_team, away_team, kalshi_markets)

        comparison: dict[str, Any] = {
            "event_id": event.get("event_id"),
            "home_team": home_team,
            "away_team": away_team,
            "commence_time": event.get("commence_time"),
            "game_status": event.get("game_status", "pre_game"),
            # Vegas data (with vig)
            "vegas_home_odds": best_home_odds,
            "vegas_away_odds": best_away_odds,
            "vegas_home_prob": round(vegas_home_prob, 4),
            "vegas_away_prob": round(vegas_away_prob, 4),
            "vegas_vig": round(vegas_vig, 4),
            "vegas_vig_percent": round(vegas_vig * 100, 2),
        }

        if kalshi_match:
            kalshi_prob = kalshi_match.get("implied_probability")
            if kalshi_prob is not None:
                # Compute edge: Kalshi vs Vegas (with vig)
                # Positive delta = Kalshi higher than Vegas
                # Negative delta = Kalshi lower than Vegas
                home_delta = kalshi_prob - vegas_home_prob

                comparison.update({
                    "kalshi_market_id": kalshi_match.get("market_id"),
                    "kalshi_title": kalshi_match.get("title"),
                    "kalshi_yes_bid": kalshi_match.get("yes_bid"),
                    "kalshi_yes_ask": kalshi_match.get("yes_ask"),
                    "kalshi_implied_prob": round(kalshi_prob, 4),
                    "kalshi_volume": kalshi_match.get("volume"),
                    # Edge metrics
                    "delta_home": round(home_delta, 4),
                    "delta_home_percent": round(home_delta * 100, 2),
                    "edge_magnitude": round(abs(home_delta), 4),
                    "edge_direction": "kalshi_higher" if home_delta > 0 else "vegas_higher",
                    "matched": True,
                })
            else:
                comparison["matched"] = False
                comparison["match_note"] = "Kalshi market found but no price"
        else:
            comparison["matched"] = False
            comparison["match_note"] = "No Kalshi market found"

        return comparison

    def _find_kalshi_match(
        self,
        home_team: str,
        away_team: str,
        kalshi_markets: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Find Kalshi market matching the given teams.

        Searches market titles for team name matches.

        Args:
            home_team: Home team name
            away_team: Away team name
            kalshi_markets: List of Kalshi markets

        Returns:
            Matching market or None
        """
        home_lower = home_team.lower()
        away_lower = away_team.lower()

        # Extract key words from team names (e.g., "Lakers" from "Los Angeles Lakers")
        home_keywords = self._extract_team_keywords(home_team)
        away_keywords = self._extract_team_keywords(away_team)

        for market in kalshi_markets:
            title = (market.get("title") or "").lower()

            # Check if market title contains both teams
            home_found = any(kw in title for kw in home_keywords)
            away_found = any(kw in title for kw in away_keywords)

            if home_found and away_found:
                return market

            # Also try full team names
            if home_lower in title and away_lower in title:
                return market

        return None

    def _extract_team_keywords(self, team_name: str) -> list[str]:
        """Extract searchable keywords from team name.

        Args:
            team_name: Full team name (e.g., "Los Angeles Lakers")

        Returns:
            List of keywords to search for
        """
        words = team_name.lower().split()
        keywords = [team_name.lower()]

        # Common city names to skip
        cities = {
            "los", "angeles", "new", "york", "san", "francisco", "antonio",
            "golden", "state", "oklahoma", "city", "portland", "trail",
            "minnesota", "indiana", "milwaukee", "philadelphia", "phoenix",
            "detroit", "chicago", "boston", "miami", "orlando", "charlotte",
            "atlanta", "cleveland", "toronto", "brooklyn", "washington",
            "denver", "utah", "sacramento", "memphis", "dallas", "houston",
        }

        # Get the last word (usually the team nickname)
        if words:
            last_word = words[-1]
            if last_word not in cities:
                keywords.append(last_word)

        return keywords

    def _build_conclusions(
        self,
        comparisons: list[dict[str, Any]],
        edges_found: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build conclusions from comparisons.

        Args:
            comparisons: All game comparisons
            edges_found: Comparisons with significant edges

        Returns:
            Conclusions dictionary
        """
        matched = [c for c in comparisons if c.get("matched")]
        kalshi_higher = [c for c in matched if c.get("edge_direction") == "kalshi_higher"]
        vegas_higher = [c for c in matched if c.get("edge_direction") == "vegas_higher"]

        avg_delta = 0.0
        if matched:
            avg_delta = sum(c.get("delta_home", 0) for c in matched) / len(matched)

        avg_vig = 0.0
        if comparisons:
            avg_vig = sum(c.get("vegas_vig", 0) for c in comparisons) / len(comparisons)

        return {
            "total_games": len(comparisons),
            "matched_with_kalshi": len(matched),
            "unmatched": len(comparisons) - len(matched),
            "kalshi_higher_count": len(kalshi_higher),
            "vegas_higher_count": len(vegas_higher),
            "avg_delta": round(avg_delta, 4),
            "avg_delta_percent": round(avg_delta * 100, 2),
            "avg_vegas_vig": round(avg_vig, 4),
            "avg_vegas_vig_percent": round(avg_vig * 100, 2),
            "significant_edges": len(edges_found),
            "summary": self._generate_summary(matched, edges_found),
        }

    def _generate_summary(
        self,
        matched: list[dict[str, Any]],
        edges_found: list[dict[str, Any]],
    ) -> str:
        """Generate human-readable summary.

        Args:
            matched: Matched comparisons
            edges_found: Significant edges

        Returns:
            Summary string
        """
        if not matched:
            return "No Kalshi markets matched to Vegas games."

        if not edges_found:
            return (
                f"Analyzed {len(matched)} games with Kalshi matches. "
                "No significant edges (>3%) found."
            )

        edge_teams = [e.get("home_team", "?") for e in edges_found[:3]]
        return (
            f"Found {len(edges_found)} significant edge(s) (>3% delta) "
            f"across {len(matched)} matched games. "
            f"Top opportunities: {', '.join(edge_teams)}"
        )

    def _build_recommendations(
        self,
        edges_found: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build recommended actions from edges.

        Args:
            edges_found: Comparisons with significant edges

        Returns:
            List of recommended actions
        """
        recommendations = []

        # Sort by edge magnitude
        sorted_edges = sorted(
            edges_found,
            key=lambda x: x.get("edge_magnitude", 0),
            reverse=True,
        )

        for edge in sorted_edges[:5]:  # Top 5 recommendations
            direction = edge.get("edge_direction", "")
            delta = edge.get("delta_home_percent", 0)
            home_team = edge.get("home_team", "?")
            kalshi_prob = edge.get("kalshi_implied_prob")
            vegas_prob = edge.get("vegas_home_prob")

            if direction == "kalshi_higher":
                # Kalshi thinks home team is more likely than Vegas
                action = {
                    "type": "potential_edge",
                    "game": f"{edge.get('away_team')} @ {home_team}",
                    "signal": f"Kalshi {delta:+.1f}% vs Vegas on {home_team}",
                    "kalshi_prob": kalshi_prob,
                    "vegas_prob_with_vig": vegas_prob,
                    "interpretation": (
                        f"Kalshi market implies {home_team} has "
                        f"{kalshi_prob:.1%} chance vs Vegas {vegas_prob:.1%} (with vig). "
                        f"If you trust Vegas, consider NO on Kalshi."
                    ),
                    "event_id": edge.get("event_id"),
                    "kalshi_market_id": edge.get("kalshi_market_id"),
                }
            else:
                # Vegas thinks home team is more likely than Kalshi
                action = {
                    "type": "potential_edge",
                    "game": f"{edge.get('away_team')} @ {home_team}",
                    "signal": f"Vegas {-delta:+.1f}% vs Kalshi on {home_team}",
                    "kalshi_prob": kalshi_prob,
                    "vegas_prob_with_vig": vegas_prob,
                    "interpretation": (
                        f"Vegas implies {home_team} has "
                        f"{vegas_prob:.1%} chance (with vig) vs Kalshi {kalshi_prob:.1%}. "
                        f"If you trust Vegas, consider YES on Kalshi."
                    ),
                    "event_id": edge.get("event_id"),
                    "kalshi_market_id": edge.get("kalshi_market_id"),
                }

            recommendations.append(action)

        return recommendations
