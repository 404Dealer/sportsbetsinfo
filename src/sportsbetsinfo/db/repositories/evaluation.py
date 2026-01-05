"""Repository for Evaluation entities."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from sportsbetsinfo.core.exceptions import DuplicateEntityError
from sportsbetsinfo.core.models import Evaluation, EvaluationMetrics
from sportsbetsinfo.db.repositories.base import ImmutableRepository


class EvaluationRepository(ImmutableRepository[Evaluation]):
    """Repository for Evaluation entities.

    Evaluations score analyses against actual outcomes.
    """

    def insert(self, evaluation: Evaluation) -> Evaluation:
        """Insert a new evaluation.

        Args:
            evaluation: Evaluation to insert

        Returns:
            The inserted evaluation

        Raises:
            DuplicateEntityError: If hash already exists
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO evaluations (
                    evaluation_id, analysis_id, game_id, scored_at,
                    brier_score, log_loss, roi, edge_realized, notes, hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation.evaluation_id,
                    evaluation.analysis_id,
                    evaluation.game_id,
                    evaluation.scored_at.isoformat(),
                    evaluation.metrics.brier_score,
                    evaluation.metrics.log_loss,
                    evaluation.metrics.roi,
                    evaluation.metrics.edge_realized,
                    json.dumps(evaluation.notes) if evaluation.notes else None,
                    evaluation.hash,
                ),
            )
            self._conn.commit()
            return evaluation
        except sqlite3.IntegrityError as e:
            self._conn.rollback()
            raise DuplicateEntityError("Evaluation", evaluation.hash) from e

    def get_by_id(self, evaluation_id: str) -> Evaluation | None:
        """Get evaluation by ID.

        Args:
            evaluation_id: Evaluation UUID

        Returns:
            Evaluation if found, None otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM evaluations WHERE evaluation_id = ?",
            (evaluation_id,),
        )
        row = cursor.fetchone()
        return self._row_to_entity(row) if row else None

    def get_by_analysis_id(self, analysis_id: str) -> list[Evaluation]:
        """Get all evaluations for an analysis.

        Args:
            analysis_id: Analysis UUID

        Returns:
            List of evaluations for the analysis
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM evaluations
            WHERE analysis_id = ?
            ORDER BY scored_at DESC
            """,
            (analysis_id,),
        )
        return [self._row_to_entity(row) for row in cursor.fetchall()]

    def get_by_game_id(self, game_id: str) -> list[Evaluation]:
        """Get all evaluations for a game.

        Args:
            game_id: Game identifier

        Returns:
            List of evaluations for the game
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM evaluations
            WHERE game_id = ?
            ORDER BY scored_at DESC
            """,
            (game_id,),
        )
        return [self._row_to_entity(row) for row in cursor.fetchall()]

    def get_all(self, limit: int = 100, offset: int = 0) -> list[Evaluation]:
        """Get evaluations with pagination.

        Args:
            limit: Maximum number
            offset: Number to skip

        Returns:
            List of evaluations ordered by scored_at DESC
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM evaluations
            ORDER BY scored_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [self._row_to_entity(row) for row in cursor.fetchall()]

    def get_aggregate_metrics(self) -> dict[str, float | None]:
        """Get aggregate metrics across all evaluations.

        Returns:
            Dictionary with average metrics
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT
                AVG(brier_score) as avg_brier,
                AVG(log_loss) as avg_log_loss,
                AVG(roi) as avg_roi,
                AVG(edge_realized) as avg_edge,
                COUNT(*) as count
            FROM evaluations
            """
        )
        row = cursor.fetchone()
        return {
            "avg_brier_score": row["avg_brier"],
            "avg_log_loss": row["avg_log_loss"],
            "avg_roi": row["avg_roi"],
            "avg_edge_realized": row["avg_edge"],
            "count": row["count"],
        }

    def _row_to_entity(self, row: sqlite3.Row) -> Evaluation:
        """Convert database row to Evaluation entity.

        Args:
            row: SQLite row

        Returns:
            Evaluation with verified hash
        """
        evaluation = Evaluation(
            evaluation_id=row["evaluation_id"],
            analysis_id=row["analysis_id"],
            game_id=row["game_id"],
            scored_at=datetime.fromisoformat(row["scored_at"]),
            metrics=EvaluationMetrics(
                brier_score=row["brier_score"],
                log_loss=row["log_loss"],
                roi=row["roi"],
                edge_realized=row["edge_realized"],
            ),
            notes=json.loads(row["notes"]) if row["notes"] else None,
            hash=row["hash"],
        )
        return self._verify_hash_on_read(evaluation)
