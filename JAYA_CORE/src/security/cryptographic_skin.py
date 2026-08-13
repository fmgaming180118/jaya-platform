"""P13 Cryptographic Skin: authenticated, DNA-signed Core envelopes."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_SCHEMA_VERSION = 1
_ALGORITHM_SUITE = "AES-256-GCM+ED25519"
_ATTESTATION_PURPOSE = "crypto-skin-envelope-v1"
_ZERO_DIGEST = "0" * 64
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$")
_SAFE_PURPOSE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_SAFE_CONTENT_TYPE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}/" r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}$"
)


def _now() -> datetime:
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
        if set(value) != expected or not isinstance(value.get("attestation"), Mapping):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
                "cryptographic envelope schema is invalid",
            )
        try:
            return cls(
                envelope_id=str(value["envelope_id"]),
                key_id=str(value["key_id"]),
                purpose=str(value["purpose"]),
                subject=str(value["subject"]),
                content_type=str(value["content_type"]),
                issued_at=str(value["issued_at"]),
                expires_at=str(value["expires_at"]),
                nonce=str(value["nonce"]),
                ciphertext=str(value["ciphertext"]),
                attestation=dict(value["attestation"]),  # type: ignore[arg-type]
                algorithm_suite=str(value["algorithm_suite"]),
                schema_version=int(value["schema_version"]),
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
    ) -> None:
        secret = (
            encryption_secret.encode("utf-8")
            if isinstance(encryption_secret, str)
            else bytes(encryption_secret)
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
        if not 1 <= max_payload_bytes <= 64 * 1024 * 1024:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "max payload bytes must be between 1 and 67108864",
            )
        if key_binding_context is not None and len(key_binding_context) < 32:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.INVALID_INPUT,
                "cryptographic hardware binding context must contain 32 bytes",
            )
        path = Path(db_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._lock = threading.RLock()
        self._clock = clock
        self._nonce_factory = nonce_factory
        self._sign = attestation_signer
        self._verify = attestation_verifier
        self.max_payload_bytes = max_payload_bytes
        self.hardware_bound = key_binding_context is not None
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
        self._initialize_key_registry()
        self._ensure_ready()

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
        plaintext = bytes(payload)
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
        attestation = dict(self._sign(_ATTESTATION_PURPOSE, unsigned.digest()))
        sealed = SealedEnvelope(**{**asdict(unsigned), "attestation": attestation})
        if not self._attestation_valid(sealed):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.SIGNATURE_INVALID,
                "DNA signer returned an invalid envelope attestation",
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
        envelope = (
            value
            if isinstance(value, SealedEnvelope)
            else SealedEnvelope.from_dict(value)
        )
        self._validate_envelope(envelope)
        if not self._attestation_valid(envelope):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.SIGNATURE_INVALID,
                "cryptographic envelope DNA attestation is invalid",
            )
        state = self._key_state(envelope.key_id)
        if state is KeyState.REVOKED:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.KEY_REVOKED,
                "cryptographic envelope key is revoked",
            )
        if self._utc_now() >= datetime.fromisoformat(envelope.expires_at):
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.ENVELOPE_EXPIRED,
                "cryptographic envelope expired",
            )
        nonce = _decode(envelope.nonce)
        ciphertext = _decode(envelope.ciphertext)
        if len(nonce) != 12 or len(ciphertext) < 16:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
                "cryptographic envelope nonce or ciphertext is invalid",
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
                    self._connection.execute(
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
                    self._insert_key(
                        new_key_id,
                        KeyState.ACTIVE,
                        occurred,
                        None,
                        previous,
                    )
            except sqlite3.Error as exc:
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.STORAGE_ERROR,
                    "cryptographic key rotation could not be persisted",
                ) from exc
        self._record_event(
            "KEY_ROTATED",
            {"previous_key_id": previous, "active_key_id": new_key_id},
        )
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
                    self._connection.execute(
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
            except sqlite3.Error as exc:
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.STORAGE_ERROR,
                    "cryptographic key revocation could not be persisted",
                ) from exc
        self._record_event("KEY_REVOKED", {"key_id": key_id})

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
        try:
            rows = self._connection.execute(
                "SELECT state, COUNT(*) AS count FROM crypto_skin_keys GROUP BY state"
            ).fetchall()
            counts = {str(row["state"]): int(row["count"]) for row in rows}
            nonces = int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM crypto_skin_nonces"
                ).fetchone()[0]
            )
            valid_keys = self._key_registry_valid()
            valid_audit = self.audit_chain_valid()
            active_key = self.active_key_id() if valid_keys else None
        except (sqlite3.Error, CryptographicSkinError):
            counts, nonces, valid_keys, valid_audit, active_key = (
                {},
                0,
                False,
                False,
                None,
            )
        return {
            "ready": valid_keys and valid_audit,
            "algorithm_suite": _ALGORITHM_SUITE,
            "active_key_id": active_key,
            "key_counts": counts,
            "reserved_nonces": nonces,
            "key_registry_valid": valid_keys,
            "audit_chain_valid": valid_audit,
            "max_payload_bytes": self.max_payload_bytes,
            "hardware_bound": self.hardware_bound,
        }

    def close(self) -> None:
        with self._lock:
            self._master_key = b"\x00" * len(self._master_key)
            self._connection.close()

    def _attestation_valid(self, envelope: SealedEnvelope) -> bool:
        attestation = envelope.attestation
        return (
            attestation.get("purpose") == _ATTESTATION_PURPOSE
            and attestation.get("payload_sha256") == envelope.digest()
            and self._verify(attestation)
        )

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
        try:
            issued = datetime.fromisoformat(envelope.issued_at)
            expires = datetime.fromisoformat(envelope.expires_at)
        except ValueError as exc:
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
            info=f"JAYA:P13:{key_id}".encode("utf-8"),
        ).derive(self._master_key)

    def _reserve_nonce(self, key_id: str) -> bytes:
        for _ in range(8):
            nonce = self._nonce_factory(12)
            if not isinstance(nonce, bytes) or len(nonce) != 12:
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.NOT_CONFIGURED,
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
        if not self.audit_chain_valid() or not self._key_registry_valid():
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
            if (
                not _SAFE_ID.fullmatch(str(row["key_id"]))
                or expected != row["row_digest"]
            ):
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
            f"SELECT {column} FROM crypto_skin_keys WHERE key_id = ?",  # noqa: S608
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
        row = self._connection.execute(
            "SELECT COUNT(*) FROM crypto_skin_keys"
        ).fetchone()
        if row is None or int(row[0]) != 0:
            return
        created = self._utc_now().isoformat()
        key_id = f"key-{uuid.uuid4().hex}"
        try:
            with self._connection:
                self._insert_key(key_id, KeyState.ACTIVE, created, None, None)
        except sqlite3.Error as exc:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.STORAGE_ERROR,
                "initial cryptographic key could not be persisted",
            ) from exc
        self._record_event("KEY_CREATED", {"active_key_id": key_id})

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
                self._key_row_digest(
                    key_id, state, created_at, retired_at, previous_key_id
                ),
            ),
        )

    def _record_event(self, event: str, payload: Mapping[str, Any]) -> None:
        occurred = self._utc_now().isoformat()
        with self._lock:
            try:
                with self._connection:
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
            except sqlite3.Error as exc:
                raise CryptographicSkinError(
                    CryptographicSkinFailureCode.STORAGE_ERROR,
                    "cryptographic audit event could not be persisted",
                ) from exc

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
        value = self._clock()
        if value.tzinfo is None:
            raise CryptographicSkinError(
                CryptographicSkinFailureCode.NOT_CONFIGURED,
                "cryptographic clock must be timezone-aware",
            )
        return value.astimezone(timezone.utc)


__all__ = [
    "CryptographicSkin",
    "CryptographicSkinError",
    "CryptographicSkinFailureCode",
    "KeyState",
    "SealedEnvelope",
]
