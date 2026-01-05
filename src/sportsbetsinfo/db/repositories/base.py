"""Base repository with append-only operations.

All repositories enforce immutability: only insert and read operations
are exposed. There are no update or delete methods.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from sportsbetsinfo.core.exceptions import HashMismatchError
from sportsbetsinfo.core.hashing import verify_hash

T = TypeVar("T")


class ImmutableRepository(ABC, Generic[T]):
    """Abstract base repository enforcing append-only operations.

    Subclasses must implement insert, get_by_id, and get_all.
    No update or delete methods are provided.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Initialize repository with database connection.

        Args:
            connection: SQLite connection
        """
        self._conn = connection
        self._conn.row_factory = sqlite3.Row

    @abstractmethod
    def insert(self, entity: T) -> T:
        """Insert a new entity.

        This is the only mutation operation allowed.

        Args:
            entity: Entity to insert

        Returns:
            The inserted entity
        """
        pass

    @abstractmethod
    def get_by_id(self, entity_id: str) -> T | None:
        """Retrieve entity by primary key.

        Args:
            entity_id: Primary key value

        Returns:
            Entity if found, None otherwise
        """
        pass

    @abstractmethod
    def get_all(self, limit: int = 100, offset: int = 0) -> list[T]:
        """Retrieve entities with pagination.

        Args:
            limit: Maximum number of entities to return
            offset: Number of entities to skip

        Returns:
            List of entities
        """
        pass

    def _verify_hash_on_read(self, entity: T) -> T:
        """Verify hash integrity when reading from database.

        Args:
            entity: Entity to verify

        Returns:
            The entity if hash is valid

        Raises:
            HashMismatchError: If computed hash doesn't match stored hash
        """
        if not verify_hash(entity):
            entity_type = type(entity).__name__
            entity_id = getattr(entity, f"{entity_type.lower()}_id", "unknown")
            expected = getattr(entity, "hash", "")
            from sportsbetsinfo.core import hashing

            # Re-compute hash to get actual value
            hash_funcs = {
                "InfoSnapshot": hashing.compute_snapshot_hash,
                "Analysis": hashing.compute_analysis_hash,
                "Outcome": hashing.compute_outcome_hash,
                "Evaluation": hashing.compute_evaluation_hash,
                "ImprovementProposal": hashing.compute_proposal_hash,
            }
            actual = hash_funcs.get(entity_type, lambda x: "")(entity)
            raise HashMismatchError(entity_type, str(entity_id), expected, actual)
        return entity
