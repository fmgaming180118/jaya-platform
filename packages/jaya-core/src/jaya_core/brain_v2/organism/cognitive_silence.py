"""Pillar 7 — durable Cognitive Silence control plane.

The controller owns the state transition, decision taxonomy (ANSWER, WAIT, ASK,
DECLINE, SAFE_STOP), hysteresis, expiry bounds, zero-model-invocation gating,
and persistence contract. Runtime components must query ``allows()`` or pass
through ``CognitiveSilenceModelGate`` before executing work.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


class SilenceConfigurationError(ValueError):
    """Raised when the configured silence policy is unsafe or inconsistent."""


class SilencePersistenceError(RuntimeError):
    """Raised when durable silence state cannot be read or written safely."""


class SilenceReason(str, Enum):
    OWNER_STOP = "OWNER_STOP"
    RESOURCE_PRESSURE = "RESOURCE_PRESSURE"
    PRIVACY_BOUNDARY = "PRIVACY_BOUNDARY"
    PERMISSION_REVOKED = "PERMISSION_REVOKED"
    IDLE = "IDLE"
    SAFETY_VIOLATION = "SAFETY_VIOLATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    AMBIGUOUS_REQUEST = "AMBIGUOUS_REQUEST"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class WakeSource(str, Enum):
    OWNER_REQUEST = "OWNER_REQUEST"
    RESOURCE_RECOVERED = "RESOURCE_RECOVERED"
    PRIVACY_RELEASED = "PRIVACY_RELEASED"
    PERMISSION_RESTORED = "PERMISSION_RESTORED"
    TASK_RECEIVED = "TASK_RECEIVED"


class CognitiveSilenceAction(str, Enum):
    ANSWER = "ANSWER"
    WAIT = "WAIT"
    ASK = "ASK"
    DECLINE = "DECLINE"
    SAFE_STOP = "SAFE_STOP"


class RuntimeService(str, Enum):
    AUDIT = "audit"
    CANCELLATION = "cancellation"
    CHECKPOINT = "checkpoint"
    HEALTHCHECK = "healthcheck"
    RESOURCE_MONITOR = "resource_monitor"
    PROACTIVE_SCHEDULER = "proactive_scheduler"
    MODEL_GENERATION = "model_generation"
    NETWORK = "network"
    TOOL_EXECUTION = "tool_execution"


_WAKE_POLICY: Mapping[SilenceReason, frozenset[WakeSource]] = {
    SilenceReason.OWNER_STOP: frozenset({WakeSource.OWNER_REQUEST}),
    SilenceReason.RESOURCE_PRESSURE: frozenset(
        {WakeSource.OWNER_REQUEST, WakeSource.RESOURCE_RECOVERED}
    ),
    SilenceReason.PRIVACY_BOUNDARY: frozenset(
        {WakeSource.OWNER_REQUEST, WakeSource.PRIVACY_RELEASED}
    ),
    SilenceReason.PERMISSION_REVOKED: frozenset(
        {WakeSource.OWNER_REQUEST, WakeSource.PERMISSION_RESTORED}
    ),
    SilenceReason.IDLE: frozenset(
        {WakeSource.OWNER_REQUEST, WakeSource.TASK_RECEIVED}
    ),
    SilenceReason.SAFETY_VIOLATION: frozenset(
        {WakeSource.OWNER_REQUEST, WakeSource.PERMISSION_RESTORED}
    ),
    SilenceReason.INSUFFICIENT_EVIDENCE: frozenset(
        {WakeSource.OWNER_REQUEST, WakeSource.TASK_RECEIVED}
    ),
    SilenceReason.AMBIGUOUS_REQUEST: frozenset(
        {WakeSource.OWNER_REQUEST, WakeSource.TASK_RECEIVED}
    ),
    SilenceReason.PROVIDER_UNAVAILABLE: frozenset(
        {WakeSource.OWNER_REQUEST, WakeSource.RESOURCE_RECOVERED}
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class CognitiveSilenceSignals:
    """Standard signals consumed by Cognitive Silence decision evaluation."""

    request_text: str = ""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    battery_percent: float = -1.0
    uncertainty: float = 0.0
    evidence_count: int = 1
    privacy_boundary_active: bool = False
    safety_violation: bool = False
    permission_revoked: bool = False
    provider_available: bool = True
    is_owner_stop: bool = False
    timestamp_utc: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> CognitiveSilenceSignals:
        return cls(
            request_text=str(data.get("request_text", "")),
            cpu_percent=float(data.get("cpu_percent", 0.0)),
            memory_percent=float(data.get("memory_percent", 0.0)),
            battery_percent=float(data.get("battery_percent", -1.0)),
            uncertainty=float(data.get("uncertainty", 0.0)),
            evidence_count=int(data.get("evidence_count", 1)),
            privacy_boundary_active=bool(data.get("privacy_boundary_active", False)),
            safety_violation=bool(data.get("safety_violation", False)),
            permission_revoked=bool(data.get("permission_revoked", False)),
            provider_available=bool(data.get("provider_available", True)),
            is_owner_stop=bool(data.get("is_owner_stop", False)),
            timestamp_utc=str(data.get("timestamp_utc", "")),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "request_text": self.request_text,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "battery_percent": self.battery_percent,
            "uncertainty": self.uncertainty,
            "evidence_count": self.evidence_count,
            "privacy_boundary_active": self.privacy_boundary_active,
            "safety_violation": self.safety_violation,
            "permission_revoked": self.permission_revoked,
            "provider_available": self.provider_available,
            "is_owner_stop": self.is_owner_stop,
            "timestamp_utc": self.timestamp_utc,
        }


@dataclass(frozen=True, slots=True)
class CognitiveSilencePolicy:
    """Validated runtime policy for silence mode and decision boundaries."""

    silence_topk_ratio: float = 0.02
    max_checkpoint_bytes: int = 262_144
    allowed_services: frozenset[RuntimeService] = frozenset(
        {
            RuntimeService.AUDIT,
            RuntimeService.CANCELLATION,
            RuntimeService.CHECKPOINT,
            RuntimeService.HEALTHCHECK,
            RuntimeService.RESOURCE_MONITOR,
        }
    )
    high_cpu_threshold: float = 85.0
    recovery_cpu_threshold: float = 60.0
    high_memory_threshold: float = 90.0
    recovery_memory_threshold: float = 75.0
    low_battery_threshold: float = 12.0
    recovery_battery_threshold: float = 20.0
    max_uncertainty_threshold: float = 0.85
    max_wait_seconds: float = 30.0
    max_ask_seconds: float = 60.0
    stale_signal_threshold_seconds: float = 120.0

    def __post_init__(self) -> None:
        if not 0.0 < self.silence_topk_ratio <= 1.0:
            raise SilenceConfigurationError(
                "silence_topk_ratio must be in the interval (0, 1]"
            )
        if self.max_checkpoint_bytes < 1_024:
            raise SilenceConfigurationError(
                "max_checkpoint_bytes must be at least 1024"
            )
        required = {
            RuntimeService.AUDIT,
            RuntimeService.CANCELLATION,
            RuntimeService.CHECKPOINT,
            RuntimeService.HEALTHCHECK,
        }
        if not required.issubset(self.allowed_services):
            raise SilenceConfigurationError(
                "allowed_services must retain audit, cancellation, checkpoint, and healthcheck"
            )
        forbidden = {
            RuntimeService.PROACTIVE_SCHEDULER,
            RuntimeService.MODEL_GENERATION,
            RuntimeService.NETWORK,
            RuntimeService.TOOL_EXECUTION,
        }
        if forbidden.intersection(self.allowed_services):
            raise SilenceConfigurationError(
                "silence allowlist cannot include scheduler, model, network, or tools"
            )
        if not (0.0 <= self.recovery_cpu_threshold < self.high_cpu_threshold <= 100.0):
            raise SilenceConfigurationError("CPU thresholds and hysteresis margin are invalid")
        if not (0.0 <= self.recovery_memory_threshold < self.high_memory_threshold <= 100.0):
            raise SilenceConfigurationError("Memory thresholds and hysteresis margin are invalid")
        if not (0.0 <= self.low_battery_threshold < self.recovery_battery_threshold <= 100.0):
            raise SilenceConfigurationError("Battery thresholds and hysteresis margin are invalid")
        if not (0.0 < self.max_uncertainty_threshold <= 1.0):
            raise SilenceConfigurationError("max_uncertainty_threshold must be in (0, 1]")
        if self.max_wait_seconds <= 0.0 or self.max_ask_seconds <= 0.0:
            raise SilenceConfigurationError("wait and ask timeouts must be positive")
        if self.stale_signal_threshold_seconds <= 0.0:
            raise SilenceConfigurationError("stale_signal_threshold_seconds must be positive")


@dataclass(frozen=True, slots=True)
class SilenceTransition:
    request_id: str
    previous_active: bool
    active: bool
    reason: SilenceReason | None
    wake_source: WakeSource | None
    observed_at: str
    checkpoint: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "previous_active": self.previous_active,
            "active": self.active,
            "reason": self.reason.value if self.reason else None,
            "wake_source": self.wake_source.value if self.wake_source else None,
            "observed_at": self.observed_at,
            "checkpoint": dict(self.checkpoint),
        }


@dataclass(frozen=True, slots=True)
class CognitiveSilenceDecision:
    """Formal deterministic output of silence policy evaluation."""

    decision_id: str
    action: CognitiveSilenceAction
    reason_code: str
    message: str
    model_allowed: bool
    evaluated_at: str
    expires_at: str | None = None
    max_wait_seconds: float | None = None
    signals_summary: Mapping[str, object] = field(default_factory=dict)
    decision_sha256: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "action": self.action.value,
            "reason_code": self.reason_code,
            "message": self.message,
            "model_allowed": self.model_allowed,
            "evaluated_at": self.evaluated_at,
            "expires_at": self.expires_at,
            "max_wait_seconds": self.max_wait_seconds,
            "signals_summary": dict(self.signals_summary) if self.signals_summary else {},
            "decision_sha256": self.decision_sha256,
        }


class CognitiveSilenceStore:
    """SQLite transition and decision ledger with schema versioning and integrity hashes."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).expanduser().resolve(strict=False)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                str(self.db_path), timeout=5.0, check_same_thread=False
            )
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._migrate()
        except (OSError, sqlite3.Error) as exc:
            raise SilencePersistenceError(
                f"unable to initialize Cognitive Silence store: {exc}"
            ) from exc

    def _migrate(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cognitive_silence_schema (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    version INTEGER NOT NULL
                )
                """
            )
            row = self._connection.execute(
                "SELECT version FROM cognitive_silence_schema WHERE singleton = 1"
            ).fetchone()
            if row is not None and int(row[0]) > self.SCHEMA_VERSION:
                raise SilencePersistenceError(
                    "Cognitive Silence database uses a newer schema"
                )
            self._connection.execute(
                "INSERT OR IGNORE INTO cognitive_silence_schema(singleton, version) VALUES (1, ?)",
                (self.SCHEMA_VERSION,),
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cognitive_silence_transitions (
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL UNIQUE,
                    previous_active INTEGER NOT NULL CHECK (previous_active IN (0, 1)),
                    active INTEGER NOT NULL CHECK (active IN (0, 1)),
                    reason TEXT,
                    wake_source TEXT,
                    observed_at TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cognitive_silence_latest
                ON cognitive_silence_transitions(transition_id DESC)
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cognitive_silence_decisions (
                    decision_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    model_allowed INTEGER NOT NULL CHECK (model_allowed IN (0, 1)),
                    evaluated_at TEXT NOT NULL,
                    expires_at TEXT,
                    max_wait_seconds REAL,
                    signals_json TEXT NOT NULL,
                    decision_sha256 TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cognitive_silence_decisions_time
                ON cognitive_silence_decisions(evaluated_at DESC)
                """
            )

    @staticmethod
    def _digest(values: Iterable[object]) -> str:
        payload = "\x1f".join(str(value) for value in values)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def append(self, transition: SilenceTransition) -> SilenceTransition:
        checkpoint_json = _canonical_json(dict(transition.checkpoint))
        values = (
            transition.request_id,
            int(transition.previous_active),
            int(transition.active),
            transition.reason.value if transition.reason else "",
            transition.wake_source.value if transition.wake_source else "",
            transition.observed_at,
            checkpoint_json,
        )
        digest = self._digest(values)
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO cognitive_silence_transitions (
                        request_id, previous_active, active, reason, wake_source,
                        observed_at, checkpoint_json, event_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (*values, digest),
                )
        except sqlite3.IntegrityError:
            existing = self.by_request_id(transition.request_id)
            if existing is None or existing != transition:
                raise SilencePersistenceError(
                    "duplicate silence request_id has different transition data"
                )
            return existing
        except sqlite3.Error as exc:
            raise SilencePersistenceError(
                f"unable to persist Cognitive Silence transition: {exc}"
            ) from exc
        return transition

    def _decode_row(self, row: tuple[object, ...]) -> SilenceTransition:
        values = row[:7]
        stored_digest = str(row[7])
        if self._digest(values) != stored_digest:
            raise SilencePersistenceError(
                "Cognitive Silence transition integrity check failed"
            )
        try:
            checkpoint = json.loads(str(row[6]))
            if not isinstance(checkpoint, dict):
                raise ValueError("checkpoint is not an object")
            return SilenceTransition(
                request_id=str(row[0]),
                previous_active=bool(row[1]),
                active=bool(row[2]),
                reason=SilenceReason(str(row[3])) if row[3] else None,
                wake_source=WakeSource(str(row[4])) if row[4] else None,
                observed_at=str(row[5]),
                checkpoint=checkpoint,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise SilencePersistenceError(
                "Cognitive Silence transition payload is invalid"
            ) from exc

    def latest(self) -> SilenceTransition | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT request_id, previous_active, active, reason, wake_source,
                       observed_at, checkpoint_json, event_sha256
                FROM cognitive_silence_transitions
                ORDER BY transition_id DESC LIMIT 1
                """
            ).fetchone()
        return self._decode_row(row) if row is not None else None

    def by_request_id(self, request_id: str) -> SilenceTransition | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT request_id, previous_active, active, reason, wake_source,
                       observed_at, checkpoint_json, event_sha256
                FROM cognitive_silence_transitions WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
        return self._decode_row(row) if row is not None else None

    def append_decision(self, decision: CognitiveSilenceDecision) -> CognitiveSilenceDecision:
        signals_json = _canonical_json(dict(decision.signals_summary))
        values = (
            decision.decision_id,
            decision.action.value,
            decision.reason_code,
            decision.message,
            int(decision.model_allowed),
            decision.evaluated_at,
            decision.expires_at or "",
            float(decision.max_wait_seconds) if decision.max_wait_seconds is not None else -1.0,
            signals_json,
        )
        digest = self._digest(values)
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO cognitive_silence_decisions (
                        decision_id, action, reason_code, message, model_allowed,
                        evaluated_at, expires_at, max_wait_seconds, signals_json,
                        decision_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (*values, digest),
                )
        except sqlite3.IntegrityError:
            existing = self.decision_by_id(decision.decision_id)
            if existing is None or existing.decision_id != decision.decision_id:
                raise SilencePersistenceError("duplicate decision_id conflict")
            return existing
        except sqlite3.Error as exc:
            raise SilencePersistenceError(
                f"unable to persist Cognitive Silence decision: {exc}"
            ) from exc
        return decision

    def _decode_decision_row(self, row: tuple[object, ...]) -> CognitiveSilenceDecision:
        values = (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            int(row[4]),
            str(row[5]),
            str(row[6]) if row[6] is not None else "",
            float(row[7]) if row[7] is not None else -1.0,
            str(row[8]),
        )
        stored_digest = str(row[9])
        if self._digest(values) != stored_digest:
            raise SilencePersistenceError("Cognitive Silence decision integrity check failed")
        try:
            signals = json.loads(str(row[8]))
            wait_sec = float(row[7]) if row[7] is not None and float(row[7]) >= 0 else None
            return CognitiveSilenceDecision(
                decision_id=str(row[0]),
                action=CognitiveSilenceAction(str(row[1])),
                reason_code=str(row[2]),
                message=str(row[3]),
                model_allowed=bool(row[4]),
                evaluated_at=str(row[5]),
                expires_at=str(row[6]) if row[6] else None,
                max_wait_seconds=wait_sec,
                signals_summary=signals if isinstance(signals, dict) else {},
                decision_sha256=stored_digest,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise SilencePersistenceError("Cognitive Silence decision payload corrupted") from exc

    def decision_by_id(self, decision_id: str) -> CognitiveSilenceDecision | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT decision_id, action, reason_code, message, model_allowed,
                       evaluated_at, expires_at, max_wait_seconds, signals_json, decision_sha256
                FROM cognitive_silence_decisions WHERE decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
        return self._decode_decision_row(row) if row is not None else None

    def latest_decision(self) -> CognitiveSilenceDecision | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT decision_id, action, reason_code, message, model_allowed,
                       evaluated_at, expires_at, max_wait_seconds, signals_json, decision_sha256
                FROM cognitive_silence_decisions
                ORDER BY rowid DESC LIMIT 1
                """
            ).fetchone()
        return self._decode_decision_row(row) if row is not None else None

    def decision_count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM cognitive_silence_decisions"
            ).fetchone()
            return int(row[0]) if row else 0

    def healthcheck(self) -> dict[str, object]:
        try:
            with self._lock:
                self._connection.execute("SELECT 1").fetchone()
                decisions = self.decision_count()
            return {
                "ok": True,
                "schema_version": self.SCHEMA_VERSION,
                "db_path": str(self.db_path),
                "decisions_count": decisions,
            }
        except sqlite3.Error as exc:
            return {
                "ok": False,
                "schema_version": self.SCHEMA_VERSION,
                "error": str(exc),
            }

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class CognitiveSilenceController:
    """Thread-safe, restart-safe entry/wake policy and decision gate for Cognitive Silence."""

    def __init__(
        self,
        store: CognitiveSilenceStore,
        policy: CognitiveSilencePolicy | None = None,
    ) -> None:
        self.store = store
        self.policy = policy or CognitiveSilencePolicy()
        self._lock = threading.RLock()
        latest = self.store.latest()
        self._active = bool(latest.active) if latest else False
        self._reason = latest.reason if latest and latest.active else None
        self._entered_at = latest.observed_at if latest and latest.active else None
        self._last_transition = latest

        # Hysteresis state
        self._resource_throttled: bool = False
        # Evaluation metrics
        self._total_evaluations: int = 0
        self._avoided_calls: int = 0
        self._actions_count: dict[str, int] = {
            action.value: 0 for action in CognitiveSilenceAction
        }
        self._decision_latencies_ms: list[float] = []

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def current_reason(self) -> SilenceReason | None:
        with self._lock:
            return self._reason

    def allows(self, service: RuntimeService | str) -> bool:
        try:
            normalized = (
                service if isinstance(service, RuntimeService) else RuntimeService(service)
            )
        except ValueError:
            return not self.active
        with self._lock:
            return not self._active or normalized in self.policy.allowed_services

    def enter(
        self,
        reason: SilenceReason | str,
        checkpoint: Mapping[str, object],
        *,
        request_id: str | None = None,
    ) -> dict[str, object]:
        normalized_reason = (
            reason if isinstance(reason, SilenceReason) else SilenceReason(reason)
        )
        normalized_request_id = str(request_id or uuid.uuid4())
        if not normalized_request_id.strip():
            raise ValueError("request_id cannot be empty")
        checkpoint_payload = dict(checkpoint)
        encoded = _canonical_json(checkpoint_payload).encode("utf-8")
        if len(encoded) > self.policy.max_checkpoint_bytes:
            raise ValueError("silence checkpoint exceeds configured size limit")

        with self._lock:
            if self._active:
                return {
                    "ok": True,
                    "changed": False,
                    "active": True,
                    "reason": self._reason.value if self._reason else None,
                    "request_id": (
                        self._last_transition.request_id if self._last_transition else None
                    ),
                }
            transition = SilenceTransition(
                request_id=normalized_request_id,
                previous_active=False,
                active=True,
                reason=normalized_reason,
                wake_source=None,
                observed_at=_utc_now(),
                checkpoint=checkpoint_payload,
            )
            self.store.append(transition)
            self._active = True
            self._reason = normalized_reason
            self._entered_at = transition.observed_at
            self._last_transition = transition
            return {"ok": True, "changed": True, **transition.as_dict()}

    def exit(
        self,
        wake_source: WakeSource | str,
        *,
        request_id: str | None = None,
    ) -> dict[str, object]:
        normalized_source = (
            wake_source if isinstance(wake_source, WakeSource) else WakeSource(wake_source)
        )
        normalized_request_id = str(request_id or uuid.uuid4())
        if not normalized_request_id.strip():
            raise ValueError("request_id cannot be empty")

        with self._lock:
            if not self._active:
                return {
                    "ok": True,
                    "changed": False,
                    "active": False,
                    "wake_source": normalized_source.value,
                }
            reason = self._reason
            if reason is None or normalized_source not in _WAKE_POLICY[reason]:
                return {
                    "ok": False,
                    "changed": False,
                    "active": True,
                    "error": "WAKE_SOURCE_DENIED",
                    "reason": reason.value if reason else None,
                    "wake_source": normalized_source.value,
                }
            transition = SilenceTransition(
                request_id=normalized_request_id,
                previous_active=True,
                active=False,
                reason=reason,
                wake_source=normalized_source,
                observed_at=_utc_now(),
                checkpoint={},
            )
            self.store.append(transition)
            self._active = False
            self._reason = None
            self._entered_at = None
            self._last_transition = transition
            self._resource_throttled = False
            return {"ok": True, "changed": True, **transition.as_dict()}

    def evaluate_decision(
        self,
        signals: CognitiveSilenceSignals | Mapping[str, Any],
        *,
        decision_id: str | None = None,
        persist: bool = True,
    ) -> CognitiveSilenceDecision:
        """Deterministic policy gate returning ANSWER, WAIT, ASK, DECLINE, or SAFE_STOP."""
        import time

        t0 = time.monotonic()
        sig = (
            signals
            if isinstance(signals, CognitiveSilenceSignals)
            else CognitiveSilenceSignals.from_mapping(signals)
        )
        dec_id = str(decision_id or uuid.uuid4())
        now_dt = datetime.now(timezone.utc)
        now_str = now_dt.isoformat()

        action: CognitiveSilenceAction
        reason_code: str
        message: str
        model_allowed: bool
        expires_at: str | None = None
        max_wait_seconds: float | None = None

        with self._lock:
            # 1. Stale signals check
            if sig.timestamp_utc:
                try:
                    ts = datetime.fromisoformat(sig.timestamp_utc)
                    age_seconds = abs((now_dt - ts).total_seconds())
                    if age_seconds > self.policy.stale_signal_threshold_seconds:
                        action = CognitiveSilenceAction.WAIT
                        reason_code = "STALE_SIGNALS_REJECTED"
                        message = f"Signal timestamp age ({age_seconds:.1f}s) exceeds stale threshold ({self.policy.stale_signal_threshold_seconds:.1f}s)"
                        model_allowed = False
                        max_wait_seconds = 10.0
                        expires_at = (now_dt + timedelta(seconds=10.0)).isoformat()
                        return self._finalize_decision(
                            dec_id, action, reason_code, message, model_allowed,
                            now_str, expires_at, max_wait_seconds, sig, persist, t0,
                        )
                except (ValueError, TypeError):
                    pass

            # 2. Explicit owner stop
            if sig.is_owner_stop:
                action = CognitiveSilenceAction.SAFE_STOP
                reason_code = "OWNER_REQUESTED_STOP"
                message = "Execution halted by owner request"
                model_allowed = False
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, None, None, sig, persist, t0,
                )

            # 3. Active silence state check
            if self._active:
                action = CognitiveSilenceAction.SAFE_STOP
                reason_code = f"COGNITIVE_SILENCE_ACTIVE_{self._reason.value if self._reason else 'UNKNOWN'}"
                message = f"System is currently silent due to {self._reason.value if self._reason else 'UNKNOWN'}"
                model_allowed = False
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, None, None, sig, persist, t0,
                )

            # 4. Safety policy violation (fail-closed)
            if sig.safety_violation:
                action = CognitiveSilenceAction.DECLINE
                reason_code = "SAFETY_POLICY_VIOLATION"
                message = "Request declined due to safety policy constraint"
                model_allowed = False
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, None, None, sig, persist, t0,
                )

            # 5. Permission revoked
            if sig.permission_revoked:
                action = CognitiveSilenceAction.DECLINE
                reason_code = "PERMISSION_REVOKED"
                message = "Required capability permissions have been revoked"
                model_allowed = False
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, None, None, sig, persist, t0,
                )

            # 6. Privacy boundary active
            if sig.privacy_boundary_active:
                action = CognitiveSilenceAction.DECLINE
                reason_code = "PRIVACY_BOUNDARY_ACTIVE"
                message = "Operation crosses privacy boundary without explicit consent"
                model_allowed = False
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, None, None, sig, persist, t0,
                )

            # 7. Provider unavailable
            if not sig.provider_available:
                action = CognitiveSilenceAction.WAIT
                reason_code = "PROVIDER_UNAVAILABLE"
                message = "Underlying model/tool provider is unavailable; deferring"
                model_allowed = False
                max_wait_seconds = self.policy.max_wait_seconds
                expires_at = (now_dt + timedelta(seconds=max_wait_seconds)).isoformat()
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, expires_at, max_wait_seconds, sig, persist, t0,
                )

            # 8. Critical battery depletion -> SAFE_STOP
            if 0.0 <= sig.battery_percent <= 5.0:
                action = CognitiveSilenceAction.SAFE_STOP
                reason_code = "BATTERY_CRITICAL_DEPLETION"
                message = f"Battery level ({sig.battery_percent:.1f}%) critically depleted"
                model_allowed = False
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, None, None, sig, persist, t0,
                )

            # 9. Resource Pressure with Hysteresis -> WAIT
            high_load = (
                sig.cpu_percent >= self.policy.high_cpu_threshold
                or sig.memory_percent >= self.policy.high_memory_threshold
                or (0.0 <= sig.battery_percent <= self.policy.low_battery_threshold)
            )
            recovered = (
                sig.cpu_percent < self.policy.recovery_cpu_threshold
                and sig.memory_percent < self.policy.recovery_memory_threshold
                and (
                    sig.battery_percent < 0.0
                    or sig.battery_percent >= self.policy.recovery_battery_threshold
                )
            )

            if high_load:
                self._resource_throttled = True
            elif recovered:
                self._resource_throttled = False

            if self._resource_throttled:
                action = CognitiveSilenceAction.WAIT
                reason_code = "RESOURCE_PRESSURE_THROTTLED"
                message = (
                    f"Resource pressure active (CPU={sig.cpu_percent:.1f}%, "
                    f"RAM={sig.memory_percent:.1f}%, Battery={sig.battery_percent:.1f}%); deferring"
                )
                model_allowed = False
                max_wait_seconds = self.policy.max_wait_seconds
                expires_at = (now_dt + timedelta(seconds=max_wait_seconds)).isoformat()
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, expires_at, max_wait_seconds, sig, persist, t0,
                )

            # 10. Ambiguous / Empty Request -> ASK
            if not sig.request_text.strip():
                action = CognitiveSilenceAction.ASK
                reason_code = "AMBIGUOUS_REQUEST"
                message = "Request input is empty or ambiguous; owner clarification needed"
                model_allowed = False
                max_wait_seconds = self.policy.max_ask_seconds
                expires_at = (now_dt + timedelta(seconds=max_wait_seconds)).isoformat()
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, expires_at, max_wait_seconds, sig, persist, t0,
                )

            # 11. Insufficient Evidence / High Uncertainty -> ASK
            if sig.evidence_count <= 0:
                action = CognitiveSilenceAction.ASK
                reason_code = "INSUFFICIENT_EVIDENCE"
                message = "Zero grounded evidence available for requested reasoning topic"
                model_allowed = False
                max_wait_seconds = self.policy.max_ask_seconds
                expires_at = (now_dt + timedelta(seconds=max_wait_seconds)).isoformat()
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, expires_at, max_wait_seconds, sig, persist, t0,
                )

            if sig.uncertainty >= self.policy.max_uncertainty_threshold:
                action = CognitiveSilenceAction.ASK
                reason_code = "HIGH_UNCERTAINTY"
                message = f"Reasoning uncertainty ({sig.uncertainty:.2f}) exceeds threshold ({self.policy.max_uncertainty_threshold:.2f})"
                model_allowed = False
                max_wait_seconds = self.policy.max_ask_seconds
                expires_at = (now_dt + timedelta(seconds=max_wait_seconds)).isoformat()
                return self._finalize_decision(
                    dec_id, action, reason_code, message, model_allowed,
                    now_str, expires_at, max_wait_seconds, sig, persist, t0,
                )

            # 12. Normal Execution -> ANSWER
            action = CognitiveSilenceAction.ANSWER
            reason_code = "NORMAL_EXECUTION"
            message = "All cognitive regulation, safety, resource, and privacy gates passed"
            model_allowed = True
            return self._finalize_decision(
                dec_id, action, reason_code, message, model_allowed,
                now_str, None, None, sig, persist, t0,
            )

    def _finalize_decision(
        self,
        decision_id: str,
        action: CognitiveSilenceAction,
        reason_code: str,
        message: str,
        model_allowed: bool,
        evaluated_at: str,
        expires_at: str | None,
        max_wait_seconds: float | None,
        signals: CognitiveSilenceSignals,
        persist: bool,
        t0: float,
    ) -> CognitiveSilenceDecision:
        import time

        elapsed_ms = (time.monotonic() - t0) * 1_000.0
        self._total_evaluations += 1
        if not model_allowed:
            self._avoided_calls += 1
        self._actions_count[action.value] = self._actions_count.get(action.value, 0) + 1
        self._decision_latencies_ms.append(elapsed_ms)
        if len(self._decision_latencies_ms) > 1000:
            self._decision_latencies_ms.pop(0)

        summary = signals.as_dict()
        digest_values = (
            decision_id,
            action.value,
            reason_code,
            message,
            int(model_allowed),
            evaluated_at,
            expires_at or "",
            float(max_wait_seconds) if max_wait_seconds is not None else -1.0,
            _canonical_json(summary),
        )
        digest = self.store._digest(digest_values)

        decision = CognitiveSilenceDecision(
            decision_id=decision_id,
            action=action,
            reason_code=reason_code,
            message=message,
            model_allowed=model_allowed,
            evaluated_at=evaluated_at,
            expires_at=expires_at,
            max_wait_seconds=max_wait_seconds,
            signals_summary=summary,
            decision_sha256=digest,
        )
        if persist:
            self.store.append_decision(decision)
        return decision

    def status(self) -> dict[str, object]:
        with self._lock:
            mean_lat = (
                sum(self._decision_latencies_ms) / len(self._decision_latencies_ms)
                if self._decision_latencies_ms
                else 0.0
            )
            return {
                "available": True,
                "active": self._active,
                "reason": self._reason.value if self._reason else None,
                "entered_at": self._entered_at,
                "resource_throttled": self._resource_throttled,
                "allowed_services": sorted(
                    service.value for service in self.policy.allowed_services
                ),
                "last_transition": (
                    self._last_transition.as_dict() if self._last_transition else None
                ),
                "metrics": {
                    "total_evaluations": self._total_evaluations,
                    "avoided_calls": self._avoided_calls,
                    "actions_count": dict(self._actions_count),
                    "mean_latency_ms": round(mean_lat, 3),
                },
                "storage": self.store.healthcheck(),
            }

    def close(self) -> None:
        with self._lock:
            self.store.close()


class CognitiveSilenceModelGate:
    """Zero-model-invocation execution gate wrapping model/tool providers.

    Guarantees that when Cognitive Silence policy selects SILENCE, DECLINE,
    SAFE_STOP, WAIT, or ASK, model/provider invocation count strictly remains 0.
    """

    def __init__(self, controller: CognitiveSilenceController) -> None:
        self.controller = controller
        self.invocations_count: int = 0
        self.avoided_invocations_count: int = 0
        self._lock = threading.RLock()

    def execute(
        self,
        provider_fn: Callable[..., Any],
        signals: CognitiveSilenceSignals | Mapping[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, object]:
        with self._lock:
            decision = self.controller.evaluate_decision(signals)
            if (
                not decision.model_allowed
                or not self.controller.allows(RuntimeService.MODEL_GENERATION)
            ):
                self.avoided_invocations_count += 1
                return {
                    "executed": False,
                    "decision": decision.as_dict(),
                    "error": f"EXECUTION_BLOCKED_{decision.action.value}",
                    "reason_code": decision.reason_code,
                    "message": decision.message,
                    "invocations_count": self.invocations_count,
                }

            result = provider_fn(*args, **kwargs)
            self.invocations_count += 1
            return {
                "executed": True,
                "decision": decision.as_dict(),
                "result": result,
                "invocations_count": self.invocations_count,
            }


__all__ = [
    "CognitiveSilenceAction",
    "CognitiveSilenceController",
    "CognitiveSilenceDecision",
    "CognitiveSilenceModelGate",
    "CognitiveSilencePolicy",
    "CognitiveSilenceSignals",
    "CognitiveSilenceStore",
    "RuntimeService",
    "SilenceConfigurationError",
    "SilencePersistenceError",
    "SilenceReason",
    "SilenceTransition",
    "WakeSource",
]
