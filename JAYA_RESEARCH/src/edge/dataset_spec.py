"""
dataset_spec.py — Legal & Versioned Student Dataset Specification for Edge Model Training.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class StudentDatasetSpec:
    dataset_id: str
    name: str
    version: str
    license_name: str  # e.g. "MIT", "Apache-2.0", "CC-BY-4.0"
    sample_count: int
    provenance_uri: str
    is_legal_cleared: bool = True
    sampling_frame: str = "balanced_multilingual"
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StudentDatasetValidator:
    """Validates student datasets for edge distillation to ensure compliance with legal & quality gates."""

    PERMITTED_LICENSES = {"mit", "apache-2.0", "cc-by-4.0", "bsd-3-clause"}

    def validate_spec(self, spec: StudentDatasetSpec) -> Tuple[bool, List[str]]:
        reasons = []

        if not spec.is_legal_cleared:
            reasons.append("Dataset is not legally cleared for model distillation")

        if spec.license_name.lower() not in self.PERMITTED_LICENSES:
            reasons.append(f"License '{spec.license_name}' is not in permitted list: {self.PERMITTED_LICENSES}")

        if spec.sample_count < 100:
            reasons.append(f"Sample count {spec.sample_count} is below required minimum of 100")

        if not spec.provenance_uri:
            reasons.append("Missing provenance URI")

        is_valid = len(reasons) == 0
        if not is_valid:
            logger.warning("Dataset spec %s invalid: %s", spec.dataset_id, reasons)

        return is_valid, reasons
