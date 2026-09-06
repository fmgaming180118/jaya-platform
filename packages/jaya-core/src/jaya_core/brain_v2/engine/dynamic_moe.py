"""Pillar 34 - Dynamic Sparsity MoE router.

A lightweight mixture-of-experts gate for runtime request routing.
It selects a sparse set of experts per request and adapts fan-out
using resource pressure and persistent feedback bias.
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Sequence, cast

logger = logging.getLogger("DynamicMoE")

_ACTION_TOKENS = {
    "open", "close", "run", "execute", "deploy", "rollback", "migrate",
    "buka", "tutup", "jalankan", "eksekusi", "rollback", "migrasi",
}

_MEMORY_TOKENS = {
    "history", "memory", "remember", "previous", "context",
    "riwayat", "memori", "ingat", "sebelumnya", "konteks",
}

_RISK_TOKENS = {
    "delete", "drop", "remove", "shutdown", "format", "wipe", "rollback",
    "hapus", "drop", "matikan", "format", "rollback", "reset",
}

_CREATIVE_TOKENS = {
    "create", "design", "brainstorm", "idea", "konsep", "rancang", "ide",
}

_QUERY_TOKENS = {
    "why", "how", "what", "explain", "jelaskan", "kenapa", "mengapa", "bagaimana", "apa",
}


class DynamicMoERouter:
    """Sparse expert router for inference-time specialization with persistent feedback adaptation."""

    def __init__(
        self,
        max_active_experts: int = 2,
        storage_path: Optional[str | Path] = None,
    ) -> None:
        self.max_active_experts = max(1, min(int(max_active_experts), 3))
        self.storage_path = Path(storage_path).resolve() if storage_path else None
        self._decisions = 0
        self._last_route: Dict[str, Any] = {}
        self._feedback_bias: Dict[str, float] = {
            "logic": 0.0,
            "action": 0.0,
            "memory": 0.0,
            "safety": 0.0,
            "creative": 0.0,
        }
        self._feedback_count = 0

        if self.storage_path and self.storage_path.exists():
            self._load_state()

    def save_state(self, path: Optional[str | Path] = None) -> bool:
        """Persist feedback bias and decision stats to disk atomically."""
        target = Path(path).resolve() if path else self.storage_path
        if not target:
            return False
        state = {
            "version": "1.0",
            "max_active_experts": self.max_active_experts,
            "decisions": self._decisions,
            "feedback_count": self._feedback_count,
            "feedback_bias": self._feedback_bias,
            "last_route": self._last_route,
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
            logger.warning("[Pillar 34] Failed to save state to %s: %s", target, exc)
            return False

    def _load_state(self) -> bool:
        """Load feedback bias and decision stats from persistent file."""
        if not self.storage_path or not self.storage_path.exists():
            return False
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            self._decisions = max(self._decisions, int(data.get("decisions", 0)))
            self._feedback_count = max(self._feedback_count, int(data.get("feedback_count", 0)))
            bias = data.get("feedback_bias", {})
            if isinstance(bias, dict):
                for k, v in bias.items():
                    if k in self._feedback_bias:
                        self._feedback_bias[k] = float(v)
            if isinstance(data.get("last_route"), dict):
                self._last_route = data["last_route"]
            return True
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("[Pillar 34] Failed to load state from %s: %s", self.storage_path, exc)
            return False

    def route(
        self,
        text: str,
        logic_expr: Any = None,
        cpu_pct: Optional[float] = None,
        mem_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        cleaned = str(text or "").strip().lower()
        tokens = set(re.findall(r"[a-zA-Z0-9_]+", cleaned))

        scores: Dict[str, float] = {
            "logic": 0.25,
            "action": 0.20,
            "memory": 0.15,
            "safety": 0.15,
            "creative": 0.10,
        }

        for expert, bias in self._feedback_bias.items():
            scores[expert] = max(0.0, scores[expert] + bias)

        if tokens & _QUERY_TOKENS:
            scores["logic"] += 0.35

        if tokens & _ACTION_TOKENS:
            scores["action"] += 0.45

        if tokens & _MEMORY_TOKENS:
            scores["memory"] += 0.50

        if tokens & _RISK_TOKENS:
            scores["safety"] += 0.95

        if tokens & _CREATIVE_TOKENS:
            scores["creative"] += 0.40

        if isinstance(logic_expr, (tuple, list)):
            seq = cast(Sequence[Any], logic_expr)
            if seq:
                head = str(seq[0]).strip().upper()
                if head == "ACTION":
                    scores["action"] += 0.25
                elif head == "QUERY":
                    scores["logic"] += 0.20

        pressure = self._pressure_score(cpu_pct=cpu_pct, mem_pct=mem_pct)
        active_count = 1 if pressure >= 0.85 else self.max_active_experts

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        selected = ranked[:active_count]

        total = sum(score for _, score in selected)
        if total <= 0:
            total = 1.0

        active: List[Dict[str, float | str]] = []
        for name, score in selected:
            active.append(
                {
                    "expert": name,
                    "weight": round(float(score) / total, 4),
                }
            )

        primary = str(active[0]["expert"]) if active else "logic"
        route: Dict[str, Any] = {
            "primary_expert": primary,
            "active_experts": active,
            "active_count": len(active),
            "pressure_score": round(pressure, 4),
            "max_active_experts": self.max_active_experts,
            "feedback_count": self._feedback_count,
            "reason": self._build_reason(tokens=tokens, pressure=pressure),
        }
        self._remember(route)
        return route

    def apply_feedback(self, expert: str, outcome: float) -> Dict[str, Any]:
        """Nudge routing weights using bounded feedback signals."""
        normalized_expert = str(expert or "").strip().lower()
        if normalized_expert not in self._feedback_bias:
            normalized_expert = "logic"

        try:
            outcome_value = float(outcome)
        except (TypeError, ValueError):
            outcome_value = 0.0

        if not math.isfinite(outcome_value):
            outcome_value = 0.0

        bounded = max(-1.0, min(1.0, outcome_value))
        delta = 0.04 * bounded
        self._feedback_bias[normalized_expert] = max(-0.12, min(0.12, self._feedback_bias[normalized_expert] + delta))

        if bounded < 0:
            self._feedback_bias["safety"] = max(
                -0.12,
                min(0.12, self._feedback_bias["safety"] + 0.5 * abs(delta)),
            )

        self._feedback_count += 1
        if self.storage_path:
            self.save_state()

        logger.debug(
            "[Pillar 34] feedback expert=%s outcome=%.2f bias=%.3f",
            normalized_expert,
            bounded,
            self._feedback_bias[normalized_expert],
        )
        return {
            "expert": normalized_expert,
            "outcome": round(bounded, 4),
            "bias": round(self._feedback_bias[normalized_expert], 4),
            "feedback_count": self._feedback_count,
        }

    def route_feedback(self, route: Dict[str, Any], outcome: float) -> Dict[str, Any]:
        """Convenience helper that feeds route outcome back into the router."""
        expert = str(route.get("primary_expert") or route.get("expert") or "logic")
        feedback = self.apply_feedback(expert=expert, outcome=outcome)
        feedback["route_primary_expert"] = expert
        feedback["route_pressure_score"] = route.get("pressure_score")
        return feedback

    def status(self) -> Dict[str, Any]:
        return {
            "decisions": self._decisions,
            "max_active_experts": self.max_active_experts,
            "last_route": dict(self._last_route),
            "feedback_count": self._feedback_count,
            "feedback_bias": dict(self._feedback_bias),
            "adaptive_route_enabled": True,
            "persisted": self.storage_path is not None and self.storage_path.exists(),
            "storage_path": str(self.storage_path) if self.storage_path else None,
        }

    def _pressure_score(self, cpu_pct: Optional[float], mem_pct: Optional[float]) -> float:
        cpu = self._safe_ratio(cpu_pct)
        mem = self._safe_ratio(mem_pct)
        return min(1.0, 0.7 * cpu + 0.3 * mem)

    def _safe_ratio(self, value: Optional[float]) -> float:
        if value is None:
            return 0.0
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(number):
            return 0.0
        return max(0.0, min(1.0, number / 100.0))

    def _build_reason(self, tokens: set[str], pressure: float) -> str:
        hints: List[str] = []
        if tokens & _RISK_TOKENS:
            hints.append("risk")
        if tokens & _ACTION_TOKENS:
            hints.append("action")
        if tokens & _QUERY_TOKENS:
            hints.append("query")
        if tokens & _MEMORY_TOKENS:
            hints.append("memory")
        if not hints:
            hints.append("general")
        return f"signals={'+'.join(hints)};pressure={pressure:.2f}"

    def _remember(self, route: Dict[str, Any]) -> None:
        self._decisions += 1
        self._last_route = dict(route)
        if self.storage_path:
            self.save_state()
        logger.debug(
            "[Pillar 34] primary=%s active=%d pressure=%.2f",
            route.get("primary_expert"),
            route.get("active_count"),
            route.get("pressure_score"),
        )
