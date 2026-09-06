"""P13 Cryptographic Skin: authenticated, DNA-signed Core envelopes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from jaya_core.providers import (
    CryptographicEnvelopeContract,
    NativeProviderError,
    TrustedCryptographicSkinDecision,
    TrustedCryptographicSkinGate,
    get_trusted_cryptographic_skin_gate,
)

_SCHEMA_VERSION = 1
_STORAGE_SCHEMA_VERSION = 2
_ALGORITHM_SUITE = "AES-256-GCM+ED25519"
_ATTESTATION_PURPOSE = "crypto-skin-envelope-v1"
_ZERO_DIGEST = "0" * 64
_STATE_TAG_KEY = "state_auth_hmac_sha256"
_STORAGE_SCHEMA_KEY = "storage_schema_version"
_MAX_ATTESTATION_BYTES = 64 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$")
_SAFE_PURPOSE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_SAFE_CONTENT_TYPE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}/" r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}$"
)


def _now() -> datetime:
    return datetime.now(UTC)


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
    if not isinstance(value, str) or len(value) > 64 * 1024 * 1024:
        raise CryptographicSkinError(
            CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
            "cryptographic envelope contains invalid encoded data",
        )
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (TypeError, ValueError) as exc:
        raise CryptographicSkinError(
            CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
            "cryptographic envelope contains invalid encoded data",
        ) from exc


class CryptographicSkinFailureCode(str, Enum):
    INVALID_INPUT = "CRYPTO_SKIN_INVALID_INPUT"
    NOT_CONFIGURED = "CRYPTO_SKIN_NOT_CONFIGURED"
    PAYLOAD_TOO_LARGE = "CRYPTO_SKIN_PAYLOAD_TOO_LARGE"
    CORRUPT_ENVELOPE = "CRYPTO_SKIN_CORRUPT_ENVELOPE"
    SIGNATURE_INVALID = "CRYPTO_SKIN_SIGNATURE_INVALID"
    KEY_UNAVAILABLE = "CRYPTO_SKIN_KEY_UNAVAILABLE"
    KEY_REVOKED = "CRYPTO_SKIN_KEY_REVOKED"
    KEY_STATE_INVALID = "CRYPTO_SKIN_KEY_STATE_INVALID"
    ENVELOPE_EXPIRED = "CRYPTO_SKIN_ENVELOPE_EXPIRED"
    NONCE_COLLISION = "CRYPTO_SKIN_NONCE_COLLISION"
    DECRYPTION_FAILED = "CRYPTO_SKIN_DECRYPTION_FAILED"
    AUDIT_CORRUPT = "CRYPTO_SKIN_AUDIT_CORRUPT"
    STORAGE_ERROR = "CRYPTO_SKIN_STORAGE_ERROR"
    STORAGE_SCHEMA_UNSUPPORTED = "CRYPTO_SKIN_STORAGE_SCHEMA_UNSUPPORTED"
    ATTESTATION_UNAVAILABLE = "CRYPTO_SKIN_ATTESTATION_UNAVAILABLE"
    CLOCK_UNAVAILABLE = "CRYPTO_SKIN_CLOCK_UNAVAILABLE"
    CLOCK_SKEW = "CRYPTO_SKIN_CLOCK_SKEW"
    NONCE_UNAVAILABLE = "CRYPTO_SKIN_NONCE_UNAVAILABLE"
    CONCURRENT_MODIFICATION = "CRYPTO_SKIN_CONCURRENT_MODIFICATION"
    PROVIDER_UNAVAILABLE = "CRYPTO_SKIN_PROVIDER_UNAVAILABLE"


class CryptographicSkinError(RuntimeError):
    def __init__(
        self,
        code: CryptographicSkinFailureCode,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


class KeyState(str, Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class SealedEnvelope:
    envelope_id: str
    key_id: str
    purpose: str
    subject: str
    content_type: str
    issued_at: str
    expires_at: str
    nonce: str
    ciphertext: str
    attestation: Mapping[str, object]
    algorithm_suite: str = _ALGORITHM_SUITE
    schema_version: int = _SCHEMA_VERSION

    def associated_data(self) -> bytes:
        return _canonical(
            {
                "algorithm_suite": self.algorithm_suite,
                "content_type": self.content_type,
                "envelope_id": self.envelope_id,
                "expires_at": self.expires_at,
                "issued_at": self.issued_at,
                "key_id": self.key_id,
                "purpose": self.purpose,
                "schema_version": self.schema_version,
                "subject": self.subject,
            }
        )

    def unsigned_dict(self) -> dict[str, object]:
        return {
            **json.loads(self.associated_data()),
            "nonce": self.nonce,
            "ciphertext": self.ciphertext,
        }

    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "attestation": dict(self.attestation)}

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> SealedEnvelope:
        expected = {
            "algorithm_suite",
            "attestation",
            "ciphertext",
            "content_type",
            "envelope_id",
            "expires_at",
            "issued_at",
            "key_id",
            "nonce",
            "purpose",
            "schema_version",
            "subject",
        }
        string_fields = expected - {"attestation", "schema_version"}
        if (
            set(value) != expected
            or not isinstance(value.get("attestation"), Mapping)
            or type(value.get("schema_version")) is not int
            or any(type(value.get(field)) is not str for field in string_fields)
        ):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
                "cryptographic envelope schema is invalid",
            )
        try:
            return cls(
                envelope_id=value["envelope_id"],  # type: ignore[arg-type]
                key_id=value["key_id"],  # type: ignore[arg-type]
                purpose=value["purpose"],  # type: ignore[arg-type]
                subject=value["subject"],  # type: ignore[arg-type]
                content_type=value["content_type"],  # type: ignore[arg-type]
                issued_at=value["issued_at"],  # type: ignore[arg-type]
                expires_at=value["expires_at"],  # type: ignore[arg-type]
                nonce=value["nonce"],  # type: ignore[arg-type]
                ciphertext=value["ciphertext"],  # type: ignore[arg-type]
                attestation=dict(value["attestation"]),  # type: ignore[arg-type]
                algorithm_suite=value["algorithm_suite"],  # type: ignore[arg-type]
                schema_version=value["schema_version"],  # type: ignore[arg-type]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
                "cryptographic envelope schema is invalid",
            ) from exc


AttestationSigner = Callable[[str, str], Mapping[str, object]]
AttestationVerifier = Callable[[Mapping[str, object]], bool]


class CryptographicSkin:
    """Persistent key lifecycle and authenticated envelope service."""

    def __init__(
        self,
        db_path: Path | str,
        encryption_secret: str | bytes,
        *,
        attestation_signer: AttestationSigner,
        attestation_verifier: AttestationVerifier,
        clock: Callable[[], datetime] = _now,
        nonce_factory: Callable[[int], bytes] = os.urandom,
        max_payload_bytes: int = 16 * 1024 * 1024,
        key_binding_context: bytes | None = None,
        max_clock_skew_seconds: float = 5.0,
        storage_timeout_seconds: float = 5.0,
        allow_legacy_migration: bool = False,
        envelope_gate: TrustedCryptographicSkinGate | None = None,
    ) -> None:
        if isinstance(encryption_secret, str):
            secret = encryption_secret.encode("utf-8")
        elif isinstance(encryption_secret, bytes):
            secret = encryption_secret
        else:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "cryptographic skin secret must be text or bytes",
            )
        if len(secret) < 32:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "cryptographic skin secret must contain at least 32 bytes",
            )
        if not callable(attestation_signer) or not callable(attestation_verifier):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.NOT_CONFIGURED,
                "DNA attestation signer and verifier are required",
            )
        if type(max_payload_bytes) is not int or not 1 <= max_payload_bytes <= 64 * 1024 * 1024:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "max payload bytes must be between 1 and 67108864",
            )
        if key_binding_context is not None and (
            not isinstance(key_binding_context, bytes) or len(key_binding_context) < 32
        ):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "cryptographic hardware binding context must contain 32 bytes",
            )
        if (
            isinstance(max_clock_skew_seconds, bool)
            or not isinstance(max_clock_skew_seconds, (int, float))
            or not 0 <= float(max_clock_skew_seconds) <= 300
        ):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "max clock skew seconds must be between 0 and 300",
            )
        if (
            isinstance(storage_timeout_seconds, bool)
            or not isinstance(storage_timeout_seconds, (int, float))
            or not 0.05 <= float(storage_timeout_seconds) <= 30
        ):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "storage timeout seconds must be between 0.05 and 30",
            )
        if type(allow_legacy_migration) is not bool:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "legacy migration flag must be boolean",
            )
        try:
            self._envelope_gate = envelope_gate or get_trusted_cryptographic_skin_gate()
        except NativeProviderError as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.PROVIDER_UNAVAILABLE,
                "cryptographic envelope admission provider is unavailable",
            ) from exc
        if not isinstance(self._envelope_gate, TrustedCryptographicSkinGate):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "cryptographic envelope admission provider is invalid",
            )
        try:
            path = Path(db_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                path,
                timeout=float(storage_timeout_seconds),
                check_same_thread=False,
            )
        except (OSError, TypeError, sqlite3.Error) as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.STORAGE_ERROR,
                "cryptographic storage cannot be opened",
            ) from exc
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute(
            f"PRAGMA busy_timeout = {int(float(storage_timeout_seconds) * 1_000)}"
        )
        self._lock = threading.RLock()
        self._clock = clock
        self._nonce_factory = nonce_factory
        self._sign = attestation_signer
        self._verify = attestation_verifier
        self.max_payload_bytes = max_payload_bytes
        self.max_clock_skew_seconds = float(max_clock_skew_seconds)
        self.storage_timeout_seconds = float(storage_timeout_seconds)
        self._allow_legacy_migration = allow_legacy_migration
        self.hardware_bound = key_binding_context is not None
        self._closed = False
        self._master_key = b""
        self._state_auth_key = b""
        try:
            self._create_schema()
            salt = self._load_or_create_salt()
            key_material = secret
            if key_binding_context is not None:
                key_material += b"\x00JAYA:P14\x00" + key_binding_context
            self._master_key = Scrypt(
                salt=salt,
                length=32,
                n=2**14,
                r=8,
                p=1,
            ).derive(key_material)
            self._state_auth_key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=b"JAYA:P13:STATE-AUTH:v2",
            ).derive(self._master_key)
            self._prepare_storage_schema()
            self._initialize_key_registry()
            self._initialize_state_authenticator()
            self._ensure_ready()
        except Exception:
            self._master_key = b"\x00" * len(self._master_key)
            self._state_auth_key = b"\x00" * len(self._state_auth_key)
            self._connection.close()
            self._closed = True
            raise

    def seal(
        self,
        payload: bytes,
        *,
        purpose: str,
        subject: str,
        content_type: str = "application/octet-stream",
        ttl_seconds: int = 3_600,
    ) -> SealedEnvelope:
        """Seal one bounded payload using the current active key."""

        self._ensure_ready()
        try:
            plaintext = bytes(payload)
        except (TypeError, ValueError) as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "cryptographic payload must be bytes",
            ) from exc
        self._validate_seal_input(
            plaintext,
            purpose=purpose,
            subject=subject,
            content_type=content_type,
            ttl_seconds=ttl_seconds,
        )
        issued = self._utc_now()
        expires = issued + timedelta(seconds=ttl_seconds)
        key_id = self.active_key_id()
        envelope = SealedEnvelope(
            envelope_id=f"env-{uuid.uuid4().hex}",
            key_id=key_id,
            purpose=purpose,
            subject=subject,
            content_type=content_type,
            issued_at=issued.isoformat(),
            expires_at=expires.isoformat(),
            nonce="",
            ciphertext="",
            attestation={},
        )
        nonce = self._reserve_nonce(key_id)
        ciphertext = AESGCM(self._derive_key(key_id)).encrypt(
            nonce,
            plaintext,
            envelope.associated_data(),
        )
        unsigned = SealedEnvelope(
            **{
                **asdict(envelope),
                "nonce": _encode(nonce),
                "ciphertext": _encode(ciphertext),
            }
        )
        try:
            signed = self._sign(_ATTESTATION_PURPOSE, unsigned.digest())
            if not isinstance(signed, Mapping):
                raise TypeError("attestation signer did not return a mapping")
            attestation = dict(signed)
        except CryptographicSkinError:
            raise
        except Exception as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.ATTESTATION_UNAVAILABLE,
                "DNA attestation signer is unavailable",
            ) from exc
        sealed = SealedEnvelope(**{**asdict(unsigned), "attestation": attestation})
        self._validate_envelope(sealed)
        self._require_attestation(sealed, operation_code=1)
        if not self._attestation_valid(sealed):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.SIGNATURE_INVALID,
                "DNA signer returned an invalid envelope attestation",
            )
        self._require_envelope_admission(
            sealed,
            operation_code=1,
            key_state=self._key_state(sealed.key_id),
            temporal_state=1,
            nonce_size_bytes=len(nonce),
            ciphertext_size_bytes=len(ciphertext),
        )
        self._record_event(
            "ENVELOPE_SEALED",
            {
                "envelope_id": sealed.envelope_id,
                "key_id": sealed.key_id,
                "envelope_sha256": sealed.digest(),
                "payload_size_bytes": len(plaintext),
                "purpose": sealed.purpose,
            },
        )
        return sealed

    def open(self, value: SealedEnvelope | Mapping[str, object]) -> bytes:
        """Authenticate, authorize key state, and decrypt one envelope."""

        self._ensure_ready()
        envelope = value if isinstance(value, SealedEnvelope) else SealedEnvelope.from_dict(value)
        self._validate_envelope(envelope)
        self._require_attestation(envelope, operation_code=2)
        if not self._attestation_valid(envelope):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.SIGNATURE_INVALID,
                "cryptographic envelope DNA attestation is invalid",
            )
        state = self._key_state(envelope.key_id)
        now = self._utc_now()
        issued = datetime.fromisoformat(envelope.issued_at)
        expires = datetime.fromisoformat(envelope.expires_at)
        temporal_state = 1
        if issued > now + timedelta(seconds=self.max_clock_skew_seconds):
            temporal_state = 2
        elif now >= expires:
            temporal_state = 3
        self._require_envelope_admission(
            envelope,
            operation_code=2,
            key_state=state,
            temporal_state=temporal_state,
            nonce_size_bytes=0,
            ciphertext_size_bytes=0,
            bytes_pending=True,
        )
        nonce = _decode(envelope.nonce)
        ciphertext = _decode(envelope.ciphertext)
        self._require_envelope_admission(
            envelope,
            operation_code=2,
            key_state=state,
            temporal_state=temporal_state,
            nonce_size_bytes=len(nonce),
            ciphertext_size_bytes=len(ciphertext),
        )
        try:
            plaintext = AESGCM(self._derive_key(envelope.key_id)).decrypt(
                nonce,
                ciphertext,
                envelope.associated_data(),
            )
        except (InvalidTag, ValueError) as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.DECRYPTION_FAILED,
                "cryptographic envelope could not be authenticated or decrypted",
            ) from exc
        if len(plaintext) > self.max_payload_bytes:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.PAYLOAD_TOO_LARGE,
                "decrypted payload exceeded the configured resource limit",
            )
        self._record_event(
            "ENVELOPE_OPENED",
            {
                "envelope_id": envelope.envelope_id,
                "key_id": envelope.key_id,
                "envelope_sha256": envelope.digest(),
                "payload_size_bytes": len(plaintext),
                "purpose": envelope.purpose,
            },
        )
        return plaintext

    def rotate_key(self) -> str:
        """Retire the active data key and create a fresh derived key ID."""

        self._ensure_ready()
        occurred = self._utc_now().isoformat()
        previous = self.active_key_id()
        new_key_id = f"key-{uuid.uuid4().hex}"
        with self._lock:
            try:
                with self._connection:
                    retired_digest = self._key_row_digest(
                        previous,
                        KeyState.RETIRED,
                        self._key_created_at(previous),
                        occurred,
                        self._key_previous(previous),
                    )
                    updated = self._connection.execute(
                        """
                        UPDATE crypto_skin_keys
                        SET state = ?, retired_at = ?, row_digest = ?
                        WHERE key_id = ? AND state = ?
                        """,
                        (
                            KeyState.RETIRED.value,
                            occurred,
                            retired_digest,
                            previous,
                            KeyState.ACTIVE.value,
                        ),
                    )
                    if updated.rowcount != 1:
                        raise CryptographicSkinError(
                            CryptographicSkinFailureCode.CONCURRENT_MODIFICATION,
                            "active cryptographic key changed concurrently",
                        )
                    self._insert_key(
                        new_key_id,
                        KeyState.ACTIVE,
                        occurred,
                        None,
                        previous,
                    )
                    self._append_event_in_transaction(
                        "KEY_ROTATED",
                        {"previous_key_id": previous, "active_key_id": new_key_id},
                    )
                    self._write_state_authenticator()
            except CryptographicSkinError:
                raise
            except sqlite3.IntegrityError as exc:
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.CONCURRENT_MODIFICATION,
                    "cryptographic key rotation conflicted with another writer",
                ) from exc
            except sqlite3.Error as exc:
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.STORAGE_ERROR,
                    "cryptographic key rotation could not be persisted",
                ) from exc
        self._ensure_ready()
        return new_key_id

    def revoke_key(self, key_id: str) -> None:
        """Revoke a retired key; active keys must be rotated first."""

        self._ensure_ready()
        state = self._key_state(key_id)
        if state is KeyState.ACTIVE:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.KEY_STATE_INVALID,
                "active key must be rotated before revocation",
            )
        if state is KeyState.REVOKED:
            return
        created_at = self._key_created_at(key_id)
        retired_at = self._key_retired_at(key_id) or self._utc_now().isoformat()
        previous = self._key_previous(key_id)
        digest = self._key_row_digest(
            key_id,
            KeyState.REVOKED,
            created_at,
            retired_at,
            previous,
        )
        with self._lock:
            try:
                with self._connection:
                    updated = self._connection.execute(
                        """
                        UPDATE crypto_skin_keys
                        SET state = ?, retired_at = ?, row_digest = ?
                        WHERE key_id = ? AND state = ?
                        """,
                        (
                            KeyState.REVOKED.value,
                            retired_at,
                            digest,
                            key_id,
                            KeyState.RETIRED.value,
                        ),
                    )
                    if updated.rowcount != 1:
                        raise CryptographicSkinError(
                            CryptographicSkinFailureCode.CONCURRENT_MODIFICATION,
                            "cryptographic key state changed concurrently",
                        )
                    self._append_event_in_transaction("KEY_REVOKED", {"key_id": key_id})
                    self._write_state_authenticator()
            except CryptographicSkinError:
                raise
            except sqlite3.Error as exc:
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.STORAGE_ERROR,
                    "cryptographic key revocation could not be persisted",
                ) from exc
        self._ensure_ready()

    def active_key_id(self) -> str:
        try:
            row = self._connection.execute(
                "SELECT key_id FROM crypto_skin_keys WHERE state = ?",
                (KeyState.ACTIVE.value,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.STORAGE_ERROR,
                "active cryptographic key cannot be read",
            ) from exc
        if row is None:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.KEY_UNAVAILABLE,
                "active cryptographic key is unavailable",
            )
        return str(row["key_id"])

    def audit_chain_valid(self) -> bool:
        try:
            rows = self._connection.execute(
                """
                SELECT occurred_at, event, payload_json,
                       previous_sha256, event_sha256
                FROM crypto_skin_audit ORDER BY event_id
                """
            ).fetchall()
        except sqlite3.Error:
            return False
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
        return bool(rows)

    def status(self) -> dict[str, object]:
        if self._closed:
            return {
                "ready": False,
                "mode": "CLOSED",
                "algorithm_suite": _ALGORITHM_SUITE,
                "storage_schema_version": _STORAGE_SCHEMA_VERSION,
                "envelope_gate": self._envelope_gate.profile(),
            }
        try:
            rows = self._connection.execute(
                "SELECT state, COUNT(*) AS count FROM crypto_skin_keys GROUP BY state"
            ).fetchall()
            counts = {str(row["state"]): int(row["count"]) for row in rows}
            nonces = int(
                self._connection.execute("SELECT COUNT(*) FROM crypto_skin_nonces").fetchone()[0]
            )
            valid_keys = self._key_registry_valid()
            valid_audit = self.audit_chain_valid()
            state_authenticated = self._state_authenticator_valid()
            active_key = self.active_key_id() if valid_keys else None
        except (sqlite3.Error, CryptographicSkinError):
            counts, nonces, valid_keys, valid_audit, state_authenticated, active_key = (
                {},
                0,
                False,
                False,
                False,
                None,
            )
        return {
            "ready": valid_keys and valid_audit and state_authenticated,
            "mode": "READY"
            if valid_keys and valid_audit and state_authenticated
            else "FAIL_CLOSED",
            "algorithm_suite": _ALGORITHM_SUITE,
            "storage_schema_version": _STORAGE_SCHEMA_VERSION,
            "active_key_id": active_key,
            "key_counts": counts,
            "reserved_nonces": nonces,
            "key_registry_valid": valid_keys,
            "audit_chain_valid": valid_audit,
            "state_authenticated": state_authenticated,
            "max_payload_bytes": self.max_payload_bytes,
            "max_clock_skew_seconds": self.max_clock_skew_seconds,
            "storage_timeout_seconds": self.storage_timeout_seconds,
            "hardware_bound": self.hardware_bound,
            "envelope_gate": self._envelope_gate.profile(),
        }

    def health_check(self) -> dict[str, object]:
        """Return bounded readiness without exposing key material."""

        return self.status()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._master_key = b"\x00" * len(self._master_key)
            self._state_auth_key = b"\x00" * len(self._state_auth_key)
            self._connection.close()
            self._closed = True

    def _attestation_valid(self, envelope: SealedEnvelope) -> bool:
        attestation = envelope.attestation
        if (
            attestation.get("purpose") != _ATTESTATION_PURPOSE
            or attestation.get("payload_sha256") != envelope.digest()
        ):
            return False
        try:
            return self._verify(attestation) is True
        except Exception as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.ATTESTATION_UNAVAILABLE,
                "DNA attestation verifier is unavailable",
            ) from exc

    def _require_attestation(self, envelope: SealedEnvelope, *, operation_code: int) -> None:
        decision = self._evaluate_envelope_gate(
            envelope,
            operation_code=operation_code,
            key_state=0,
            attestation_state=0,
            temporal_state=0,
            nonce_size_bytes=0,
            ciphertext_size_bytes=0,
        )
        if decision.effect != 3 or decision.reason_code != "ATTESTATION_REQUIRED":
            self._raise_envelope_decision(decision)

    def _require_envelope_admission(
        self,
        envelope: SealedEnvelope,
        *,
        operation_code: int,
        key_state: KeyState,
        temporal_state: int,
        nonce_size_bytes: int,
        ciphertext_size_bytes: int,
        bytes_pending: bool = False,
    ) -> None:
        state_code = {
            KeyState.ACTIVE: 1,
            KeyState.RETIRED: 2,
            KeyState.REVOKED: 3,
        }[key_state]
        decision = self._evaluate_envelope_gate(
            envelope,
            operation_code=operation_code,
            key_state=state_code,
            attestation_state=1,
            temporal_state=temporal_state,
            nonce_size_bytes=nonce_size_bytes,
            ciphertext_size_bytes=ciphertext_size_bytes,
        )
        if (
            bytes_pending
            and decision.effect == 3
            and decision.reason_code == ("ENVELOPE_BYTES_REQUIRED")
        ):
            return
        if decision.effect != 1 or decision.reason_code != ("VERIFIED_CRYPTOGRAPHIC_ENVELOPE"):
            self._raise_envelope_decision(decision)

    def _evaluate_envelope_gate(
        self,
        envelope: SealedEnvelope,
        *,
        operation_code: int,
        key_state: int,
        attestation_state: int,
        temporal_state: int,
        nonce_size_bytes: int,
        ciphertext_size_bytes: int,
    ) -> TrustedCryptographicSkinDecision:
        contract = CryptographicEnvelopeContract(
            envelope_id=envelope.envelope_id,
            key_id=envelope.key_id,
            purpose=envelope.purpose,
            subject=envelope.subject,
            content_type=envelope.content_type,
            schema_version=envelope.schema_version,
            algorithm_suite_code=1 if envelope.algorithm_suite == _ALGORITHM_SUITE else 0,
            operation_code=operation_code,
            key_state=key_state,
            attestation_state=attestation_state,
            temporal_state=temporal_state,
            nonce_size_bytes=nonce_size_bytes,
            ciphertext_size_bytes=ciphertext_size_bytes,
            max_payload_bytes=self.max_payload_bytes,
        )
        try:
            return self._envelope_gate.evaluate(contract)
        except NativeProviderError as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.PROVIDER_UNAVAILABLE,
                "cryptographic envelope admission provider failed",
            ) from exc

    @staticmethod
    def _raise_envelope_decision(decision: TrustedCryptographicSkinDecision) -> None:
        failures = {
            "CRYPTO_SKIN_CONTRACT_INVALID": (
                CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
                "cryptographic envelope contract is invalid",
            ),
            "CRYPTO_SKIN_SIGNATURE_INVALID": (
                CryptographicSkinFailureCode.SIGNATURE_INVALID,
                "cryptographic envelope DNA attestation is invalid",
            ),
            "CRYPTO_SKIN_ATTESTATION_UNAVAILABLE": (
                CryptographicSkinFailureCode.ATTESTATION_UNAVAILABLE,
                "cryptographic envelope attestation provider is unavailable",
            ),
            "CRYPTO_SKIN_KEY_STATE_INVALID": (
                CryptographicSkinFailureCode.KEY_STATE_INVALID,
                "cryptographic envelope key state is invalid for the operation",
            ),
            "CRYPTO_SKIN_KEY_REVOKED": (
                CryptographicSkinFailureCode.KEY_REVOKED,
                "cryptographic envelope key is revoked",
            ),
            "CRYPTO_SKIN_CLOCK_SKEW": (
                CryptographicSkinFailureCode.CLOCK_SKEW,
                "cryptographic envelope was issued beyond the allowed clock skew",
            ),
            "CRYPTO_SKIN_ENVELOPE_EXPIRED": (
                CryptographicSkinFailureCode.ENVELOPE_EXPIRED,
                "cryptographic envelope expired",
            ),
            "CRYPTO_SKIN_NONCE_INVALID": (
                CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
                "cryptographic envelope nonce is invalid",
            ),
            "CRYPTO_SKIN_CIPHERTEXT_INVALID": (
                CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
                "cryptographic envelope ciphertext is invalid",
            ),
            "CRYPTO_SKIN_PAYLOAD_TOO_LARGE": (
                CryptographicSkinFailureCode.PAYLOAD_TOO_LARGE,
                "cryptographic envelope exceeded the configured resource limit",
            ),
        }
        failure = failures.get(decision.reason_code)
        if failure is None:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.PROVIDER_UNAVAILABLE,
                "cryptographic envelope provider returned an invalid decision",
            )
        raise CryptographicSkinError(*failure)

    def _validate_seal_input(
        self,
        payload: bytes,
        *,
        purpose: str,
        subject: str,
        content_type: str,
        ttl_seconds: int,
    ) -> None:
        if len(payload) > self.max_payload_bytes:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.PAYLOAD_TOO_LARGE,
                "payload exceeded the configured cryptographic resource limit",
            )
        if (
            not payload
            or type(purpose) is not str
            or type(subject) is not str
            or type(content_type) is not str
            or type(ttl_seconds) is not int
            or not _SAFE_PURPOSE.fullmatch(purpose)
            or not _SAFE_ID.fullmatch(subject)
            or not _SAFE_CONTENT_TYPE.fullmatch(content_type)
            or not 1 <= ttl_seconds <= 31_536_000
        ):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "cryptographic envelope input is invalid",
            )

    def _validate_envelope(self, envelope: SealedEnvelope) -> None:
        string_values = (
            envelope.envelope_id,
            envelope.key_id,
            envelope.purpose,
            envelope.subject,
            envelope.content_type,
            envelope.issued_at,
            envelope.expires_at,
            envelope.nonce,
            envelope.ciphertext,
            envelope.algorithm_suite,
        )
        if (
            any(type(value) is not str for value in string_values)
            or type(envelope.schema_version) is not int
            or not isinstance(envelope.attestation, Mapping)
        ):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
                "cryptographic envelope types are invalid",
            )
        try:
            issued = datetime.fromisoformat(envelope.issued_at)
            expires = datetime.fromisoformat(envelope.expires_at)
            attestation_size = len(_canonical(dict(envelope.attestation)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
                "cryptographic envelope timestamps are invalid",
            ) from exc
        if (
            envelope.schema_version != _SCHEMA_VERSION
            or envelope.algorithm_suite != _ALGORITHM_SUITE
            or not _SAFE_ID.fullmatch(envelope.envelope_id)
            or not _SAFE_ID.fullmatch(envelope.key_id)
            or not _SAFE_PURPOSE.fullmatch(envelope.purpose)
            or not _SAFE_ID.fullmatch(envelope.subject)
            or not _SAFE_CONTENT_TYPE.fullmatch(envelope.content_type)
            or issued.tzinfo is None
            or expires.tzinfo is None
            or expires <= issued
            or (expires - issued).total_seconds() > 31_536_000
            or attestation_size > _MAX_ATTESTATION_BYTES
        ):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
                "cryptographic envelope contract is invalid",
            )

    def _derive_key(self, key_id: str) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"JAYA:P13:{key_id}".encode(),
        ).derive(self._master_key)

    def _reserve_nonce(self, key_id: str) -> bytes:
        for _ in range(8):
            try:
                nonce = self._nonce_factory(12)
            except Exception as exc:
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.NONCE_UNAVAILABLE,
                    "cryptographic nonce provider is unavailable",
                ) from exc
            if not isinstance(nonce, bytes) or len(nonce) != 12:
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.NONCE_UNAVAILABLE,
                    "nonce provider returned an invalid value",
                )
            try:
                with self._lock, self._connection:
                    self._connection.execute(
                        """
                        INSERT INTO crypto_skin_nonces(key_id, nonce, reserved_at)
                        VALUES (?, ?, ?)
                        """,
                        (key_id, _encode(nonce), self._utc_now().isoformat()),
                    )
                    self._append_event_in_transaction(
                        "NONCE_RESERVED",
                        {
                            "key_id": key_id,
                            "nonce_sha256": hashlib.sha256(nonce).hexdigest(),
                        },
                    )
                    self._write_state_authenticator()
                return nonce
            except sqlite3.IntegrityError:
                continue
            except sqlite3.Error as exc:
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.STORAGE_ERROR,
                    "cryptographic nonce reservation failed",
                ) from exc
        raise CryptographicSkinError(
            CryptographicSkinFailureCode.NONCE_COLLISION,
            "cryptographic nonce provider repeatedly collided",
        )

    def _ensure_ready(self) -> None:
        if self._closed:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.STORAGE_ERROR,
                "cryptographic storage is closed",
            )
        valid = False
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                valid = (
                    self.audit_chain_valid()
                    and self._key_registry_valid()
                    and self._state_authenticator_valid()
                )
            except sqlite3.Error:
                valid = False
            finally:
                try:
                    self._connection.rollback()
                except sqlite3.Error:
                    valid = False
        if not valid:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.AUDIT_CORRUPT,
                "cryptographic key registry or audit chain is corrupt",
            )

    def _key_registry_valid(self) -> bool:
        try:
            rows = self._connection.execute(
                """
                SELECT key_id, state, created_at, retired_at,
                       previous_key_id, row_digest
                FROM crypto_skin_keys ORDER BY rowid
                """
            ).fetchall()
        except sqlite3.Error:
            return False
        active = 0
        known: set[str] = set()
        for row in rows:
            try:
                state = KeyState(row["state"])
                expected = self._key_row_digest(
                    str(row["key_id"]),
                    state,
                    str(row["created_at"]),
                    row["retired_at"],
                    row["previous_key_id"],
                )
            except (TypeError, ValueError):
                return False
            if not _SAFE_ID.fullmatch(str(row["key_id"])) or expected != row["row_digest"]:
                return False
            previous = row["previous_key_id"]
            if previous is not None and previous not in known:
                return False
            if state is KeyState.ACTIVE:
                active += 1
                if row["retired_at"] is not None:
                    return False
            elif row["retired_at"] is None:
                return False
            known.add(str(row["key_id"]))
        return bool(rows) and active == 1

    def _key_state(self, key_id: str) -> KeyState:
        try:
            row = self._connection.execute(
                "SELECT state FROM crypto_skin_keys WHERE key_id = ?", (key_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.STORAGE_ERROR,
                "cryptographic key state cannot be read",
            ) from exc
        if row is None:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.KEY_UNAVAILABLE,
                "cryptographic envelope key is unavailable",
            )
        try:
            return KeyState(row["state"])
        except ValueError as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.AUDIT_CORRUPT,
                "cryptographic key state is corrupt",
            ) from exc

    def _key_created_at(self, key_id: str) -> str:
        return self._key_column(key_id, "created_at") or ""

    def _key_retired_at(self, key_id: str) -> str | None:
        return self._key_column(key_id, "retired_at")

    def _key_previous(self, key_id: str) -> str | None:
        return self._key_column(key_id, "previous_key_id")

    def _key_column(self, key_id: str, column: str) -> str | None:
        allowed = {"created_at", "retired_at", "previous_key_id"}
        if column not in allowed:
            raise ValueError("unsupported key column")
        row = self._connection.execute(
            f"SELECT {column} FROM crypto_skin_keys WHERE key_id = ?",
            (key_id,),
        ).fetchone()
        if row is None:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.KEY_UNAVAILABLE,
                "cryptographic key is unavailable",
            )
        return None if row[column] is None else str(row[column])

    @staticmethod
    def _key_row_digest(
        key_id: str,
        state: KeyState,
        created_at: str,
        retired_at: str | None,
        previous_key_id: str | None,
    ) -> str:
        return hashlib.sha256(
            _canonical(
                {
                    "created_at": created_at,
                    "key_id": key_id,
                    "previous_key_id": previous_key_id,
                    "retired_at": retired_at,
                    "state": state.value,
                }
            )
        ).hexdigest()

    def _initialize_key_registry(self) -> None:
        row = self._connection.execute("SELECT COUNT(*) FROM crypto_skin_keys").fetchone()
        if row is None or int(row[0]) != 0:
            return
        created = self._utc_now().isoformat()
        key_id = f"key-{uuid.uuid4().hex}"
        try:
            with self._connection:
                self._insert_key(key_id, KeyState.ACTIVE, created, None, None)
                self._append_event_in_transaction("KEY_CREATED", {"active_key_id": key_id})
                self._write_state_authenticator()
        except sqlite3.Error as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.STORAGE_ERROR,
                "initial cryptographic key could not be persisted",
            ) from exc

    def _insert_key(
        self,
        key_id: str,
        state: KeyState,
        created_at: str,
        retired_at: str | None,
        previous_key_id: str | None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO crypto_skin_keys(
                key_id, state, created_at, retired_at,
                previous_key_id, row_digest
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                key_id,
                state.value,
                created_at,
                retired_at,
                previous_key_id,
                self._key_row_digest(key_id, state, created_at, retired_at, previous_key_id),
            ),
        )

    def _record_event(self, event: str, payload: Mapping[str, Any]) -> None:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._append_event_in_transaction(event, payload)
                self._write_state_authenticator()
                self._connection.commit()
            except CryptographicSkinError:
                self._connection.rollback()
                raise
            except sqlite3.Error as exc:
                self._connection.rollback()
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.STORAGE_ERROR,
                    "cryptographic audit event could not be persisted",
                ) from exc

    def _append_event_in_transaction(
        self,
        event: str,
        payload: Mapping[str, Any],
    ) -> None:
        occurred = self._utc_now().isoformat()
        row = self._connection.execute(
            """
            SELECT event_sha256 FROM crypto_skin_audit
            ORDER BY event_id DESC LIMIT 1
            """
        ).fetchone()
        previous = str(row[0]) if row else _ZERO_DIGEST
        content = {
            "occurred_at": occurred,
            "event": event,
            "payload": dict(payload),
            "previous_sha256": previous,
        }
        digest = hashlib.sha256(_canonical(content)).hexdigest()
        self._connection.execute(
            """
            INSERT INTO crypto_skin_audit(
                occurred_at, event, payload_json,
                previous_sha256, event_sha256
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                occurred,
                event,
                _canonical(payload).decode("utf-8"),
                previous,
                digest,
            ),
        )

    def _prepare_storage_schema(self) -> None:
        try:
            version_row = self._connection.execute(
                "SELECT value FROM crypto_skin_metadata WHERE key = ?",
                (_STORAGE_SCHEMA_KEY,),
            ).fetchone()
            tag_row = self._connection.execute(
                "SELECT value FROM crypto_skin_metadata WHERE key = ?",
                (_STATE_TAG_KEY,),
            ).fetchone()
            if version_row is None:
                if tag_row is not None:
                    raise CryptographicSkinError(
                        CryptographicSkinFailureCode.AUDIT_CORRUPT,
                        "cryptographic storage schema metadata is incomplete",
                    )
                key_count = int(
                    self._connection.execute("SELECT COUNT(*) FROM crypto_skin_keys").fetchone()[0]
                )
                audit_count = int(
                    self._connection.execute("SELECT COUNT(*) FROM crypto_skin_audit").fetchone()[0]
                )
                if (key_count or audit_count) and not self._allow_legacy_migration:
                    raise CryptographicSkinError(
                        CryptographicSkinFailureCode.STORAGE_SCHEMA_UNSUPPORTED,
                        "legacy cryptographic storage requires explicit migration",
                    )
                with self._connection:
                    self._connection.execute(
                        "INSERT INTO crypto_skin_metadata(key, value) VALUES (?, ?)",
                        (_STORAGE_SCHEMA_KEY, str(_STORAGE_SCHEMA_VERSION)),
                    )
                return
            if str(version_row["value"]) != str(_STORAGE_SCHEMA_VERSION):
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.STORAGE_SCHEMA_UNSUPPORTED,
                    "cryptographic storage schema version is unsupported",
                )
        except CryptographicSkinError:
            raise
        except sqlite3.Error as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.STORAGE_ERROR,
                "cryptographic storage schema cannot be inspected",
            ) from exc

    def _initialize_state_authenticator(self) -> None:
        try:
            row = self._connection.execute(
                "SELECT value FROM crypto_skin_metadata WHERE key = ?",
                (_STATE_TAG_KEY,),
            ).fetchone()
            if row is not None:
                return
            if not self.audit_chain_valid() or not self._key_registry_valid():
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.AUDIT_CORRUPT,
                    "legacy cryptographic state cannot be authenticated",
                )
            with self._connection:
                self._write_state_authenticator()
        except CryptographicSkinError:
            raise
        except sqlite3.Error as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.STORAGE_ERROR,
                "cryptographic state authenticator cannot be initialized",
            ) from exc

    def _state_material(self) -> bytes:
        metadata = [
            dict(row)
            for row in self._connection.execute(
                """
                SELECT key, value FROM crypto_skin_metadata
                WHERE key != ? ORDER BY key
                """,
                (_STATE_TAG_KEY,),
            ).fetchall()
        ]
        keys = [
            dict(row)
            for row in self._connection.execute(
                """
                SELECT key_id, state, created_at, retired_at,
                       previous_key_id, row_digest
                FROM crypto_skin_keys ORDER BY rowid
                """
            ).fetchall()
        ]
        nonces = [
            dict(row)
            for row in self._connection.execute(
                """
                SELECT key_id, nonce, reserved_at
                FROM crypto_skin_nonces ORDER BY key_id, nonce
                """
            ).fetchall()
        ]
        audit = [
            dict(row)
            for row in self._connection.execute(
                """
                SELECT event_id, occurred_at, event, payload_json,
                       previous_sha256, event_sha256
                FROM crypto_skin_audit ORDER BY event_id
                """
            ).fetchall()
        ]
        schema = [
            dict(row)
            for row in self._connection.execute(
                """
                SELECT type, name, tbl_name, sql FROM sqlite_master
                WHERE name LIKE 'crypto_skin_%' ORDER BY type, name
                """
            ).fetchall()
        ]
        return _canonical(
            {
                "audit": audit,
                "keys": keys,
                "metadata": metadata,
                "nonces": nonces,
                "schema": schema,
            }
        )

    def _state_authenticator_digest(self) -> str:
        return hmac.new(
            self._state_auth_key,
            self._state_material(),
            hashlib.sha256,
        ).hexdigest()

    def _write_state_authenticator(self) -> None:
        digest = self._state_authenticator_digest()
        self._connection.execute(
            """
            INSERT INTO crypto_skin_metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (_STATE_TAG_KEY, digest),
        )

    def _state_authenticator_valid(self) -> bool:
        try:
            for _ in range(3):
                before = self._connection.execute(
                    "SELECT value FROM crypto_skin_metadata WHERE key = ?",
                    (_STATE_TAG_KEY,),
                ).fetchone()
                if before is None:
                    return False
                digest = self._state_authenticator_digest()
                after = self._connection.execute(
                    "SELECT value FROM crypto_skin_metadata WHERE key = ?",
                    (_STATE_TAG_KEY,),
                ).fetchone()
                if after is None:
                    return False
                before_value = str(before["value"])
                after_value = str(after["value"])
                if before_value == after_value:
                    return hmac.compare_digest(after_value, digest)
            return False
        except (OSError, TypeError, ValueError, sqlite3.Error):
            return False

    def _load_or_create_salt(self) -> bytes:
        try:
            with self._connection:
                row = self._connection.execute(
                    "SELECT value FROM crypto_skin_metadata WHERE key = 'kdf_salt'"
                ).fetchone()
                if row is None:
                    salt = os.urandom(16)
                    self._connection.execute(
                        """
                        INSERT INTO crypto_skin_metadata(key, value)
                        VALUES ('kdf_salt', ?)
                        """,
                        (_encode(salt),),
                    )
                    return salt
        except sqlite3.Error as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.STORAGE_ERROR,
                "cryptographic KDF metadata cannot be persisted",
            ) from exc
        salt = _decode(str(row["value"]))
        if len(salt) != 16:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.AUDIT_CORRUPT,
                "cryptographic KDF metadata is corrupt",
            )
        return salt

    def _create_schema(self) -> None:
        try:
            with self._connection:
                self._connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS crypto_skin_metadata(
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS crypto_skin_keys(
                        key_id TEXT PRIMARY KEY,
                        state TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        retired_at TEXT,
                        previous_key_id TEXT,
                        row_digest TEXT NOT NULL,
                        FOREIGN KEY(previous_key_id)
                            REFERENCES crypto_skin_keys(key_id)
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS
                        idx_crypto_skin_one_active_key
                    ON crypto_skin_keys(state) WHERE state = 'ACTIVE';
                    CREATE TABLE IF NOT EXISTS crypto_skin_nonces(
                        key_id TEXT NOT NULL,
                        nonce TEXT NOT NULL,
                        reserved_at TEXT NOT NULL,
                        PRIMARY KEY(key_id, nonce),
                        FOREIGN KEY(key_id) REFERENCES crypto_skin_keys(key_id)
                    );
                    CREATE TABLE IF NOT EXISTS crypto_skin_audit(
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        occurred_at TEXT NOT NULL,
                        event TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        previous_sha256 TEXT NOT NULL,
                        event_sha256 TEXT NOT NULL UNIQUE
                    );
                    """
                )
        except sqlite3.Error as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.STORAGE_ERROR,
                "cryptographic schema cannot be initialized",
            ) from exc

    def _utc_now(self) -> datetime:
        try:
            value = self._clock()
        except Exception as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.CLOCK_UNAVAILABLE,
                "cryptographic clock is unavailable",
            ) from exc
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.CLOCK_UNAVAILABLE,
                "cryptographic clock must be timezone-aware",
            )
        try:
            return value.astimezone(UTC)
        except (OverflowError, ValueError) as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.CLOCK_UNAVAILABLE,
                "cryptographic clock value is invalid",
            ) from exc


__all__ = [
    "CryptographicSkin",
    "CryptographicSkinError",
    "CryptographicSkinFailureCode",
    "KeyState",
    "SealedEnvelope",
]
