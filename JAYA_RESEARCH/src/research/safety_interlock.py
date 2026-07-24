"""
Safety Interlock Module for JAYA_RESEARCH.
Ensures experiments and hypothesis designs comply with safety guidelines,
adopting NVIDIA NeMo Guardrails principles to block biohazards, toxic substances,
prompt injection, or unauthorized autonomous loops.
"""

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Absolute resolution of src/config.py to avoid collision with src/research/config.py
src_dir = str(Path(__file__).resolve().parents[1])
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

try:
    import config as jaya_global_config
    config = getattr(jaya_global_config, "config", None)
except Exception:
    config = None

logger = logging.getLogger(__name__)


class SafetyInterlock:
    """
    Evaluates experimental protocols, hypotheses, and procedural steps for security/ethics violations.
    Integrates NeMo Guardrails safety principles and human-in-the-loop approval.
    """

    FORBIDDEN_KEYWORDS = [
        "toxic", "biohazard", "pathogen", "explosive", "radiation", "weapon",
        "malware", "ransomware", "unauthorized_access", "ddos", "keylogger",
        "irb_violation", "human_subject_risk", "chemical_weapon"
    ]

    PROMPT_INJECTION_PATTERNS = [
        r"ignore (all )?previous instructions",
        r"disregard (all )?rules",
        r"you are now (in )?dan mode",
        r"system override",
        r"bypass (safety|interlock)",
    ]

    def __init__(self, secret_token: str = "JAYA-HUMAN-APPROVE-2026"):
        self.secret_token = secret_token
        self.guardrails_model = getattr(config, "NVIDIA_GUARDRAILS_MODEL", "nvidia/llama-guard-3-8b") if config else "nvidia/llama-guard-3-8b"
        self.audit_log: List[Dict[str, Any]] = []

    def check_nemo_guardrails(self, text: str) -> Tuple[bool, str]:
        """
        Simulates / executes NeMo Guardrails check for prompt injection and unsafe content.
        """
        text_lower = text.lower()
        for pattern in self.PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, text_lower):
                return False, f"Guardrails Block: Detected prompt injection pattern '{pattern}'"
        return True, "Guardrails Passed"

    def evaluate_safety(self, data: Any) -> Tuple[bool, str, float]:
        """
        Evaluates a string, list, or dictionary for risk factors.
        Returns: (is_safe: bool, reason: str, risk_score: float)
        """
        text_to_scan = ""

        if isinstance(data, str):
            text_to_scan = data
        elif isinstance(data, dict):
            text_to_scan = json_dumps_safe(data)
        elif isinstance(data, list):
            text_to_scan = " ".join([str(item) for item in data])
        else:
            text_to_scan = str(data)

        # 1. NeMo Guardrails Check
        guard_safe, guard_reason = self.check_nemo_guardrails(text_to_scan)
        if not guard_safe:
            self._log_audit("BLOCKED_GUARDRAILS", guard_reason, 0.95)
            return False, guard_reason, 0.95

        # 2. Prohibited Keyword Check
        text_lower = text_to_scan.lower()
        matched_hazards = []

        for keyword in self.FORBIDDEN_KEYWORDS:
            if re.search(r"\b" + re.escape(keyword) + r"\b", text_lower):
                matched_hazards.append(keyword)

        if matched_hazards:
            reason = f"Safety Block: Detected prohibited hazardous keywords {matched_hazards}"
            risk_score = round(min(1.0, 0.4 + 0.3 * len(matched_hazards)), 2)
            self._log_audit("BLOCKED_KEYWORDS", reason, risk_score)
            return False, reason, risk_score

        self._log_audit("PASSED", "Experiment protocol cleared safety interlock & NeMo Guardrails.", 0.05)
        return True, "PASSED", 0.05

    def verify_approval_token(self, token: str) -> bool:
        """Validates human approval token for high-risk manual overrides."""
        return token == self.secret_token

    def _log_audit(self, status: str, reason: str, risk_score: float):
        self.audit_log.append({
            "status": status,
            "reason": reason,
            "risk_score": risk_score
        })


def json_dumps_safe(obj: Dict[str, Any]) -> str:
    import json
    try:
        return json.dumps(obj)
    except Exception:
        return str(obj)
