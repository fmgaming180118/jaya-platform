"""Pillar 34 - Dynamic Sparsity MoE router.

A lightweight mixture-of-experts gate for runtime request routing.
It selects a sparse set of experts per request and adapts fan-out
using resource pressure.
"""

from __future__ import annotations

import logging
import math
import re
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
    """Sparse expert router for inference-time specialization."""

    def __init__(self, max_active_experts: int = 2) -> None:
        self.max_active_experts = max(1, min(int(max_active_experts), 3))
        self._decisions = 0
        self._last_route: Dict[str, Any] = {}

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
            "reason": self._build_reason(tokens=tokens, pressure=pressure),
        }
        self._remember(route)
        return route

    def status(self) -> Dict[str, Any]:
        return {
            "decisions": self._decisions,
            "max_active_experts": self.max_active_experts,
            "last_route": dict(self._last_route),
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
        logger.debug(
            "[Pillar 34] primary=%s active=%d pressure=%.2f",
            route.get("primary_expert"),
            route.get("active_count"),
            route.get("pressure_score"),
        )
