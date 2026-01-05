"""Repository for Outcome entities."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from sportsbetsinfo.core.exceptions import DuplicateEntityError
from sportsbetsinfo.core.models import FinalScore, Outcome
from sportsbetsinfo.db.repositories.base import ImmutableRepository


class OutcomeRepository(ImmutableRepository[Outcome]):
    """Repository for Outcome (ground truth) entities.

    Each game can have only one outcome (enforced by UNIQUE constraint on game_id).
    """

    def insert(self, outcome: Outcome) -> Outcome:
        """Insert a new outcome.

        Args:
            outcome: Outcome to insert

        Returns:
            The inserted outcome

        Raises:
            DuplicateEntityError: If game_id or hash already exists
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO outcomes (
                    outcome_id, game_id, occurred_at, final_score,
                    winner, stats_summary, source, hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.outcome_id,
                    outcome.game_id,
                    outcome.occurred_at.isoformat(),
                    json.dumps(outcome.final_score.to_dict()),
                    outcome.winner,
                    json.dumps(outcome.stats_summary),
                    outcome.source,
                    outcome.hash,
                ),
            )
            self._conn.commit()
            return outcome
        except sqlite3.IntegrityError as e:
            self._conn.rollback()
            raise DuplicateEntityError("Outcome", outcome.hash) from e

    def get_by_id(self, outcome_id: str) -> Outcome | None:
        """Get outcome by ID.

        Args:
            outcome_id: Outcome UUID

        Returns:
            Outcome if found, None otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM outcomes WHERE outcome_id = ?",
            (outcome_id,),
        )
        row = cursor.fetchone()
        return self._row_to_entity(row) if row else None

    def get_by_game_id(self, game_id: str) -> Outcome | None:
        """Get outcome for a specific game.

        Args:
            game_id: Game identifier

        Returns:
            Outcome if exists, None otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM outcomes WHERE game_id = ?",
            (game_id,),
        )
        row = cursor.fetchone()
        return self._row_to_entity(row) if row else None

    def get_all(self, limit: int = 100, offset: int = 0) -> list[Outcome]:
        """Get outcomes with pagination.

        Args:
            limit: Maximum number
            offset: Number to skip

        Returns:
            List of outcomes ordered by occurred_at DESC
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM outcomes
            ORDER BY occurred_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [self._row_to_entity(row) for row in cursor.fetchall()]

    def get_pending_games(
        self, game_ids: list[str]
    ) -> list[str]:
        """Get game IDs that don't have outcomes yet.

        Args:
            game_ids: List of game IDs to check

        Returns:
            List of game IDs without outcomes
        """
        if not game_ids:
            return []

        cursor = self._conn.cursor()
        placeholders = ",".join("?" for _ in game_ids)
        cursor.execute(
            f"SELECT game_id FROM outcomes WHERE game_id IN ({placeholders})",  # noqa: S608
            game_ids,
        )
        existing = {row["game_id"] for row in cursor.fetchall()}
        return [gid for gid in game_ids if gid not in existing]

    def _row_to_entity(self, row: sqlite3.Row) -> Outcome:
        """Convert database row to Outcome entity.

        Args:
            row: SQLite row

        Returns:
            Outcome with verified hash
        """
        final_score_dict = json.loads(row["final_score"])
        outcome = Outcome(
            outcome_id=row["outcome_id"],
            game_id=row["game_id"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            final_score=FinalScore.from_dict(final_score_dict),
            winner=row["winner"],
            stats_summary=json.loads(row["stats_summary"]),
            source=row["source"],
            hash=row["hash"],
        )
        return self._verify_hash_on_read(outcome)
