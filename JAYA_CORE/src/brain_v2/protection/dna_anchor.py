"""Portable, owner-controlled identity anchor for JAYA Core.

The brain identity is intentionally independent from hardware and node IDs.
Private material lives in an encrypted keystore supplied by the caller; the
SQLite store contains public identity records, one-time challenges, and an
append-only audit chain. Missing or damaged state always fails closed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_SAFE_PURPOSE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_KEYSTORE_AAD = b"jaya-dna-keystore-v1"
_SCHEMA_VERSION = 1


class DNAFailureCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    IDENTITY_ALREADY_ENROLLED = "IDENTITY_ALREADY_ENROLLED"
    IDENTITY_NOT_ENROLLED = "IDENTITY_NOT_ENROLLED"
    IDENTITY_CORRUPT = "IDENTITY_CORRUPT"
    IDENTITY_REVOKED = "IDENTITY_REVOKED"
    KEYSTORE_ALREADY_EXISTS = "KEYSTORE_ALREADY_EXISTS"
    KEYSTORE_UNAVAILABLE = "KEYSTORE_UNAVAILABLE"
    KEYSTORE_DECRYPTION_FAILED = "KEYSTORE_DECRYPTION_FAILED"
    KEYSTORE_MISMATCH = "KEYSTORE_MISMATCH"
    CHALLENGE_INVALID = "CHALLENGE_INVALID"
    CHALLENGE_EXPIRED = "CHALLENGE_EXPIRED"
    REPLAY_DETECTED = "REPLAY_DETECTED"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    STORAGE_ERROR = "STORAGE_ERROR"


class DNAAnchorError(RuntimeError):
    """Typed fail-closed identity error without secret-bearing details."""

    def __init__(self, code: DNAFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class IdentityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ROTATED = "ROTATED"
    REVOKED = "REVOKED"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    except (ValueError, TypeError) as exc:
        raise DNAAnchorError(
            DNAFailureCode.IDENTITY_CORRUPT,
            "identity contains invalid base64 data",
        ) from exc


def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _private_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )


def _fingerprint(public_key: bytes) -> str:
    return hashlib.sha256(public_key).hexdigest()


@dataclass(frozen=True, slots=True)
class BrainIdentityRecord:
    schema_version: int
    brain_id: str
    owner_id: str
    key_version: int
    public_key: str
    previous_key_fingerprint: str | None
    status: IdentityStatus
    created_at: str
    updated_at: str
    record_signature: str
    rotation_proof: str | None = None

    def signed_payload(self) -> bytes:
        return _canonical(
            {
                "schema_version": self.schema_version,
                "brain_id": self.brain_id,
                "owner_id": self.owner_id,
                "key_version": self.key_version,
                "public_key": self.public_key,
                "previous_key_fingerprint": self.previous_key_fingerprint,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        )

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["status"] = self.status.value
        return value

    @property
    def public_key_fingerprint(self) -> str:
        return _fingerprint(_decode(self.public_key))


@dataclass(frozen=True, slots=True)
class IdentityChallenge:
    schema_version: int
    brain_id: str
    purpose: str
    nonce: str
    issued_at: str
    expires_at: str

    def signed_payload(self) -> bytes:
        return _canonical(asdict(self))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IdentityReceipt:
    event: str
    brain_id: str
    owner_id: str
    key_version: int
    occurred_at: str
    public_key_fingerprint: str
    receipt_sha256: str
    signature: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IdentityAttestation:
    """Domain-separated signature over a non-secret artifact digest."""

    schema_version: int
    brain_id: str
    key_version: int
    purpose: str
    payload_sha256: str
    signature: str

    def signed_payload(self) -> bytes:
        return _canonical(
            {
                "schema_version": self.schema_version,
                "brain_id": self.brain_id,
                "key_version": self.key_version,
                "purpose": self.purpose,
                "payload_sha256": self.payload_sha256,
            }
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class EncryptedFileKeyStore:
    """Encrypted local keystore whose unlock secret is injected at runtime."""

    def __init__(self, root: Path | str, unlock_secret: str | bytes) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "dna_private_key.json"
        secret = (
            unlock_secret.encode("utf-8")
            if isinstance(unlock_secret, str)
            else bytes(unlock_secret)
        )
        if len(secret) < 32:
            raise DNAAnchorError(
                DNAFailureCode.INVALID_INPUT,
                "keystore unlock secret must contain at least 32 bytes",
            )
        self._secret = secret
        self._lock = threading.RLock()

    def exists(self) -> bool:
        return self.path.is_file()

    def create(self, private_key: bytes, key_version: int) -> None:
        with self._lock:
            if self.path.exists():
                raise DNAAnchorError(
                    DNAFailureCode.KEYSTORE_ALREADY_EXISTS,
                    "identity keystore already exists",
                )
            self._write(private_key, key_version)

    def replace(self, private_key: bytes, key_version: int) -> None:
        with self._lock:
            if not self.path.is_file():
                raise DNAAnchorError(
                    DNAFailureCode.KEYSTORE_UNAVAILABLE,
                    "identity keystore is unavailable",
                )
            self._write(private_key, key_version)

    def load(self) -> tuple[bytes, int]:
        with self._lock:
            try:
                if self.path.stat().st_size > 65_536:
                    raise DNAAnchorError(
                        DNAFailureCode.KEYSTORE_DECRYPTION_FAILED,
                        "identity keystore exceeds its size limit",
                    )
                envelope = json.loads(self.path.read_text(encoding="utf-8"))
                if envelope.get("schema_version") != _SCHEMA_VERSION:
                    raise ValueError("schema")
                salt = _decode(str(envelope["salt"]))
                nonce = _decode(str(envelope["nonce"]))
                ciphertext = _decode(str(envelope["ciphertext"]))
                key = self._derive_key(salt)
                plaintext = AESGCM(key).decrypt(nonce, ciphertext, _KEYSTORE_AAD)
                payload = json.loads(plaintext.decode("utf-8"))
                private_key = _decode(str(payload["private_key"]))
                key_version = int(payload["key_version"])
                if len(private_key) != 32 or key_version <= 0:
                    raise ValueError("material")
                return private_key, key_version
            except DNAAnchorError:
                raise
            except FileNotFoundError as exc:
                raise DNAAnchorError(
                    DNAFailureCode.KEYSTORE_UNAVAILABLE,
                    "identity keystore is unavailable",
                ) from exc
            except (OSError, KeyError, TypeError, ValueError, InvalidTag) as exc:
                raise DNAAnchorError(
                    DNAFailureCode.KEYSTORE_DECRYPTION_FAILED,
                    "identity keystore cannot be decrypted",
                ) from exc

    def delete(self) -> None:
        with self._lock:
            try:
                self.path.unlink(missing_ok=True)
            except OSError as exc:
                raise DNAAnchorError(
                    DNAFailureCode.KEYSTORE_UNAVAILABLE,
                    "identity keystore cannot be removed",
                ) from exc

    def snapshot(self) -> bytes:
        try:
            return self.path.read_bytes()
        except OSError as exc:
            raise DNAAnchorError(
                DNAFailureCode.KEYSTORE_UNAVAILABLE,
                "identity keystore cannot be snapshotted",
            ) from exc

    def restore(self, encrypted_blob: bytes) -> None:
        with self._lock:
            self._atomic_write(encrypted_blob)

    def _write(self, private_key: bytes, key_version: int) -> None:
        if len(private_key) != 32 or key_version <= 0:
            raise DNAAnchorError(
                DNAFailureCode.INVALID_INPUT,
                "private key material is invalid",
            )
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        payload = _canonical(
            {
                "private_key": _encode(private_key),
                "key_version": key_version,
            }
        )
        ciphertext = AESGCM(self._derive_key(salt)).encrypt(
            nonce,
            payload,
            _KEYSTORE_AAD,
        )
        envelope = _canonical(
            {
                "schema_version": _SCHEMA_VERSION,
                "kdf": "scrypt-n16384-r8-p1",
                "salt": _encode(salt),
                "nonce": _encode(nonce),
                "ciphertext": _encode(ciphertext),
            }
        )
        self._atomic_write(envelope)

    def _atomic_write(self, payload: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".dna-private-key.",
            suffix=".tmp",
            dir=self.root,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        except OSError as exc:
            raise DNAAnchorError(
                DNAFailureCode.KEYSTORE_UNAVAILABLE,
                "identity keystore cannot be persisted",
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

    def _derive_key(self, salt: bytes) -> bytes:
        return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(self._secret)


class DNAAnchor:
    """Persistent portable brain identity with signed lineage and replay guard."""

    def __init__(
        self,
        data_root: Path | str,
        keystore: EncryptedFileKeyStore,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.data_root = Path(data_root).resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.data_root / "dna_identity.db"
        self.keystore = keystore
        self._clock = clock
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                self.database_path,
                check_same_thread=False,
                timeout=5.0,
            )
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._migrate()
        except sqlite3.Error as exc:
            raise DNAAnchorError(
                DNAFailureCode.STORAGE_ERROR,
                "identity storage cannot be initialized",
            ) from exc

    def enroll(self) -> tuple[BrainIdentityRecord, IdentityReceipt]:
        """Create one portable identity; never silently replaces prior state."""
        with self._lock:
            if self._record_count() > 0:
                raise DNAAnchorError(
                    DNAFailureCode.IDENTITY_ALREADY_ENROLLED,
                    "brain identity is already enrolled",
                )
            if self.keystore.exists():
                raise DNAAnchorError(
                    DNAFailureCode.KEYSTORE_ALREADY_EXISTS,
                    "keystore exists without an identity record",
                )
            private_key = Ed25519PrivateKey.generate()
            public = _public_bytes(private_key)
            now = self._clock().astimezone(timezone.utc).isoformat()
            brain_id = f"brain-{uuid.uuid4()}"
            owner_id = f"owner-{uuid.uuid4()}"
            unsigned = BrainIdentityRecord(
                schema_version=_SCHEMA_VERSION,
                brain_id=brain_id,
                owner_id=owner_id,
                key_version=1,
                public_key=_encode(public),
                previous_key_fingerprint=None,
                status=IdentityStatus.ACTIVE,
                created_at=now,
                updated_at=now,
                record_signature="",
            )
            signature = private_key.sign(unsigned.signed_payload())
            record = BrainIdentityRecord(
                **{
                    **unsigned.to_dict(),
                    "status": IdentityStatus.ACTIVE,
                    "record_signature": _encode(signature),
                }
            )
            self.keystore.create(_private_bytes(private_key), 1)
            try:
                with self._connection:
                    self._insert_record(record)
                    receipt = self._append_audit("ENROLLED", record)
            except Exception:
                self.keystore.delete()
                raise
            return record, receipt

    def initialize(self) -> BrainIdentityRecord:
        """Compatibility entrypoint that only loads; enrollment stays explicit."""
        return self.load_identity()

    def load_identity(self) -> BrainIdentityRecord:
        with self._lock:
            record = self._latest_record()
            if record.status is IdentityStatus.REVOKED:
                raise DNAAnchorError(
                    DNAFailureCode.IDENTITY_REVOKED,
                    "brain identity has been revoked",
                )
            self._verify_record(record)
            private_bytes, key_version = self.keystore.load()
            private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
            if key_version != record.key_version or not secrets.compare_digest(
                _public_bytes(private_key),
                _decode(record.public_key),
            ):
                raise DNAAnchorError(
                    DNAFailureCode.KEYSTORE_MISMATCH,
                    "keystore does not belong to the active identity record",
                )
            return record

    def issue_challenge(
        self,
        purpose: str,
        *,
        ttl_seconds: int = 60,
    ) -> IdentityChallenge:
        if not _SAFE_PURPOSE.fullmatch(purpose):
            raise DNAAnchorError(
                DNAFailureCode.INVALID_INPUT,
                "challenge purpose is invalid",
            )
        if not 1 <= ttl_seconds <= 300:
            raise DNAAnchorError(
                DNAFailureCode.INVALID_INPUT,
                "challenge ttl_seconds must be between 1 and 300",
            )
        with self._lock:
            record = self.load_identity()
            issued = self._clock().astimezone(timezone.utc)
            challenge = IdentityChallenge(
                schema_version=_SCHEMA_VERSION,
                brain_id=record.brain_id,
                purpose=purpose,
                nonce=_encode(secrets.token_bytes(32)),
                issued_at=issued.isoformat(),
                expires_at=(issued + timedelta(seconds=ttl_seconds)).isoformat(),
            )
            nonce_hash = hashlib.sha256(_decode(challenge.nonce)).hexdigest()
            try:
                with self._connection:
                    self._connection.execute(
                        """
                        INSERT INTO identity_challenges (
                            nonce_sha256, brain_id, purpose, issued_at, expires_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            nonce_hash,
                            challenge.brain_id,
                            challenge.purpose,
                            challenge.issued_at,
                            challenge.expires_at,
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                raise DNAAnchorError(
                    DNAFailureCode.CHALLENGE_INVALID,
                    "identity challenge nonce collided",
                ) from exc
            except sqlite3.Error as exc:
                raise DNAAnchorError(
                    DNAFailureCode.STORAGE_ERROR,
                    "identity challenge cannot be persisted",
                ) from exc
            return challenge

    def sign_challenge(self, challenge: IdentityChallenge) -> str:
        with self._lock:
            record = self.load_identity()
            if (
                challenge.schema_version != _SCHEMA_VERSION
                or challenge.brain_id != record.brain_id
            ):
                raise DNAAnchorError(
                    DNAFailureCode.CHALLENGE_INVALID,
                    "identity challenge does not belong to this brain",
                )
            private_bytes, _ = self.keystore.load()
            signature = Ed25519PrivateKey.from_private_bytes(private_bytes).sign(
                challenge.signed_payload()
            )
            return _encode(signature)

    def sign_attestation(
        self,
        purpose: str,
        payload_sha256: str,
    ) -> IdentityAttestation:
        """Sign a domain-separated SHA-256 receipt using the active DNA key."""

        if not _SAFE_PURPOSE.fullmatch(purpose) or not re.fullmatch(
            r"[0-9a-f]{64}", payload_sha256
        ):
            raise DNAAnchorError(
                DNAFailureCode.INVALID_INPUT,
                "attestation purpose or payload digest is invalid",
            )
        with self._lock:
            record = self.load_identity()
            private_bytes, key_version = self.keystore.load()
            if key_version != record.key_version:
                raise DNAAnchorError(
                    DNAFailureCode.KEYSTORE_MISMATCH,
                    "keystore cannot sign this identity attestation",
                )
            unsigned = IdentityAttestation(
                schema_version=_SCHEMA_VERSION,
                brain_id=record.brain_id,
                key_version=record.key_version,
                purpose=purpose,
                payload_sha256=payload_sha256,
                signature="",
            )
            signature = Ed25519PrivateKey.from_private_bytes(private_bytes).sign(
                unsigned.signed_payload()
            )
            return IdentityAttestation(
                **{**unsigned.to_dict(), "signature": _encode(signature)}
            )

    def verify_attestation(
        self,
        value: IdentityAttestation | Mapping[str, object],
    ) -> bool:
        """Verify a current or historical DNA attestation against key lineage."""

        try:
            attestation = (
                value
                if isinstance(value, IdentityAttestation)
                else IdentityAttestation(
                    schema_version=int(value["schema_version"]),
                    brain_id=str(value["brain_id"]),
                    key_version=int(value["key_version"]),
                    purpose=str(value["purpose"]),
                    payload_sha256=str(value["payload_sha256"]),
                    signature=str(value["signature"]),
                )
            )
            if (
                attestation.schema_version != _SCHEMA_VERSION
                or not _SAFE_PURPOSE.fullmatch(attestation.purpose)
                or not re.fullmatch(r"[0-9a-f]{64}", attestation.payload_sha256)
            ):
                return False
            record = self._record_for_version(
                attestation.brain_id,
                attestation.key_version,
            )
            self._verify_record(record)
            Ed25519PublicKey.from_public_bytes(_decode(record.public_key)).verify(
                _decode(attestation.signature),
                attestation.signed_payload(),
            )
            return True
        except (
            DNAAnchorError,
            InvalidSignature,
            KeyError,
            TypeError,
            ValueError,
        ):
            return False

    def verify_challenge(
        self,
        challenge: IdentityChallenge,
        signature: str,
    ) -> IdentityReceipt:
        with self._lock:
            record = self.load_identity()
            try:
                nonce_hash = hashlib.sha256(_decode(challenge.nonce)).hexdigest()
                row = self._connection.execute(
                    """
                    SELECT brain_id, purpose, issued_at, expires_at, used_at
                    FROM identity_challenges WHERE nonce_sha256 = ?
                    """,
                    (nonce_hash,),
                ).fetchone()
            except sqlite3.Error as exc:
                raise DNAAnchorError(
                    DNAFailureCode.STORAGE_ERROR,
                    "identity challenge cannot be read",
                ) from exc
            if row is None or tuple(row[:4]) != (
                challenge.brain_id,
                challenge.purpose,
                challenge.issued_at,
                challenge.expires_at,
            ):
                raise DNAAnchorError(
                    DNAFailureCode.CHALLENGE_INVALID,
                    "identity challenge is unknown or was modified",
                )
            if row[4] is not None:
                raise DNAAnchorError(
                    DNAFailureCode.REPLAY_DETECTED,
                    "identity challenge was already consumed",
                )
            expires_at = datetime.fromisoformat(challenge.expires_at)
            if self._clock().astimezone(timezone.utc) >= expires_at:
                raise DNAAnchorError(
                    DNAFailureCode.CHALLENGE_EXPIRED,
                    "identity challenge has expired",
                )
            try:
                Ed25519PublicKey.from_public_bytes(_decode(record.public_key)).verify(
                    _decode(signature), challenge.signed_payload()
                )
            except (InvalidSignature, ValueError) as exc:
                raise DNAAnchorError(
                    DNAFailureCode.SIGNATURE_INVALID,
                    "identity challenge signature is invalid",
                ) from exc
            occurred = self._clock().astimezone(timezone.utc).isoformat()
            try:
                with self._connection:
                    cursor = self._connection.execute(
                        """
                        UPDATE identity_challenges SET used_at = ?
                        WHERE nonce_sha256 = ? AND used_at IS NULL
                        """,
                        (occurred, nonce_hash),
                    )
                    if cursor.rowcount != 1:
                        raise DNAAnchorError(
                            DNAFailureCode.REPLAY_DETECTED,
                            "identity challenge was consumed concurrently",
                        )
                    return self._append_audit("CHALLENGE_VERIFIED", record)
            except DNAAnchorError:
                raise
            except sqlite3.Error as exc:
                raise DNAAnchorError(
                    DNAFailureCode.STORAGE_ERROR,
                    "identity challenge cannot be consumed",
                ) from exc

    def rotate_key(self) -> tuple[BrainIdentityRecord, IdentityReceipt]:
        with self._lock:
            current = self.load_identity()
            old_private_bytes, old_version = self.keystore.load()
            old_private = Ed25519PrivateKey.from_private_bytes(old_private_bytes)
            new_private = Ed25519PrivateKey.generate()
            new_public = _public_bytes(new_private)
            now = self._clock().astimezone(timezone.utc).isoformat()
            unsigned = BrainIdentityRecord(
                schema_version=_SCHEMA_VERSION,
                brain_id=current.brain_id,
                owner_id=current.owner_id,
                key_version=current.key_version + 1,
                public_key=_encode(new_public),
                previous_key_fingerprint=_fingerprint(_decode(current.public_key)),
                status=IdentityStatus.ACTIVE,
                created_at=current.created_at,
                updated_at=now,
                record_signature="",
            )
            payload = unsigned.signed_payload()
            record = BrainIdentityRecord(
                **{
                    **unsigned.to_dict(),
                    "status": IdentityStatus.ACTIVE,
                    "record_signature": _encode(new_private.sign(payload)),
                    "rotation_proof": _encode(old_private.sign(payload)),
                }
            )
            previous_blob = self.keystore.snapshot()
            self.keystore.replace(_private_bytes(new_private), record.key_version)
            try:
                with self._connection:
                    self._set_status(
                        current.brain_id,
                        current.key_version,
                        IdentityStatus.ROTATED,
                    )
                    self._insert_record(record)
                    receipt = self._append_audit("KEY_ROTATED", record)
            except Exception:
                self.keystore.restore(previous_blob)
                if old_version != current.key_version:
                    raise DNAAnchorError(
                        DNAFailureCode.KEYSTORE_MISMATCH,
                        "previous keystore version was inconsistent",
                    )
                raise
            return record, receipt

    def revoke(self, reason: str) -> IdentityReceipt:
        if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 256:
            raise DNAAnchorError(
                DNAFailureCode.INVALID_INPUT,
                "revocation reason must contain 3-256 characters",
            )
        with self._lock:
            record = self.load_identity()
            with self._connection:
                self._set_status(
                    record.brain_id,
                    record.key_version,
                    IdentityStatus.REVOKED,
                )
                receipt = self._append_audit("IDENTITY_REVOKED", record)
            self.keystore.delete()
            return receipt

    def audit_chain_valid(self) -> bool:
        with self._lock:
            try:
                rows = self._connection.execute(
                    """
                    SELECT occurred_at, event, payload_json, previous_sha256,
                           event_sha256, event_signature
                    FROM identity_audit ORDER BY event_id
                    """
                ).fetchall()
            except sqlite3.Error:
                return False
        previous = "0" * 64
        for (
            occurred_at,
            event,
            payload_json,
            stored_previous,
            stored_hash,
            event_signature,
        ) in rows:
            if stored_previous != previous:
                return False
            actual = hashlib.sha256(
                _canonical(
                    {
                        "occurred_at": occurred_at,
                        "event": event,
                        "payload_json": payload_json,
                        "previous_sha256": previous,
                    }
                )
            ).hexdigest()
            if not secrets.compare_digest(actual, stored_hash):
                return False
            try:
                payload = json.loads(payload_json)
                record = self._record_for_version(
                    str(payload["brain_id"]),
                    int(payload["key_version"]),
                )
                Ed25519PublicKey.from_public_bytes(_decode(record.public_key)).verify(
                    _decode(event_signature), bytes.fromhex(stored_hash)
                )
            except (
                DNAAnchorError,
                InvalidSignature,
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                return False
            previous = stored_hash
        return True

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _migrate(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS brain_identity_records (
                    brain_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    key_version INTEGER NOT NULL,
                    public_key TEXT NOT NULL,
                    previous_key_fingerprint TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    record_signature TEXT NOT NULL,
                    rotation_proof TEXT,
                    row_sha256 TEXT NOT NULL,
                    PRIMARY KEY (brain_id, key_version)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS identity_challenges (
                    nonce_sha256 TEXT PRIMARY KEY,
                    brain_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS identity_audit (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_sha256 TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL,
                    event_signature TEXT NOT NULL
                )
                """
            )
            audit_columns = {
                str(row[1])
                for row in self._connection.execute(
                    "PRAGMA table_info(identity_audit)"
                ).fetchall()
            }
            if "event_signature" not in audit_columns:
                self._connection.execute(
                    """
                    ALTER TABLE identity_audit
                    ADD COLUMN event_signature TEXT NOT NULL DEFAULT ''
                    """
                )

    def _record_count(self) -> int:
        try:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM brain_identity_records"
            ).fetchone()
        except sqlite3.Error as exc:
            raise DNAAnchorError(
                DNAFailureCode.STORAGE_ERROR,
                "identity records cannot be counted",
            ) from exc
        return int(row[0])

    def _latest_record(self) -> BrainIdentityRecord:
        try:
            row = self._connection.execute(
                """
                SELECT brain_id, owner_id, key_version, public_key,
                       previous_key_fingerprint, status, created_at, updated_at,
                       record_signature, rotation_proof, row_sha256
                FROM brain_identity_records
                ORDER BY key_version DESC LIMIT 1
                """
            ).fetchone()
        except sqlite3.Error as exc:
            raise DNAAnchorError(
                DNAFailureCode.STORAGE_ERROR,
                "identity record cannot be loaded",
            ) from exc
        if row is None:
            raise DNAAnchorError(
                DNAFailureCode.IDENTITY_NOT_ENROLLED,
                "brain identity has not been enrolled",
            )
        record = BrainIdentityRecord(
            schema_version=_SCHEMA_VERSION,
            brain_id=str(row[0]),
            owner_id=str(row[1]),
            key_version=int(row[2]),
            public_key=str(row[3]),
            previous_key_fingerprint=row[4],
            status=IdentityStatus(str(row[5])),
            created_at=str(row[6]),
            updated_at=str(row[7]),
            record_signature=str(row[8]),
            rotation_proof=row[9],
        )
        if not secrets.compare_digest(self._row_digest(record), str(row[10])):
            raise DNAAnchorError(
                DNAFailureCode.IDENTITY_CORRUPT,
                "identity record digest mismatch",
            )
        return record

    def _verify_record(self, record: BrainIdentityRecord) -> None:
        if record.schema_version != _SCHEMA_VERSION or record.key_version <= 0:
            raise DNAAnchorError(
                DNAFailureCode.IDENTITY_CORRUPT,
                "identity record schema is invalid",
            )
        try:
            public_key = Ed25519PublicKey.from_public_bytes(_decode(record.public_key))
            public_key.verify(
                _decode(record.record_signature),
                record.signed_payload(),
            )
        except (InvalidSignature, ValueError) as exc:
            raise DNAAnchorError(
                DNAFailureCode.IDENTITY_CORRUPT,
                "identity record signature is invalid",
            ) from exc
        if record.key_version > 1:
            previous = self._record_for_version(
                record.brain_id,
                record.key_version - 1,
            )
            if not secrets.compare_digest(
                record.previous_key_fingerprint or "",
                _fingerprint(_decode(previous.public_key)),
            ):
                raise DNAAnchorError(
                    DNAFailureCode.IDENTITY_CORRUPT,
                    "identity key lineage fingerprint is invalid",
                )
            try:
                Ed25519PublicKey.from_public_bytes(_decode(previous.public_key)).verify(
                    _decode(record.rotation_proof or ""),
                    record.signed_payload(),
                )
            except (InvalidSignature, ValueError) as exc:
                raise DNAAnchorError(
                    DNAFailureCode.IDENTITY_CORRUPT,
                    "identity rotation proof is invalid",
                ) from exc

    def _record_for_version(
        self,
        brain_id: str,
        key_version: int,
    ) -> BrainIdentityRecord:
        row = self._connection.execute(
            """
            SELECT owner_id, public_key, previous_key_fingerprint, status,
                   created_at, updated_at, record_signature, rotation_proof,
                   row_sha256
            FROM brain_identity_records
            WHERE brain_id = ? AND key_version = ?
            """,
            (brain_id, key_version),
        ).fetchone()
        if row is None:
            raise DNAAnchorError(
                DNAFailureCode.IDENTITY_CORRUPT,
                "identity lineage record is missing",
            )
        record = BrainIdentityRecord(
            schema_version=_SCHEMA_VERSION,
            brain_id=brain_id,
            owner_id=str(row[0]),
            key_version=key_version,
            public_key=str(row[1]),
            previous_key_fingerprint=row[2],
            status=IdentityStatus(str(row[3])),
            created_at=str(row[4]),
            updated_at=str(row[5]),
            record_signature=str(row[6]),
            rotation_proof=row[7],
        )
        if not secrets.compare_digest(self._row_digest(record), str(row[8])):
            raise DNAAnchorError(
                DNAFailureCode.IDENTITY_CORRUPT,
                "identity lineage digest mismatch",
            )
        return record

    def _insert_record(self, record: BrainIdentityRecord) -> None:
        try:
            self._connection.execute(
                """
                INSERT INTO brain_identity_records (
                    brain_id, owner_id, key_version, public_key,
                    previous_key_fingerprint, status, created_at, updated_at,
                    record_signature, rotation_proof, row_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.brain_id,
                    record.owner_id,
                    record.key_version,
                    record.public_key,
                    record.previous_key_fingerprint,
                    record.status.value,
                    record.created_at,
                    record.updated_at,
                    record.record_signature,
                    record.rotation_proof,
                    self._row_digest(record),
                ),
            )
        except sqlite3.Error as exc:
            raise DNAAnchorError(
                DNAFailureCode.STORAGE_ERROR,
                "identity record cannot be persisted",
            ) from exc

    def _set_status(
        self,
        brain_id: str,
        key_version: int,
        status: IdentityStatus,
    ) -> None:
        record = self._record_for_version(brain_id, key_version)
        changed = BrainIdentityRecord(**{**record.to_dict(), "status": status})
        cursor = self._connection.execute(
            """
            UPDATE brain_identity_records SET status = ?, row_sha256 = ?
            WHERE brain_id = ? AND key_version = ?
            """,
            (
                status.value,
                self._row_digest(changed),
                brain_id,
                key_version,
            ),
        )
        if cursor.rowcount != 1:
            raise DNAAnchorError(
                DNAFailureCode.STORAGE_ERROR,
                "identity status cannot be updated",
            )

    def _append_audit(
        self,
        event: str,
        record: BrainIdentityRecord,
    ) -> IdentityReceipt:
        occurred_at = self._clock().astimezone(timezone.utc).isoformat()
        payload = {
            "brain_id": record.brain_id,
            "owner_id": record.owner_id,
            "key_version": record.key_version,
            "public_key_fingerprint": _fingerprint(_decode(record.public_key)),
        }
        payload_json = _canonical(payload).decode("utf-8")
        row = self._connection.execute(
            "SELECT event_sha256 FROM identity_audit ORDER BY event_id DESC LIMIT 1"
        ).fetchone()
        previous = str(row[0]) if row else "0" * 64
        event_sha256 = hashlib.sha256(
            _canonical(
                {
                    "occurred_at": occurred_at,
                    "event": event,
                    "payload_json": payload_json,
                    "previous_sha256": previous,
                }
            )
        ).hexdigest()
        private_key_bytes, key_version = self.keystore.load()
        if key_version != record.key_version:
            raise DNAAnchorError(
                DNAFailureCode.KEYSTORE_MISMATCH,
                "keystore cannot sign this identity audit event",
            )
        event_signature = _encode(
            Ed25519PrivateKey.from_private_bytes(private_key_bytes).sign(
                bytes.fromhex(event_sha256)
            )
        )
        self._connection.execute(
            """
            INSERT INTO identity_audit (
                occurred_at, event, payload_json, previous_sha256, event_sha256,
                event_signature
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                occurred_at,
                event,
                payload_json,
                previous,
                event_sha256,
                event_signature,
            ),
        )
        return IdentityReceipt(
            event=event,
            brain_id=record.brain_id,
            owner_id=record.owner_id,
            key_version=record.key_version,
            occurred_at=occurred_at,
            public_key_fingerprint=str(payload["public_key_fingerprint"]),
            receipt_sha256=event_sha256,
            signature=event_signature,
        )

    @staticmethod
    def _row_digest(record: BrainIdentityRecord) -> str:
        return hashlib.sha256(_canonical(record.to_dict())).hexdigest()


__all__ = [
    "BrainIdentityRecord",
    "DNAAnchor",
    "DNAAnchorError",
    "DNAFailureCode",
    "EncryptedFileKeyStore",
    "IdentityChallenge",
    "IdentityAttestation",
    "IdentityReceipt",
    "IdentityStatus",
]
