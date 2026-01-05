"""Content-addressable hashing for immutable entities.

All entities are hashed using SHA-256 with deterministic JSON serialization.
Hashes are computed from content fields only (excludes generated IDs and timestamps).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sportsbetsinfo.core.models import (
        Analysis,
        Evaluation,
        ImprovementProposal,
        InfoSnapshot,
        Outcome,
    )


def _serialize_for_hash(obj: Any) -> str:
    """Deterministically serialize object for hashing.

    Uses sorted keys and compact separators for consistent output.
    Handles datetime, dataclass-like objects with to_dict(), and enums.
    """
    def default(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if hasattr(o, "to_dict"):
            return o.to_dict()
        if hasattr(o, "value"):  # Enum
            return o.value
        if hasattr(o, "__dict__"):
            return o.__dict__
        raise TypeError(f"Cannot serialize {type(o).__name__}")

    return json.dumps(obj, sort_keys=True, default=default, separators=(",", ":"))


def _compute_hash(data: dict[str, Any]) -> str:
    """Compute SHA-256 hash of serialized data."""
    serialized = _serialize_for_hash(data)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_snapshot_hash(snapshot: InfoSnapshot) -> str:
    """Compute hash for InfoSnapshot.

    Includes: game_id, collected_at, schema_version, source_versions,
              raw_payloads, normalized_fields
    Excludes: snapshot_id, hash (generated/computed fields)
    """
    data = {
        "game_id": snapshot.game_id,
        "collected_at": snapshot.collected_at,
        "schema_version": snapshot.schema_version,
        "source_versions": snapshot.source_versions.to_dict(),
        "raw_payloads": snapshot.raw_payloads,
        "normalized_fields": snapshot.normalized_fields,
    }
    return _compute_hash(data)


def compute_analysis_hash(analysis: Analysis) -> str:
    """Compute hash for Analysis.

    Includes: analysis_version, code_version, model_version, parent_analysis_id,
              input_snapshot_ids, derived_features, conclusions, recommended_actions
    Excludes: analysis_id, created_at, hash
    """
    data = {
        "analysis_version": analysis.analysis_version,
        "code_version": analysis.code_version,
        "model_version": analysis.model_version,
        "parent_analysis_id": analysis.parent_analysis_id,
        "input_snapshot_ids": list(analysis.input_snapshot_ids),
        "derived_features": analysis.derived_features,
        "conclusions": analysis.conclusions,
        "recommended_actions": analysis.recommended_actions,
    }
    return _compute_hash(data)


def compute_outcome_hash(outcome: Outcome) -> str:
    """Compute hash for Outcome.

    Includes: game_id, occurred_at, final_score, winner, stats_summary, source
    Excludes: outcome_id, hash
    """
    data = {
        "game_id": outcome.game_id,
        "occurred_at": outcome.occurred_at,
        "final_score": outcome.final_score.to_dict(),
        "winner": outcome.winner,
        "stats_summary": outcome.stats_summary,
        "source": outcome.source,
    }
    return _compute_hash(data)


def compute_evaluation_hash(evaluation: Evaluation) -> str:
    """Compute hash for Evaluation.

    Includes: analysis_id, game_id, metrics, notes
    Excludes: evaluation_id, scored_at, hash
    """
    data = {
        "analysis_id": evaluation.analysis_id,
        "game_id": evaluation.game_id,
        "brier_score": evaluation.metrics.brier_score,
        "log_loss": evaluation.metrics.log_loss,
        "roi": evaluation.metrics.roi,
        "edge_realized": evaluation.metrics.edge_realized,
        "notes": evaluation.notes,
    }
    return _compute_hash(data)


def compute_proposal_hash(proposal: ImprovementProposal) -> str:
    """Compute hash for ImprovementProposal.

    Includes: based_on_evaluation_ids, proposal_text, suggested_schema_additions,
              suggested_modules, expected_impact
    Excludes: proposal_id, created_at, status, hash
    """
    data = {
        "based_on_evaluation_ids": list(proposal.based_on_evaluation_ids),
        "proposal_text": proposal.proposal_text,
        "suggested_schema_additions": proposal.suggested_schema_additions,
        "suggested_modules": proposal.suggested_modules,
        "expected_impact": proposal.expected_impact,
    }
    return _compute_hash(data)


def verify_hash(entity: Any) -> bool:
    """Verify entity hash matches computed value.

    Args:
        entity: An entity with a 'hash' attribute

    Returns:
        True if hash matches, False otherwise
    """
    from sportsbetsinfo.core.models import (
        Analysis,
        Evaluation,
        ImprovementProposal,
        InfoSnapshot,
        Outcome,
    )

    hash_funcs: dict[type, Any] = {
        InfoSnapshot: compute_snapshot_hash,
        Analysis: compute_analysis_hash,
        Outcome: compute_outcome_hash,
        Evaluation: compute_evaluation_hash,
        ImprovementProposal: compute_proposal_hash,
    }

    hash_func = hash_funcs.get(type(entity))
    if hash_func is None:
        raise TypeError(f"Unknown entity type: {type(entity).__name__}")

    computed = hash_func(entity)
    return computed == entity.hash
