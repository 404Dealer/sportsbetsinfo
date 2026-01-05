"""Evaluation service for scoring analyses against outcomes.

Computes Brier score, log loss, and edge metrics to measure
how well analyses predicted actual game results.
"""

from __future__ import annotations

import math
from typing import Any

from sportsbetsinfo.config.settings import Settings
from sportsbetsinfo.core.exceptions import DuplicateEntityError
from sportsbetsinfo.core.models import Analysis, Evaluation, EvaluationMetrics, Outcome
from sportsbetsinfo.db.connection import get_connection
from sportsbetsinfo.db.repositories.analysis import AnalysisRepository
from sportsbetsinfo.db.repositories.evaluation import EvaluationRepository
from sportsbetsinfo.db.repositories.outcome import OutcomeRepository


class EvaluationService:
    """Service for evaluating analyses against actual outcomes.

    Computes scoring metrics (Brier, log loss, ROI) to measure
    prediction accuracy and edge realization.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize with settings.

        Args:
            settings: Application settings
        """
        self.settings = settings

    def evaluate_all_pending(self) -> list[Evaluation]:
        """Evaluate all analyses that have outcomes but no evaluation.

        Returns:
            List of created Evaluation objects
        """
        with get_connection(self.settings.db_path) as conn:
            analysis_repo = AnalysisRepository(conn)
            outcome_repo = OutcomeRepository(conn)
            eval_repo = EvaluationRepository(conn)

            # Get all analyses
            analyses = analysis_repo.get_all(limit=1000)

            # Get all outcomes
            outcomes = outcome_repo.get_all(limit=1000)
            outcomes_by_game = {o.game_id: o for o in outcomes}

            # Get existing evaluations to avoid duplicates
            existing_evals = eval_repo.get_all(limit=10000)
            evaluated_pairs = {
                (e.analysis_id, e.game_id) for e in existing_evals
            }

        evaluations = []

        for analysis in analyses:
            # Get game_ids from the analysis comparisons
            comparisons = analysis.derived_features.get("comparisons", [])

            for comp in comparisons:
                game_id = comp.get("event_id")
                if not game_id:
                    continue

                # Skip if already evaluated
                if (analysis.analysis_id, game_id) in evaluated_pairs:
                    continue

                # Check if we have an outcome
                outcome = outcomes_by_game.get(game_id)
                if not outcome:
                    continue

                # Create evaluation
                evaluation = self._evaluate_comparison(
                    analysis=analysis,
                    comparison=comp,
                    outcome=outcome,
                )

                if evaluation:
                    try:
                        with get_connection(self.settings.db_path) as conn:
                            repo = EvaluationRepository(conn)
                            saved = repo.insert(evaluation)
                            evaluations.append(saved)
                            evaluated_pairs.add((analysis.analysis_id, game_id))
                    except DuplicateEntityError:
                        pass

        return evaluations

    def evaluate_analysis(self, analysis_id: str) -> list[Evaluation]:
        """Evaluate a specific analysis against all available outcomes.

        Args:
            analysis_id: Analysis UUID

        Returns:
            List of created Evaluation objects
        """
        with get_connection(self.settings.db_path) as conn:
            analysis_repo = AnalysisRepository(conn)
            outcome_repo = OutcomeRepository(conn)
            eval_repo = EvaluationRepository(conn)

            analysis = analysis_repo.get_by_id(analysis_id)
            if not analysis:
                return []

            # Get existing evaluations for this analysis
            existing = eval_repo.get_by_analysis_id(analysis_id)
            evaluated_games = {e.game_id for e in existing}

            outcomes = outcome_repo.get_all(limit=1000)
            outcomes_by_game = {o.game_id: o for o in outcomes}

        evaluations = []
        comparisons = analysis.derived_features.get("comparisons", [])

        for comp in comparisons:
            game_id = comp.get("event_id")
            if not game_id or game_id in evaluated_games:
                continue

            outcome = outcomes_by_game.get(game_id)
            if not outcome:
                continue

            evaluation = self._evaluate_comparison(
                analysis=analysis,
                comparison=comp,
                outcome=outcome,
            )

            if evaluation:
                try:
                    with get_connection(self.settings.db_path) as conn:
                        repo = EvaluationRepository(conn)
                        saved = repo.insert(evaluation)
                        evaluations.append(saved)
                except DuplicateEntityError:
                    pass

        return evaluations

    def _evaluate_comparison(
        self,
        analysis: Analysis,
        comparison: dict[str, Any],
        outcome: Outcome,
    ) -> Evaluation | None:
        """Evaluate a single comparison against an outcome.

        Args:
            analysis: The analysis containing the comparison
            comparison: Single game comparison from derived_features
            outcome: Actual game outcome

        Returns:
            Evaluation object or None if can't evaluate
        """
        game_id = comparison.get("event_id")
        home_team = comparison.get("home_team")

        if not game_id or not home_team:
            return None

        # Determine actual outcome (1 = home won, 0 = away won)
        home_won = outcome.winner == home_team
        actual = 1.0 if home_won else 0.0

        # Get predicted probability (Vegas with vig)
        vegas_home_prob = comparison.get("vegas_home_prob")
        kalshi_prob = comparison.get("kalshi_implied_prob")

        if vegas_home_prob is None:
            return None

        # Compute Brier score: (predicted - actual)²
        brier_score = (vegas_home_prob - actual) ** 2

        # Compute log loss: -(actual * log(p) + (1-actual) * log(1-p))
        # Clamp probability to avoid log(0)
        p = max(min(vegas_home_prob, 0.9999), 0.0001)
        log_loss = -(actual * math.log(p) + (1 - actual) * math.log(1 - p))

        # Compute edge realized (if we had Kalshi data)
        edge_realized = None
        if kalshi_prob is not None:
            # Edge = difference between Kalshi and Vegas
            # Edge realized = did betting on the edge direction win?
            delta = comparison.get("delta_home", 0)

            if abs(delta) > 0.03:  # Significant edge
                # If Kalshi > Vegas (positive delta), edge says bet NO (away)
                # If Kalshi < Vegas (negative delta), edge says bet YES (home)
                edge_bet_home = delta < 0  # Bet home when Vegas thinks home more likely

                if edge_bet_home == home_won:
                    # Edge bet would have won
                    edge_realized = abs(delta)  # Profit proportional to edge
                else:
                    # Edge bet would have lost
                    edge_realized = -abs(delta)

        # Compute simple ROI based on Vegas odds
        # If we bet $1 on home at vegas_home_prob implied odds
        roi = None
        vegas_home_odds = comparison.get("vegas_home_odds")
        if vegas_home_odds is not None:
            if home_won:
                # Won: profit = payout - stake
                if vegas_home_odds > 0:
                    payout = vegas_home_odds / 100  # +150 pays $1.50 profit
                else:
                    payout = 100 / abs(vegas_home_odds)  # -150 pays $0.67 profit
                roi = payout  # Return on $1 bet
            else:
                roi = -1.0  # Lost $1

        # Build notes
        notes = {
            "home_team": home_team,
            "away_team": comparison.get("away_team"),
            "actual_winner": outcome.winner,
            "home_won": home_won,
            "final_score": f"{outcome.final_score.away}-{outcome.final_score.home}",
            "vegas_home_prob": vegas_home_prob,
            "kalshi_prob": kalshi_prob,
            "delta": comparison.get("delta_home"),
            "edge_direction": comparison.get("edge_direction"),
        }

        return Evaluation.create(
            analysis_id=analysis.analysis_id,
            game_id=game_id,
            metrics=EvaluationMetrics(
                brier_score=round(brier_score, 6),
                log_loss=round(log_loss, 6),
                roi=round(roi, 4) if roi is not None else None,
                edge_realized=round(edge_realized, 4) if edge_realized is not None else None,
            ),
            notes=notes,
        )

    def get_aggregate_report(self) -> dict[str, Any]:
        """Get aggregate performance metrics.

        Returns:
            Dictionary with overall performance stats
        """
        with get_connection(self.settings.db_path) as conn:
            eval_repo = EvaluationRepository(conn)
            aggregates = eval_repo.get_aggregate_metrics()
            evaluations = eval_repo.get_all(limit=10000)

        # Compute additional stats
        total = len(evaluations)
        if total == 0:
            return {"error": "No evaluations found"}

        # Count edge outcomes
        edge_wins = 0
        edge_losses = 0
        edge_neutral = 0

        for e in evaluations:
            if e.metrics.edge_realized is not None:
                if e.metrics.edge_realized > 0:
                    edge_wins += 1
                elif e.metrics.edge_realized < 0:
                    edge_losses += 1
                else:
                    edge_neutral += 1

        edge_total = edge_wins + edge_losses
        edge_win_rate = edge_wins / edge_total if edge_total > 0 else None

        # ROI stats
        roi_values = [e.metrics.roi for e in evaluations if e.metrics.roi is not None]
        total_roi = sum(roi_values) if roi_values else None

        return {
            "total_evaluations": total,
            "avg_brier_score": aggregates.get("avg_brier_score"),
            "avg_log_loss": aggregates.get("avg_log_loss"),
            "avg_roi": aggregates.get("avg_roi"),
            "total_roi": total_roi,
            "avg_edge_realized": aggregates.get("avg_edge_realized"),
            "edge_bets_won": edge_wins,
            "edge_bets_lost": edge_losses,
            "edge_win_rate": edge_win_rate,
            "interpretation": self._interpret_metrics(aggregates, edge_win_rate),
        }

    def _interpret_metrics(
        self,
        aggregates: dict[str, Any],
        edge_win_rate: float | None,
    ) -> str:
        """Generate human-readable interpretation of metrics.

        Args:
            aggregates: Aggregate metrics
            edge_win_rate: Win rate on edge bets

        Returns:
            Interpretation string
        """
        parts = []

        brier = aggregates.get("avg_brier_score")
        if brier is not None:
            if brier < 0.2:
                parts.append(f"Brier {brier:.3f} (good calibration)")
            elif brier < 0.25:
                parts.append(f"Brier {brier:.3f} (fair calibration)")
            else:
                parts.append(f"Brier {brier:.3f} (needs improvement)")

        roi = aggregates.get("avg_roi")
        if roi is not None:
            if roi > 0:
                parts.append(f"ROI {roi:+.1%} (profitable)")
            else:
                parts.append(f"ROI {roi:+.1%} (losing)")

        if edge_win_rate is not None:
            if edge_win_rate > 0.55:
                parts.append(f"Edge bets {edge_win_rate:.0%} win rate (edge working)")
            elif edge_win_rate > 0.45:
                parts.append(f"Edge bets {edge_win_rate:.0%} win rate (inconclusive)")
            else:
                parts.append(f"Edge bets {edge_win_rate:.0%} win rate (edge not working)")

        return " | ".join(parts) if parts else "Insufficient data"
