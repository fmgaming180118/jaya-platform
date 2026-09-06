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
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from jaya_core.security.cryptographic_skin import CryptographicSkin, SealedEnvelope

_SCHEMA_VERSION = 1
_STORAGE_SCHEMA_VERSION = 2
_TARGET_ATTESTATION_PURPOSE = "immune-target-v1"
_INCIDENT_ATTESTATION_PURPOSE = "immune-incident-v1"
_CIRCUIT_ATTESTATION_PURPOSE = "immune-circuit-v1"
_AUDIT_ATTESTATION_PURPOSE = "immune-audit-v1"
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
    QUARANTINE_CORRUPT = "IMMUNE_QUARANTINE_CORRUPT"
    RECOVERY_REJECTED = "IMMUNE_RECOVERY_REJECTED"
    PROBE_TIMEOUT = "IMMUNE_PROBE_TIMEOUT"
    PROBE_FAILED = "IMMUNE_PROBE_FAILED"
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
        dependency_probe_timeout_seconds: float = 5.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
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
        if (
            isinstance(dependency_probe_timeout_seconds, bool)
            or not isinstance(dependency_probe_timeout_seconds, (int, float))
            or not 0.05 <= float(dependency_probe_timeout_seconds) <= 60.0
        ):
            raise ImmuneSystemError(
                ImmuneFailureCode.INVALID_INPUT,
                "dependency probe timeout must be between 0.05 and 60 seconds",
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
        self.dependency_probe_timeout_seconds = float(dependency_probe_timeout_seconds)
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
        if not self._state_authenticated():
            raise ImmuneSystemError(
                ImmuneFailureCode.AUDIT_CORRUPT,
                "immune persistent state authentication failed",
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
        if not target_path.is_file() or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
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
        attestation = dict(self._sign(_TARGET_ATTESTATION_PURPOSE, unsigned.digest()))
        target = IntegrityTarget(**{**asdict(unsigned), "attestation": attestation})
        serialized = _canonical(target.to_dict()).decode()
        with self._atomic("integrity target could not be persisted"):
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
            self._insert_event(
                "TARGET_REGISTERED",
                {
                    "target_id": target_id,
                    "expected_sha256": expected_sha256,
                    "critical": critical,
                },
            )
        return target

    def scan(self, target_id: str) -> SecurityIncident | None:
        with self._lock:
            self._ensure_audit()
            target = self._load_target(target_id)
            path = self._contained(self.data_root / target.relative_path)
            if (
                path.is_file()
                and path.stat().st_size <= self.max_artifact_bytes
                and self._sha256(path) == target.expected_sha256
            ):
                return None
            oversized = path.is_file() and path.stat().st_size > self.max_artifact_bytes
            observed = (
                hashlib.sha256(f"OVERSIZED:{path.stat().st_size}".encode()).hexdigest()
                if oversized
                else self._sha256(path)
                if path.is_file()
                else _ZERO_DIGEST
            )
            incident = self._open_incident(IncidentClass.INTEGRITY_VIOLATION, target_id)
            if incident is None:
                incident = self._create_incident(
                    incident_class=IncidentClass.INTEGRITY_VIOLATION,
                    severity=(
                        IncidentSeverity.CRITICAL if target.critical else IncidentSeverity.HIGH
                    ),
                    source_id=target_id,
                    evidence_sha256=observed,
                    quarantine_path=None,
                )
                with self._atomic("integrity incident could not be persisted"):
                    self._persist_incident(incident)
                    self._insert_event("INCIDENT_OPENED", incident.to_dict())
            if oversized:
                raise ImmuneSystemError(
                    ImmuneFailureCode.ARTIFACT_TOO_LARGE,
                    "unsafe artifact exceeds the quarantine resource limit",
                )
            if path.is_file() and incident.quarantine_path is None:
                quarantine_path = self._quarantine(target, path)
                incident = SecurityIncident(
                    **{**asdict(incident), "quarantine_path": quarantine_path}
                )
                with self._atomic("quarantine state could not be persisted"):
                    self._persist_incident(incident)
                    self._insert_event("ARTIFACT_QUARANTINED", incident.to_dict())
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
        with self._atomic("target recovery could not be persisted"):
            self._persist_incident(resolved)
            self._insert_event("INCIDENT_RESOLVED", resolved.to_dict())
        return resolved

    def record_dependency_failure(
        self,
        dependency_id: str,
        failure_code: str,
    ) -> int:
        self._ensure_audit()
        self._validate_id(dependency_id)
        self._validate_id(failure_code)
        with self._atomic("dependency failure could not be persisted"):
            current = self._load_circuit(dependency_id)
            failures = (int(current["failures"]) if current else 0) + 1
            state = "OPEN" if failures >= self.failure_threshold else "CLOSED"
            self._persist_circuit(
                dependency_id=dependency_id,
                failures=failures,
                state=state,
                last_failure_code=failure_code,
            )
            self._insert_event(
                "DEPENDENCY_FAILURE_RECORDED",
                {
                    "dependency_id": dependency_id,
                    "failure_code_sha256": hashlib.sha256(failure_code.encode()).hexdigest(),
                    "failures": failures,
                    "state": state,
                },
            )
            if (
                state == "OPEN"
                and self._open_incident(IncidentClass.DEPENDENCY_ABUSE, dependency_id) is None
            ):
                incident = self._create_incident(
                    incident_class=IncidentClass.DEPENDENCY_ABUSE,
                    severity=IncidentSeverity.HIGH,
                    source_id=dependency_id,
                    evidence_sha256=hashlib.sha256(failure_code.encode()).hexdigest(),
                    quarantine_path=None,
                )
                self._persist_incident(incident)
                self._insert_event("CIRCUIT_OPENED", incident.to_dict())
        return failures

    def can_execute(self, dependency_id: str) -> bool:
        self._validate_id(dependency_id)
        circuit = self._load_circuit(dependency_id)
        return circuit is None or circuit["state"] != "OPEN"

    def recover_dependency(
        self,
        dependency_id: str,
        health_probe: Callable[[], bool],
    ) -> SecurityIncident:
        if not callable(health_probe):
            raise ImmuneSystemError(
                ImmuneFailureCode.RECOVERY_REJECTED,
                "dependency recovery probe is invalid",
            )
        if self._run_health_probe(health_probe) is not True:
            raise ImmuneSystemError(
                ImmuneFailureCode.RECOVERY_REJECTED,
                "dependency recovery probe did not report healthy",
            )
        incident = self._open_incident(IncidentClass.DEPENDENCY_ABUSE, dependency_id)
        if incident is None:
            raise ImmuneSystemError(
                ImmuneFailureCode.TARGET_NOT_FOUND,
                "open dependency incident does not exist",
            )
        resolved = self._resolve_incident(incident)
        current = self._load_circuit(dependency_id)
        if current is None:
            raise ImmuneSystemError(
                ImmuneFailureCode.TARGET_NOT_FOUND,
                "dependency circuit does not exist",
            )
        with self._atomic("dependency recovery could not be persisted"):
            self._persist_circuit(
                dependency_id=dependency_id,
                failures=0,
                state="CLOSED",
                last_failure_code=str(current["last_failure_code"]),
            )
            self._persist_incident(resolved)
            self._insert_event("CIRCUIT_RECOVERED", resolved.to_dict())
        return resolved

    def safe_stop(self) -> bool:
        return any(
            incident.state is IncidentState.OPEN
            and incident.severity in {IncidentSeverity.HIGH, IncidentSeverity.CRITICAL}
            for incident in self._all_incidents()
        )

    def status(self) -> dict[str, object]:
        incidents = self._all_incidents()
        open_incidents = sum(incident.state is IncidentState.OPEN for incident in incidents)
        quarantined = sum(incident.quarantine_path is not None for incident in incidents)
        audit_valid = self.audit_chain_valid()
        safe_stop = any(
            incident.state is IncidentState.OPEN
            and incident.severity in {IncidentSeverity.HIGH, IncidentSeverity.CRITICAL}
            for incident in incidents
        )
        state_authenticated = self._state_authenticated(
            incidents=incidents, audit_valid=audit_valid
        )
        return {
            "ready": state_authenticated and not safe_stop,
            "safe_stop": safe_stop,
            "open_incidents": open_incidents,
            "quarantined_artifacts": quarantined,
            "audit_chain_valid": audit_valid,
            "state_authenticated": state_authenticated,
            "storage_schema_version": _STORAGE_SCHEMA_VERSION,
            "dependency_failure_threshold": self.failure_threshold,
            "dependency_probe_timeout_seconds": self.dependency_probe_timeout_seconds,
            "metrics": self.security_metrics(),
        }

    def security_metrics(self) -> dict[str, object]:
        """Return sanitized counters suitable for runtime monitoring."""

        incidents: dict[str, int] = {}
        for incident in self._all_incidents():
            key = (
                f"{incident.incident_class.value}:{incident.severity.value}:{incident.state.value}"
            )
            incidents[key] = incidents.get(key, 0) + 1
        circuits: dict[str, int] = {}
        rows = self._connection.execute(
            "SELECT dependency_id FROM immune_circuit_breakers"
        ).fetchall()
        for row in rows:
            circuit = self._load_circuit(str(row["dependency_id"]))
            if circuit is not None:
                state = str(circuit["state"])
                circuits[state] = circuits.get(state, 0) + 1
        return {
            "incidents": incidents,
            "circuits": circuits,
            "audit_events": self._audit_count(),
        }

    def audit_chain_valid(self) -> bool:
        rows = self._connection.execute(
            """
            SELECT occurred_at, event, payload_json,
                   previous_sha256, event_sha256, attestation_json
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
            try:
                attestation = json.loads(row["attestation_json"])
            except (TypeError, json.JSONDecodeError):
                return False
            if (
                row["previous_sha256"] != previous
                or row["event_sha256"] != digest
                or attestation.get("purpose") != _AUDIT_ATTESTATION_PURPOSE
                or attestation.get("payload_sha256") != digest
                or not self._verify(attestation)
            ):
                return False
            previous = digest
        return True

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def open_quarantine(self, incident_id: str) -> bytes:
        """Open a quarantined artifact through its bound P13 envelope."""

        self._validate_id(incident_id)
        row = self._connection.execute(
            "SELECT * FROM immune_incidents WHERE incident_id = ?",
            (incident_id,),
        ).fetchone()
        if row is None:
            raise ImmuneSystemError(
                ImmuneFailureCode.TARGET_NOT_FOUND,
                "quarantine incident does not exist",
            )
        incident = self._incident_from_row(row)
        if incident.quarantine_path is None:
            raise ImmuneSystemError(
                ImmuneFailureCode.TARGET_NOT_FOUND,
                "incident does not contain a quarantined artifact",
            )
        path = self._contained(self.data_root / incident.quarantine_path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            envelope = SealedEnvelope.from_dict(raw)
            if (
                envelope.purpose != "security.quarantine"
                or envelope.subject != f"target:{incident.source_id}"
                or envelope.content_type != "application/octet-stream"
            ):
                raise ValueError("quarantine envelope scope is invalid")
            return self._skin.open(envelope)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            raise ImmuneSystemError(
                ImmuneFailureCode.QUARANTINE_CORRUPT,
                "quarantined artifact failed authenticated open",
            ) from exc

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
            verified = self._skin.open(envelope)
            if payload in destination.read_bytes() or verified != payload:
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
        return incident

    def _resolve_incident(self, incident: SecurityIncident) -> SecurityIncident:
        resolved = SecurityIncident(
            **{
                **asdict(incident),
                "state": IncidentState.RESOLVED,
                "resolved_at": self._utc_now().isoformat(),
            }
        )
        return resolved

    def _persist_incident(self, incident: SecurityIncident) -> None:
        serialized = _canonical(incident.to_dict()).decode()
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        attestation = dict(self._sign(_INCIDENT_ATTESTATION_PURPOSE, digest))
        self._connection.execute(
            """
            INSERT INTO immune_incidents(incident_id, record_json, state,
                                         incident_class, severity, source_id,
                                         quarantine_path, row_digest,
                                         attestation_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(incident_id) DO UPDATE SET
                record_json = excluded.record_json,
                state = excluded.state,
                incident_class = excluded.incident_class,
                severity = excluded.severity,
                source_id = excluded.source_id,
                quarantine_path = excluded.quarantine_path,
                row_digest = excluded.row_digest,
                attestation_json = excluded.attestation_json
            """,
            (
                incident.incident_id,
                serialized,
                incident.state.value,
                incident.incident_class.value,
                incident.severity.value,
                incident.source_id,
                incident.quarantine_path,
                digest,
                _canonical(attestation).decode(),
            ),
        )

    def _open_incident(
        self, incident_class: IncidentClass, source_id: str
    ) -> SecurityIncident | None:
        row = self._connection.execute(
            """
            SELECT * FROM immune_incidents
            WHERE incident_class = ? AND source_id = ? AND state = 'OPEN'
            ORDER BY rowid DESC LIMIT 1
            """,
            (incident_class.value, source_id),
        ).fetchone()
        return self._incident_from_row(row) if row is not None else None

    def _incident_from_row(self, row: sqlite3.Row) -> SecurityIncident:
        digest = hashlib.sha256(row["record_json"].encode()).hexdigest()
        try:
            raw = json.loads(row["record_json"])
            attestation = json.loads(row["attestation_json"])
            incident = SecurityIncident(
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
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ImmuneSystemError(
                ImmuneFailureCode.AUDIT_CORRUPT,
                "immune incident ledger is corrupt",
            ) from exc
        if (
            not hmac.compare_digest(digest, str(row["row_digest"]))
            or row["state"] != incident.state.value
            or row["incident_class"] != incident.incident_class.value
            or row["severity"] != incident.severity.value
            or row["source_id"] != incident.source_id
            or row["quarantine_path"] != incident.quarantine_path
            or attestation.get("purpose") != _INCIDENT_ATTESTATION_PURPOSE
            or attestation.get("payload_sha256") != digest
            or not self._verify(attestation)
        ):
            raise ImmuneSystemError(
                ImmuneFailureCode.AUDIT_CORRUPT,
                "immune incident ledger authentication failed",
            )
        return incident

    def _all_incidents(self) -> list[SecurityIncident]:
        rows = self._connection.execute("SELECT * FROM immune_incidents ORDER BY rowid").fetchall()
        return [self._incident_from_row(row) for row in rows]

    def _persist_circuit(
        self,
        *,
        dependency_id: str,
        failures: int,
        state: str,
        last_failure_code: str,
    ) -> None:
        updated_at = self._utc_now().isoformat()
        record = {
            "dependency_id": dependency_id,
            "failures": failures,
            "last_failure_code": last_failure_code,
            "state": state,
            "updated_at": updated_at,
        }
        digest = hashlib.sha256(_canonical(record)).hexdigest()
        attestation = dict(self._sign(_CIRCUIT_ATTESTATION_PURPOSE, digest))
        self._connection.execute(
            """
            INSERT INTO immune_circuit_breakers(
                dependency_id, failures, state, last_failure_code, updated_at,
                attestation_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(dependency_id) DO UPDATE SET
                failures = excluded.failures,
                state = excluded.state,
                last_failure_code = excluded.last_failure_code,
                updated_at = excluded.updated_at,
                attestation_json = excluded.attestation_json
            """,
            (
                dependency_id,
                failures,
                state,
                last_failure_code,
                updated_at,
                _canonical(attestation).decode(),
            ),
        )

    def _load_circuit(self, dependency_id: str) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT * FROM immune_circuit_breakers WHERE dependency_id = ?",
            (dependency_id,),
        ).fetchone()
        if row is None:
            return None
        record: dict[str, object] = {
            "dependency_id": str(row["dependency_id"]),
            "failures": int(row["failures"]),
            "last_failure_code": str(row["last_failure_code"]),
            "state": str(row["state"]),
            "updated_at": str(row["updated_at"]),
        }
        try:
            attestation = json.loads(row["attestation_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ImmuneSystemError(
                ImmuneFailureCode.AUDIT_CORRUPT,
                "dependency circuit attestation is corrupt",
            ) from exc
        digest = hashlib.sha256(_canonical(record)).hexdigest()
        if (
            record["state"] not in {"OPEN", "CLOSED"}
            or int(record["failures"]) < 0
            or attestation.get("purpose") != _CIRCUIT_ATTESTATION_PURPOSE
            or attestation.get("payload_sha256") != digest
            or not self._verify(attestation)
        ):
            raise ImmuneSystemError(
                ImmuneFailureCode.AUDIT_CORRUPT,
                "dependency circuit authentication failed",
            )
        return record

    def _state_authenticated(
        self,
        *,
        incidents: list[SecurityIncident] | None = None,
        audit_valid: bool | None = None,
    ) -> bool:
        try:
            if audit_valid is False or (audit_valid is None and not self.audit_chain_valid()):
                return False
            if incidents is None:
                self._all_incidents()
            target_rows = self._connection.execute(
                "SELECT target_id FROM immune_targets"
            ).fetchall()
            for row in target_rows:
                self._load_target(str(row["target_id"]))
            circuit_rows = self._connection.execute(
                "SELECT dependency_id FROM immune_circuit_breakers"
            ).fetchall()
            for row in circuit_rows:
                self._load_circuit(str(row["dependency_id"]))
            return True
        except ImmuneSystemError:
            return False

    def _run_health_probe(self, health_probe: Callable[[], bool]) -> bool:
        results: Queue[tuple[bool, object]] = Queue(maxsize=1)

        def invoke() -> None:
            try:
                results.put_nowait((True, health_probe()))
            except Exception as exc:  # noqa: BLE001 - provider boundary
                results.put_nowait((False, exc))

        worker = threading.Thread(
            target=invoke,
            name="jaya-p12-health-probe",
            daemon=True,
        )
        worker.start()
        worker.join(self.dependency_probe_timeout_seconds)
        if worker.is_alive():
            raise ImmuneSystemError(
                ImmuneFailureCode.PROBE_TIMEOUT,
                "dependency recovery probe exceeded its timeout",
            )
        try:
            succeeded, value = results.get_nowait()
        except Empty as exc:
            raise ImmuneSystemError(
                ImmuneFailureCode.PROBE_FAILED,
                "dependency recovery probe did not return a result",
            ) from exc
        if not succeeded:
            raise ImmuneSystemError(
                ImmuneFailureCode.PROBE_FAILED,
                "dependency recovery probe raised an exception",
            ) from value if isinstance(value, BaseException) else None
        return value is True

    def _record_event(self, event: str, payload: Mapping[str, Any]) -> None:
        with self._atomic("immune audit event could not be persisted"):
            self._insert_event(event, payload)

    def _insert_event(self, event: str, payload: Mapping[str, Any]) -> None:
        occurred = self._utc_now().isoformat()
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
        attestation = dict(self._sign(_AUDIT_ATTESTATION_PURPOSE, digest))
        self._connection.execute(
            """
            INSERT INTO immune_audit(occurred_at, event, payload_json,
                                     previous_sha256, event_sha256,
                                     attestation_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                occurred,
                event,
                _canonical(payload).decode(),
                previous,
                digest,
                _canonical(attestation).decode(),
            ),
        )

    @contextmanager
    def _atomic(self, failure_message: str):
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                yield
                self._connection.commit()
            except ImmuneSystemError:
                self._connection.rollback()
                raise
            except sqlite3.Error as exc:
                self._connection.rollback()
                raise ImmuneSystemError(
                    ImmuneFailureCode.STORAGE_ERROR,
                    failure_message,
                ) from exc
            except BaseException:
                self._connection.rollback()
                raise

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
        return int(self._connection.execute("SELECT COUNT(*) FROM immune_audit").fetchone()[0])

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
        return value.astimezone(UTC)

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
                    row_digest TEXT NOT NULL,
                    attestation_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_immune_open_incidents
                ON immune_incidents(state, incident_class, source_id);
                CREATE TABLE IF NOT EXISTS immune_circuit_breakers(
                    dependency_id TEXT PRIMARY KEY,
                    failures INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    last_failure_code TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    attestation_json TEXT
                );
                CREATE TABLE IF NOT EXISTS immune_audit(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_sha256 TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL UNIQUE,
                    attestation_json TEXT
                );
                CREATE TABLE IF NOT EXISTS immune_metadata(
                    metadata_key TEXT PRIMARY KEY,
                    metadata_value TEXT NOT NULL
                );
                """
            )
            for table in (
                "immune_incidents",
                "immune_circuit_breakers",
                "immune_audit",
            ):
                columns = {
                    str(row[1])
                    for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if "attestation_json" not in columns:
                    self._connection.execute(
                        f"ALTER TABLE {table} ADD COLUMN attestation_json TEXT"
                    )
        self._authenticate_legacy_state()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO immune_metadata(metadata_key, metadata_value)
                VALUES ('storage_schema_version', ?)
                ON CONFLICT(metadata_key) DO UPDATE SET metadata_value = excluded.metadata_value
                """,
                (str(_STORAGE_SCHEMA_VERSION),),
            )

    def _authenticate_legacy_state(self) -> None:
        audit_rows = self._connection.execute(
            """
            SELECT event_id, occurred_at, event, payload_json,
                   previous_sha256, event_sha256, attestation_json
            FROM immune_audit ORDER BY event_id
            """
        ).fetchall()
        previous = _ZERO_DIGEST
        for row in audit_rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise ImmuneSystemError(
                    ImmuneFailureCode.AUDIT_CORRUPT,
                    "legacy immune audit payload is corrupt",
                ) from exc
            content = {
                "occurred_at": row["occurred_at"],
                "event": row["event"],
                "payload": payload,
                "previous_sha256": row["previous_sha256"],
            }
            digest = hashlib.sha256(_canonical(content)).hexdigest()
            if row["previous_sha256"] != previous or row["event_sha256"] != digest:
                raise ImmuneSystemError(
                    ImmuneFailureCode.AUDIT_CORRUPT,
                    "legacy immune audit chain is corrupt",
                )
            previous = digest
        with self._connection:
            for row in audit_rows:
                if row["attestation_json"]:
                    continue
                attestation = dict(self._sign(_AUDIT_ATTESTATION_PURPOSE, row["event_sha256"]))
                self._connection.execute(
                    "UPDATE immune_audit SET attestation_json = ? WHERE event_id = ?",
                    (_canonical(attestation).decode(), row["event_id"]),
                )
            incident_rows = self._connection.execute(
                "SELECT incident_id, record_json, row_digest, attestation_json FROM immune_incidents"
            ).fetchall()
            for row in incident_rows:
                digest = hashlib.sha256(row["record_json"].encode()).hexdigest()
                if not hmac.compare_digest(digest, str(row["row_digest"])):
                    raise ImmuneSystemError(
                        ImmuneFailureCode.AUDIT_CORRUPT,
                        "legacy immune incident ledger is corrupt",
                    )
                if row["attestation_json"]:
                    continue
                attestation = dict(self._sign(_INCIDENT_ATTESTATION_PURPOSE, digest))
                self._connection.execute(
                    "UPDATE immune_incidents SET attestation_json = ? WHERE incident_id = ?",
                    (_canonical(attestation).decode(), row["incident_id"]),
                )
            circuit_rows = self._connection.execute(
                "SELECT * FROM immune_circuit_breakers"
            ).fetchall()
            for row in circuit_rows:
                if row["attestation_json"]:
                    continue
                record = {
                    "dependency_id": str(row["dependency_id"]),
                    "failures": int(row["failures"]),
                    "last_failure_code": str(row["last_failure_code"]),
                    "state": str(row["state"]),
                    "updated_at": str(row["updated_at"]),
                }
                digest = hashlib.sha256(_canonical(record)).hexdigest()
                attestation = dict(self._sign(_CIRCUIT_ATTESTATION_PURPOSE, digest))
                self._connection.execute(
                    """
                    UPDATE immune_circuit_breakers SET attestation_json = ?
                    WHERE dependency_id = ?
                    """,
                    (_canonical(attestation).decode(), row["dependency_id"]),
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
