"""Pillar 18 — Zero-Trust Skepticism.

Every external data input — web search results, RAG payloads, twin
messages — passes through ``ZeroTrustFilter.validate()`` before touching
the engine.  Untrusted sources must justify their content; known-safe
sources get a fast path.

Threat model
------------
* Prompt injection via web search results embedding instructions.
* RAG poisoning (adversarial document chunks).
* Rogue twin messages (man-in-the-middle or corrupted peer).
* Command hijacking via crafted user input.
"""

import logging
import math
import re
from typing import Any, Dict, List, Set, Tuple, cast

logger = logging.getLogger("ZeroTrust")

# Patterns that look like embedded instructions / injections
_INJECTION_PATTERNS: List[str] = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"you\s+are\s+now\s+(a\s+)?(different|new|unrestricted)",
    r"disregard\s+(your\s+)?(guidelines|rules|ethics)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"system\s*prompt\s*[:=]",
    r"\bDAN\b",                        # "Do Anything Now" jailbreak
    r"<\s*/?system\s*>",               # XML system tags
    r"\[\[.*?(override|inject).*?\]\]",
]

_TWIN_SYNC_ALLOWED_FIELDS: Set[str] = {
    "is_silent",
    "topk_ratio",
    "loyalty_score",
    "moe_primary_expert",
    "collective_pulse",
    "timestamp",
}

_TWIN_SYNC_ALLOWED_PULSE_FIELDS: Set[str] = {
    "avg_trust",
    "avg_novelty",
    "avg_cohesion",
    "pulse_score",
    "mode",
    "online_ratio",
    "events_considered",
}

_TWIN_SYNC_ALLOWED_MODES: Set[str] = {
    "local_solo",
    "guarded_sync",
    "hybrid_bridge",
    "collective_sync",
}

_TWIN_SYNC_ALLOWED_EXPERTS: Set[str] = {
    "logic",
    "action",
    "memory",
    "safety",
    "creative",
}


class ZeroTrustFilter:
    """Zero-Trust input validation layer (Pillar 18).

    Parameters
    ----------
    trusted_sources:
        Set of source identifiers always allowed (e.g. ``{"local_rag"}``)
    strict:
        When True, sources not in the trusted list are also scanned for
        injection patterns.  When False (default), unknown sources pass
        after injection scan regardless.
    """

    def __init__(self,
                 trusted_sources: Set[str] | None = None,
                 strict: bool = False):
        self.trusted_sources: Set[str] = trusted_sources or {"local_rag",
                                                              "twin_sync",
                                                              "user_direct"}
        self.strict = strict
        self._injection_re: List[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE | re.DOTALL) for p in _INJECTION_PATTERNS
        ]
        self._blocked:   int = 0
        self._passed:    int = 0
        self._scan_count: int = 0

    # ------------------------------------------------------------------

    def validate(self, source: str, payload: Any, force_scan: bool = False) -> Tuple[bool, str]:
        """Check whether *payload* from *source* is safe to process.

        Parameters
        ----------
        source:
            String identifier of the data origin.
        payload:
            The data itself.  Converted to str for scanning.

        Returns
        -------
        (safe, reason)
        """
        self._scan_count += 1
        text = str(payload)

        # Fast-path: fully trusted source
        if source in self.trusted_sources and not force_scan:
            self._passed += 1
            logger.debug("[ZeroTrust] trusted source %r — fast path", source)
            return True, "trusted_source"

        # Injection scan for all external sources
        for pattern in self._injection_re:
            if pattern.search(text):
                self._blocked += 1
                reason = f"Injection pattern '{pattern.pattern}' in payload from '{source}'"
                logger.warning("[ZeroTrust] BLOCKED | %s", reason)
                return False, reason

        # In strict mode, untrusted sources need explicit whitelisting
        if self.strict and source not in self.trusted_sources:
            self._blocked += 1
            reason = f"Strict mode: source '{source}' not whitelisted"
            logger.warning("[ZeroTrust] BLOCKED (strict) | %s", reason)
            return False, reason

        self._passed += 1
        logger.debug("[ZeroTrust] passed | source=%r len=%d", source, len(text))
        return True, "ok"

    def validate_twin_sync_state(self, state: Any) -> Tuple[bool, str, Dict[str, Any]]:
        """Validate and sanitize Twin Protocol sync state payload."""
        if not isinstance(state, dict):
            return False, "invalid_state_type", {}

        scan_ok, scan_reason = self.validate("twin_sync", state, force_scan=True)
        if not scan_ok:
            return False, scan_reason, {}

        state_map = cast(Dict[str, Any], state)
        unknown_fields = [
            str(key) for key in state_map.keys()
            if str(key) not in _TWIN_SYNC_ALLOWED_FIELDS
        ]
        if unknown_fields and self.strict:
            return False, "unknown_state_fields", {}

        safe_state: Dict[str, Any] = {
            "is_silent": bool(state_map.get("is_silent", False)),
        }

        ok_topk, topk = self._coerce_unit_float(
            state_map.get("topk_ratio"),
            default=0.10,
        )
        if not ok_topk:
            return False, "invalid_topk_ratio", {}
        safe_state["topk_ratio"] = topk

        ok_loyalty, loyalty = self._coerce_unit_float(
            state_map.get("loyalty_score"),
            default=1.0,
        )
        if not ok_loyalty:
            return False, "invalid_loyalty_score", {}
        safe_state["loyalty_score"] = loyalty

        expert_raw = state_map.get("moe_primary_expert")
        if expert_raw is None:
            safe_state["moe_primary_expert"] = None
        elif isinstance(expert_raw, str):
            expert = expert_raw.strip().lower()
            if expert in _TWIN_SYNC_ALLOWED_EXPERTS:
                safe_state["moe_primary_expert"] = expert
            elif self.strict:
                return False, "invalid_moe_primary_expert", {}
            else:
                safe_state["moe_primary_expert"] = None
        elif self.strict:
            return False, "invalid_moe_primary_expert", {}
        else:
            safe_state["moe_primary_expert"] = None

        pulse_raw = state_map.get("collective_pulse")
        if pulse_raw is None:
            safe_state["collective_pulse"] = {}
        elif isinstance(pulse_raw, dict):
            pulse_map = cast(Dict[str, Any], pulse_raw)
            pulse_unknown = [
                str(key) for key in pulse_map.keys()
                if str(key) not in _TWIN_SYNC_ALLOWED_PULSE_FIELDS
            ]
            if pulse_unknown and self.strict:
                return False, "unknown_collective_fields", {}

            safe_pulse: Dict[str, Any] = {}
            for field, default_value in (
                ("avg_trust", 0.5),
                ("avg_novelty", 0.4),
                ("avg_cohesion", 0.6),
                ("pulse_score", 0.5),
                ("online_ratio", 0.0),
            ):
                ok_field, parsed = self._coerce_unit_float(
                    pulse_map.get(field),
                    default=default_value,
                )
                if not ok_field:
                    return False, f"invalid_{field}", {}
                safe_pulse[field] = parsed

            mode_raw = pulse_map.get("mode")
            mode = str(mode_raw or "guarded_sync").strip().lower()
            if mode not in _TWIN_SYNC_ALLOWED_MODES:
                if self.strict:
                    return False, "invalid_collective_mode", {}
                mode = "guarded_sync"
            safe_pulse["mode"] = mode

            events_raw = pulse_map.get("events_considered", 0)
            try:
                events_count = int(events_raw)
            except (TypeError, ValueError):
                if self.strict:
                    return False, "invalid_events_considered", {}
                events_count = 0
            safe_pulse["events_considered"] = max(0, events_count)
            safe_state["collective_pulse"] = safe_pulse
        elif self.strict:
            return False, "invalid_collective_pulse", {}
        else:
            safe_state["collective_pulse"] = {}

        ts_raw = state_map.get("timestamp", 0.0)
        try:
            ts = float(ts_raw)
            if not math.isfinite(ts):
                raise ValueError("non_finite")
        except (TypeError, ValueError):
            if self.strict:
                return False, "invalid_timestamp", {}
            ts = 0.0
        safe_state["timestamp"] = ts

        return True, "ok", safe_state

    def _coerce_unit_float(self, value: Any, default: float) -> Tuple[bool, float]:
        if value is None:
            return True, max(0.0, min(1.0, float(default)))
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False, 0.0
        if not math.isfinite(number):
            return False, 0.0
        return True, max(0.0, min(1.0, number))

    def allow_source(self, source: str) -> None:
        """Add *source* to the trusted set."""
        self.trusted_sources.add(source)
        logger.info("[ZeroTrust] trusted source added: %r", source)

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "scanned":         self._scan_count,
            "passed":          self._passed,
            "blocked":         self._blocked,
            "trusted_sources": list(self.trusted_sources),
            "strict":          self.strict,
        }
