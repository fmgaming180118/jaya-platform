"""
scientific_worker.py — Scientific Gate Interlock for Worker Hardening.

Interlocks background worker execution with scientific validation gates.
If a research job lacks empirical evidence or fails the reproduction gate,
the job status is set to SUSPENDED_UNSCIENTIFIC.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .citation_audit import SynthesisAuditReport
from .empirical_gold_pipeline import EmpiricalReproductionResult

logger = logging.getLogger(__name__)


class JobScientificStatus(str, Enum):
    VALIDATED = "VALIDATED"
    SUSPENDED_UNSCIENTIFIC = "SUSPENDED_UNSCIENTIFIC"
    AWAITING_EVIDENCE = "AWAITING_EVIDENCE"


@dataclass
class JobGateEvaluation:
    job_id: str
    is_allowed: bool
    scientific_status: JobScientificStatus
    rejection_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["scientific_status"] = self.scientific_status.value
        return res


class ScientificGateWorkerHardening:
    """Worker hardening gate enforcing scientific evidence checks before background job completion."""

    def evaluate_job_scientific_readiness(
        self,
        job_id: str,
        audit_report: Optional[SynthesisAuditReport] = None,
        reproduction_result: Optional[EmpiricalReproductionResult] = None,
        require_reproduction: bool = True,
    ) -> JobGateEvaluation:
        reasons = []

        # 1. Citation audit check
        if not audit_report:
            reasons.append("Missing CitationSynthesisAuditReport")
        elif audit_report.status == "ABSTAIN" or audit_report.abstention_triggered:
            reasons.append(f"Citation audit failed or abstained (status={audit_report.status})")

        # 2. Reproduction check
        if require_reproduction:
            if not reproduction_result:
                reasons.append("Missing EmpiricalReproductionResult")
            elif reproduction_result.reproduction_status != "INDEPENDENT_REPRODUCTION_PASSED":
                reasons.append(f"Independent reproduction gate failed (status={reproduction_result.reproduction_status})")

        if reasons:
            logger.warning("Scientific gate rejected job %s: %s", job_id, reasons)
            return JobGateEvaluation(
                job_id=job_id,
                is_allowed=False,
                scientific_status=JobScientificStatus.SUSPENDED_UNSCIENTIFIC,
                rejection_reasons=reasons,
            )

        return JobGateEvaluation(
            job_id=job_id,
            is_allowed=True,
            scientific_status=JobScientificStatus.VALIDATED,
            rejection_reasons=[],
        )
