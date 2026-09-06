"""Pillar 10 — bounded, transparent affective control state.

"Affective" here means runtime control variables, not human emotion.  The
controller can make planning more cautious, urgent, patient, or escalatory,
but it cannot grant authority, weaken safety, or change factual content.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum


class ControlSignalSource(str, Enum):
    TASK = "TASK"
    RESOURCE = "RESOURCE"
    SAFETY = "SAFETY"
    USER_CONFIRMED = "USER_CONFIRMED"


class AffectiveSignalConflict(ValueError):
    """Raised when one signal ID is reused with different control material."""


@dataclass(frozen=True, slots=True)
class AffectiveControlPolicy:
    baseline_urgency: float = 0.20
    baseline_caution: float = 0.50
    baseline_patience: float = 0.70
    baseline_escalation: float = 0.00
    max_delta_per_signal: float = 0.25
    decay_half_life_seconds: float = 300.0
    confirmation_caution_threshold: float = 0.70
    escalation_threshold: float = 0.75
    max_signal_history: int = 4_096

    def __post_init__(self) -> None:
        bounded = (
            self.baseline_urgency,
            self.baseline_caution,
            self.baseline_patience,
            self.baseline_escalation,
            self.max_delta_per_signal,
            self.confirmation_caution_threshold,
            self.escalation_threshold,
        )
        if any(not 0.0 <= value <= 1.0 for value in bounded):
            raise ValueError("affective policy ratios must be in [0, 1]")
        if self.max_delta_per_signal <= 0:
            raise ValueError("max_delta_per_signal must be positive")
        if self.decay_half_life_seconds <= 0:
            raise ValueError("decay_half_life_seconds must be positive")
        if self.max_signal_history <= 0:
            raise ValueError("max_signal_history must be positive")


@dataclass(frozen=True, slots=True)
class AffectiveSignal:
    source: ControlSignalSource
    urgency_delta: float = 0.0
    caution_delta: float = 0.0
    patience_delta: float = 0.0
    escalation_delta: float = 0.0
    signal_id: str = ""
    user_state_confirmed: bool = False

    def __post_init__(self) -> None:
        if self.source is ControlSignalSource.USER_CONFIRMED and not self.user_state_confirmed:
            raise ValueError("user-derived state requires explicit confirmation")
        for value in (
            self.urgency_delta,
            self.caution_delta,
            self.patience_delta,
            self.escalation_delta,
        ):
            if not math.isfinite(value):
                raise ValueError("control signal deltas must be finite")


@dataclass(frozen=True, slots=True)
class AffectiveControlState:
    urgency: float
    caution: float
    patience: float
    escalation: float
    revision: int
    updated_at: str
    last_signal_id: str | None = None
    last_signal_source: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "urgency": self.urgency,
            "caution": self.caution,
            "patience": self.patience,
            "escalation": self.escalation,
            "revision": self.revision,
            "updated_at": self.updated_at,
            "last_signal_id": self.last_signal_id,
            "last_signal_source": self.last_signal_source,
        }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


class AffectiveMetabolismController:
    """Applies bounded signals and exposes a planner-facing policy decision."""

    HIGH_CAUTION_ACTIONS = frozenset(
        {"DELETE", "RESET", "MOVE", "SEND", "STOP", "TURN_OFF"}
    )
    URGENT_ACTIONS = frozenset({"STOP", "TURN_OFF"})

    def __init__(
        self,
        policy: AffectiveControlPolicy | None = None,
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy or AffectiveControlPolicy()
        self._clock = monotonic_clock
        self._lock = threading.RLock()
        self._last_tick = self._clock()
        self._seen_signal_ids: set[str] = set()
        self._signal_digests: dict[str, str] = {}
        self._signal_order: deque[str] = deque()
        self._state = self._baseline_state(revision=0)

    def _baseline_state(self, revision: int) -> AffectiveControlState:
        return AffectiveControlState(
            urgency=self.policy.baseline_urgency,
            caution=self.policy.baseline_caution,
            patience=self.policy.baseline_patience,
            escalation=self.policy.baseline_escalation,
            revision=revision,
            updated_at=_utc_now(),
        )

    def _decay_locked(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_tick)
        self._last_tick = now
        if elapsed == 0:
            return
        retention = math.pow(0.5, elapsed / self.policy.decay_half_life_seconds)

        def decay(value: float, baseline: float) -> float:
            return baseline + (value - baseline) * retention

        state = self._state
        self._state = replace(
            state,
            urgency=_bounded(decay(state.urgency, self.policy.baseline_urgency)),
            caution=max(
                self.policy.baseline_caution,
                _bounded(decay(state.caution, self.policy.baseline_caution)),
            ),
            patience=_bounded(decay(state.patience, self.policy.baseline_patience)),
            escalation=_bounded(
                decay(state.escalation, self.policy.baseline_escalation)
            ),
            updated_at=_utc_now(),
        )

    def apply(self, signal: AffectiveSignal) -> dict[str, object]:
        signal_id = signal.signal_id.strip() or str(uuid.uuid4())
        signal_digest = hashlib.sha256(
            json.dumps(
                {
                    "source": signal.source.value,
                    "urgency_delta": signal.urgency_delta,
                    "caution_delta": signal.caution_delta,
                    "patience_delta": signal.patience_delta,
                    "escalation_delta": signal.escalation_delta,
                    "user_state_confirmed": signal.user_state_confirmed,
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        with self._lock:
            if signal_id in self._seen_signal_ids:
                if self._signal_digests.get(signal_id) != signal_digest:
                    raise AffectiveSignalConflict(
                        "signal_id is already bound to different control material"
                    )
                return {
                    "ok": True,
                    "changed": False,
                    "state": self._state.as_dict(),
                    "decision": self._decision_locked(),
                }
            self._decay_locked()
            limit = self.policy.max_delta_per_signal

            def clipped(value: float) -> float:
                return max(-limit, min(limit, value))

            state = self._state
            self._state = AffectiveControlState(
                urgency=_bounded(state.urgency + clipped(signal.urgency_delta)),
                caution=max(
                    self.policy.baseline_caution,
                    _bounded(state.caution + clipped(signal.caution_delta)),
                ),
                patience=_bounded(state.patience + clipped(signal.patience_delta)),
                escalation=_bounded(
                    state.escalation + clipped(signal.escalation_delta)
                ),
                revision=state.revision + 1,
                updated_at=_utc_now(),
                last_signal_id=signal_id,
                last_signal_source=signal.source.value,
            )
            self._seen_signal_ids.add(signal_id)
            self._signal_digests[signal_id] = signal_digest
            self._signal_order.append(signal_id)
            while len(self._signal_order) > self.policy.max_signal_history:
                expired = self._signal_order.popleft()
                self._seen_signal_ids.discard(expired)
                self._signal_digests.pop(expired, None)
            return {
                "ok": True,
                "changed": True,
                "state": self._state.as_dict(),
                "decision": self._decision_locked(),
            }

    def observe_logic_expr(self, expr: object) -> dict[str, object]:
        """Derive task-control signals from parsed structure, never user emotion."""
        if not isinstance(expr, tuple) or len(expr) < 2:
            return self.status()
        head = str(expr[0])
        kind = str(expr[1])
        urgency = 0.0
        caution = 0.0
        patience = 0.0
        escalation = 0.0
        if head == "ACTION":
            if kind in self.HIGH_CAUTION_ACTIONS:
                caution = self.policy.max_delta_per_signal
            if kind in self.URGENT_ACTIONS:
                urgency = self.policy.max_delta_per_signal
        elif head == "QUERY":
            patience = min(0.05, self.policy.max_delta_per_signal)
        signal = AffectiveSignal(
            source=ControlSignalSource.TASK,
            urgency_delta=urgency,
            caution_delta=caution,
            patience_delta=patience,
            escalation_delta=escalation,
        )
        return self.apply(signal)

    def _decision_locked(self) -> dict[str, object]:
        state = self._state
        if state.urgency >= 0.75:
            priority = "critical"
            interaction_mode = "concise"
        elif state.urgency >= 0.50:
            priority = "high"
            interaction_mode = "concise"
        elif state.patience >= 0.70:
            priority = "normal"
            interaction_mode = "measured"
        else:
            priority = "normal"
            interaction_mode = "neutral"
        return {
            "planner_priority": priority,
            "interaction_mode": interaction_mode,
            "confirmation_recommended": (
                state.caution >= self.policy.confirmation_caution_threshold
            ),
            "escalation_recommended": (
                state.escalation >= self.policy.escalation_threshold
            ),
            "authority_changed": False,
            "safety_relaxed": False,
            "factual_content_changed": False,
        }

    def decision(self) -> dict[str, object]:
        with self._lock:
            self._decay_locked()
            return self._decision_locked()

    def reset(self) -> dict[str, object]:
        with self._lock:
            revision = self._state.revision + 1
            self._state = self._baseline_state(revision=revision)
            self._seen_signal_ids.clear()
            self._signal_digests.clear()
            self._signal_order.clear()
            self._last_tick = self._clock()
            return self.status()

    def status(self) -> dict[str, object]:
        with self._lock:
            self._decay_locked()
            return {
                "available": True,
                "classification": "RULE_BASED_CONTROL_STATE",
                "persistent": False,
                "state": self._state.as_dict(),
                "decision": self._decision_locked(),
            }


__all__ = [
    "AffectiveControlPolicy",
    "AffectiveControlState",
    "AffectiveMetabolismController",
    "AffectiveSignal",
    "AffectiveSignalConflict",
    "ControlSignalSource",
]
