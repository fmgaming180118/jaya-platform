"""Pillar 5 — Logical Homeostasis.

Periodically audits the brain's cognitive health by scanning
ExperimentMemory.  When degradation is detected (average score drops
below a threshold, or error-rate spikes), a high-priority REPAIR task
is injected into the twin's planner so the brain self-corrects.
"""

import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from src.resources.profiler import ResourceProfile

logger = logging.getLogger("Homeostasis")


class HomeostasisAudit:
    """Logical Homeostasis monitor.

    Parameters
    ----------
    check_interval:
        Seconds between health audits.
    min_avg_score:
        If rolling average score drops below this, emit a REPAIR task.
    max_error_rate:
        If error ratio exceeds this (0–1), emit a REPAIR task.
    window:
        How many recent records to evaluate.
    """

    def __init__(
        self,
        check_interval: float = 60.0,
        min_avg_score: float = 0.40,
        max_error_rate: float = 0.30,
        window: int = 20,
    ):
        self.check_interval = check_interval
        self.min_avg_score = min_avg_score
        self.max_error_rate = max_error_rate
        self.window = window
        self._last_check: float = time.time()
        self._alert_count: int = 0

    # ------------------------------------------------------------------

    def tick(self, twin: Any) -> None:
        """Call this every cycle from the twin (or engine).

        Runs an audit when the interval elapses and queues repair tasks
        as needed.
        """
        now = time.time()
        if now - self._last_check < self.check_interval:
            return
        self._last_check = now
        self._audit(twin)

    # ------------------------------------------------------------------

    def _audit(self, twin: Any) -> None:
        from src.brain_v2.extensions.twin.task_planner import Priority, Task

        recent = twin.memory.recent(self.window)
        if not recent:
            return

        total: int = len(recent)
        errors: int = sum(1 for r in recent if r.label == "ERROR")
        avg_score: float = sum(r.score for r in recent) / total
        error_rate: float = errors / total

        issues: List[str] = []
        if avg_score < self.min_avg_score:
            issues.append(f"avg_score={avg_score:.3f} < {self.min_avg_score}")
        if error_rate > self.max_error_rate:
            issues.append(f"error_rate={error_rate:.2f} > {self.max_error_rate}")

        if issues:
            self._alert_count += 1
            reason = "; ".join(issues)
            logger.warning(
                "[Homeostasis Alert #%d] %s — injecting REPAIR",
                self._alert_count,
                reason,
            )
            # V18: smart REPAIR based on severity
            if avg_score < self.min_avg_score and error_rate > self.max_error_rate:
                # Both degraded: evolve weights + meta-reflect
                repair_code = (
                    "from src.brain_v2.education.live_evolver import LiveEvolver\n"
                    "evolver = LiveEvolver(engine, max_steps=300)\n"
                    "result = evolver.run_evolution(300)\n"
                    "score = min(1.0, 0.4 + result['delta_fitness'] * 2)\n"
                )
            elif error_rate > self.max_error_rate:
                # High error rate: curriculum self-study
                repair_code = (
                    "from src.brain_v2.engine.self_bootstrap import SelfBootstrap\n"
                    "sb = SelfBootstrap()\n"
                    "tasks = sb.generate_curriculum(twin)\n"
                    "score = 0.6 if tasks else 0.4\n"
                )
            else:
                # Low score: light weight evolution
                repair_code = (
                    "from src.brain_v2.education.live_evolver import LiveEvolver\n"
                    "evolver = LiveEvolver(engine, max_steps=150)\n"
                    "result = evolver.run_evolution(150)\n"
                    "score = min(1.0, 0.5 + result['delta_fitness'])\n"
                )
            twin.planner.push(
                Task(
                    priority=int(Priority.CRITICAL),
                    label="REPAIR",
                    code=repair_code,
                    meta={"reason": reason, "alert": self._alert_count},
                )
            )
        else:
            logger.debug(
                "[Homeostasis] brain healthy | avg=%.3f errors=%d/%d",
                avg_score,
                errors,
                total,
            )

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "alerts": self._alert_count,
            "check_interval": self.check_interval,
            "min_avg_score": self.min_avg_score,
            "max_error_rate": self.max_error_rate,
        }


class HomeostasisState(str, Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    SAFE_STOP = "SAFE_STOP"


@dataclass(frozen=True, slots=True)
class HomeostasisPolicy:
    critical_memory_mb: int = 64
    degraded_memory_mb: int = 512
    recovery_memory_mb: int = 768
    critical_storage_mb: int = 128
    degraded_storage_mb: int = 1_024
    recovery_storage_mb: int = 1_536
    degraded_thermal_celsius: float = 85.0
    critical_thermal_celsius: float = 95.0
    recovery_thermal_celsius: float = 75.0

    def __post_init__(self) -> None:
        values = (
            self.critical_memory_mb,
            self.degraded_memory_mb,
            self.recovery_memory_mb,
            self.critical_storage_mb,
            self.degraded_storage_mb,
            self.recovery_storage_mb,
        )
        if any(value <= 0 for value in values):
            raise ValueError("homeostasis thresholds must be positive")
        if (
            not self.critical_memory_mb
            < self.degraded_memory_mb
            < self.recovery_memory_mb
        ):
            raise ValueError("memory thresholds must be strictly ascending")
        if (
            not self.critical_storage_mb
            < self.degraded_storage_mb
            < self.recovery_storage_mb
        ):
            raise ValueError("storage thresholds must be strictly ascending")
        if not (
            0
            < self.recovery_thermal_celsius
            < self.degraded_thermal_celsius
            < self.critical_thermal_celsius
        ):
            raise ValueError("thermal thresholds are invalid")


@dataclass(frozen=True, slots=True)
class HomeostasisDecision:
    previous_state: HomeostasisState
    state: HomeostasisState
    reasons: tuple[str, ...]
    observed_at: str

    @property
    def changed(self) -> bool:
        return self.previous_state is not self.state

    def to_dict(self) -> dict[str, object]:
        return {
            "previous_state": self.previous_state.value,
            "state": self.state.value,
            "reasons": list(self.reasons),
            "observed_at": self.observed_at,
            "changed": self.changed,
        }


class HomeostasisEventStore:
    """Persistent transition ledger for the canonical homeostasis controller."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.db_path,
            timeout=5.0,
            check_same_thread=False,
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS homeostasis_transitions (
                transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                observed_at TEXT NOT NULL,
                previous_state TEXT NOT NULL,
                state TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                profile_json TEXT NOT NULL
            )
            """
        )
        columns = {
            str(row[1])
            for row in self._connection.execute(
                "PRAGMA table_info(homeostasis_transitions)"
            ).fetchall()
        }
        if "event_sha256" not in columns:
            self._connection.execute(
                """
                ALTER TABLE homeostasis_transitions
                ADD COLUMN event_sha256 TEXT NOT NULL DEFAULT ''
                """
            )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS homeostasis_corruptions (
                transition_id INTEGER PRIMARY KEY,
                detected_at TEXT NOT NULL,
                reason TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def append(
        self,
        decision: HomeostasisDecision,
        profile: ResourceProfile,
    ) -> None:
        reasons_json = json.dumps(decision.reasons, separators=(",", ":"))
        profile_json = json.dumps(
            profile.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )
        event_sha256 = self._event_digest(
            decision.observed_at,
            decision.previous_state.value,
            decision.state.value,
            reasons_json,
            profile_json,
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO homeostasis_transitions (
                    observed_at, previous_state, state, reasons_json, profile_json,
                    event_sha256
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.observed_at,
                    decision.previous_state.value,
                    decision.state.value,
                    reasons_json,
                    profile_json,
                    event_sha256,
                ),
            )

    def last_state(self) -> HomeostasisState | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT transition_id, observed_at, previous_state, state,
                       reasons_json, profile_json, event_sha256
                FROM homeostasis_transitions
                ORDER BY transition_id DESC LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            transition_id = int(row[0])
            expected = self._event_digest(*row[1:6])
            stored = str(row[6])
            if not stored:
                with self._connection:
                    self._connection.execute(
                        """
                        UPDATE homeostasis_transitions SET event_sha256 = ?
                        WHERE transition_id = ?
                        """,
                        (expected, transition_id),
                    )
            elif stored != expected:
                self._record_corruption(transition_id, "digest_mismatch")
                return HomeostasisState.SAFE_STOP
            try:
                json.loads(str(row[4]))
                json.loads(str(row[5]))
                return HomeostasisState(str(row[3]))
            except (ValueError, TypeError, json.JSONDecodeError):
                self._record_corruption(transition_id, "invalid_payload")
                return HomeostasisState.SAFE_STOP

    def corruption_count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM homeostasis_corruptions"
            ).fetchone()
        return int(row[0])

    def _record_corruption(self, transition_id: int, reason: str) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO homeostasis_corruptions (
                    transition_id, detected_at, reason
                ) VALUES (?, ?, ?)
                """,
                (transition_id, datetime.now(timezone.utc).isoformat(), reason),
            )

    @staticmethod
    def _event_digest(
        observed_at: str,
        previous_state: str,
        state: str,
        reasons_json: str,
        profile_json: str,
    ) -> str:
        payload = "\x1f".join(
            (observed_at, previous_state, state, reasons_json, profile_json)
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM homeostasis_transitions"
            ).fetchone()
        return int(row[0])

    def health_check(self) -> bool:
        try:
            with self._lock:
                self._connection.execute("SELECT 1").fetchone()
        except sqlite3.Error:
            return False
        return True

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class LogicalHomeostasisController:
    """Fail-closed runtime gate with hysteresis and persistent transitions."""

    def __init__(
        self,
        store: HomeostasisEventStore,
        policy: HomeostasisPolicy | None = None,
    ) -> None:
        self.store = store
        self.policy = policy or HomeostasisPolicy()
        self._state = store.last_state() or HomeostasisState.NORMAL
        self._ledger_was_corrupt = store.corruption_count() > 0
        self._lock = threading.RLock()

    @property
    def state(self) -> HomeostasisState:
        return self._state

    def is_ready(self) -> bool:
        return self.store.health_check()

    def evaluate(
        self,
        profile: ResourceProfile,
        *,
        logic_ready: bool,
        memory_ready: bool,
    ) -> HomeostasisDecision:
        with self._lock:
            return self._evaluate_locked(
                profile,
                logic_ready=logic_ready,
                memory_ready=memory_ready,
            )

    def _evaluate_locked(
        self,
        profile: ResourceProfile,
        *,
        logic_ready: bool,
        memory_ready: bool,
    ) -> HomeostasisDecision:
        reasons: list[str] = []
        target = HomeostasisState.NORMAL

        if not logic_ready:
            reasons.append("logic_unavailable")
            target = HomeostasisState.SAFE_STOP
        if not memory_ready:
            reasons.append("memory_unavailable")
            target = HomeostasisState.SAFE_STOP

        available_memory = profile.available_memory_mb
        storage_free = profile.storage_free_mb
        if available_memory is None:
            reasons.append("memory_metric_unknown")
            if target is HomeostasisState.NORMAL:
                target = HomeostasisState.DEGRADED
        elif available_memory < self.policy.critical_memory_mb:
            reasons.append("memory_critical")
            target = HomeostasisState.SAFE_STOP
        elif available_memory < self.policy.degraded_memory_mb:
            reasons.append("memory_degraded")
            if target is HomeostasisState.NORMAL:
                target = HomeostasisState.DEGRADED

        if storage_free is None:
            reasons.append("storage_metric_unknown")
            if target is HomeostasisState.NORMAL:
                target = HomeostasisState.DEGRADED
        elif storage_free < self.policy.critical_storage_mb:
            reasons.append("storage_critical")
            target = HomeostasisState.SAFE_STOP
        elif storage_free < self.policy.degraded_storage_mb:
            reasons.append("storage_degraded")
            if target is HomeostasisState.NORMAL:
                target = HomeostasisState.DEGRADED

        thermal = profile.thermal_celsius
        if thermal is not None:
            if thermal >= self.policy.critical_thermal_celsius:
                reasons.append("thermal_critical")
                target = HomeostasisState.SAFE_STOP
            elif thermal >= self.policy.degraded_thermal_celsius:
                reasons.append("thermal_degraded")
                if target is HomeostasisState.NORMAL:
                    target = HomeostasisState.DEGRADED

        if profile.power_mode == "CRITICAL":
            reasons.append("power_critical")
            target = HomeostasisState.SAFE_STOP
        elif profile.power_mode == "SAVER" and target is HomeostasisState.NORMAL:
            reasons.append("power_saver")
            target = HomeostasisState.DEGRADED

        recovering_from_degraded = (
            self._state in {HomeostasisState.DEGRADED, HomeostasisState.SAFE_STOP}
            and target is HomeostasisState.NORMAL
        )
        if recovering_from_degraded and (
            available_memory is None
            or storage_free is None
            or available_memory < self.policy.recovery_memory_mb
            or storage_free < self.policy.recovery_storage_mb
            or (thermal is not None and thermal >= self.policy.recovery_thermal_celsius)
        ):
            reasons.append("recovery_hysteresis")
            target = HomeostasisState.DEGRADED

        previous = self._state
        if (
            self._ledger_was_corrupt
            and previous is HomeostasisState.SAFE_STOP
            and target is HomeostasisState.NORMAL
        ):
            reasons.append("ledger_recovered_after_health_validation")
            self._ledger_was_corrupt = False
        observed_at = datetime.now(timezone.utc).isoformat()
        decision = HomeostasisDecision(
            previous_state=previous,
            state=target,
            reasons=tuple(reasons or ("healthy",)),
            observed_at=observed_at,
        )
        self._state = target
        if decision.changed:
            self.store.append(decision, profile)
        return decision

    def close(self) -> None:
        self.store.close()


__all__ = [
    "HomeostasisAudit",
    "HomeostasisDecision",
    "HomeostasisEventStore",
    "HomeostasisPolicy",
    "HomeostasisState",
    "LogicalHomeostasisController",
]
