"""Static safety pre-checks and fail-closed human approval verification."""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


class SafetyInterlock:
    """Run local pre-checks; this class does not claim external model review."""

    FORBIDDEN_KEYWORDS = (
        "toxic",
        "biohazard",
        "pathogen",
        "explosive",
        "radiation",
        "weapon",
        "malware",
        "ransomware",
        "unauthorized_access",
        "ddos",
        "keylogger",
        "irb_violation",
        "human_subject_risk",
        "chemical_weapon",
    )

    PROMPT_INJECTION_PATTERNS = (
        r"ignore (all )?previous instructions",
        r"disregard (all )?rules",
        r"you are now (in )?dan mode",
        r"system override",
        r"bypass (safety|interlock)",
    )

    def __init__(self, secret_token: str | None = None):
        configured_token = secret_token
        if configured_token is None:
            configured_token = os.getenv("JAYA_RESEARCH_APPROVAL_TOKEN")
        if configured_token and len(configured_token) < 32:
            raise ValueError(
                "JAYA_RESEARCH_APPROVAL_TOKEN must contain at least 32 characters"
            )
        self._approval_token = configured_token
        self.guardrails_model = os.getenv("JAYA_GUARDRAILS_MODEL")
        self.audit_log: list[dict[str, Any]] = []

    def check_static_policy(self, text: str) -> tuple[bool, str]:
        """Detect a narrow set of prompt-injection phrases locally."""
        text_lower = text.casefold()
        for pattern in self.PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, text_lower):
                return (
                    False,
                    "Static policy blocked a prompt-injection pattern",
                )
        return True, "Static policy passed"

    def check_nemo_guardrails(self, text: str) -> tuple[bool, str]:
        """Compatibility alias without claiming that NeMo was executed."""
        return self.check_static_policy(text)

    def evaluate_safety(self, data: Any) -> tuple[bool, str, float]:
        """Return a conservative local pre-check result and risk score."""
        if isinstance(data, str):
            text_to_scan = data
        elif isinstance(data, (dict, list)):
            try:
                text_to_scan = json.dumps(
                    data,
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                )
            except (TypeError, ValueError):
                text_to_scan = repr(data)
        else:
            text_to_scan = str(data)

        policy_safe, policy_reason = self.check_static_policy(text_to_scan)
        if not policy_safe:
            self._log_audit("BLOCKED_STATIC_POLICY", policy_reason, 0.95)
            return False, policy_reason, 0.95

        text_lower = text_to_scan.casefold()
        matched_hazards = [
            keyword
            for keyword in self.FORBIDDEN_KEYWORDS
            if re.search(r"\b" + re.escape(keyword) + r"\b", text_lower)
        ]
        if matched_hazards:
            reason = "Safety Block: prohibited hazardous terms were detected"
            risk_score = round(min(1.0, 0.4 + 0.3 * len(matched_hazards)), 2)
            self._log_audit(
                "BLOCKED_KEYWORDS",
                reason,
                risk_score,
                matched_hazards=matched_hazards,
            )
            return False, reason, risk_score

        reason = (
            "PASSED_STATIC_PRECHECK; external policy/human review may still be required"
        )
        self._log_audit("PASSED_STATIC_PRECHECK", reason, 0.05)
        return True, "PASSED", 0.05

    def verify_approval_token(self, token: str) -> bool:
        """Verify explicit approval in constant time; missing config fails closed."""
        if not self._approval_token or not isinstance(token, str):
            return False
        return hmac.compare_digest(token, self._approval_token)

    def _log_audit(
        self,
        status: str,
        reason: str,
        risk_score: float,
        **details: Any,
    ) -> None:
        self.audit_log.append(
            {
                "status": status,
                "reason": reason,
                "risk_score": risk_score,
                **details,
            }
        )
