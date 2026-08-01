"""
candidate_gate.py — Fail-closed Cognitive Artifact Candidate Readiness Gate.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CandidateStatus(str, Enum):
    RECEIVED = "RECEIVED"
    INVALID = "INVALID"
    VALIDATED = "VALIDATED"
    STAGED = "STAGED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    REJECTED = "REJECTED"


@dataclass
class CandidateArtifact:
    artifact_id: str
    artifact_type: str
    target_system: str
    provenance: Dict[str, Any]
    payload: Dict[str, Any]
    evidence_kind: str = "UNVERIFIED"
    executable: bool = False
    auto_install: bool = False
    human_review_required: bool = True
    rollback_info: Optional[Dict[str, Any]] = None
    status: CandidateStatus = CandidateStatus.RECEIVED

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["status"] = self.status.value
        return res


@dataclass
class ArtifactValidationResult:
    artifact_id: str
    is_valid: bool
    status: CandidateStatus
    rejection_reasons: List[str] = field(default_factory=list)


class CognitiveArtifactGate:
    """Fail-closed gate for incoming research candidates into JAYA Core."""

    def evaluate_candidate(self, candidate: CandidateArtifact) -> ArtifactValidationResult:
        reasons = []

        # 1. Missing provenance check
        if not candidate.provenance or not isinstance(candidate.provenance, dict):
            reasons.append("Missing or invalid provenance metadata")

        # 2. Executable before approval check
        if candidate.executable:
            reasons.append("Candidate artifact executable flag must be False before approval")

        if candidate.auto_install:
            reasons.append("Auto install is strictly forbidden for cognitive artifacts")

        # 3. Target system check
        if candidate.target_system not in ("JAYA_CORE", "JAYA_RESEARCH"):
            reasons.append(f"Invalid target_system '{candidate.target_system}'")

        # 4. Simulation check for cognitive updates
        if candidate.evidence_kind.upper() == "SIMULATION" and candidate.artifact_type in (
            "cognitive_update",
            "reasoning_strategy",
            "policy_candidate",
        ):
            reasons.append("SIMULATION evidence is forbidden for cognitive/policy updates")

        # 5. Rollback info check
        if not candidate.rollback_info or not candidate.rollback_info.get("rollback_supported"):
            reasons.append("Candidate missing rollback information or rollback is not supported")

        if reasons:
            candidate.status = CandidateStatus.REJECTED
            logger.warning("Rejected artifact %s: %s", candidate.artifact_id, ", ".join(reasons))
            return ArtifactValidationResult(
                artifact_id=candidate.artifact_id,
                is_valid=False,
                status=CandidateStatus.REJECTED,
                rejection_reasons=reasons,
            )

        candidate.status = CandidateStatus.STAGED
        logger.info("Artifact %s validated and STAGED", candidate.artifact_id)
        return ArtifactValidationResult(
            artifact_id=candidate.artifact_id,
            is_valid=True,
            status=CandidateStatus.STAGED,
        )
