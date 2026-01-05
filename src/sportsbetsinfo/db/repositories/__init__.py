"""Append-only repositories for immutable entities."""

from sportsbetsinfo.db.repositories.base import ImmutableRepository
from sportsbetsinfo.db.repositories.snapshot import SnapshotRepository
from sportsbetsinfo.db.repositories.analysis import AnalysisRepository
from sportsbetsinfo.db.repositories.outcome import OutcomeRepository
from sportsbetsinfo.db.repositories.evaluation import EvaluationRepository
from sportsbetsinfo.db.repositories.proposal import ProposalRepository

__all__ = [
    "ImmutableRepository",
    "SnapshotRepository",
    "AnalysisRepository",
    "OutcomeRepository",
    "EvaluationRepository",
    "ProposalRepository",
]
