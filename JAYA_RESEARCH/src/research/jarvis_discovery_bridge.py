"""Discovery artifact exporter; direct Core database mutation is forbidden."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from research.experiment_runner import (
        ExperimentInputError,
        validate_experiment_result_receipt,
    )
    from research.research_artifact import (
        EvidenceKind,
        ResearchArtifactOutbox,
        build_research_artifact,
    )
except ImportError:
    from .experiment_runner import (
        ExperimentInputError,
        validate_experiment_result_receipt,
    )
    from .research_artifact import (
        EvidenceKind,
        ResearchArtifactOutbox,
        build_research_artifact,
    )


logger = logging.getLogger(__name__)


class JarvisDiscoveryBridge:
    """Packages discovery results for review without activating them."""

    def __init__(
        self,
        outbox_dir: Path | str | None = None,
        core_db_path: Path | None = None,
    ):
        if core_db_path is not None:
            logger.warning(
                "core_db_path is ignored: direct Core database access is disabled"
            )
        project_root = Path(__file__).resolve().parents[2]
        self.outbox = ResearchArtifactOutbox(
            outbox_dir or project_root / "data" / "artifact_outbox"
        )

    def create_jarvis_patch(
        self,
        hypothesis: dict[str, Any],
        learning_analysis: dict[str, Any],
        paper: dict[str, Any] | None = None,
        run_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a non-executable candidate payload with honest evidence labels."""
        run = dict(run_result or {})
        evidence_kind = str(
            run.get("evidence_kind")
            or learning_analysis.get("evidence_kind")
            or EvidenceKind.UNVERIFIED.value
        ).upper()
        hypothesis_id = str(hypothesis.get("hypothesis_id") or "HYP-UNKNOWN")
        digest_seed = json.dumps(
            {
                "hypothesis_id": hypothesis_id,
                "run_id": run.get("run_id"),
                "statement": hypothesis.get("statement", ""),
            },
            sort_keys=True,
        )
        suffix = hashlib.sha256(digest_seed.encode("utf-8")).hexdigest()[:12]
        return {
            "patch_id": f"JAYPATCH-{suffix}",
            "artifact_type": "knowledge_candidate",
            "target_system": "JAYA_CORE",
            "topic": str(hypothesis.get("topic") or "Unknown"),
            "statement": str(hypothesis.get("statement") or ""),
            "confidence": float(learning_analysis.get("posterior_confidence") or 0.0),
            "evidence_kind": evidence_kind,
            "status": "CANDIDATE",
            "executable": False,
            "hypothesis_id": hypothesis_id,
            "run_id": run.get("run_id"),
            "dataset_sha256": run.get("dataset_sha256", ""),
            "source_hashes": list(run.get("source_hashes") or []),
            "reproduction": dict(run.get("reproduction") or {}),
            "license": dict(run.get("license") or {}),
            "proposed_directives": [
                {
                    "trigger": f"User mentions {hypothesis.get('topic', 'topic')}",
                    "recommendation": str(hypothesis.get("statement") or ""),
                    "active": False,
                }
            ],
            "paper_digest": hashlib.sha256(
                json.dumps(paper or {}, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def apply_patch_to_core(self, patch: dict[str, Any]) -> bool:
        """Fail closed: Research is not authorized to mutate Core."""
        logger.error(
            "Blocked direct Core mutation for candidate %s",
            patch.get("patch_id", "unknown"),
        )
        return False

    def deploy_discovery_to_jarvis(
        self,
        hypothesis: dict[str, Any],
        run_result: dict[str, Any],
        learning_analysis: dict[str, Any],
        paper: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Export eligible evidence to outbox or reject it before review."""
        patch = self.create_jarvis_patch(
            hypothesis,
            learning_analysis,
            paper=paper,
            run_result=run_result,
        )
        evidence_kind = EvidenceKind(patch["evidence_kind"])
        if evidence_kind is EvidenceKind.SIMULATION:
            return {
                "status": "REJECTED_SIMULATION",
                "patch_id": patch["patch_id"],
                "target_system": "JAYA_CORE",
                "auto_deployed": False,
                "reason": "Simulation cannot be promoted",
            }
        if evidence_kind is EvidenceKind.EMPIRICAL:
            try:
                validate_experiment_result_receipt(run_result)
            except ExperimentInputError as exc:
                return {
                    "status": "INVALID_EVIDENCE_RECEIPT",
                    "patch_id": patch["patch_id"],
                    "target_system": "JAYA_CORE",
                    "auto_deployed": False,
                    "reason": str(exc),
                }

        recommendation = str(learning_analysis.get("recommendation") or "HOLD")
        if recommendation != "ACCEPT_HYPOTHESIS":
            return {
                "status": "PROMOTION_SKIPPED",
                "patch_id": patch["patch_id"],
                "target_system": "JAYA_CORE",
                "auto_deployed": False,
                "reason": f"Recommendation is {recommendation}",
            }

        reproduction = dict(run_result.get("reproduction") or {})
        artifact = build_research_artifact(
            artifact_id=patch["patch_id"],
            artifact_type=patch["artifact_type"],
            finding_id=str(hypothesis.get("hypothesis_id") or "HYP-UNKNOWN"),
            evidence_kind=evidence_kind,
            subject=patch["topic"],
            payload=patch,
            provenance={
                "source_hashes": patch["source_hashes"],
                "dataset_sha256": patch["dataset_sha256"],
            },
            reproducibility=reproduction,
            license_info=patch["license"],
            confidence=patch["confidence"],
        )
        artifact_path = self.outbox.publish(artifact)
        return {
            "status": artifact.status.value,
            "patch_id": patch["patch_id"],
            "target_system": "JAYA_CORE",
            "artifact_path": str(artifact_path),
            "auto_deployed": False,
            "human_review_required": True,
        }
