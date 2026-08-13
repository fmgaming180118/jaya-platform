"""P12 Immune System: persistent detection, quarantine, and recovery."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from src.security.cryptographic_skin import CryptographicSkin

_SCHEMA_VERSION = 1
_TARGET_ATTESTATION_PURPOSE = "immune-target-v1"
_ZERO_DIGEST = "0" * 64
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


class ImmuneFailureCode(str, Enum):
    INVALID_INPUT = "IMMUNE_INVALID_INPUT"
    PATH_OUTSIDE_ROOT = "IMMUNE_PATH_OUTSIDE_ROOT"
    TARGET_NOT_FOUND = "IMMUNE_TARGET_NOT_FOUND"
    TARGET_CORRUPT = "IMMUNE_TARGET_CORRUPT"
    ARTIFACT_TOO_LARGE = "IMMUNE_ARTIFACT_TOO_LARGE"
    QUARANTINE_FAILED = "IMMUNE_QUARANTINE_FAILED"
    RECOVERY_REJECTED = "IMMUNE_RECOVERY_REJECTED"
    DEPENDENCY_QUARANTINED = "IMMUNE_DEPENDENCY_QUARANTINED"
    AUDIT_CORRUPT = "IMMUNE_AUDIT_CORRUPT"
    STORAGE_ERROR = "IMMUNE_STORAGE_ERROR"


class ImmuneSystemError(RuntimeError):
    def __init__(self, code: ImmuneFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class IncidentClass(str, Enum):
    INTEGRITY_VIOLATION = "INTEGRITY_VIOLATION"
    DEPENDENCY_ABUSE = "DEPENDENCY_ABUSE"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentState(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True, slots=True)
class IntegrityTarget:
    target_id: str
    relative_path: str
    expected_sha256: str
    critical: bool
    registered_at: str
    attestation: Mapping[str, object]
    schema_version: int = _SCHEMA_VERSION

    def unsigned_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("attestation")
        return value

    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "attestation": dict(self.attestation)}


@dataclass(frozen=True, slots=True)
class SecurityIncident:
    incident_id: str
    incident_class: IncidentClass
    severity: IncidentSeverity
    source_id: str
    evidence_sha256: str
    state: IncidentState
    detected_at: str
    resolved_at: str | None
    quarantine_path: str | None

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["incident_class"] = self.incident_class.value
        value["severity"] = self.severity.value
        value["state"] = self.state.value
        return value


AttestationSigner = Callable[[str, str], Mapping[str, object]]
AttestationVerifier = Callable[[Mapping[str, object]], bool]


class ImmuneSystem:
    """Monitor registered artifacts and isolate failures fail-closed."""

    def __init__(
        self,
        db_path: Path | str,
        data_root: Path | str,
        cryptographic_skin: CryptographicSkin,
        *,
        attestation_signer: AttestationSigner,
        attestation_verifier: AttestationVerifier,
        dependency_failure_threshold: int = 3,
        max_artifact_bytes: int = 16 * 1024 * 1024,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if not 1 <= dependency_failure_threshold <= 100:
            raise ImmuneSystemError(
                ImmuneFailureCode.INVALID_INPUT,
                "dependency failure threshold must be between 1 and 100",
            )
        if not 1 <= max_artifact_bytes <= 64 * 1024 * 1024:
            raise ImmuneSystemError(
                ImmuneFailureCode.INVALID_INPUT,
                "immune artifact limit must be between 1 and 67108864 bytes",
            )
        self.data_root = Path(data_root).resolve()
        if not self.data_root.is_dir():
            raise ImmuneSystemError(
                ImmuneFailureCode.INVALID_INPUT,
                "immune data root must be an existing directory",
            )
        self.quarantine_dir = self.data_root / "quarantine"
        self.quarantine_dir.mkdir(exist_ok=True)
        path = Path(db_path).resolve()
        self._skin = cryptographic_skin
        self._sign = attestation_signer
        self._verify = attestation_verifier
        self._clock = clock
        self.failure_threshold = dependency_failure_threshold
        self.max_artifact_bytes = max_artifact_bytes
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._create_schema()
        if not self.audit_chain_valid() and self._audit_count() > 0:
            raise ImmuneSystemError(
                ImmuneFailureCode.AUDIT_CORRUPT,
                "immune audit chain is corrupt",
            )

    def register_target(
        self,
        target_id: str,
        path: Path | str,
        expected_sha256: str,
        *,
        critical: bool,
    ) -> IntegrityTarget:
        self._validate_id(target_id)
        target_path = self._contained(path)
        if not target_path.is_file() or not re.fullmatch(
            r"[0-9a-f]{64}", expected_sha256
        ):
            raise ImmuneSystemError(
                ImmuneFailureCode.INVALID_INPUT,
                "integrity target or expected digest is invalid",
            )
        if self._sha256(target_path) != expected_sha256:
            raise ImmuneSystemError(
                ImmuneFailureCode.RECOVERY_REJECTED,
                "integrity target does not match its approved digest",
            )
        unsigned = IntegrityTarget(
            target_id=target_id,
            relative_path=target_path.relative_to(self.data_root).as_posix(),
            expected_sha256=expected_sha256,
            critical=critical,
            registered_at=self._utc_now().isoformat(),
            attestation={},
        )
        attestation = dict(
            self._sign(_TARGET_ATTESTATION_PURPOSE, unsigned.digest())
        )
        target = IntegrityTarget(**{**asdict(unsigned), "attestation": attestation})
        serialized = _canonical(target.to_dict()).decode()
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO immune_targets(
                        target_id, record_json, row_digest
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(target_id) DO UPDATE SET
                        record_json = excluded.record_json,
                        row_digest = excluded.row_digest
                    """,
                    (
                        target_id,
                        serialized,
                        hashlib.sha256(serialized.encode()).hexdigest(),
                    ),
                )
        except sqlite3.Error as exc:
            raise ImmuneSystemError(
                ImmuneFailureCode.STORAGE_ERROR,
                "integrity target could not be persisted",
            ) from exc
        self._record_event(
            "TARGET_REGISTERED",
            {
                "target_id": target_id,
                "expected_sha256": expected_sha256,
                "critical": critical,
            },
        )
        return target

    def scan(self, target_id: str) -> SecurityIncident | None:
        self._ensure_audit()
        target = self._load_target(target_id)
        path = self._contained(self.data_root / target.relative_path)
        if path.is_file() and self._sha256(path) == target.expected_sha256:
            return None
        observed = self._sha256(path) if path.is_file() else _ZERO_DIGEST
        existing = self._open_incident(IncidentClass.INTEGRITY_VIOLATION, target_id)
        incident = existing
        if incident is None:
            incident = self._create_incident(
                incident_class=IncidentClass.INTEGRITY_VIOLATION,
                severity=(
                    IncidentSeverity.CRITICAL
                    if target.critical
                    else IncidentSeverity.HIGH
                ),
                source_id=target_id,
                evidence_sha256=observed,
                quarantine_path=None,
            )
            self._record_event("INCIDENT_OPENED", incident.to_dict())
        if path.is_file() and incident.quarantine_path is None:
            quarantine_path = self._quarantine(target, path)
            incident = SecurityIncident(
                **{**asdict(incident), "quarantine_path": quarantine_path}
            )
            self._persist_incident(incident)
            self._record_event("ARTIFACT_QUARANTINED", incident.to_dict())
        return incident

    def recover_target(self, target_id: str) -> SecurityIncident:
        self._ensure_audit()
        target = self._load_target(target_id)
        path = self._contained(self.data_root / target.relative_path)
        if not path.is_file() or self._sha256(path) != target.expected_sha256:
            raise ImmuneSystemError(
                ImmuneFailureCode.RECOVERY_REJECTED,
                "replacement artifact did not pass the approved integrity probe",
            )
        incident = self._open_incident(IncidentClass.INTEGRITY_VIOLATION, target_id)
        if incident is None:
            raise ImmuneSystemError(
                ImmuneFailureCode.TARGET_NOT_FOUND,
                "open integrity incident does not exist",
            )
        resolved = self._resolve_incident(incident)
        self._record_event("INCIDENT_RESOLVED", resolved.to_dict())
        return resolved

    def record_dependency_failure(
        self,
        dependency_id: str,
        failure_code: str,
    ) -> int:
        self._ensure_audit()
        self._validate_id(dependency_id)
        self._validate_id(failure_code)
        with self._connection:
            row = self._connection.execute(
                "SELECT failures FROM immune_circuit_breakers WHERE dependency_id = ?",
                (dependency_id,),
            ).fetchone()
            failures = (int(row[0]) if row else 0) + 1
            state = "OPEN" if failures >= self.failure_threshold else "CLOSED"
            self._connection.execute(
                """
                INSERT INTO immune_circuit_breakers(
                    dependency_id, failures, state, last_failure_code, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(dependency_id) DO UPDATE SET
                    failures = excluded.failures,
                    state = excluded.state,
                    last_failure_code = excluded.last_failure_code,
                    updated_at = excluded.updated_at
                """,
                (
                    dependency_id,
                    failures,
                    state,
                    failure_code,
                    self._utc_now().isoformat(),
                ),
            )
        if state == "OPEN" and self._open_incident(
            IncidentClass.DEPENDENCY_ABUSE, dependency_id
        ) is None:
            incident = self._create_incident(
                incident_class=IncidentClass.DEPENDENCY_ABUSE,
                severity=IncidentSeverity.HIGH,
                source_id=dependency_id,
                evidence_sha256=hashlib.sha256(failure_code.encode()).hexdigest(),
                quarantine_path=None,
            )
            self._record_event("CIRCUIT_OPENED", incident.to_dict())
        return failures

    def can_execute(self, dependency_id: str) -> bool:
        row = self._connection.execute(
            "SELECT state FROM immune_circuit_breakers WHERE dependency_id = ?",
            (dependency_id,),
        ).fetchone()
        return row is None or row[0] != "OPEN"

    def recover_dependency(
        self,
        dependency_id: str,
        health_probe: Callable[[], bool],
    ) -> SecurityIncident:
        if not callable(health_probe) or health_probe() is not True:
            raise ImmuneSystemError(
                ImmuneFailureCode.RECOVERY_REJECTED,
                "dependency recovery probe did not report healthy",
            )
        incident = self._open_incident(
            IncidentClass.DEPENDENCY_ABUSE, dependency_id
        )
        if incident is None:
            raise ImmuneSystemError(
                ImmuneFailureCode.TARGET_NOT_FOUND,
                "open dependency incident does not exist",
            )
        with self._connection:
            self._connection.execute(
                """
                UPDATE immune_circuit_breakers
                SET failures = 0, state = 'CLOSED', updated_at = ?
                WHERE dependency_id = ?
                """,
                (self._utc_now().isoformat(), dependency_id),
            )
        resolved = self._resolve_incident(incident)
        self._record_event("CIRCUIT_RECOVERED", resolved.to_dict())
        return resolved

    def safe_stop(self) -> bool:
        row = self._connection.execute(
            """
            SELECT COUNT(*) FROM immune_incidents
            WHERE state = 'OPEN' AND severity IN ('HIGH', 'CRITICAL')
            """
        ).fetchone()
        return bool(row and int(row[0]) > 0)

    def status(self) -> dict[str, object]:
        open_incidents = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM immune_incidents WHERE state = 'OPEN'"
            ).fetchone()[0]
        )
        quarantined = int(
            self._connection.execute(
                """
                SELECT COUNT(*) FROM immune_incidents
                WHERE quarantine_path IS NOT NULL
                """
            ).fetchone()[0]
        )
        audit_valid = self.audit_chain_valid()
        return {
            "ready": audit_valid and not self.safe_stop(),
            "safe_stop": self.safe_stop(),
            "open_incidents": open_incidents,
            "quarantined_artifacts": quarantined,
            "audit_chain_valid": audit_valid,
            "dependency_failure_threshold": self.failure_threshold,
            "metrics": self.security_metrics(),
        }

    def security_metrics(self) -> dict[str, object]:
        """Return sanitized counters suitable for runtime monitoring."""

        incident_rows = self._connection.execute(
            """
            SELECT incident_class, severity, state, COUNT(*) AS total
            FROM immune_incidents GROUP BY incident_class, severity, state
            """
        ).fetchall()
        circuit_rows = self._connection.execute(
            """
            SELECT state, COUNT(*) AS total
            FROM immune_circuit_breakers GROUP BY state
            """
        ).fetchall()
        return {
            "incidents": {
                f"{row['incident_class']}:{row['severity']}:{row['state']}": int(
                    row["total"]
                )
                for row in incident_rows
            },
            "circuits": {
                str(row["state"]): int(row["total"]) for row in circuit_rows
            },
            "audit_events": self._audit_count(),
        }

    def audit_chain_valid(self) -> bool:
        rows = self._connection.execute(
            """
            SELECT occurred_at, event, payload_json,
                   previous_sha256, event_sha256
            FROM immune_audit ORDER BY event_id
            """
        ).fetchall()
        previous = _ZERO_DIGEST
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                return False
            content = {
                "occurred_at": row["occurred_at"],
                "event": row["event"],
                "payload": payload,
                "previous_sha256": row["previous_sha256"],
            }
            digest = hashlib.sha256(_canonical(content)).hexdigest()
            if row["previous_sha256"] != previous or row["event_sha256"] != digest:
                return False
            previous = digest
        return True

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _quarantine(self, target: IntegrityTarget, path: Path) -> str:
        size = path.stat().st_size
        if size > self.max_artifact_bytes:
            raise ImmuneSystemError(
                ImmuneFailureCode.ARTIFACT_TOO_LARGE,
                "unsafe artifact exceeds the quarantine resource limit",
            )
        temporary_name: str | None = None
        destination: Path | None = None
        try:
            payload = path.read_bytes()
            envelope = self._skin.seal(
                payload,
                purpose="security.quarantine",
                subject=f"target:{target.target_id}",
                content_type="application/octet-stream",
                ttl_seconds=31_536_000,
            )
            target_digest = hashlib.sha256(target.target_id.encode()).hexdigest()[:16]
            destination = self.quarantine_dir / (
                f"{target_digest}-{uuid.uuid4().hex}.jaya-quarantine.json"
            )
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=self.quarantine_dir,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(envelope.to_dict(), handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
            if payload in destination.read_bytes():
                raise OSError("quarantine envelope leaked plaintext")
            path.unlink()
            return destination.relative_to(self.data_root).as_posix()
        except (OSError, RuntimeError) as exc:
            raise ImmuneSystemError(
                ImmuneFailureCode.QUARANTINE_FAILED,
                "unsafe artifact could not be quarantined",
            ) from exc
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)

    def _load_target(self, target_id: str) -> IntegrityTarget:
        self._validate_id(target_id)
        row = self._connection.execute(
            "SELECT record_json, row_digest FROM immune_targets WHERE target_id = ?",
            (target_id,),
        ).fetchone()
        if row is None:
            raise ImmuneSystemError(
                ImmuneFailureCode.TARGET_NOT_FOUND,
                "integrity target does not exist",
            )
        if not hmac.compare_digest(
            hashlib.sha256(row["record_json"].encode()).hexdigest(),
            row["row_digest"],
        ):
            raise ImmuneSystemError(
                ImmuneFailureCode.TARGET_CORRUPT,
                "integrity target row digest is invalid",
            )
        try:
            raw = json.loads(row["record_json"])
            target = IntegrityTarget(
                target_id=raw["target_id"],
                relative_path=raw["relative_path"],
                expected_sha256=raw["expected_sha256"],
                critical=bool(raw["critical"]),
                registered_at=raw["registered_at"],
                attestation=raw["attestation"],
                schema_version=int(raw["schema_version"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ImmuneSystemError(
                ImmuneFailureCode.TARGET_CORRUPT,
                "integrity target record is invalid",
            ) from exc
        if (
            target.schema_version != _SCHEMA_VERSION
            or target.attestation.get("purpose") != _TARGET_ATTESTATION_PURPOSE
            or target.attestation.get("payload_sha256") != target.digest()
            or not self._verify(target.attestation)
        ):
            raise ImmuneSystemError(
                ImmuneFailureCode.TARGET_CORRUPT,
                "integrity target attestation is invalid",
            )
        return target

    def _create_incident(
        self,
        *,
        incident_class: IncidentClass,
        severity: IncidentSeverity,
        source_id: str,
        evidence_sha256: str,
        quarantine_path: str | None,
    ) -> SecurityIncident:
        incident = SecurityIncident(
            incident_id=f"incident-{uuid.uuid4().hex}",
            incident_class=incident_class,
            severity=severity,
            source_id=source_id,
            evidence_sha256=evidence_sha256,
            state=IncidentState.OPEN,
            detected_at=self._utc_now().isoformat(),
            resolved_at=None,
            quarantine_path=quarantine_path,
        )
        self._persist_incident(incident)
        return incident

    def _resolve_incident(self, incident: SecurityIncident) -> SecurityIncident:
        resolved = SecurityIncident(
            **{
                **asdict(incident),
                "state": IncidentState.RESOLVED,
                "resolved_at": self._utc_now().isoformat(),
            }
        )
        self._persist_incident(resolved)
        return resolved

    def _persist_incident(self, incident: SecurityIncident) -> None:
        serialized = _canonical(incident.to_dict()).decode()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO immune_incidents(incident_id, record_json, state,
                                             incident_class, severity, source_id,
                                             quarantine_path, row_digest)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    record_json = excluded.record_json,
                    state = excluded.state,
                    quarantine_path = excluded.quarantine_path,
                    row_digest = excluded.row_digest
                """,
                (
                    incident.incident_id,
                    serialized,
                    incident.state.value,
                    incident.incident_class.value,
                    incident.severity.value,
                    incident.source_id,
                    incident.quarantine_path,
                    hashlib.sha256(serialized.encode()).hexdigest(),
                ),
            )

    def _open_incident(
        self, incident_class: IncidentClass, source_id: str
    ) -> SecurityIncident | None:
        row = self._connection.execute(
            """
            SELECT record_json, row_digest FROM immune_incidents
            WHERE incident_class = ? AND source_id = ? AND state = 'OPEN'
            ORDER BY rowid DESC LIMIT 1
            """,
            (incident_class.value, source_id),
        ).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row["record_json"].encode()).hexdigest() != row["row_digest"]:
            raise ImmuneSystemError(
                ImmuneFailureCode.AUDIT_CORRUPT,
                "immune incident ledger is corrupt",
            )
        raw = json.loads(row["record_json"])
        return SecurityIncident(
            incident_id=raw["incident_id"],
            incident_class=IncidentClass(raw["incident_class"]),
            severity=IncidentSeverity(raw["severity"]),
            source_id=raw["source_id"],
            evidence_sha256=raw["evidence_sha256"],
            state=IncidentState(raw["state"]),
            detected_at=raw["detected_at"],
            resolved_at=raw["resolved_at"],
            quarantine_path=raw["quarantine_path"],
        )

    def _record_event(self, event: str, payload: Mapping[str, Any]) -> None:
        occurred = self._utc_now().isoformat()
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT event_sha256 FROM immune_audit ORDER BY event_id DESC LIMIT 1"
            ).fetchone()
            previous = row[0] if row else _ZERO_DIGEST
            content = {
                "occurred_at": occurred,
                "event": event,
                "payload": dict(payload),
                "previous_sha256": previous,
            }
            digest = hashlib.sha256(_canonical(content)).hexdigest()
            self._connection.execute(
                """
                INSERT INTO immune_audit(occurred_at, event, payload_json,
                                         previous_sha256, event_sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    occurred,
                    event,
                    _canonical(payload).decode(),
                    previous,
                    digest,
                ),
            )

    def _contained(self, path: Path | str) -> Path:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.data_root)
        except ValueError as exc:
            raise ImmuneSystemError(
                ImmuneFailureCode.PATH_OUTSIDE_ROOT,
                "immune target escaped the configured data root",
            ) from exc
        return resolved

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _ensure_audit(self) -> None:
        if not self.audit_chain_valid():
            raise ImmuneSystemError(
                ImmuneFailureCode.AUDIT_CORRUPT,
                "immune audit chain is corrupt",
            )

    def _audit_count(self) -> int:
        return int(
            self._connection.execute("SELECT COUNT(*) FROM immune_audit").fetchone()[0]
        )

    @staticmethod
    def _validate_id(value: str) -> None:
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise ImmuneSystemError(
                ImmuneFailureCode.INVALID_INPUT,
                "immune identifier is invalid",
            )

    def _utc_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ImmuneSystemError(
                ImmuneFailureCode.INVALID_INPUT,
                "immune clock must be timezone-aware",
            )
        return value.astimezone(timezone.utc)

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS immune_targets(
                    target_id TEXT PRIMARY KEY,
                    record_json TEXT NOT NULL,
                    row_digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS immune_incidents(
                    incident_id TEXT PRIMARY KEY,
                    record_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    incident_class TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    quarantine_path TEXT,
                    row_digest TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_immune_open_incidents
                ON immune_incidents(state, incident_class, source_id);
                CREATE TABLE IF NOT EXISTS immune_circuit_breakers(
                    dependency_id TEXT PRIMARY KEY,
                    failures INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    last_failure_code TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS immune_audit(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_sha256 TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL UNIQUE
                );
                """
            )


__all__ = [
    "ImmuneFailureCode",
    "ImmuneSystem",
    "ImmuneSystemError",
    "IncidentClass",
    "IncidentSeverity",
    "IncidentState",
    "IntegrityTarget",
    "SecurityIncident",
]
