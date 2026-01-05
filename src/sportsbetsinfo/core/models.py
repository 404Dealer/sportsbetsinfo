"""Immutable domain models for the sportsbetsinfo platform.

All models use frozen dataclasses to enforce immutability at the Python level.
Factory methods handle ID generation and hash computation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ProposalStatus(Enum):
    """Status of an improvement proposal."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"


@dataclass(frozen=True)
class SourceVersions:
    """Versions of external data sources used in a snapshot."""

    kalshi: str = ""
    odds_api: str = ""

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for serialization."""
        return {"kalshi": self.kalshi, "odds_api": self.odds_api}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> SourceVersions:
        """Create from dictionary."""
        return cls(
            kalshi=data.get("kalshi", ""),
            odds_api=data.get("odds_api", ""),
        )


@dataclass(frozen=True)
class FinalScore:
    """Structured final score for a game."""

    home: int
    away: int

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary for serialization."""
        return {"home": self.home, "away": self.away}

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> FinalScore:
        """Create from dictionary."""
        return cls(home=data["home"], away=data["away"])


@dataclass(frozen=True)
class EvaluationMetrics:
    """Scoring metrics for evaluating an analysis against an outcome."""

    brier_score: float | None = None
    log_loss: float | None = None
    roi: float | None = None
    edge_realized: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        """Convert to dictionary for serialization."""
        return {
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "roi": self.roi,
            "edge_realized": self.edge_realized,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float | None]) -> EvaluationMetrics:
        """Create from dictionary."""
        return cls(
            brier_score=data.get("brier_score"),
            log_loss=data.get("log_loss"),
            roi=data.get("roi"),
            edge_realized=data.get("edge_realized"),
        )


@dataclass(frozen=True)
class InfoSnapshot:
    """Immutable snapshot of market data at a point in time.

    This represents "what we knew at time T" - the raw ingredients
    captured exactly as they were, forever preserved.

    Attributes:
        snapshot_id: Unique identifier (UUID v4)
        game_id: Identifier for the game/event this snapshot relates to
        collected_at: When this data was collected
        schema_version: Version of the data schema
        source_versions: Versions of each data source API
        raw_payloads: Original API responses (preserved exactly)
        normalized_fields: Standardized/computed fields
        hash: SHA-256 content hash for integrity verification
    """

    snapshot_id: str
    game_id: str
    collected_at: datetime
    schema_version: str
    source_versions: SourceVersions
    raw_payloads: dict[str, Any]
    normalized_fields: dict[str, Any]
    hash: str = field(default="")

    @classmethod
    def create(
        cls,
        game_id: str,
        collected_at: datetime,
        schema_version: str,
        source_versions: SourceVersions,
        raw_payloads: dict[str, Any],
        normalized_fields: dict[str, Any],
    ) -> InfoSnapshot:
        """Factory method that generates ID and computes hash.

        Args:
            game_id: Identifier for the game/event
            collected_at: When data was collected
            schema_version: Data schema version
            source_versions: API versions used
            raw_payloads: Raw API responses
            normalized_fields: Computed/standardized data

        Returns:
            New InfoSnapshot with generated ID and computed hash
        """
        from sportsbetsinfo.core.hashing import compute_snapshot_hash

        snapshot_id = str(uuid.uuid4())
        instance = cls(
            snapshot_id=snapshot_id,
            game_id=game_id,
            collected_at=collected_at,
            schema_version=schema_version,
            source_versions=source_versions,
            raw_payloads=raw_payloads,
            normalized_fields=normalized_fields,
        )
        hash_value = compute_snapshot_hash(instance)
        # Use object.__setattr__ since dataclass is frozen
        object.__setattr__(instance, "hash", hash_value)
        return instance


@dataclass(frozen=True)
class Analysis:
    """Derived analysis artifact forming a DAG (like git commits).

    An analysis is a saved object that references input snapshots and
    optionally a parent analysis. This creates a directed acyclic graph
    where you can trace the lineage of any conclusion back to its inputs.

    Attributes:
        analysis_id: Unique identifier (UUID v4)
        created_at: When this analysis was created
        analysis_version: Version of the analysis logic
        code_version: Git commit hash of the codebase
        model_version: ML model version (if applicable)
        parent_analysis_id: Link to parent analysis (DAG structure)
        input_snapshot_ids: Snapshots used as inputs
        derived_features: Computed features (no-vig prob, deltas, etc.)
        conclusions: Analysis conclusions
        recommended_actions: Suggested actions based on analysis
        hash: SHA-256 content hash
    """

    analysis_id: str
    created_at: datetime
    analysis_version: str
    code_version: str
    model_version: str | None
    parent_analysis_id: str | None
    input_snapshot_ids: tuple[str, ...]
    derived_features: dict[str, Any]
    conclusions: dict[str, Any]
    recommended_actions: list[dict[str, Any]]
    hash: str = field(default="")

    @classmethod
    def create(
        cls,
        analysis_version: str,
        code_version: str,
        input_snapshot_ids: list[str],
        derived_features: dict[str, Any],
        conclusions: dict[str, Any],
        recommended_actions: list[dict[str, Any]],
        model_version: str | None = None,
        parent_analysis_id: str | None = None,
    ) -> Analysis:
        """Factory method that generates ID and computes hash.

        Args:
            analysis_version: Version of analysis logic
            code_version: Git commit hash
            input_snapshot_ids: IDs of input snapshots
            derived_features: Computed features
            conclusions: Analysis conclusions
            recommended_actions: Suggested actions
            model_version: Optional ML model version
            parent_analysis_id: Optional parent for DAG

        Returns:
            New Analysis with generated ID and computed hash
        """
        from sportsbetsinfo.core.hashing import compute_analysis_hash

        analysis_id = str(uuid.uuid4())
        instance = cls(
            analysis_id=analysis_id,
            created_at=datetime.now(timezone.utc),
            analysis_version=analysis_version,
            code_version=code_version,
            model_version=model_version,
            parent_analysis_id=parent_analysis_id,
            input_snapshot_ids=tuple(input_snapshot_ids),
            derived_features=derived_features,
            conclusions=conclusions,
            recommended_actions=recommended_actions,
        )
        hash_value = compute_analysis_hash(instance)
        object.__setattr__(instance, "hash", hash_value)
        return instance


@dataclass(frozen=True)
class Outcome:
    """Ground truth result for a game.

    This is the actual outcome that we attach after the game ends.
    Used to evaluate whether our analyses were accurate.

    Attributes:
        outcome_id: Unique identifier (UUID v4)
        game_id: Identifier for the game (matches InfoSnapshot.game_id)
        occurred_at: When the game ended
        final_score: The final score
        winner: Team identifier or None for draw
        stats_summary: Detailed game statistics
        source: Where the outcome data came from
        hash: SHA-256 content hash
    """

    outcome_id: str
    game_id: str
    occurred_at: datetime
    final_score: FinalScore
    winner: str | None
    stats_summary: dict[str, Any]
    source: str
    hash: str = field(default="")

    @classmethod
    def create(
        cls,
        game_id: str,
        occurred_at: datetime,
        final_score: FinalScore,
        winner: str | None,
        stats_summary: dict[str, Any],
        source: str,
    ) -> Outcome:
        """Factory method that generates ID and computes hash."""
        from sportsbetsinfo.core.hashing import compute_outcome_hash

        outcome_id = str(uuid.uuid4())
        instance = cls(
            outcome_id=outcome_id,
            game_id=game_id,
            occurred_at=occurred_at,
            final_score=final_score,
            winner=winner,
            stats_summary=stats_summary,
            source=source,
        )
        hash_value = compute_outcome_hash(instance)
        object.__setattr__(instance, "hash", hash_value)
        return instance


@dataclass(frozen=True)
class Evaluation:
    """Scoring of an analysis against an outcome.

    This allows you to measure how accurate your analyses were
    compared to what actually happened.

    Attributes:
        evaluation_id: Unique identifier (UUID v4)
        analysis_id: The analysis being evaluated
        game_id: The game (links to outcome)
        scored_at: When evaluation was performed
        metrics: Scoring metrics (Brier, log loss, ROI, etc.)
        notes: Additional notes/observations
        hash: SHA-256 content hash
    """

    evaluation_id: str
    analysis_id: str
    game_id: str
    scored_at: datetime
    metrics: EvaluationMetrics
    notes: dict[str, Any] | None
    hash: str = field(default="")

    @classmethod
    def create(
        cls,
        analysis_id: str,
        game_id: str,
        metrics: EvaluationMetrics,
        notes: dict[str, Any] | None = None,
    ) -> Evaluation:
        """Factory method that generates ID and computes hash."""
        from sportsbetsinfo.core.hashing import compute_evaluation_hash

        evaluation_id = str(uuid.uuid4())
        instance = cls(
            evaluation_id=evaluation_id,
            analysis_id=analysis_id,
            game_id=game_id,
            scored_at=datetime.now(timezone.utc),
            metrics=metrics,
            notes=notes,
        )
        hash_value = compute_evaluation_hash(instance)
        object.__setattr__(instance, "hash", hash_value)
        return instance


@dataclass(frozen=True)
class ImprovementProposal:
    """LLM-suggested improvement based on evaluation evidence.

    Rather than asking "how do I improve?" in a vacuum, proposals
    are grounded in specific evaluation data showing what worked
    and what didn't.

    Attributes:
        proposal_id: Unique identifier (UUID v4)
        created_at: When proposal was generated
        based_on_evaluation_ids: Evidence the proposal is based on
        proposal_text: Human-readable proposal description
        suggested_schema_additions: Schema changes to consider
        suggested_modules: New modules/code to add
        expected_impact: Hypothesis about impact
        status: Current status (pending, accepted, rejected, implemented)
        hash: SHA-256 content hash
    """

    proposal_id: str
    created_at: datetime
    based_on_evaluation_ids: tuple[str, ...]
    proposal_text: str
    suggested_schema_additions: dict[str, Any] | None
    suggested_modules: list[str] | None
    expected_impact: dict[str, Any] | None
    status: ProposalStatus
    hash: str = field(default="")

    @classmethod
    def create(
        cls,
        based_on_evaluation_ids: list[str],
        proposal_text: str,
        suggested_schema_additions: dict[str, Any] | None = None,
        suggested_modules: list[str] | None = None,
        expected_impact: dict[str, Any] | None = None,
    ) -> ImprovementProposal:
        """Factory method that generates ID and computes hash."""
        from sportsbetsinfo.core.hashing import compute_proposal_hash

        proposal_id = str(uuid.uuid4())
        instance = cls(
            proposal_id=proposal_id,
            created_at=datetime.now(timezone.utc),
            based_on_evaluation_ids=tuple(based_on_evaluation_ids),
            proposal_text=proposal_text,
            suggested_schema_additions=suggested_schema_additions,
            suggested_modules=suggested_modules,
            expected_impact=expected_impact,
            status=ProposalStatus.PENDING,
        )
        hash_value = compute_proposal_hash(instance)
        object.__setattr__(instance, "hash", hash_value)
        return instance
