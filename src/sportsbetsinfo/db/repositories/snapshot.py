"""Repository for InfoSnapshot entities."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from sportsbetsinfo.core.exceptions import DuplicateEntityError
from sportsbetsinfo.core.models import InfoSnapshot, SourceVersions
from sportsbetsinfo.db.repositories.base import ImmutableRepository


class SnapshotRepository(ImmutableRepository[InfoSnapshot]):
    """Repository for InfoSnapshot entities.

    Provides append-only storage for market data snapshots.
    """

    def insert(self, snapshot: InfoSnapshot) -> InfoSnapshot:
        """Insert a new snapshot.

        If a snapshot with the same hash already exists, returns the existing one
        (idempotent insert for content-addressed data).

        Args:
            snapshot: InfoSnapshot to insert

        Returns:
            The inserted snapshot (or existing one if duplicate hash)

        Raises:
            DuplicateEntityError: If snapshot_id already exists with different hash
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO info_snapshots (
                    snapshot_id, game_id, collected_at, schema_version,
                    source_versions, raw_payloads, normalized_fields, hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.game_id,
                    snapshot.collected_at.isoformat(),
                    snapshot.schema_version,
                    json.dumps(snapshot.source_versions.to_dict()),
                    json.dumps(snapshot.raw_payloads),
                    json.dumps(snapshot.normalized_fields),
                    snapshot.hash,
                ),
            )
            self._conn.commit()
            return snapshot
        except sqlite3.IntegrityError as e:
            self._conn.rollback()
            if "UNIQUE constraint failed" in str(e) and "hash" in str(e):
                # Idempotent: same content already exists
                existing = self.get_by_hash(snapshot.hash)
                if existing:
                    return existing
            raise DuplicateEntityError("InfoSnapshot", snapshot.hash) from e

    def get_by_id(self, snapshot_id: str) -> InfoSnapshot | None:
        """Get snapshot by ID.

        Args:
            snapshot_id: Snapshot UUID

        Returns:
            InfoSnapshot if found, None otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM info_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        row = cursor.fetchone()
        return self._row_to_entity(row) if row else None

    def get_by_hash(self, hash_value: str) -> InfoSnapshot | None:
        """Get snapshot by content hash.

        Args:
            hash_value: SHA-256 hash

        Returns:
            InfoSnapshot if found, None otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM info_snapshots WHERE hash = ?",
            (hash_value,),
        )
        row = cursor.fetchone()
        return self._row_to_entity(row) if row else None

    def get_by_game_id(
        self, game_id: str, limit: int = 100
    ) -> list[InfoSnapshot]:
        """Get all snapshots for a game, ordered by collection time.

        Args:
            game_id: Game identifier
            limit: Maximum number to return

        Returns:
            List of snapshots ordered by collected_at
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM info_snapshots
            WHERE game_id = ?
            ORDER BY collected_at ASC
            LIMIT ?
            """,
            (game_id, limit),
        )
        return [self._row_to_entity(row) for row in cursor.fetchall()]

    def get_latest_by_game_id(self, game_id: str) -> InfoSnapshot | None:
        """Get the most recent snapshot for a game.

        Args:
            game_id: Game identifier

        Returns:
            Most recent InfoSnapshot if any exist, None otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM info_snapshots
            WHERE game_id = ?
            ORDER BY collected_at DESC
            LIMIT 1
            """,
            (game_id,),
        )
        row = cursor.fetchone()
        return self._row_to_entity(row) if row else None

    def get_all(self, limit: int = 100, offset: int = 0) -> list[InfoSnapshot]:
        """Get snapshots with pagination.

        Args:
            limit: Maximum number of snapshots
            offset: Number to skip

        Returns:
            List of snapshots ordered by collected_at DESC
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM info_snapshots
            ORDER BY collected_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [self._row_to_entity(row) for row in cursor.fetchall()]

    def _row_to_entity(self, row: sqlite3.Row) -> InfoSnapshot:
        """Convert database row to InfoSnapshot entity.

        Also verifies hash integrity.

        Args:
            row: SQLite row

        Returns:
            InfoSnapshot with verified hash
        """
        source_versions_dict = json.loads(row["source_versions"])
        snapshot = InfoSnapshot(
            snapshot_id=row["snapshot_id"],
            game_id=row["game_id"],
            collected_at=datetime.fromisoformat(row["collected_at"]),
            schema_version=row["schema_version"],
            source_versions=SourceVersions.from_dict(source_versions_dict),
            raw_payloads=json.loads(row["raw_payloads"]),
            normalized_fields=json.loads(row["normalized_fields"]),
            hash=row["hash"],
        )
        return self._verify_hash_on_read(snapshot)
