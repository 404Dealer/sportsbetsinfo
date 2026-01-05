"""Repository for Analysis entities with DAG traversal support."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from sportsbetsinfo.core.exceptions import DuplicateEntityError
from sportsbetsinfo.core.models import Analysis
from sportsbetsinfo.db.repositories.base import ImmutableRepository


class AnalysisRepository(ImmutableRepository[Analysis]):
    """Repository for Analysis entities.

    Supports DAG operations like lineage traversal and child lookup.
    """

    def insert(self, analysis: Analysis) -> Analysis:
        """Insert a new analysis with its snapshot relationships.

        Args:
            analysis: Analysis to insert

        Returns:
            The inserted analysis

        Raises:
            DuplicateEntityError: If hash already exists
        """
        cursor = self._conn.cursor()
        try:
            # Insert main analysis record
            cursor.execute(
                """
                INSERT INTO analyses (
                    analysis_id, created_at, analysis_version, code_version,
                    model_version, parent_analysis_id, derived_features,
                    conclusions, recommended_actions, hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.analysis_id,
                    analysis.created_at.isoformat(),
                    analysis.analysis_version,
                    analysis.code_version,
                    analysis.model_version,
                    analysis.parent_analysis_id,
                    json.dumps(analysis.derived_features),
                    json.dumps(analysis.conclusions),
                    json.dumps(analysis.recommended_actions),
                    analysis.hash,
                ),
            )

            # Insert snapshot relationships
            for snapshot_id in analysis.input_snapshot_ids:
                cursor.execute(
                    """
                    INSERT INTO analysis_snapshots (analysis_id, snapshot_id)
                    VALUES (?, ?)
                    """,
                    (analysis.analysis_id, snapshot_id),
                )

            self._conn.commit()
            return analysis
        except sqlite3.IntegrityError as e:
            self._conn.rollback()
            raise DuplicateEntityError("Analysis", analysis.hash) from e

    def get_by_id(self, analysis_id: str) -> Analysis | None:
        """Get analysis by ID including snapshot relationships.

        Args:
            analysis_id: Analysis UUID

        Returns:
            Analysis if found, None otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM analyses WHERE analysis_id = ?",
            (analysis_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        # Get related snapshot IDs
        cursor.execute(
            "SELECT snapshot_id FROM analysis_snapshots WHERE analysis_id = ?",
            (analysis_id,),
        )
        snapshot_ids = [r["snapshot_id"] for r in cursor.fetchall()]

        return self._row_to_entity(row, snapshot_ids)

    def get_by_hash(self, hash_value: str) -> Analysis | None:
        """Get analysis by content hash.

        Args:
            hash_value: SHA-256 hash

        Returns:
            Analysis if found, None otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM analyses WHERE hash = ?",
            (hash_value,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute(
            "SELECT snapshot_id FROM analysis_snapshots WHERE analysis_id = ?",
            (row["analysis_id"],),
        )
        snapshot_ids = [r["snapshot_id"] for r in cursor.fetchall()]

        return self._row_to_entity(row, snapshot_ids)

    def get_children(self, analysis_id: str) -> list[Analysis]:
        """Get all analyses that have this as parent (direct children in DAG).

        Args:
            analysis_id: Parent analysis ID

        Returns:
            List of child analyses
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM analyses WHERE parent_analysis_id = ?",
            (analysis_id,),
        )
        results = []
        for row in cursor.fetchall():
            cursor.execute(
                "SELECT snapshot_id FROM analysis_snapshots WHERE analysis_id = ?",
                (row["analysis_id"],),
            )
            snapshot_ids = [r["snapshot_id"] for r in cursor.fetchall()]
            results.append(self._row_to_entity(row, snapshot_ids))
        return results

    def get_lineage(self, analysis_id: str) -> list[Analysis]:
        """Get full lineage from root to this analysis (DAG path).

        Walks the parent_analysis_id chain back to the root.

        Args:
            analysis_id: Analysis to get lineage for

        Returns:
            List of analyses from root to the given analysis
        """
        lineage: list[Analysis] = []
        current_id: str | None = analysis_id

        while current_id:
            analysis = self.get_by_id(current_id)
            if analysis is None:
                break
            lineage.append(analysis)
            current_id = analysis.parent_analysis_id

        return list(reversed(lineage))  # Root first

    def get_roots(self, limit: int = 100) -> list[Analysis]:
        """Get all root analyses (those with no parent).

        Args:
            limit: Maximum number to return

        Returns:
            List of root analyses
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM analyses
            WHERE parent_analysis_id IS NULL
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        results = []
        for row in cursor.fetchall():
            cursor.execute(
                "SELECT snapshot_id FROM analysis_snapshots WHERE analysis_id = ?",
                (row["analysis_id"],),
            )
            snapshot_ids = [r["snapshot_id"] for r in cursor.fetchall()]
            results.append(self._row_to_entity(row, snapshot_ids))
        return results

    def get_all(self, limit: int = 100, offset: int = 0) -> list[Analysis]:
        """Get analyses with pagination.

        Args:
            limit: Maximum number
            offset: Number to skip

        Returns:
            List of analyses ordered by created_at DESC
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM analyses
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        results = []
        for row in cursor.fetchall():
            cursor.execute(
                "SELECT snapshot_id FROM analysis_snapshots WHERE analysis_id = ?",
                (row["analysis_id"],),
            )
            snapshot_ids = [r["snapshot_id"] for r in cursor.fetchall()]
            results.append(self._row_to_entity(row, snapshot_ids))
        return results

    def _row_to_entity(
        self, row: sqlite3.Row, snapshot_ids: list[str]
    ) -> Analysis:
        """Convert database row to Analysis entity.

        Args:
            row: SQLite row
            snapshot_ids: Related snapshot IDs

        Returns:
            Analysis with verified hash
        """
        analysis = Analysis(
            analysis_id=row["analysis_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            analysis_version=row["analysis_version"],
            code_version=row["code_version"],
            model_version=row["model_version"],
            parent_analysis_id=row["parent_analysis_id"],
            input_snapshot_ids=tuple(snapshot_ids),
            derived_features=json.loads(row["derived_features"]),
            conclusions=json.loads(row["conclusions"]),
            recommended_actions=json.loads(row["recommended_actions"]),
            hash=row["hash"],
        )
        return self._verify_hash_on_read(analysis)
