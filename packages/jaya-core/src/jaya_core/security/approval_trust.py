"""Persistent approval trust-key lifecycle for P15 Ethical Heart.

The registry stores only public approval keys.  Every install, rotation,
revocation, and recovery event is signed by a separately managed Ed25519
recovery authority and chained to the previous event.  The recovery private
key is never owned by this registry or by Ethical Heart.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_SCHEMA_VERSION = 1
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,191}$")
_SAFE_REASON = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.: /-]{0,255}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "approver_id",
    "generation",
    "action",
    "public_key",
    "reason",
    "occurred_at",
    "previous_event_sha256",
    "signature",
}


def _canonical(value: Mapping[str, Any]) -> bytes:
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
        raise ApprovalTrustError(
            ApprovalTrustFailureCode.INVALID_EVENT,
            "approval trust event contains invalid base64 data",
        ) from exc


class ApprovalTrustAction(str, Enum):
    INSTALL = "INSTALL"
    ROTATE = "ROTATE"
    REVOKE = "REVOKE"
    RECOVER = "RECOVER"


class ApprovalTrustFailureCode(str, Enum):
    INVALID_INPUT = "APPROVAL_TRUST_INVALID_INPUT"
    INVALID_EVENT = "APPROVAL_TRUST_INVALID_EVENT"
    INVALID_SIGNATURE = "APPROVAL_TRUST_INVALID_SIGNATURE"
    CONFLICT = "APPROVAL_TRUST_CONFLICT"
    CORRUPT = "APPROVAL_TRUST_CORRUPT"
    STORAGE_ERROR = "APPROVAL_TRUST_STORAGE_ERROR"


class ApprovalTrustError(RuntimeError):
    """Stable failure raised by the approval trust boundary."""

    def __init__(self, code: ApprovalTrustFailureCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ApprovalTrustEvent:
    schema_version: int
    event_id: str
    approver_id: str
    generation: int
    action: ApprovalTrustAction
    public_key: str | None
    reason: str
    occurred_at: str
    previous_event_sha256: str
    signature: str

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_EVENT,
                "unsupported approval trust event schema",
            )
        if not _SAFE_ID.fullmatch(self.event_id) or not _SAFE_ID.fullmatch(
            self.approver_id
        ):
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_EVENT,
                "approval trust event identity is invalid",
            )
        if type(self.generation) is not int or self.generation <= 0:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_EVENT,
                "approval trust generation must be positive",
            )
        if not isinstance(self.action, ApprovalTrustAction):
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_EVENT,
                "approval trust action is invalid",
            )
        if not _SAFE_REASON.fullmatch(self.reason):
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_EVENT,
                "approval trust reason is invalid",
            )
        try:
            occurred = datetime.fromisoformat(self.occurred_at)
        except ValueError as exc:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_EVENT,
                "approval trust timestamp is invalid",
            ) from exc
        if occurred.tzinfo is None or not _SHA256.fullmatch(
            self.previous_event_sha256
        ):
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_EVENT,
                "approval trust time or chain digest is invalid",
            )
        if self.action is ApprovalTrustAction.REVOKE:
            if self.public_key is not None:
                raise ApprovalTrustError(
                    ApprovalTrustFailureCode.INVALID_EVENT,
                    "revocation must not contain public key material",
                )
        elif self.public_key is None or len(_decode(self.public_key)) != 32:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_EVENT,
                "approval trust public key is invalid",
            )

    def unsigned_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["action"] = self.action.value
        value.pop("signature")
        return value

    def signed_payload(self) -> bytes:
        return _canonical(self.unsigned_dict())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.signed_payload()).hexdigest()

    def to_dict(self) -> dict[str, object]:
        value = self.unsigned_dict()
        value["signature"] = self.signature
        return value


@dataclass(frozen=True, slots=True)
class _ApproverState:
    generation: int
    active: bool
    public_key: bytes | None


class ApprovalTrustRegistry:
    """SQLite-backed, recovery-signed trust registry for human approvers."""

    def __init__(
        self,
        db_path: Path | str,
        recovery_public_key: bytes,
        *,
        storage_timeout_seconds: float = 5.0,
    ) -> None:
        if len(recovery_public_key) != 32:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_INPUT,
                "recovery public key must be a raw Ed25519 key",
            )
        if (
            isinstance(storage_timeout_seconds, bool)
            or not isinstance(storage_timeout_seconds, (int, float))
            or not 0.001 <= float(storage_timeout_seconds) <= 30.0
        ):
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_INPUT,
                "storage timeout must be within 0.001-30 seconds",
            )
        self.database_path = Path(db_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._root_raw = bytes(recovery_public_key)
        self._root = Ed25519PublicKey.from_public_bytes(self._root_raw)
        self._root_fingerprint = hashlib.sha256(self._root_raw).hexdigest()
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                self.database_path,
                check_same_thread=False,
                timeout=float(storage_timeout_seconds),
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._create_schema()
            self._bind_recovery_root()
            self._validated_state()
        except ApprovalTrustError:
            raise
        except sqlite3.Error as exc:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.STORAGE_ERROR,
                "approval trust registry is unavailable",
            ) from exc

    @property
    def recovery_root_fingerprint(self) -> str:
        return self._root_fingerprint

    def prepare_event(
        self,
        *,
        approver_id: str,
        action: ApprovalTrustAction,
        reason: str,
        occurred_at: str,
        signer: Callable[[bytes], bytes],
        public_key: bytes | None = None,
        event_id: str | None = None,
    ) -> ApprovalTrustEvent:
        """Prepare a root-signed lifecycle event without owning the root key."""

        with self._lock:
            states, previous = self._validated_state()
            current = states.get(approver_id)
            generation = self._next_generation(approver_id, action, current)
        encoded_key = _encode(public_key) if public_key is not None else None
        unsigned = ApprovalTrustEvent(
            schema_version=_SCHEMA_VERSION,
            event_id=event_id or f"trust-{uuid.uuid4()}",
            approver_id=approver_id,
            generation=generation,
            action=action,
            public_key=encoded_key,
            reason=reason,
            occurred_at=occurred_at,
            previous_event_sha256=previous,
            signature="",
        )
        try:
            signature = signer(unsigned.signed_payload())
        except Exception as exc:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_SIGNATURE,
                "external approval recovery signer failed",
            ) from exc
        if not isinstance(signature, bytes) or len(signature) != 64:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_SIGNATURE,
                "external approval recovery signer returned invalid data",
            )
        return replace(unsigned, signature=_encode(signature))

    def apply(self, event: ApprovalTrustEvent) -> str:
        """Atomically verify and append one trust lifecycle event."""

        if not isinstance(event, ApprovalTrustEvent):
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_EVENT,
                "approval trust event must be structured",
            )
        self._verify_signature(event)
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                states, previous = self._validated_state()
                if event.previous_event_sha256 != previous:
                    raise ApprovalTrustError(
                        ApprovalTrustFailureCode.CONFLICT,
                        "approval trust event is based on stale state",
                    )
                current = states.get(event.approver_id)
                expected = self._next_generation(
                    event.approver_id,
                    event.action,
                    current,
                )
                if event.generation != expected:
                    raise ApprovalTrustError(
                        ApprovalTrustFailureCode.CONFLICT,
                        "approval trust generation conflicts with current state",
                    )
                self._connection.execute(
                    """
                    INSERT INTO approval_trust_events(
                        event_id, event_json, event_sha256, applied_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        _canonical(event.to_dict()).decode("utf-8"),
                        event.digest,
                        event.occurred_at,
                    ),
                )
                self._connection.commit()
            except ApprovalTrustError:
                self._connection.rollback()
                raise
            except sqlite3.IntegrityError as exc:
                self._connection.rollback()
                raise ApprovalTrustError(
                    ApprovalTrustFailureCode.CONFLICT,
                    "approval trust event already exists",
                ) from exc
            except sqlite3.Error as exc:
                self._connection.rollback()
                raise ApprovalTrustError(
                    ApprovalTrustFailureCode.STORAGE_ERROR,
                    "approval trust event could not be persisted",
                ) from exc
        return event.digest

    def resolve_public_key(self, approver_id: str) -> bytes | None:
        """Return the active key, or None for unknown/revoked approvers."""

        if not _SAFE_ID.fullmatch(approver_id):
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_INPUT,
                "approver id is invalid",
            )
        with self._lock:
            states, _ = self._validated_state()
            state = states.get(approver_id)
        if state is None or not state.active:
            return None
        return state.public_key

    def audit_chain_valid(self) -> bool:
        try:
            with self._lock:
                self._validated_state()
            return True
        except (ApprovalTrustError, sqlite3.Error):
            return False

    def status(self) -> dict[str, object]:
        with self._lock:
            states, previous = self._validated_state()
            row = self._connection.execute(
                "SELECT COUNT(*) FROM approval_trust_events"
            ).fetchone()
        return {
            "schema_version": _SCHEMA_VERSION,
            "recovery_root_sha256": self._root_fingerprint,
            "events": int(row[0]) if row else 0,
            "active_approvers": sum(1 for state in states.values() if state.active),
            "last_event_sha256": previous,
            "audit_chain_valid": True,
        }

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _next_generation(
        approver_id: str,
        action: ApprovalTrustAction,
        current: _ApproverState | None,
    ) -> int:
        if not _SAFE_ID.fullmatch(approver_id):
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_INPUT,
                "approver id is invalid",
            )
        if action is ApprovalTrustAction.INSTALL:
            if current is not None:
                raise ApprovalTrustError(
                    ApprovalTrustFailureCode.CONFLICT,
                    "approver is already installed",
                )
            return 1
        if current is None:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.CONFLICT,
                "approver must be installed before lifecycle changes",
            )
        if action in {ApprovalTrustAction.ROTATE, ApprovalTrustAction.REVOKE}:
            if not current.active:
                raise ApprovalTrustError(
                    ApprovalTrustFailureCode.CONFLICT,
                    "revoked approver requires recovery",
                )
            return current.generation + 1
        if action is ApprovalTrustAction.RECOVER:
            if current.active:
                raise ApprovalTrustError(
                    ApprovalTrustFailureCode.CONFLICT,
                    "active approver cannot be recovered",
                )
            return current.generation + 1
        raise ApprovalTrustError(
            ApprovalTrustFailureCode.INVALID_EVENT,
            "approval trust action is unsupported",
        )

    def _validated_state(self) -> tuple[dict[str, _ApproverState], str]:
        try:
            rows = self._connection.execute(
                "SELECT event_json, event_sha256 FROM approval_trust_events ORDER BY sequence"
            ).fetchall()
        except sqlite3.Error as exc:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.STORAGE_ERROR,
                "approval trust events are unavailable",
            ) from exc
        states: dict[str, _ApproverState] = {}
        previous = "0" * 64
        for row in rows:
            event = self._parse_event(row["event_json"])
            if event.previous_event_sha256 != previous or event.digest != row[
                "event_sha256"
            ]:
                raise ApprovalTrustError(
                    ApprovalTrustFailureCode.CORRUPT,
                    "approval trust event chain is corrupt",
                )
            self._verify_signature(event)
            current = states.get(event.approver_id)
            expected = self._next_generation(event.approver_id, event.action, current)
            if event.generation != expected:
                raise ApprovalTrustError(
                    ApprovalTrustFailureCode.CORRUPT,
                    "approval trust lifecycle is inconsistent",
                )
            states[event.approver_id] = _ApproverState(
                generation=event.generation,
                active=event.action is not ApprovalTrustAction.REVOKE,
                public_key=(
                    _decode(event.public_key) if event.public_key is not None else None
                ),
            )
            previous = event.digest
        return states, previous

    def _verify_signature(self, event: ApprovalTrustEvent) -> None:
        try:
            signature = _decode(event.signature)
            if len(signature) != 64:
                raise ValueError("signature length")
            self._root.verify(signature, event.signed_payload())
        except (InvalidSignature, ValueError) as exc:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.INVALID_SIGNATURE,
                "approval trust event signature is invalid",
            ) from exc

    @staticmethod
    def _parse_event(raw: str) -> ApprovalTrustEvent:
        try:
            value = json.loads(raw)
            if not isinstance(value, dict) or set(value) != _EVENT_FIELDS:
                raise ValueError("schema")
            return ApprovalTrustEvent(
                schema_version=value["schema_version"],
                event_id=value["event_id"],
                approver_id=value["approver_id"],
                generation=value["generation"],
                action=ApprovalTrustAction(value["action"]),
                public_key=value["public_key"],
                reason=value["reason"],
                occurred_at=value["occurred_at"],
                previous_event_sha256=value["previous_event_sha256"],
                signature=value["signature"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.CORRUPT,
                "stored approval trust event is corrupt",
            ) from exc

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS approval_trust_metadata(
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    schema_version INTEGER NOT NULL,
                    recovery_root_sha256 TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approval_trust_events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_json TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                );
                """
            )

    def _bind_recovery_root(self) -> None:
        try:
            with self._connection:
                row = self._connection.execute(
                    "SELECT * FROM approval_trust_metadata WHERE singleton = 1"
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        """
                        INSERT INTO approval_trust_metadata(
                            singleton, schema_version, recovery_root_sha256
                        ) VALUES (1, ?, ?)
                        """,
                        (_SCHEMA_VERSION, self._root_fingerprint),
                    )
                elif (
                    row["schema_version"] != _SCHEMA_VERSION
                    or row["recovery_root_sha256"] != self._root_fingerprint
                ):
                    raise ApprovalTrustError(
                        ApprovalTrustFailureCode.CONFLICT,
                        "approval recovery root does not match persisted registry",
                    )
        except ApprovalTrustError:
            raise
        except sqlite3.Error as exc:
            raise ApprovalTrustError(
                ApprovalTrustFailureCode.STORAGE_ERROR,
                "approval trust metadata is unavailable",
            ) from exc


__all__ = [
    "ApprovalTrustAction",
    "ApprovalTrustError",
    "ApprovalTrustEvent",
    "ApprovalTrustFailureCode",
    "ApprovalTrustRegistry",
]
