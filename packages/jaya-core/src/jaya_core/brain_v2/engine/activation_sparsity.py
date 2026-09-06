"""Pillar 35 - Activation Sparsity controller.

Adjusts active-neuron ratio (top-k) per request based on:
- resource pressure (cpu/memory),
- intent complexity,
- action risk profile,
- current silence state.

The controller is deterministic, bounded, dependency-free, and supports ACID disk persistence.
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
import re
import time
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
    """Adaptive top-k gating policy for runtime execution with persistent state."""

    def __init__(
        self,
        min_topk: float = 0.02,
        max_topk: float = 0.14,
        default_topk: float = 0.10,
        storage_path: Optional[str | Path] = None,
    ) -> None:
        self.min_topk = float(min_topk)
        self.max_topk = float(max_topk)
        self.default_topk = float(default_topk)
        self.storage_path = Path(storage_path).resolve() if storage_path else None

        self._decisions: int = 0
        self._last_decision: Dict[str, Any] = {}

        if self.storage_path and self.storage_path.exists():
            self._load_state()

    def save_state(self, path: Optional[str | Path] = None) -> bool:
        """Persist decision stats to disk atomically."""
        target = Path(path).resolve() if path else self.storage_path
        if not target:
            return False
        state = {
            "version": "1.0",
            "min_topk": self.min_topk,
            "max_topk": self.max_topk,
            "default_topk": self.default_topk,
            "decisions": self._decisions,
            "last_decision": self._last_decision,
            "updated_at": round(time.time(), 3),
        }
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_target = target.with_suffix(f"{target.suffix}.tmp")
            with open(tmp_target, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp_target, target)
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("[Pillar 35] Failed to save state to %s: %s", target, exc)
            return False

    def _load_state(self) -> bool:
        """Load decision stats from persistent file."""
        if not self.storage_path or not self.storage_path.exists():
            return False
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            self._decisions = max(self._decisions, int(data.get("decisions", 0)))
            if isinstance(data.get("last_decision"), dict):
                self._last_decision = data["last_decision"]
            return True
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("[Pillar 35] Failed to load state from %s: %s", self.storage_path, exc)
            return False

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
            "available": True,
            "min_topk": self.min_topk,
            "max_topk": self.max_topk,
            "default_topk": self.default_topk,
            "decisions": self._decisions,
            "last_decision": dict(self._last_decision),
            "persisted": self.storage_path is not None and self.storage_path.exists(),
            "storage_path": str(self.storage_path) if self.storage_path else None,
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

        return "general"

    def _complexity_score(self, text: str) -> float:
        cleaned = str(text or "").strip()
        if not cleaned:
            return 0.0

        length_factor = min(1.0, len(cleaned) / 240.0)
        word_count = len(cleaned.split())
        word_factor = min(1.0, word_count / 40.0)

        clause_count = len(re.findall(r"[,;:.?!]", cleaned))
        clause_factor = min(1.0, clause_count / 6.0)

        score = (0.45 * length_factor) + (0.35 * word_factor) + (0.20 * clause_factor)
        return max(0.0, min(1.0, score))

    def _pressure_score(self, cpu_pct: Optional[float], mem_pct: Optional[float]) -> float:
        cpu = self._safe_ratio(cpu_pct)
        mem = self._safe_ratio(mem_pct)
        return min(1.0, (0.70 * cpu) + (0.30 * mem))

    def _safe_ratio(self, value: Optional[float]) -> float:
        if value is None:
            return 0.0
        try:
            val = float(value)
        except (TypeError, ValueError):
            return 0.0

        if not math.isfinite(val):
            return 0.0

        return max(0.0, min(1.0, val / 100.0))

    def _clamp(self, value: float) -> float:
        return max(self.min_topk, min(self.max_topk, float(value)))

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
            "text_sample": text[:32],
            "base_topk": round(base_topk, 4),
            "target_topk": round(target_topk, 4),
            "ratio_pct": round(target_topk * 100.0, 2),
            "cpu_pct": cpu_pct,
            "mem_pct": mem_pct,
            "complexity": round(complexity, 3),
            "reason": reason,
        }

    def _remember(self, decision: Dict[str, Any]) -> None:
        self._decisions += 1
        self._last_decision = dict(decision)
        if self.storage_path:
            self.save_state()
        logger.debug(
            "[Pillar 35] topk=%.3f reason=%s",
            decision.get("target_topk"),
            decision.get("reason"),
        )
