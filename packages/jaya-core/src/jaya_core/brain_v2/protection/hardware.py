"""P14 Hardware Locked: node binding without confusing hardware with brain ID.

The legacy UUID helpers remain for compatibility and resource discovery only.
They never grant authority. Production authority is provided by an explicit OS
root provider such as Windows DPAPI machine scope.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import re
import socket
import sqlite3
import subprocess
import threading
import uuid
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

_SCHEMA_VERSION = 1
_STORAGE_SCHEMA_VERSION = 2
_ATTESTATION_PURPOSE = "hardware-binding-v1"
_AUDIT_ATTESTATION_PURPOSE = "hardware-binding-audit-v1"
_ZERO_DIGEST = "0" * 64
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$")


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (TypeError, ValueError) as exc:
        raise HardwareBindingError(
            HardwareBindingFailureCode.CORRUPT_BINDING,
            "node binding contains invalid encoded data",
        ) from exc


class HardwareBindingFailureCode(str, Enum):
    INVALID_INPUT = "HARDWARE_BINDING_INVALID_INPUT"
    PROVIDER_UNAVAILABLE = "HARDWARE_PROVIDER_UNAVAILABLE"
    BINDING_NOT_FOUND = "HARDWARE_BINDING_NOT_FOUND"
    DUPLICATE_BINDING = "HARDWARE_BINDING_DUPLICATE"
    CONCURRENT_MODIFICATION = "HARDWARE_BINDING_CONCURRENT_MODIFICATION"
    NODE_MISMATCH = "HARDWARE_NODE_MISMATCH"
    WRAP_FAILED = "HARDWARE_WRAP_FAILED"
    UNWRAP_FAILED = "HARDWARE_UNWRAP_FAILED"
    SIGNATURE_INVALID = "HARDWARE_SIGNATURE_INVALID"
    BINDING_REVOKED = "HARDWARE_BINDING_REVOKED"
    CORRUPT_BINDING = "HARDWARE_BINDING_CORRUPT"
    AUDIT_CORRUPT = "HARDWARE_AUDIT_CORRUPT"
    STORAGE_ERROR = "HARDWARE_STORAGE_ERROR"


class HardwareBindingError(RuntimeError):
    def __init__(self, code: HardwareBindingFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class BindingState(str, Enum):
    ACTIVE = "ACTIVE"
    MIGRATED = "MIGRATED"
    REVOKED = "REVOKED"


class HardwareRootProvider(Protocol):
    provider_id: str
    hardware_backed: bool

    def available(self) -> bool: ...

    def wrap(self, plaintext: bytes, associated_data: bytes) -> bytes: ...

    def unwrap(self, wrapped: bytes, associated_data: bytes) -> bytes: ...


class WindowsDPAPIMachineProvider:
    """Real Windows machine-scoped DPAPI provider.

    DPAPI provides an OS-managed machine boundary. It is deliberately reported
    as not hardware-backed because TPM backing cannot be inferred from DPAPI.
    """

    provider_id = "windows-dpapi-machine-v1"
    hardware_backed = False

    def __init__(self) -> None:
        try:
            import win32crypt
        except ImportError:
            self._backend = None
        else:
            self._backend = win32crypt

    def available(self) -> bool:
        return platform.system() == "Windows" and self._backend is not None

    def health(self) -> dict[str, object]:
        """Return truthful provider capability data without implying TPM backing."""

        return {
            "provider_id": self.provider_id,
            "provider_available": self.available(),
            "provider_type": "OS_MACHINE_SCOPE",
            "protection_scope": "LOCAL_MACHINE",
            "hardware_backed": self.hardware_backed,
            "hardware_attestation": "BLOCKED_EXTERNAL",
            "backend": "pywin32.win32crypt" if self._backend is not None else None,
        }

    def wrap(self, plaintext: bytes, associated_data: bytes) -> bytes:
        if not self.available():
            raise HardwareBindingError(
                HardwareBindingFailureCode.PROVIDER_UNAVAILABLE,
                "Windows DPAPI machine provider is unavailable",
            )
        try:
            return bytes(
                self._backend.CryptProtectData(  # type: ignore[union-attr]
                    plaintext,
                    "JAYA P14 node binding",
                    hashlib.sha256(associated_data).digest(),
                    None,
                    None,
                    0x4,
                )
            )
        except Exception as exc:
            raise HardwareBindingError(
                HardwareBindingFailureCode.WRAP_FAILED,
                "OS provider could not wrap the node binding secret",
            ) from exc

    def unwrap(self, wrapped: bytes, associated_data: bytes) -> bytes:
        if not self.available():
            raise HardwareBindingError(
                HardwareBindingFailureCode.PROVIDER_UNAVAILABLE,
                "Windows DPAPI machine provider is unavailable",
            )
        try:
            _, plaintext = self._backend.CryptUnprotectData(  # type: ignore[union-attr]
                wrapped,
                hashlib.sha256(associated_data).digest(),
                None,
                None,
                0,
            )
            return bytes(plaintext)
        except Exception as exc:
            raise HardwareBindingError(
                HardwareBindingFailureCode.UNWRAP_FAILED,
                "OS provider could not unwrap the node binding secret",
            ) from exc


@dataclass(frozen=True, slots=True)
class NodeBindingRecord:
    binding_id: str
    brain_id: str
    node_id: str
    provider_id: str
    hardware_backed: bool
    wrapped_secret: str
    state: BindingState
    created_at: str
    previous_binding_id: str | None
    attestation: Mapping[str, object]
    schema_version: int = _SCHEMA_VERSION

    def binding_context(self) -> bytes:
        return _canonical(
            {
                "binding_id": self.binding_id,
                "brain_id": self.brain_id,
                "created_at": self.created_at,
                "hardware_backed": self.hardware_backed,
                "node_id": self.node_id,
                "previous_binding_id": self.previous_binding_id,
                "provider_id": self.provider_id,
                "schema_version": self.schema_version,
            }
        )

    def unsigned_dict(self) -> dict[str, object]:
        return {
            **json.loads(self.binding_context()),
            "state": self.state.value,
            "wrapped_secret": self.wrapped_secret,
        }

    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "attestation": dict(self.attestation)}


@dataclass(frozen=True, slots=True)
class NodeBootReceipt:
    binding_id: str
    brain_id: str
    node_id: str
    instance_id: str
    provider_id: str
    hardware_backed: bool
    challenge_sha256: str
    proof_sha256: str
    verified_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


AttestationSigner = Callable[[str, str], Mapping[str, object]]
AttestationVerifier = Callable[[Mapping[str, object]], bool]


class NodeBindingAuthority:
    """Persistent owner-authorized mapping between one brain and one node."""

    def __init__(
        self,
        db_path: Path | str,
        provider: HardwareRootProvider,
        *,
        attestation_signer: AttestationSigner,
        attestation_verifier: AttestationVerifier,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not provider.available():
            raise HardwareBindingError(
                HardwareBindingFailureCode.PROVIDER_UNAVAILABLE,
                "configured hardware root provider is unavailable",
            )
        path = Path(db_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        self._sign = attestation_signer
        self._verify = attestation_verifier
        self._clock = clock
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._create_schema()
        if not self.audit_chain_valid() and self._audit_count() > 0:
            raise HardwareBindingError(
                HardwareBindingFailureCode.AUDIT_CORRUPT,
                "hardware binding audit chain is corrupt",
            )

    def enroll(self, brain_id: str, node_id: str) -> NodeBindingRecord:
        self._validate_ids(brain_id, node_id)
        record = self._create_record(
            brain_id=brain_id,
            node_id=node_id,
            secret=os.urandom(32),
            previous_binding_id=None,
        )
        with self._atomic("node enrollment could not be persisted"):
            if self._active_row(brain_id) is not None:
                raise HardwareBindingError(
                    HardwareBindingFailureCode.DUPLICATE_BINDING,
                    "brain already has an active node binding",
                )
            self._insert_record(record)
            self._insert_event(
                "NODE_ENROLLED",
                {
                    "binding_id": record.binding_id,
                    "brain_id": brain_id,
                    "node_id": node_id,
                    "provider_id": record.provider_id,
                    "hardware_backed": record.hardware_backed,
                },
            )
        return record

    def authorize_boot(
        self,
        brain_id: str,
        node_id: str,
        challenge: bytes,
    ) -> NodeBootReceipt:
        self._ensure_audit()
        self._validate_ids(brain_id, node_id)
        if not isinstance(challenge, bytes) or len(challenge) < 32:
            raise HardwareBindingError(
                HardwareBindingFailureCode.INVALID_INPUT,
                "boot challenge must contain at least 32 bytes",
            )
        record = self._active_record(brain_id)
        if record.node_id != node_id:
            raise HardwareBindingError(
                HardwareBindingFailureCode.NODE_MISMATCH,
                "active node binding does not match this node",
            )
        secret = self._unwrap(record)
        challenge_digest = hashlib.sha256(challenge).hexdigest()
        proof = hmac.new(
            secret,
            b"JAYA:P14:BOOT:" + challenge,
            hashlib.sha256,
        ).digest()
        receipt = NodeBootReceipt(
            binding_id=record.binding_id,
            brain_id=brain_id,
            node_id=node_id,
            instance_id=f"instance-{uuid.uuid4().hex}",
            provider_id=record.provider_id,
            hardware_backed=record.hardware_backed,
            challenge_sha256=challenge_digest,
            proof_sha256=hashlib.sha256(proof).hexdigest(),
            verified_at=self._utc_now().isoformat(),
        )
        self._record_event("BOOT_AUTHORIZED", receipt.to_dict())
        return receipt

    def binding_key_context(self, brain_id: str, node_id: str) -> bytes:
        """Derive the portable P13 context gated by the active node root.

        The node-bound secret is preserved and rewrapped during an approved
        migration.  The derived context therefore excludes ``node_id`` so an
        authorized target can open the same brain, while a clone still cannot
        obtain the secret from a different OS root.
        """

        record = self._active_record(brain_id)
        if record.node_id != node_id:
            raise HardwareBindingError(
                HardwareBindingFailureCode.NODE_MISMATCH,
                "active node binding does not match this node",
            )
        secret = self._unwrap(record)
        return hmac.new(
            secret,
            f"JAYA:P14:P13:{brain_id}".encode(),
            hashlib.sha256,
        ).digest()

    def migrate(
        self,
        brain_id: str,
        target_node_id: str,
        target_provider: HardwareRootProvider,
    ) -> NodeBindingRecord:
        """Rewrap the binding secret for an explicitly available target root."""

        self._ensure_audit()
        self._validate_ids(brain_id, target_node_id)
        if not target_provider.available():
            raise HardwareBindingError(
                HardwareBindingFailureCode.PROVIDER_UNAVAILABLE,
                "target hardware root provider is unavailable",
            )
        current = self._active_record(brain_id)
        if target_node_id == current.node_id:
            raise HardwareBindingError(
                HardwareBindingFailureCode.INVALID_INPUT,
                "migration target must be a different node",
            )
        secret = self._unwrap(current)
        replacement = self._create_record(
            brain_id=brain_id,
            node_id=target_node_id,
            secret=secret,
            previous_binding_id=current.binding_id,
            provider=target_provider,
        )
        migrated = self._replace_state(current, BindingState.MIGRATED)
        with self._atomic("node binding migration could not be persisted"):
            latest = self._active_record(brain_id)
            if latest.binding_id != current.binding_id:
                raise HardwareBindingError(
                    HardwareBindingFailureCode.CONCURRENT_MODIFICATION,
                    "active node binding changed during migration",
                )
            self._update_record(migrated)
            self._insert_record(replacement)
            self._insert_event(
                "NODE_MIGRATED",
                {
                    "brain_id": brain_id,
                    "previous_binding_id": current.binding_id,
                    "binding_id": replacement.binding_id,
                    "node_id": replacement.node_id,
                    "provider_id": replacement.provider_id,
                },
            )
        return replacement

    def revoke(self, brain_id: str) -> NodeBindingRecord:
        current = self._active_record(brain_id)
        revoked = self._replace_state(current, BindingState.REVOKED)
        with self._atomic("node binding revocation could not be persisted"):
            latest = self._active_record(brain_id)
            if latest.binding_id != current.binding_id:
                raise HardwareBindingError(
                    HardwareBindingFailureCode.CONCURRENT_MODIFICATION,
                    "active node binding changed during revocation",
                )
            self._update_record(revoked)
            self._insert_event(
                "NODE_REVOKED",
                {"brain_id": brain_id, "binding_id": current.binding_id},
            )
        return revoked

    def status(self, brain_id: str | None = None) -> dict[str, object]:
        audit_valid = self.audit_chain_valid()
        record: NodeBindingRecord | None = None
        if brain_id is not None:
            try:
                record = self._active_record(brain_id)
            except HardwareBindingError:
                record = None
        provider_health = getattr(self.provider, "health", None)
        provider_status = (
            dict(provider_health())
            if callable(provider_health)
            else {
                "provider_id": self.provider.provider_id,
                "provider_available": self.provider.available(),
                "hardware_backed": self.provider.hardware_backed,
                "hardware_attestation": (
                    "AVAILABLE" if self.provider.hardware_backed else "BLOCKED_EXTERNAL"
                ),
            }
        )
        return {
            "ready": audit_valid and (record is not None if brain_id else True),
            "provider_id": self.provider.provider_id,
            "provider_available": self.provider.available(),
            "hardware_backed": self.provider.hardware_backed,
            "active_binding_id": record.binding_id if record else None,
            "active_node_id": record.node_id if record else None,
            "audit_chain_valid": audit_valid,
            "audit_attestations_verified": audit_valid,
            "storage_schema_version": _STORAGE_SCHEMA_VERSION,
            "provider_health": provider_status,
        }

    def audit_chain_valid(self) -> bool:
        rows = self._connection.execute(
            """
            SELECT occurred_at, event, payload_json,
                   previous_sha256, event_sha256, attestation_json
            FROM hardware_binding_audit ORDER BY event_id
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

    def _create_record(
        self,
        *,
        brain_id: str,
        node_id: str,
        secret: bytes,
        previous_binding_id: str | None,
        provider: HardwareRootProvider | None = None,
    ) -> NodeBindingRecord:
        active_provider = provider or self.provider
        unsigned = NodeBindingRecord(
            binding_id=f"binding-{uuid.uuid4().hex}",
            brain_id=brain_id,
            node_id=node_id,
            provider_id=active_provider.provider_id,
            hardware_backed=active_provider.hardware_backed,
            wrapped_secret="",
            state=BindingState.ACTIVE,
            created_at=self._utc_now().isoformat(),
            previous_binding_id=previous_binding_id,
            attestation={},
        )
        wrapped = active_provider.wrap(secret, unsigned.binding_context())
        wrapped_record = NodeBindingRecord(
            **{**asdict(unsigned), "wrapped_secret": _encode(wrapped)}
        )
        attestation = dict(self._sign(_ATTESTATION_PURPOSE, wrapped_record.digest()))
        return NodeBindingRecord(**{**asdict(wrapped_record), "attestation": attestation})

    def _unwrap(self, record: NodeBindingRecord) -> bytes:
        self._validate_record(record)
        if record.state is BindingState.REVOKED:
            raise HardwareBindingError(
                HardwareBindingFailureCode.BINDING_REVOKED,
                "node binding has been revoked",
            )
        if record.provider_id != self.provider.provider_id:
            raise HardwareBindingError(
                HardwareBindingFailureCode.NODE_MISMATCH,
                "node binding belongs to a different hardware root provider",
            )
        secret = self.provider.unwrap(_decode(record.wrapped_secret), record.binding_context())
        if len(secret) != 32:
            raise HardwareBindingError(
                HardwareBindingFailureCode.UNWRAP_FAILED,
                "node binding secret has an invalid length",
            )
        return secret

    def _validate_record(self, record: NodeBindingRecord) -> None:
        if (
            record.schema_version != _SCHEMA_VERSION
            or not all(
                _SAFE_ID.fullmatch(value)
                for value in (
                    record.binding_id,
                    record.brain_id,
                    record.node_id,
                    record.provider_id,
                )
            )
            or record.attestation.get("purpose") != _ATTESTATION_PURPOSE
            or record.attestation.get("payload_sha256") != record.digest()
            or not self._verify(record.attestation)
        ):
            raise HardwareBindingError(
                HardwareBindingFailureCode.SIGNATURE_INVALID,
                "node binding DNA attestation is invalid",
            )

    def _active_record(self, brain_id: str) -> NodeBindingRecord:
        row = self._active_row(brain_id)
        if row is None:
            raise HardwareBindingError(
                HardwareBindingFailureCode.BINDING_NOT_FOUND,
                "active node binding does not exist",
            )
        record = self._record_from_row(row)
        self._validate_record(record)
        return record

    def _active_row(self, brain_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM hardware_bindings
            WHERE brain_id = ? AND state = 'ACTIVE'
            """,
            (brain_id,),
        ).fetchone()

    def _record_from_row(self, row: sqlite3.Row) -> NodeBindingRecord:
        try:
            attestation = json.loads(row["attestation_json"])
            record = NodeBindingRecord(
                binding_id=row["binding_id"],
                brain_id=row["brain_id"],
                node_id=row["node_id"],
                provider_id=row["provider_id"],
                hardware_backed=bool(row["hardware_backed"]),
                wrapped_secret=row["wrapped_secret"],
                state=BindingState(row["state"]),
                created_at=row["created_at"],
                previous_binding_id=row["previous_binding_id"],
                attestation=attestation,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HardwareBindingError(
                HardwareBindingFailureCode.CORRUPT_BINDING,
                "node binding record is corrupt",
            ) from exc
        expected = hashlib.sha256(_canonical(record.to_dict())).hexdigest()
        if not hmac.compare_digest(expected, row["row_digest"]):
            raise HardwareBindingError(
                HardwareBindingFailureCode.CORRUPT_BINDING,
                "node binding row digest is invalid",
            )
        return record

    def _replace_state(self, record: NodeBindingRecord, state: BindingState) -> NodeBindingRecord:
        unsigned = NodeBindingRecord(**{**asdict(record), "state": state, "attestation": {}})
        attestation = dict(self._sign(_ATTESTATION_PURPOSE, unsigned.digest()))
        return NodeBindingRecord(**{**asdict(unsigned), "attestation": attestation})

    def _insert_record(self, record: NodeBindingRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO hardware_bindings(
                binding_id, brain_id, node_id, provider_id, hardware_backed,
                wrapped_secret, state, created_at, previous_binding_id,
                attestation_json, row_digest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._record_values(record),
        )

    def _update_record(self, record: NodeBindingRecord) -> None:
        values = self._record_values(record)
        self._connection.execute(
            """
            UPDATE hardware_bindings SET
                brain_id = ?, node_id = ?, provider_id = ?, hardware_backed = ?,
                wrapped_secret = ?, state = ?, created_at = ?,
                previous_binding_id = ?, attestation_json = ?, row_digest = ?
            WHERE binding_id = ?
            """,
            (*values[1:], values[0]),
        )

    @staticmethod
    def _record_values(record: NodeBindingRecord) -> tuple[object, ...]:
        serialized = _canonical(record.to_dict()).decode("utf-8")
        return (
            record.binding_id,
            record.brain_id,
            record.node_id,
            record.provider_id,
            int(record.hardware_backed),
            record.wrapped_secret,
            record.state.value,
            record.created_at,
            record.previous_binding_id,
            _canonical(record.attestation).decode("utf-8"),
            hashlib.sha256(serialized.encode()).hexdigest(),
        )

    def _record_event(self, event: str, payload: Mapping[str, object]) -> None:
        with self._atomic("hardware binding audit event could not be persisted"):
            self._insert_event(event, payload)

    def _insert_event(self, event: str, payload: Mapping[str, object]) -> None:
        occurred = self._utc_now().isoformat()
        row = self._connection.execute(
            """
            SELECT event_sha256 FROM hardware_binding_audit
            ORDER BY event_id DESC LIMIT 1
            """
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
            INSERT INTO hardware_binding_audit(
                occurred_at, event, payload_json,
                previous_sha256, event_sha256, attestation_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                occurred,
                event,
                _canonical(payload).decode("utf-8"),
                previous,
                digest,
                _canonical(attestation).decode("utf-8"),
            ),
        )

    @contextmanager
    def _atomic(self, failure_message: str):
        """Serialize a state transition and its signed audit event."""

        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                yield
                self._connection.commit()
            except HardwareBindingError:
                self._connection.rollback()
                raise
            except sqlite3.Error as exc:
                self._connection.rollback()
                raise HardwareBindingError(
                    HardwareBindingFailureCode.STORAGE_ERROR,
                    failure_message,
                ) from exc
            except BaseException:
                self._connection.rollback()
                raise

    def _ensure_audit(self) -> None:
        if not self.audit_chain_valid():
            raise HardwareBindingError(
                HardwareBindingFailureCode.AUDIT_CORRUPT,
                "hardware binding audit chain is corrupt",
            )

    def _audit_count(self) -> int:
        return int(
            self._connection.execute("SELECT COUNT(*) FROM hardware_binding_audit").fetchone()[0]
        )

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS hardware_bindings(
                    binding_id TEXT PRIMARY KEY,
                    brain_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    hardware_backed INTEGER NOT NULL,
                    wrapped_secret TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    previous_binding_id TEXT,
                    attestation_json TEXT NOT NULL,
                    row_digest TEXT NOT NULL,
                    FOREIGN KEY(previous_binding_id)
                        REFERENCES hardware_bindings(binding_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_hardware_one_active_brain
                ON hardware_bindings(brain_id) WHERE state = 'ACTIVE';
                CREATE TABLE IF NOT EXISTS hardware_binding_audit(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_sha256 TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL UNIQUE,
                    attestation_json TEXT
                );
                CREATE TABLE IF NOT EXISTS hardware_binding_metadata(
                    metadata_key TEXT PRIMARY KEY,
                    metadata_value TEXT NOT NULL
                );
                """
            )
            columns = {
                str(row[1])
                for row in self._connection.execute(
                    "PRAGMA table_info(hardware_binding_audit)"
                ).fetchall()
            }
            if "attestation_json" not in columns:
                self._connection.execute(
                    "ALTER TABLE hardware_binding_audit ADD COLUMN attestation_json TEXT"
                )
        self._authenticate_legacy_audit_rows()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO hardware_binding_metadata(metadata_key, metadata_value)
                VALUES ('storage_schema_version', ?)
                ON CONFLICT(metadata_key) DO UPDATE SET metadata_value = excluded.metadata_value
                """,
                (str(_STORAGE_SCHEMA_VERSION),),
            )

    def _authenticate_legacy_audit_rows(self) -> None:
        rows = self._connection.execute(
            """
            SELECT event_id, occurred_at, event, payload_json,
                   previous_sha256, event_sha256, attestation_json
            FROM hardware_binding_audit ORDER BY event_id
            """
        ).fetchall()
        if not rows or all(row["attestation_json"] for row in rows):
            return
        previous = _ZERO_DIGEST
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise HardwareBindingError(
                    HardwareBindingFailureCode.AUDIT_CORRUPT,
                    "legacy hardware binding audit payload is corrupt",
                ) from exc
            content = {
                "occurred_at": row["occurred_at"],
                "event": row["event"],
                "payload": payload,
                "previous_sha256": row["previous_sha256"],
            }
            digest = hashlib.sha256(_canonical(content)).hexdigest()
            if row["previous_sha256"] != previous or row["event_sha256"] != digest:
                raise HardwareBindingError(
                    HardwareBindingFailureCode.AUDIT_CORRUPT,
                    "legacy hardware binding audit chain is corrupt",
                )
            previous = digest
        with self._connection:
            for row in rows:
                if row["attestation_json"]:
                    continue
                attestation = dict(self._sign(_AUDIT_ATTESTATION_PURPOSE, row["event_sha256"]))
                self._connection.execute(
                    """
                    UPDATE hardware_binding_audit SET attestation_json = ?
                    WHERE event_id = ?
                    """,
                    (_canonical(attestation).decode("utf-8"), row["event_id"]),
                )

    @staticmethod
    def _validate_ids(*values: str) -> None:
        if any(not isinstance(value, str) or not _SAFE_ID.fullmatch(value) for value in values):
            raise HardwareBindingError(
                HardwareBindingFailureCode.INVALID_INPUT,
                "hardware binding identifier is invalid",
            )

    def _utc_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise HardwareBindingError(
                HardwareBindingFailureCode.INVALID_INPUT,
                "hardware binding clock must be timezone-aware",
            )
        return value.astimezone(UTC)


# Compatibility-only resource identity helpers. Never use these for authority.
def _run_command(args: list[str], timeout: float = 1.5) -> str | None:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _probe_native_uuid() -> tuple[str | None, str]:
    system = platform.system()
    if system == "Windows":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            ) as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                if guid and str(guid).strip():
                    return str(guid).strip(), "windows-registry"
        except OSError:
            pass

        output = _run_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID",
            ],
            timeout=5.0,
        )
        return output, "windows-cim"
    if system == "Linux":
        for path in (Path("/etc/machine-id"), Path("/sys/class/dmi/id/product_uuid")):
            try:
                value = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if value:
                return value, str(path)
    if system == "Darwin":
        return _run_command(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"]), "ioreg"
    return None, "unavailable"


def get_system_uuid_with_source() -> tuple[bytes, str]:
    """Return a compatibility fingerprint with explicit non-authority source."""

    value, source = _probe_native_uuid()
    if value is None:
        if os.getenv("JAYA_STRICT_HARDWARE_LOCK", "").strip().casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            raise RuntimeError("native hardware identifier is unavailable in strict mode")
        value = (
            f"{platform.system()}|{platform.release()}|{platform.machine()}|"
            f"{platform.node()}|{socket.gethostname()}"
        )
        source = "fallback-non-authoritative"
    return hashlib.sha3_256(value.encode()).digest(), source


def get_system_uuid() -> bytes:
    return get_system_uuid_with_source()[0]


def get_system_uuid_hex() -> str:
    return get_system_uuid().hex()


__all__ = [
    "BindingState",
    "HardwareBindingError",
    "HardwareBindingFailureCode",
    "HardwareRootProvider",
    "NodeBindingAuthority",
    "NodeBindingRecord",
    "NodeBootReceipt",
    "WindowsDPAPIMachineProvider",
    "get_system_uuid",
    "get_system_uuid_hex",
    "get_system_uuid_with_source",
]
