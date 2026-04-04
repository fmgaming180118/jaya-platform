"""Pillar 35 - Activation Sparsity controller.

Adjusts active-neuron ratio (top-k) per request based on:
- resource pressure (cpu/memory),
- intent complexity,
- action risk profile,
- current silence state.

The controller is deterministic, bounded, and dependency-free.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, Optional, Sequence, cast

logger = logging.getLogger("ActivationSparsity")

_ACTION_RISK_TOKENS = {
    "delete", "remove", "drop", "shutdown", "rollback", "migrate", "upgrade",
    "hapus", "matikan", "rollback", "migrasi", "upgrade", "ubah",
}

_SIMPLE_CHAT_TOKENS = {
    "hi", "hello", "halo", "hai", "ping", "test", "cek",
}


class ActivationSparsityController:
    """Adaptive top-k gating policy for runtime execution."""

    def __init__(
        self,
        min_topk: float = 0.02,
        max_topk: float = 0.14,
        default_topk: float = 0.10,
    ) -> None:
        self.min_topk = float(min_topk)
        self.max_topk = float(max_topk)
        self.default_topk = float(default_topk)

        self._decisions: int = 0
        self._last_decision: Dict[str, Any] = {}

    def decide(
        self,
        text: str,
        logic_expr: Any = None,
        base_topk: Optional[float] = None,
        cpu_pct: Optional[float] = None,
        mem_pct: Optional[float] = None,
        is_silent: bool = False,
    ) -> Dict[str, Any]:
        """Compute a bounded top-k ratio for this execution turn."""
        safe_base = self._clamp(base_topk if base_topk is not None else self.default_topk)

        if is_silent:
            decision = self._pack_decision(
                text=text,
                base_topk=safe_base,
                target_topk=self.min_topk,
                cpu_pct=cpu_pct,
                mem_pct=mem_pct,
                reason="cognitive_silence",
                complexity=0.0,
            )
            self._remember(decision)
            return decision

        intent = self._classify_intent(text=text, logic_expr=logic_expr)
        complexity = self._complexity_score(text)
        pressure = self._pressure_score(cpu_pct=cpu_pct, mem_pct=mem_pct)

        # Start from baseline and subtract pressure-driven sparsity.
        target = safe_base - (0.06 * pressure)

        # Hard resource pressure trims more aggressively.
        if pressure >= 0.85:
            target -= 0.01
        if pressure >= 0.95:
            target -= 0.01

        # More complex requests get a small budget bump for reasoning quality.
        target += 0.02 * complexity

        # High-risk actions get a slight bump for safer decision quality.
        if intent == "action_risk":
            target += 0.01

        # Very simple chat can be more sparse.
        if intent == "simple_chat":
            target -= 0.01

        target = self._clamp(target)

        reason = (
            f"intent={intent};pressure={pressure:.2f};complexity={complexity:.2f}"
        )
        decision = self._pack_decision(
            text=text,
            base_topk=safe_base,
            target_topk=target,
            cpu_pct=cpu_pct,
            mem_pct=mem_pct,
            reason=reason,
            complexity=complexity,
        )
        self._remember(decision)
        return decision

    def status(self) -> Dict[str, Any]:
        return {
            "min_topk": self.min_topk,
            "max_topk": self.max_topk,
            "default_topk": self.default_topk,
            "decisions": self._decisions,
            "last_decision": dict(self._last_decision),
        }

    def _classify_intent(self, text: str, logic_expr: Any = None) -> str:
        cleaned = text.lower().strip()
        tokens = set(re.findall(r"[a-zA-Z0-9_]+", cleaned))

        if tokens & _ACTION_RISK_TOKENS:
            return "action_risk"

        if isinstance(logic_expr, (tuple, list)):
            seq = cast(Sequence[Any], logic_expr)
            if not seq:
                return "general"
            head = str(seq[0]).upper()
            if head == "ACTION":
                return "action"

        if tokens and tokens.issubset(_SIMPLE_CHAT_TOKENS):
            return "simple_chat"

        if len(tokens) <= 3 and ("?" not in cleaned):
            return "simple_chat"

        return "general"

    def _complexity_score(self, text: str) -> float:
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        token_count = len(tokens)
        punctuation_weight = text.count("?") + text.count(":") + text.count(";")

        # 0.0 to 1.0, grows with lexical and punctuation complexity.
        lexical = min(1.0, token_count / 20.0)
        punct = min(1.0, punctuation_weight / 6.0)
        return min(1.0, 0.8 * lexical + 0.2 * punct)

    def _pressure_score(self, cpu_pct: Optional[float], mem_pct: Optional[float]) -> float:
        cpu = self._safe_ratio(cpu_pct)
        mem = self._safe_ratio(mem_pct)

        # CPU pressure has stronger influence than memory pressure.
        return min(1.0, 0.7 * cpu + 0.3 * mem)

    def _safe_ratio(self, value: Optional[float]) -> float:
        if value is None:
            return 0.0
        try:
            v = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(v):
            return 0.0
        return self._clamp(v / 100.0, low=0.0, high=1.0)

    def _pack_decision(
        self,
        text: str,
        base_topk: float,
        target_topk: float,
        cpu_pct: Optional[float],
        mem_pct: Optional[float],
        reason: str,
        complexity: float,
    ) -> Dict[str, Any]:
        return {
            "text_preview": text[:80],
            "base_topk": round(base_topk, 4),
            "target_topk": round(target_topk, 4),
            "cpu_pct": cpu_pct,
            "mem_pct": mem_pct,
            "complexity": round(complexity, 4),
            "reason": reason,
        }

    def _remember(self, decision: Dict[str, Any]) -> None:
        self._decisions += 1
        self._last_decision = dict(decision)
        logger.debug(
            "[Pillar 35] topk %.3f -> %.3f (%s)",
            decision.get("base_topk"),
            decision.get("target_topk"),
            decision.get("reason"),
        )

    def _clamp(self, value: float, low: Optional[float] = None, high: Optional[float] = None) -> float:
        lo = self.min_topk if low is None else low
        hi = self.max_topk if high is None else high
        return max(lo, min(hi, float(value)))
