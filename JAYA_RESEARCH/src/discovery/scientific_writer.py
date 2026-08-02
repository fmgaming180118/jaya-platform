"""
scientific_writer.py — Evidence-Gated Scientific Writer with Strict Abstention Rules.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class UnverifiedEvidenceError(Exception):
    """Raised when scientific writer attempts to produce report without verified evidence."""


@dataclass
class ScientificReport:
    report_id: str
    hypothesis_id: str
    title: str
    status: str  # "VERIFIED_DRAFT", "ABSTAINED"
    evidence_references: List[str]
    sections: Dict[str, str] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceGatedScientificWriter:
    """Scientific report generator strictly gated by verified empirical evidence stores."""

    VALID_EVIDENCE_TYPES = {"SOURCE_EVIDENCE", "EMPIRICAL_RESULT", "VERIFIED_ARTIFACT"}

    def generate_report(
        self, hypothesis_id: str, title: str, evidence_items: List[Dict[str, Any]]
    ) -> ScientificReport:
        if not evidence_items:
            logger.warning("No evidence provided for hypothesis %s; abstaining from writing", hypothesis_id)
            return ScientificReport(
                report_id=f"rep-abstain-{hypothesis_id}",
                hypothesis_id=hypothesis_id,
                title=title,
                status="ABSTAINED",
                evidence_references=[],
                sections={},
                limitations=["Abstention: No verified empirical evidence items provided."],
            )

        valid_refs = []
        invalid_items = []

        for item in evidence_items:
            ev_id = item.get("evidence_id")
            p_type = item.get("provenance_type")

            if ev_id and p_type in self.VALID_EVIDENCE_TYPES:
                valid_refs.append(ev_id)
            else:
                invalid_items.append(item)

        if not valid_refs:
            logger.error("All provided evidence items for %s failed verification: %s", hypothesis_id, invalid_items)
            raise UnverifiedEvidenceError(
                f"Cannot generate scientific report for '{hypothesis_id}': Evidence lacks valid provenance_type in {self.VALID_EVIDENCE_TYPES}"
            )

        report = ScientificReport(
            report_id=f"rep-{hypothesis_id}",
            hypothesis_id=hypothesis_id,
            title=title,
            status="VERIFIED_DRAFT",
            evidence_references=valid_refs,
            sections={
                "abstract": f"Discovery findings grounded on {len(valid_refs)} verified evidence sources.",
                "methodology": "Empirical data collected and validated via discovery pipeline.",
                "evidence_summary": f"Referenced evidence IDs: {', '.join(valid_refs)}",
            },
            limitations=[
                f"Findings restricted to evidence corpus {valid_refs}.",
                "Subject to independent reproduction and human expert review before core staging.",
            ],
        )

        logger.info("Generated evidence-gated scientific report %s with %d references", report.report_id, len(valid_refs))
        return report
