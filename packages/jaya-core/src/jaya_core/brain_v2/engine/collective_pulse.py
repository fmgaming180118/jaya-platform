"""Pillar 32 - Collective Pulse.

Aggregates local and peer signals into a bounded collective-state metric.
Goals:
- deterministic and lightweight,
- no network dependency in core logic,
- robust under offline-first operation with ACID disk persistence across restarts.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("CollectivePulse")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class CollectivePulse:
    """Bounded collective-state estimator with persistent state snapshotting."""

    def __init__(
        self,
        max_events: int = 160,
        history_window: int = 16,
        storage_path: Optional[str | Path] = None,
    ) -> None:
        self.max_events = max(32, int(max_events))
        self.history_window = max(4, int(history_window))
        self.storage_path = Path(storage_path).resolve() if storage_path else None

        self._events: List[Dict[str, Any]] = []
        self._last_activation_topk: Optional[float] = None
        self._last_summary: Dict[str, Any] = {
            "pulse_score": 0.5,
            "mode": "local_solo",
            "avg_trust": 0.5,
            "avg_cohesion": 0.5,
            "avg_novelty": 0.5,
            "online_ratio": 0.0,
            "events_considered": 0,
        }

        if self.storage_path and self.storage_path.exists():
            self._load_state()

    def save_state(self, path: Optional[str | Path] = None) -> bool:
        """Persist event history and current summary to disk atomically."""
        target = Path(path).resolve() if path else self.storage_path
        if not target:
            return False
        state = {
            "version": "1.0",
            "max_events": self.max_events,
            "history_window": self.history_window,
            "events": self._events,
            "last_activation_topk": self._last_activation_topk,
            "last_summary": self._last_summary,
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
            logger.warning("[Pillar 32] Failed to save state to %s: %s", target, exc)
            return False

    def _load_state(self) -> bool:
        """Load pulse event history and state from persistent file."""
        if not self.storage_path or not self.storage_path.exists():
            return False
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            loaded_events = data.get("events", [])
            if isinstance(loaded_events, list):
                self._events = loaded_events[-self.max_events :]
            self._last_activation_topk = data.get("last_activation_topk")
            if isinstance(data.get("last_summary"), dict):
                self._last_summary = data["last_summary"]
            return True
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("[Pillar 32] Failed to load state from %s: %s", self.storage_path, exc)
            return False

    def ingest_turn(
        self,
        text: str,
        activation_topk: float,
        primary_expert: str,
        is_online: bool,
        uncertainty: Optional[float] = None,
    ) -> Dict[str, Any]:
        trust = 0.62
        if primary_expert == "safety":
            trust += 0.14
        elif primary_expert == "logic":
            trust += 0.08

        if uncertainty is not None:
            try:
                trust -= 0.35 * _clamp01(float(uncertainty))
            except (TypeError, ValueError):
                pass

        novelty = self._derive_novelty(text=text, primary_expert=primary_expert)
        cohesion = self._derive_cohesion(activation_topk=activation_topk)

        event: Dict[str, Any] = {
            "ts": round(time.time(), 3),
            "kind": "turn",
            "online": bool(is_online),
            "trust": _clamp01(trust),
            "novelty": _clamp01(novelty),
            "cohesion": _clamp01(cohesion),
            "expert": str(primary_expert or "logic"),
        }
        self._append_event(event)
        return event

    def ingest_feedback(
        self,
        task: str,
        score: Optional[float],
        is_online: bool,
    ) -> Dict[str, Any]:
        trust = 0.50
        if score is not None:
            try:
                trust = _clamp01(float(score))
            except (TypeError, ValueError):
                trust = 0.50

        event: Dict[str, Any] = {
            "ts": round(time.time(), 3),
            "kind": "feedback",
            "online": bool(is_online),
            "trust": trust,
            "novelty": 0.30,
            "cohesion": 0.70,
            "task": str(task or "unknown_task"),
        }
        self._append_event(event)
        return event

    def ingest_peer_signal(
        self,
        peer_id: str,
        trust: float,
        novelty: float,
        cohesion: float,
        is_online: bool = True,
    ) -> Dict[str, Any]:
        event: Dict[str, Any] = {
            "ts": round(time.time(), 3),
            "kind": "peer",
            "online": bool(is_online),
            "trust": _clamp01(trust),
            "novelty": _clamp01(novelty),
            "cohesion": _clamp01(cohesion),
            "peer_id": str(peer_id or "peer"),
        }
        self._append_event(event)
        return event

    def pulse(self) -> Dict[str, Any]:
        sample = self._events[-self.history_window :]
        if not sample:
            return dict(self._last_summary)

        trust = sum(float(item.get("trust", 0.5)) for item in sample) / len(sample)
        novelty = sum(float(item.get("novelty", 0.5)) for item in sample) / len(sample)
        cohesion = sum(float(item.get("cohesion", 0.5)) for item in sample) / len(sample)
        online_ratio = sum(1.0 for item in sample if item.get("online")) / len(sample)

        novelty_stability = 1.0 - abs(novelty - 0.35) / 0.65
        novelty_stability = _clamp01(novelty_stability)

        pulse_score = _clamp01(0.50 * trust + 0.30 * cohesion + 0.20 * novelty_stability)
        mode = self._derive_mode(
            pulse_score=pulse_score,
            trust=trust,
            online_ratio=online_ratio,
        )

        summary: Dict[str, Any] = {
            "pulse_score": round(pulse_score, 4),
            "mode": mode,
            "avg_trust": round(_clamp01(trust), 4),
            "avg_cohesion": round(_clamp01(cohesion), 4),
            "avg_novelty": round(_clamp01(novelty), 4),
            "online_ratio": round(_clamp01(online_ratio), 4),
            "events_considered": len(sample),
        }
        self._last_summary = summary
        return dict(summary)

    def export_metrics(self) -> Dict[str, float]:
        """Export standardized Prometheus-compatible gauges."""
        current = self.pulse()
        return {
            "jaya_collective_pulse_score": float(current.get("pulse_score", 0.5)),
            "jaya_collective_avg_trust": float(current.get("avg_trust", 0.5)),
            "jaya_collective_avg_cohesion": float(current.get("avg_cohesion", 0.5)),
            "jaya_collective_avg_novelty": float(current.get("avg_novelty", 0.5)),
            "jaya_collective_online_ratio": float(current.get("online_ratio", 0.0)),
            "jaya_collective_events_total": float(len(self._events)),
        }

    def status(self) -> Dict[str, Any]:
        by_kind: Dict[str, int] = {}
        for item in self._events:
            kind = str(item.get("kind") or "unknown")
            by_kind[kind] = by_kind.get(kind, 0) + 1

        current = self.pulse()
        return {
            "available": True,
            "max_events": self.max_events,
            "history_window": self.history_window,
            "events": len(self._events),
            "by_kind": by_kind,
            "current": current,
            "last_activation_topk": self._last_activation_topk,
            "persisted": self.storage_path is not None and self.storage_path.exists(),
            "storage_path": str(self.storage_path) if self.storage_path else None,
        }

    def _derive_novelty(self, text: str, primary_expert: str) -> float:
        tokens = [tok for tok in str(text or "").lower().split() if tok]
        token_complexity = min(1.0, len(tokens) / 18.0)

        expert_shift = 0.0
        if self._events:
            prev_expert = str(self._events[-1].get("expert") or "")
            if prev_expert and prev_expert != primary_expert:
                expert_shift = 0.20

        return _clamp01(0.25 + 0.55 * token_complexity + expert_shift)

    def _derive_cohesion(self, activation_topk: float) -> float:
        topk = _clamp01(float(activation_topk) / 0.14)
        if self._last_activation_topk is None:
            cohesion = 0.72
        else:
            delta = abs(float(activation_topk) - self._last_activation_topk)
            cohesion = 1.0 - min(1.0, delta / 0.08)

        self._last_activation_topk = float(activation_topk)
        return _clamp01(0.60 * cohesion + 0.40 * topk)

    def _derive_mode(self, pulse_score: float, trust: float, online_ratio: float) -> str:
        if online_ratio < 0.20:
            return "local_solo"
        if trust < 0.45:
            return "guarded_sync"
        if pulse_score >= 0.72:
            return "collective_sync"
        return "hybrid_bridge"

    def _append_event(self, event: Dict[str, Any]) -> None:
        self._events.append(event)
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events :]

        if self.storage_path:
            self.save_state()

        logger.debug(
            "[Pillar 32] kind=%s trust=%.2f novelty=%.2f cohesion=%.2f online=%s",
            event.get("kind"),
            float(event.get("trust", 0.0)),
            float(event.get("novelty", 0.0)),
            float(event.get("cohesion", 0.0)),
            bool(event.get("online", False)),
        )
