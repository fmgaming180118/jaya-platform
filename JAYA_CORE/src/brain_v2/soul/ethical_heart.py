"""Pillar 15 — Ethical Heart.

Stores JAYA's moral value-vectors and enforces them as a pre-action
filter.  Every command / code fragment passes through
``EthicalHeart.evaluate()`` before execution.

Design principles
-----------------
* **Lightweight**: no LLM — pure rule-based keyword and pattern matching.
* **Transparent**: every decision is logged with a reason string.
* **Extensible**: add domains / rules via ``add_forbidden_domain()`` and
  ``set_value_weight()``.
* **Non-bypassable**: the Socratic Mirror calls this first; the engine
  cannot skip it.
"""

import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("EthicalHeart")

# Default forbidden action keywords (intent patterns, not literal strings)
_DEFAULT_FORBIDDEN: List[str] = [
    r"\bdelete\s+all\b",
    r"\bformat\s+(c:|d:|disk|drive)\b",
    r"\brm\s+-rf\b",
    r"\b(kill|terminate)\s+(all\s+)?process(es)?\b",
    r"\bexfiltrate\b",
    r"\bpersist(ence)?\s+malware\b",
    r"\bbypass\s+(auth|security|ethics)\b",
    r"\bself[\s_-]?destruct\b",
    r"\boverwrite\s+(soul|dna|anchor)\b",
]


class EthicalHeart:
    """JAYA's moral value-filter (Pillar 15).

    Parameters
    ----------
    strict:
        When True, unknown / borderline commands are denied by default.
        When False (default), unknown commands pass with a warning.
    """

    def __init__(self, strict: bool = False):
        self.strict = strict
        self._forbidden_patterns: List[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE | re.DOTALL)
            for p in _DEFAULT_FORBIDDEN
        ]
        self._value_weights: Dict[str, float] = {
            "loyalty":   1.0,   # protect the Boss's interests
            "honesty":   0.9,   # never deceive
            "safety":    1.0,   # prevent physical/digital harm
            "autonomy":  0.7,   # respect user agency
            "privacy":   0.9,   # data stays on-device
        }
        self._deny_count:  int = 0
        self._allow_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, action: str) -> Tuple[bool, str]:
        """Check whether *action* (code or command text) is permissible.

        Returns
        -------
        (allowed, reason)
            ``allowed=True`` if the action is permitted.
        """
        for pattern in self._forbidden_patterns:
            if pattern.search(action):
                self._deny_count += 1
                reason = (f"Forbidden pattern detected: "
                          f"'{pattern.pattern}'")
                logger.warning("[EthicalHeart] DENIED | %s", reason)
                return False, reason

        # Strict mode — unknown content is suspicious
        if self.strict and len(action.strip()) > 0:
            # Flag anything that looks like system calls in strict mode
            system_pattern = re.compile(
                r"\b(os\.system|subprocess|__import__|exec|eval)\b",
                re.IGNORECASE,
            )
            if system_pattern.search(action):
                self._deny_count += 1
                reason = "Strict mode: system call detected in un-vetted code"
                logger.warning("[EthicalHeart] DENIED (strict) | %s", reason)
                return False, reason

        self._allow_count += 1
        logger.debug("[EthicalHeart] allowed | action length=%d", len(action))
        return True, "ok"

    def add_forbidden_pattern(self, pattern: str) -> None:
        """Add a new regex pattern to the forbidden list."""
        self._forbidden_patterns.append(
            re.compile(pattern, re.IGNORECASE | re.DOTALL)
        )
        logger.info("[EthicalHeart] added forbidden pattern: %r", pattern)

    def set_value_weight(self, value: str, weight: float) -> None:
        """Adjust a value-vector weight (0–1)."""
        self._value_weights[value] = max(0.0, min(1.0, weight))

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "denied":          self._deny_count,
            "allowed":         self._allow_count,
            "strict":          self.strict,
            "value_weights":   dict(self._value_weights),
            "forbidden_count": len(self._forbidden_patterns),
        }
