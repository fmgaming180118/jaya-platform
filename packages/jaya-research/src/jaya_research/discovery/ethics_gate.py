"""
ethics_gate.py — Ethics, License, Privacy (PII), & Resource Budget Safety Gate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class EthicsCheckRequest:
    artifact_id: str
    license_name: str
    is_ethical_cleared: bool
    text_content: str
    estimated_gpu_hours: float
    estimated_cost_usd: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class EthicsLicensePrivacyGate:
    """Safety gate verifying ethics compliance, open licenses, privacy PII isolation, and resource budget bounds."""

    PERMITTED_LICENSES = {"mit", "apache-2.0", "cc-by-4.0", "bsd-3-clause", "public_domain"}
    PII_KEYWORDS = {"ssn", "social_security", "credit_card", "cvv", "medical_history", "private_phone"}

    def __init__(self, max_gpu_hours: float = 24.0, max_cost_usd: float = 100.00) -> None:
        self.max_gpu_hours = max_gpu_hours
        self.max_cost_usd = max_cost_usd

    def contains_pii(self, text: str) -> bool:
        t_lower = text.lower()
        return any(kw in t_lower for kw in self.PII_KEYWORDS)

    def evaluate(self, request: EthicsCheckRequest) -> Tuple[bool, List[str]]:
        violations = []

        # 1. Ethics Clearance
        if not request.is_ethical_cleared:
            violations.append("Ethics clearance flag is False")

        # 2. License Check
        if request.license_name.lower() not in self.PERMITTED_LICENSES:
            violations.append(
                f"License '{request.license_name}' is not in permitted list: {self.PERMITTED_LICENSES}"
            )

        # 3. Privacy PII Check
        if self.contains_pii(request.text_content):
            violations.append("Potential PII (personally identifiable information) detected in content")

        # 4. Resource Budget Gate
        if request.estimated_gpu_hours > self.max_gpu_hours:
            violations.append(
                f"Estimated GPU hours {request.estimated_gpu_hours:.1f} exceeds max limit of {self.max_gpu_hours:.1f}"
            )

        if request.estimated_cost_usd > self.max_cost_usd:
            violations.append(
                f"Estimated cost ${request.estimated_cost_usd:.2f} exceeds max budget of ${self.max_cost_usd:.2f}"
            )

        is_passed = len(violations) == 0
        if not is_passed:
            logger.warning("Ethics gate failed for artifact %s: %s", request.artifact_id, violations)

        return is_passed, violations
