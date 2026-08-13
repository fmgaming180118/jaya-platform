"""Review-only bridge from Research findings to immutable artifact outbox."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from research.research_artifact import (
        EvidenceKind,
        ResearchArtifact,
        ResearchArtifactOutbox,
        build_research_artifact,
    )
except ImportError:
    from .research_artifact import (
        EvidenceKind,
        ResearchArtifact,
        ResearchArtifactOutbox,
        build_research_artifact,
    )


@dataclass(frozen=True)
class ResearchFinding:
    """A proposed finding with explicit evidence and provenance metadata."""

    finding_id: str
    paper_title: str
    authors: list[str]
    topic: str
    gap_summary: str
    suggested_patch_type: str
    patch_code: str
    confidence_score: float = 0.0
    evidence_kind: str = EvidenceKind.UNVERIFIED.value
    source_hashes: list[str] = field(default_factory=list)
    dataset_sha256: str = ""
    license_id: str = ""
    reproduction_runs: int = 0
    reproduced: bool = False
    created_at: float = field(default_factory=time.time)


class ResearchEcosystemBridge:
    """Exports candidates for review and never imports or mutates JAYA Core."""

    def __init__(self, outbox_dir: Path | str | None = None, **_: Any):
        project_root = Path(__file__).resolve().parents[2]
        resolved_outbox = outbox_dir or project_root / "data" / "artifact_outbox"
        self.outbox = ResearchArtifactOutbox(resolved_outbox)
        self._submitted_findings: list[ResearchFinding] = []

    def convert_finding_to_candidate(
        self, finding: ResearchFinding
    ) -> ResearchArtifact:
        """Convert a finding into an immutable Research-owned artifact."""
        payload_sha256 = hashlib.sha256(finding.patch_code.encode("utf-8")).hexdigest()
        return build_research_artifact(
            artifact_id=f"candidate-{finding.finding_id}",
            artifact_type="research_capability_proposal",
            finding_id=finding.finding_id,
            evidence_kind=finding.evidence_kind,
            subject=finding.topic,
            payload={
                "paper_title": finding.paper_title,
                "authors": list(finding.authors),
                "gap_summary": finding.gap_summary,
                "proposal_type": finding.suggested_patch_type,
                "proposal_text": finding.patch_code,
                "proposal_sha256": payload_sha256,
                "executable": False,
            },
            provenance={
                "source_hashes": list(finding.source_hashes),
                "dataset_sha256": finding.dataset_sha256,
            },
            reproducibility={
                "run_count": int(finding.reproduction_runs),
                "reproduced": bool(finding.reproduced),
            },
            license_info={"id": finding.license_id},
            confidence=finding.confidence_score,
        )

    def submit_research_upgrade(self, finding: ResearchFinding) -> dict[str, Any]:
        """Publish a review candidate without signing, evaluating, or deploying it."""
        self._submitted_findings.append(finding)
        artifact = self.convert_finding_to_candidate(finding)
        artifact_path = self.outbox.publish(artifact)
        return {
            "finding_id": finding.finding_id,
            "candidate_id": artifact.artifact_id,
            "artifact_status": artifact.status.value,
            "evidence_kind": artifact.evidence_kind.value,
            "artifact_path": str(artifact_path),
            "gate_passed": False,
            "human_review_required": True,
            "auto_deployed_by_research": False,
            "target_path": None,
            "timestamp": time.time(),
        }

    def deploy_patch_to_core(self, finding: ResearchFinding) -> tuple[bool, str]:
        """Remain as an explicit fail-closed compatibility method."""
        del finding
        return False, "Direct Research-to-Core deployment is disabled"

    def get_submission_history(self) -> list[ResearchFinding]:
        """Return an immutable snapshot of findings submitted during this process."""
        return list(self._submitted_findings)
