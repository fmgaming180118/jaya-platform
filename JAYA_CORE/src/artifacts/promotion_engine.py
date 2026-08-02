"""
promotion_engine.py — Canary Staging & Automated Rollback Drill Engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .candidate_gate import CandidateArtifact, CandidateStatus, CognitiveArtifactGate

logger = logging.getLogger(__name__)


class PromotionStatus(str, Enum):
    IDLE = "IDLE"
    CANARY_STAGED = "CANARY_STAGED"
    OBSERVING = "OBSERVING"
    PROMOTED = "PROMOTED"
    ROLLED_BACK = "ROLLED_BACK"
    REJECTED = "REJECTED"


@dataclass
class PromotionRecord:
    artifact_id: str
    status: PromotionStatus
    canary_node_ids: List[str] = field(default_factory=list)
    error_rate: float = 0.0
    human_approved: bool = False
    rollback_performed: bool = False
    history: List[str] = field(default_factory=list)


class CognitivePromotionEngine:
    """Manages canary deployments, regression monitoring, and automated rollbacks."""

    def __init__(self, gate: Optional[CognitiveArtifactGate] = None) -> None:
        self.gate = gate or CognitiveArtifactGate()
        self._records: Dict[str, PromotionRecord] = {}

    def stage_canary(
        self, candidate: CandidateArtifact, canary_nodes: List[str]
    ) -> PromotionRecord:
        val_res = self.gate.evaluate_candidate(candidate)
        if not val_res.is_valid:
            rec = PromotionRecord(
                artifact_id=candidate.artifact_id,
                status=PromotionStatus.REJECTED,
                history=[f"Candidate rejected by gate: {val_res.rejection_reasons}"],
            )
            self._records[candidate.artifact_id] = rec
            return rec

        rec = PromotionRecord(
            artifact_id=candidate.artifact_id,
            status=PromotionStatus.CANARY_STAGED,
            canary_node_ids=canary_nodes,
            history=[f"Staged on canary nodes: {canary_nodes}"],
        )
        self._records[candidate.artifact_id] = rec
        return rec

    def report_canary_metrics(
        self, artifact_id: str, error_rate: float, max_allowed_error_rate: float = 0.05
    ) -> PromotionRecord:
        if artifact_id not in self._records:
            raise KeyError(f"Artifact {artifact_id} not found in promotion engine")

        rec = self._records[artifact_id]
        rec.error_rate = error_rate
        rec.status = PromotionStatus.OBSERVING
        rec.history.append(f"Observed error rate: {error_rate:.4f}")

        # Check for regression -> trigger automated rollback
        if error_rate > max_allowed_error_rate:
            rec.status = PromotionStatus.ROLLED_BACK
            rec.rollback_performed = True
            rec.history.append(
                f"AUTOMATED ROLLBACK TRIGGERED: error_rate {error_rate:.4f} > limit {max_allowed_error_rate:.4f}"
            )
            logger.warning("Automated rollback triggered for %s", artifact_id)

        return rec

    def promote(self, artifact_id: str, human_approved: bool) -> PromotionRecord:
        if artifact_id not in self._records:
            raise KeyError(f"Artifact {artifact_id} not found in promotion engine")

        rec = self._records[artifact_id]
        if rec.status == PromotionStatus.ROLLED_BACK:
            raise ValueError(f"Cannot promote rolled-back artifact {artifact_id}")

        if not human_approved:
            rec.status = PromotionStatus.REJECTED
            rec.history.append("Promotion denied: Human approval missing.")
            return rec

        rec.human_approved = True
        rec.status = PromotionStatus.PROMOTED
        rec.history.append("Promoted to active Core via human approval.")
        return rec
