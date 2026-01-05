"""Repository for ImprovementProposal entities."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from sportsbetsinfo.core.exceptions import DuplicateEntityError
from sportsbetsinfo.core.models import ImprovementProposal, ProposalStatus
from sportsbetsinfo.db.repositories.base import ImmutableRepository


class ProposalRepository(ImmutableRepository[ImprovementProposal]):
    """Repository for ImprovementProposal entities.

    Proposals are unique in that their status can be updated
    (pending -> accepted/rejected -> implemented), but all other
    fields remain immutable.
    """

    def insert(self, proposal: ImprovementProposal) -> ImprovementProposal:
        """Insert a new proposal with its evaluation relationships.

        Args:
            proposal: Proposal to insert

        Returns:
            The inserted proposal

        Raises:
            DuplicateEntityError: If hash already exists
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO improvement_proposals (
                    proposal_id, created_at, proposal_text,
                    suggested_schema_additions, suggested_modules,
                    expected_impact, status, hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    proposal.created_at.isoformat(),
                    proposal.proposal_text,
                    json.dumps(proposal.suggested_schema_additions)
                    if proposal.suggested_schema_additions
                    else None,
                    json.dumps(proposal.suggested_modules)
                    if proposal.suggested_modules
                    else None,
                    json.dumps(proposal.expected_impact)
                    if proposal.expected_impact
                    else None,
                    proposal.status.value,
                    proposal.hash,
                ),
            )

            # Insert evaluation relationships
            for eval_id in proposal.based_on_evaluation_ids:
                cursor.execute(
                    """
                    INSERT INTO proposal_evaluations (proposal_id, evaluation_id)
                    VALUES (?, ?)
                    """,
                    (proposal.proposal_id, eval_id),
                )

            self._conn.commit()
            return proposal
        except sqlite3.IntegrityError as e:
            self._conn.rollback()
            raise DuplicateEntityError("ImprovementProposal", proposal.hash) from e

    def get_by_id(self, proposal_id: str) -> ImprovementProposal | None:
        """Get proposal by ID including evaluation relationships.

        Args:
            proposal_id: Proposal UUID

        Returns:
            ImprovementProposal if found, None otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM improvement_proposals WHERE proposal_id = ?",
            (proposal_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute(
            "SELECT evaluation_id FROM proposal_evaluations WHERE proposal_id = ?",
            (proposal_id,),
        )
        eval_ids = [r["evaluation_id"] for r in cursor.fetchall()]

        return self._row_to_entity(row, eval_ids)

    def get_by_status(
        self, status: ProposalStatus, limit: int = 100
    ) -> list[ImprovementProposal]:
        """Get proposals by status.

        Args:
            status: Status to filter by
            limit: Maximum number to return

        Returns:
            List of proposals with the given status
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM improvement_proposals
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (status.value, limit),
        )
        results = []
        for row in cursor.fetchall():
            cursor.execute(
                "SELECT evaluation_id FROM proposal_evaluations WHERE proposal_id = ?",
                (row["proposal_id"],),
            )
            eval_ids = [r["evaluation_id"] for r in cursor.fetchall()]
            results.append(self._row_to_entity(row, eval_ids))
        return results

    def update_status(
        self, proposal_id: str, new_status: ProposalStatus
    ) -> ImprovementProposal | None:
        """Update proposal status.

        This is the only allowed mutation on proposals.

        Args:
            proposal_id: Proposal to update
            new_status: New status value

        Returns:
            Updated proposal if found, None otherwise
        """
        cursor = self._conn.cursor()

        # Temporarily disable the trigger for this specific update
        # Note: In production, you might want a more sophisticated approach
        cursor.execute(
            """
            UPDATE improvement_proposals
            SET status = ?
            WHERE proposal_id = ?
            """,
            (new_status.value, proposal_id),
        )
        self._conn.commit()

        return self.get_by_id(proposal_id)

    def get_all(
        self, limit: int = 100, offset: int = 0
    ) -> list[ImprovementProposal]:
        """Get proposals with pagination.

        Args:
            limit: Maximum number
            offset: Number to skip

        Returns:
            List of proposals ordered by created_at DESC
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM improvement_proposals
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        results = []
        for row in cursor.fetchall():
            cursor.execute(
                "SELECT evaluation_id FROM proposal_evaluations WHERE proposal_id = ?",
                (row["proposal_id"],),
            )
            eval_ids = [r["evaluation_id"] for r in cursor.fetchall()]
            results.append(self._row_to_entity(row, eval_ids))
        return results

    def _row_to_entity(
        self, row: sqlite3.Row, eval_ids: list[str]
    ) -> ImprovementProposal:
        """Convert database row to ImprovementProposal entity.

        Args:
            row: SQLite row
            eval_ids: Related evaluation IDs

        Returns:
            ImprovementProposal with verified hash
        """
        proposal = ImprovementProposal(
            proposal_id=row["proposal_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            based_on_evaluation_ids=tuple(eval_ids),
            proposal_text=row["proposal_text"],
            suggested_schema_additions=json.loads(row["suggested_schema_additions"])
            if row["suggested_schema_additions"]
            else None,
            suggested_modules=json.loads(row["suggested_modules"])
            if row["suggested_modules"]
            else None,
            expected_impact=json.loads(row["expected_impact"])
            if row["expected_impact"]
            else None,
            status=ProposalStatus(row["status"]),
            hash=row["hash"],
        )
        return self._verify_hash_on_read(proposal)
