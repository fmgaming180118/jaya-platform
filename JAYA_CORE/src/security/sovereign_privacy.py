"""P20 Sovereign Privacy: owner-bound data use and encrypted persistence."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from src.privacy_redaction import redact_private

_SCHEMA_VERSION = 1
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$")


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
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (TypeError, ValueError) as exc:
        raise PrivacyError(
            PrivacyFailureCode.CORRUPT_DATA,
            "privacy record contains invalid encoded data",
        ) from exc


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class DataPurpose(str, Enum):
    CORE_REASONING = "CORE_REASONING"
    MEMORY = "MEMORY"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    TELEMETRY = "TELEMETRY"
    EXPORT = "EXPORT"
    BACKUP = "BACKUP"


class DataDestination(str, Enum):
    LOCAL = "LOCAL"
    EXTERNAL_PROVIDER = "EXTERNAL_PROVIDER"
    OWNER_EXPORT = "OWNER_EXPORT"


class PrivacyEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class PrivacyFailureCode(str, Enum):
    INVALID_INPUT = "PRIVACY_INVALID_INPUT"
    NOT_CONFIGURED = "PRIVACY_NOT_CONFIGURED"
    CONSENT_REQUIRED = "PRIVACY_CONSENT_REQUIRED"
    CONSENT_INVALID = "PRIVACY_CONSENT_INVALID"
    CONSENT_EXPIRED = "PRIVACY_CONSENT_EXPIRED"
    CONSENT_REVOKED = "PRIVACY_CONSENT_REVOKED"
    OWNER_MISMATCH = "PRIVACY_OWNER_MISMATCH"
    PURPOSE_DENIED = "PRIVACY_PURPOSE_DENIED"
    DATA_EXPIRED = "PRIVACY_DATA_EXPIRED"
    DATA_NOT_FOUND = "PRIVACY_DATA_NOT_FOUND"
    DATA_DELETED = "PRIVACY_DATA_DELETED"
    CORRUPT_DATA = "PRIVACY_CORRUPT_DATA"
    DECRYPTION_FAILED = "PRIVACY_DECRYPTION_FAILED"
    STORAGE_ERROR = "PRIVACY_STORAGE_ERROR"


class PrivacyError(RuntimeError):
    def __init__(self, code: PrivacyFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ConsentGrant:
    consent_id: str
    approver_id: str
    owner_id: str
    subject_id: str
    classifications: tuple[DataClassification, ...]
    purposes: tuple[DataPurpose, ...]
    providers: tuple[str, ...]
    issued_at: str
    expires_at: str
    nonce: str
    signature: str
    policy_version: int = 1
    schema_version: int = _SCHEMA_VERSION

    def unsigned_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("signature")
        value["classifications"] = [item.value for item in self.classifications]
        value["purposes"] = [item.value for item in self.purposes]
        return value

    def signed_payload(self) -> bytes:
        return _canonical(self.unsigned_dict())

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "signature": self.signature}


@dataclass(frozen=True, slots=True)
class DataDescriptor:
    data_id: str
    owner_id: str
    subject_id: str
    classification: DataClassification
    allowed_purposes: tuple[DataPurpose, ...]
    retention_until: str
    plaintext_sha256: str
    created_at: str
    schema_version: int = _SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["classification"] = self.classification.value
        value["allowed_purposes"] = [item.value for item in self.allowed_purposes]
        return value


@dataclass(frozen=True, slots=True)
class PrivacyUseRequest:
    request_id: str
    actor_id: str
    owner_id: str
    subject_id: str
    data_id: str
    classification: DataClassification
    purpose: DataPurpose
    destination: DataDestination
    provider_id: str
    payload_sha256: str
    consent_id: str | None = None
    schema_version: int = _SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["classification"] = self.classification.value
        value["purpose"] = self.purpose.value
        value["destination"] = self.destination.value
        return value


@dataclass(frozen=True, slots=True)
class PrivacyDecision:
    decision_id: int
    effect: PrivacyEffect
    reason_code: str
    request_digest: str
    consent_id: str | None
    occurred_at: str
    previous_receipt_sha256: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["effect"] = self.effect.value
        return value


class PrivacyCipher:
    """AES-GCM cipher derived from an injected secret and persisted random salt."""

    def __init__(self, secret: str | bytes, salt: bytes) -> None:
        raw = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
        if len(raw) < 32 or len(salt) != 16:
            raise PrivacyError(
                PrivacyFailureCode.INVALID_INPUT,
                "privacy secret must be at least 32 bytes and salt must be 16 bytes",
            )
        self._key = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(raw)

    def encrypt(self, plaintext: bytes, aad: bytes) -> tuple[str, str]:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext, aad)
        return _encode(nonce), _encode(ciphertext)

    def decrypt(self, nonce: str, ciphertext: str, aad: bytes) -> bytes:
        try:
            return AESGCM(self._key).decrypt(
                _decode(nonce),
                _decode(ciphertext),
                aad,
            )
        except (InvalidTag, ValueError) as exc:
            raise PrivacyError(
                PrivacyFailureCode.DECRYPTION_FAILED,
                "private data could not be authenticated or decrypted",
            ) from exc


class SovereignPrivacy:
    """Persistent privacy policy, encrypted vault, consent, and audit engine."""

    def __init__(
        self,
        db_path: Path | str,
        encryption_secret: str | bytes,
        *,
        consent_public_keys: Mapping[str, bytes | str] | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(db_path), timeout=5.0, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if str(db_path) != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()
        salt = self._load_or_create_salt()
        self._cipher = PrivacyCipher(encryption_secret, salt)
        self._consent_keys = self._load_keys(consent_public_keys or {})
        if not self.audit_chain_valid():
            raise PrivacyError(
                PrivacyFailureCode.CORRUPT_DATA,
                "privacy audit chain is corrupt",
            )

    @staticmethod
    def _load_keys(
        values: Mapping[str, bytes | str],
    ) -> dict[str, Ed25519PublicKey]:
        result: dict[str, Ed25519PublicKey] = {}
        for key_id, material in values.items():
            if not _SAFE_ID.fullmatch(key_id):
                raise PrivacyError(
                    PrivacyFailureCode.INVALID_INPUT,
                    "consent approver id is invalid",
                )
            raw = material if isinstance(material, bytes) else _decode(material)
            try:
                result[key_id] = Ed25519PublicKey.from_public_bytes(raw)
            except ValueError as exc:
                raise PrivacyError(
                    PrivacyFailureCode.INVALID_INPUT,
                    "consent public key is invalid",
                ) from exc
        return result

    def install_consent(self, grant: ConsentGrant) -> str:
        self._validate_consent_contract(grant)
        key = self._consent_keys.get(grant.approver_id)
        if key is None:
            raise PrivacyError(
                PrivacyFailureCode.CONSENT_INVALID,
                "consent signer is not trusted",
            )
        try:
            key.verify(_decode(grant.signature), grant.signed_payload())
        except (InvalidSignature, ValueError) as exc:
            raise PrivacyError(
                PrivacyFailureCode.CONSENT_INVALID,
                "consent signature is invalid",
            ) from exc
        digest = hashlib.sha256(grant.signed_payload()).hexdigest()
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO privacy_consents(
                        consent_id, nonce, grant_json, digest, signature,
                        status, installed_at
                    ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?)
                    """,
                    (
                        grant.consent_id,
                        grant.nonce,
                        _canonical(grant.unsigned_dict()).decode("utf-8"),
                        digest,
                        grant.signature,
                        self._clock().isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise PrivacyError(
                PrivacyFailureCode.CONSENT_INVALID,
                "consent id or nonce already exists",
            ) from exc
        except sqlite3.Error as exc:
            raise PrivacyError(
                PrivacyFailureCode.STORAGE_ERROR,
                "consent could not be persisted",
            ) from exc
        return digest

    def revoke_consent(self, owner_id: str, consent_id: str) -> dict[str, object]:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT grant_json, status FROM privacy_consents WHERE consent_id = ?",
                (consent_id,),
            ).fetchone()
            if row is None:
                raise PrivacyError(
                    PrivacyFailureCode.CONSENT_INVALID,
                    "consent does not exist",
                )
            grant = json.loads(row["grant_json"])
            if grant.get("owner_id") != owner_id:
                raise PrivacyError(
                    PrivacyFailureCode.OWNER_MISMATCH,
                    "only the data owner can revoke consent",
                )
            self._connection.execute(
                "UPDATE privacy_consents SET status = 'REVOKED' WHERE consent_id = ?",
                (consent_id,),
            )
        return self._record_event(
            "CONSENT_REVOKED",
            {"owner_id": owner_id, "consent_id": consent_id},
        )

    def evaluate(self, request: PrivacyUseRequest) -> PrivacyDecision:
        self._validate_request(request)
        effect = PrivacyEffect.DENY
        reason = "OWNER_MISMATCH"
        consent_id: str | None = None
        if request.actor_id == request.owner_id:
            if request.destination in {
                DataDestination.LOCAL,
                DataDestination.OWNER_EXPORT,
            }:
                effect = PrivacyEffect.ALLOW
                reason = "OWNER_LOCAL_PURPOSE_ALLOWED"
            elif request.classification is DataClassification.PUBLIC:
                effect = PrivacyEffect.ALLOW
                reason = "PUBLIC_EXTERNAL_USE_ALLOWED"
            else:
                grant = self._load_active_consent(request)
                if grant is not None:
                    effect = PrivacyEffect.ALLOW
                    reason = "SIGNED_CONSENT_ALLOWED"
                    consent_id = grant.consent_id
                else:
                    reason = "SIGNED_CONSENT_REQUIRED"
        return self._record_decision(request, effect, reason, consent_id)

    def store(
        self,
        *,
        actor_id: str,
        owner_id: str,
        subject_id: str,
        data_id: str,
        classification: DataClassification,
        allowed_purposes: Sequence[DataPurpose],
        payload: Mapping[str, Any],
        retention_seconds: int,
    ) -> DataDescriptor:
        if actor_id != owner_id:
            raise PrivacyError(
                PrivacyFailureCode.OWNER_MISMATCH,
                "only the owner can store private data",
            )
        self._validate_id_fields(data_id, owner_id, subject_id)
        purposes = tuple(dict.fromkeys(allowed_purposes))
        if not purposes or not 1 <= retention_seconds <= 31_536_000:
            raise PrivacyError(
                PrivacyFailureCode.INVALID_INPUT,
                "privacy purposes or retention are invalid",
            )
        try:
            plaintext = _canonical(payload)
        except (TypeError, ValueError) as exc:
            raise PrivacyError(
                PrivacyFailureCode.INVALID_INPUT,
                "private payload must be bounded JSON",
            ) from exc
        if len(plaintext) > 8_388_608:
            raise PrivacyError(
                PrivacyFailureCode.INVALID_INPUT,
                "private payload exceeds the vault limit",
            )
        now = self._clock()
        descriptor = DataDescriptor(
            data_id=data_id,
            owner_id=owner_id,
            subject_id=subject_id,
            classification=classification,
            allowed_purposes=purposes,
            retention_until=(now + timedelta(seconds=retention_seconds)).isoformat(),
            plaintext_sha256=hashlib.sha256(plaintext).hexdigest(),
            created_at=now.isoformat(),
        )
        aad = _canonical(descriptor.to_dict())
        nonce, ciphertext = self._cipher.encrypt(plaintext, aad)
        row_digest = hashlib.sha256(
            aad + nonce.encode("ascii") + ciphertext.encode("ascii")
        ).hexdigest()
        try:
            with self._lock, self._connection:
                existing = self._connection.execute(
                    "SELECT descriptor_json, deleted_at FROM privacy_vault "
                    "WHERE data_id = ?",
                    (data_id,),
                ).fetchone()
                if existing is not None:
                    try:
                        previous = json.loads(existing["descriptor_json"])
                    except json.JSONDecodeError as exc:
                        raise PrivacyError(
                            PrivacyFailureCode.CORRUPT_DATA,
                            "existing private data descriptor is corrupt",
                        ) from exc
                    if (
                        existing["deleted_at"] is None
                        and previous.get("plaintext_sha256")
                        == descriptor.plaintext_sha256
                        and previous.get("owner_id") == owner_id
                    ):
                        return DataDescriptor(
                            data_id=previous["data_id"],
                            owner_id=previous["owner_id"],
                            subject_id=previous["subject_id"],
                            classification=DataClassification(
                                previous["classification"]
                            ),
                            allowed_purposes=tuple(
                                DataPurpose(item)
                                for item in previous["allowed_purposes"]
                            ),
                            retention_until=previous["retention_until"],
                            plaintext_sha256=previous["plaintext_sha256"],
                            created_at=previous["created_at"],
                            schema_version=int(previous["schema_version"]),
                        )
                    raise PrivacyError(
                        PrivacyFailureCode.INVALID_INPUT,
                        "data_id already exists",
                    )
                self._connection.execute(
                    """
                    INSERT INTO privacy_vault(
                        data_id, descriptor_json, nonce, ciphertext,
                        row_digest, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        data_id,
                        aad.decode("utf-8"),
                        nonce,
                        ciphertext,
                        row_digest,
                    ),
                )
        except PrivacyError:
            raise
        except sqlite3.Error as exc:
            raise PrivacyError(
                PrivacyFailureCode.STORAGE_ERROR,
                "private data could not be persisted",
            ) from exc
        self._record_event(
            "DATA_STORED",
            {
                "data_id": data_id,
                "owner_id": owner_id,
                "classification": classification.value,
                "plaintext_sha256": descriptor.plaintext_sha256,
            },
        )
        return descriptor

    def retrieve(
        self,
        *,
        actor_id: str,
        data_id: str,
        purpose: DataPurpose,
    ) -> dict[str, Any]:
        row, descriptor = self._load_vault_record(data_id)
        if descriptor.owner_id != actor_id:
            raise PrivacyError(
                PrivacyFailureCode.OWNER_MISMATCH,
                "private data owner does not match actor",
            )
        if purpose not in descriptor.allowed_purposes:
            raise PrivacyError(
                PrivacyFailureCode.PURPOSE_DENIED,
                "private data purpose is not allowed",
            )
        if self._clock() >= datetime.fromisoformat(descriptor.retention_until):
            raise PrivacyError(
                PrivacyFailureCode.DATA_EXPIRED,
                "private data retention period expired",
            )
        plaintext = self._cipher.decrypt(
            row["nonce"], row["ciphertext"], _canonical(descriptor.to_dict())
        )
        if hashlib.sha256(plaintext).hexdigest() != descriptor.plaintext_sha256:
            raise PrivacyError(
                PrivacyFailureCode.CORRUPT_DATA,
                "private data digest is invalid",
            )
        try:
            value = json.loads(plaintext)
        except json.JSONDecodeError as exc:
            raise PrivacyError(
                PrivacyFailureCode.CORRUPT_DATA,
                "decrypted private data is invalid JSON",
            ) from exc
        self._record_event(
            "DATA_ACCESSED",
            {"data_id": data_id, "actor_id": actor_id, "purpose": purpose.value},
        )
        return dict(value)

    def export_owner(self, owner_id: str) -> dict[str, object]:
        rows = self._connection.execute(
            "SELECT data_id FROM privacy_vault WHERE deleted_at IS NULL "
            "ORDER BY data_id"
        ).fetchall()
        records: list[dict[str, object]] = []
        for row in rows:
            try:
                vault_row, descriptor = self._load_vault_record(row["data_id"])
            except PrivacyError:
                continue
            if descriptor.owner_id != owner_id:
                continue
            payload = self.retrieve(
                actor_id=owner_id,
                data_id=descriptor.data_id,
                purpose=(
                    DataPurpose.EXPORT
                    if DataPurpose.EXPORT in descriptor.allowed_purposes
                    else descriptor.allowed_purposes[0]
                ),
            )
            records.append({"descriptor": descriptor.to_dict(), "payload": payload})
        body = {"schema_version": 1, "owner_id": owner_id, "records": records}
        digest = hashlib.sha256(_canonical(body)).hexdigest()
        receipt = self._record_event(
            "OWNER_EXPORTED",
            {"owner_id": owner_id, "records": len(records), "sha256": digest},
        )
        return {**body, "sha256": digest, "receipt": receipt}

    def delete_owner(self, owner_id: str) -> dict[str, object]:
        now = self._clock().isoformat()
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT data_id, descriptor_json FROM privacy_vault "
                "WHERE deleted_at IS NULL"
            ).fetchall()
            targets = [
                row["data_id"]
                for row in rows
                if json.loads(row["descriptor_json"]).get("owner_id") == owner_id
            ]
            for data_id in targets:
                self._connection.execute(
                    """
                    UPDATE privacy_vault
                    SET nonce = '', ciphertext = '', deleted_at = ?
                    WHERE data_id = ?
                    """,
                    (now, data_id),
                )
        return self._record_event(
            "OWNER_DATA_DELETED",
            {"owner_id": owner_id, "data_ids": targets, "deleted_at": now},
        )

    def purge_expired(self) -> int:
        rows = self._connection.execute(
            "SELECT data_id, descriptor_json FROM privacy_vault "
            "WHERE deleted_at IS NULL"
        ).fetchall()
        expired: list[str] = []
        now = self._clock()
        for row in rows:
            descriptor = json.loads(row["descriptor_json"])
            if now >= datetime.fromisoformat(descriptor["retention_until"]):
                expired.append(row["data_id"])
        with self._lock, self._connection:
            for data_id in expired:
                self._connection.execute(
                    """
                    UPDATE privacy_vault SET nonce = '', ciphertext = '', deleted_at = ?
                    WHERE data_id = ?
                    """,
                    (now.isoformat(), data_id),
                )
        if expired:
            self._record_event(
                "RETENTION_PURGED",
                {"data_ids": expired, "occurred_at": now.isoformat()},
            )
        return len(expired)

    def plaintext_absent(self, needle: str) -> bool:
        if not needle:
            return True
        rows = self._connection.execute(
            "SELECT descriptor_json, nonce, ciphertext FROM privacy_vault"
        ).fetchall()
        return all(
            needle not in "".join(str(value) for value in tuple(row)) for row in rows
        )

    def audit_chain_valid(self) -> bool:
        try:
            rows = self._connection.execute(
                "SELECT * FROM privacy_audit ORDER BY event_id"
            ).fetchall()
        except sqlite3.Error:
            return False
        previous = "0" * 64
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                return False
            content = {
                "occurred_at": row["occurred_at"],
                "event": row["event"],
                "payload": payload,
                "previous_sha256": row["previous_sha256"],
            }
            expected = hashlib.sha256(_canonical(content)).hexdigest()
            if row["previous_sha256"] != previous or row["event_sha256"] != expected:
                return False
            previous = expected
        return True

    def status(self) -> dict[str, object]:
        vault = self._connection.execute(
            "SELECT COUNT(*) FROM privacy_vault WHERE deleted_at IS NULL"
        ).fetchone()[0]
        consents = self._connection.execute(
            "SELECT COUNT(*) FROM privacy_consents WHERE status = 'ACTIVE'"
        ).fetchone()[0]
        return {
            "ready": self.audit_chain_valid(),
            "encrypted_records": int(vault),
            "active_consents": int(consents),
            "trusted_consent_signers": len(self._consent_keys),
            "audit_chain_valid": self.audit_chain_valid(),
        }

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _load_active_consent(self, request: PrivacyUseRequest) -> ConsentGrant | None:
        if not request.consent_id:
            return None
        row = self._connection.execute(
            "SELECT * FROM privacy_consents WHERE consent_id = ?",
            (request.consent_id,),
        ).fetchone()
        if row is None:
            return None
        if row["status"] != "ACTIVE":
            raise PrivacyError(
                PrivacyFailureCode.CONSENT_REVOKED,
                "consent is revoked",
            )
        raw = json.loads(row["grant_json"])
        if hashlib.sha256(_canonical(raw)).hexdigest() != row["digest"]:
            raise PrivacyError(
                PrivacyFailureCode.CORRUPT_DATA,
                "stored consent digest is invalid",
            )
        grant = ConsentGrant(
            consent_id=raw["consent_id"],
            approver_id=raw["approver_id"],
            owner_id=raw["owner_id"],
            subject_id=raw["subject_id"],
            classifications=tuple(
                DataClassification(item) for item in raw["classifications"]
            ),
            purposes=tuple(DataPurpose(item) for item in raw["purposes"]),
            providers=tuple(raw["providers"]),
            issued_at=raw["issued_at"],
            expires_at=raw["expires_at"],
            nonce=raw["nonce"],
            signature=row["signature"],
            policy_version=int(raw["policy_version"]),
            schema_version=int(raw["schema_version"]),
        )
        self._validate_consent_contract(grant)
        key = self._consent_keys.get(grant.approver_id)
        try:
            if key is None:
                raise InvalidSignature
            key.verify(_decode(grant.signature), grant.signed_payload())
        except (InvalidSignature, ValueError) as exc:
            raise PrivacyError(
                PrivacyFailureCode.CONSENT_INVALID,
                "stored consent signature is invalid",
            ) from exc
        if self._clock() >= datetime.fromisoformat(grant.expires_at):
            raise PrivacyError(
                PrivacyFailureCode.CONSENT_EXPIRED,
                "consent expired",
            )
        if (
            grant.owner_id != request.owner_id
            or grant.subject_id != request.subject_id
            or request.classification not in grant.classifications
            or request.purpose not in grant.purposes
            or request.provider_id not in grant.providers
        ):
            raise PrivacyError(
                PrivacyFailureCode.CONSENT_INVALID,
                "consent scope does not match the data use request",
            )
        return grant

    def _load_vault_record(self, data_id: str) -> tuple[sqlite3.Row, DataDescriptor]:
        row = self._connection.execute(
            "SELECT * FROM privacy_vault WHERE data_id = ?", (data_id,)
        ).fetchone()
        if row is None:
            raise PrivacyError(
                PrivacyFailureCode.DATA_NOT_FOUND,
                "private data does not exist",
            )
        if row["deleted_at"] is not None:
            raise PrivacyError(
                PrivacyFailureCode.DATA_DELETED,
                "private data was deleted",
            )
        try:
            raw = json.loads(row["descriptor_json"])
            descriptor = DataDescriptor(
                data_id=raw["data_id"],
                owner_id=raw["owner_id"],
                subject_id=raw["subject_id"],
                classification=DataClassification(raw["classification"]),
                allowed_purposes=tuple(
                    DataPurpose(item) for item in raw["allowed_purposes"]
                ),
                retention_until=raw["retention_until"],
                plaintext_sha256=raw["plaintext_sha256"],
                created_at=raw["created_at"],
                schema_version=int(raw["schema_version"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PrivacyError(
                PrivacyFailureCode.CORRUPT_DATA,
                "private data descriptor is corrupt",
            ) from exc
        expected = hashlib.sha256(
            _canonical(descriptor.to_dict())
            + row["nonce"].encode("ascii")
            + row["ciphertext"].encode("ascii")
        ).hexdigest()
        if expected != row["row_digest"]:
            raise PrivacyError(
                PrivacyFailureCode.CORRUPT_DATA,
                "private data row digest is invalid",
            )
        return row, descriptor

    def _record_decision(
        self,
        request: PrivacyUseRequest,
        effect: PrivacyEffect,
        reason_code: str,
        consent_id: str | None,
    ) -> PrivacyDecision:
        request_digest = hashlib.sha256(_canonical(request.to_dict())).hexdigest()
        receipt = self._record_event(
            "PRIVACY_DECISION",
            {
                "request_digest": request_digest,
                "effect": effect.value,
                "reason_code": reason_code,
                "consent_id": consent_id,
            },
        )
        return PrivacyDecision(
            decision_id=int(receipt["event_id"]),
            effect=effect,
            reason_code=reason_code,
            request_digest=request_digest,
            consent_id=consent_id,
            occurred_at=str(receipt["occurred_at"]),
            previous_receipt_sha256=str(receipt["previous_sha256"]),
            receipt_sha256=str(receipt["event_sha256"]),
        )

    def _record_event(
        self, event: str, payload: Mapping[str, Any]
    ) -> dict[str, object]:
        occurred = self._clock().isoformat()
        with self._lock, self._connection:
            previous_row = self._connection.execute(
                "SELECT event_sha256 FROM privacy_audit ORDER BY event_id DESC LIMIT 1"
            ).fetchone()
            previous = previous_row[0] if previous_row else "0" * 64
            content = {
                "occurred_at": occurred,
                "event": event,
                "payload": dict(payload),
                "previous_sha256": previous,
            }
            digest = hashlib.sha256(_canonical(content)).hexdigest()
            cursor = self._connection.execute(
                """
                INSERT INTO privacy_audit(
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
        return {
            "event_id": int(cursor.lastrowid),
            "occurred_at": occurred,
            "event": event,
            "previous_sha256": previous,
            "event_sha256": digest,
        }

    def _validate_request(self, request: PrivacyUseRequest) -> None:
        self._validate_id_fields(
            request.request_id,
            request.actor_id,
            request.owner_id,
            request.subject_id,
            request.data_id,
            request.provider_id,
        )
        if request.schema_version != _SCHEMA_VERSION or not re.fullmatch(
            r"[0-9a-f]{64}", request.payload_sha256
        ):
            raise PrivacyError(
                PrivacyFailureCode.INVALID_INPUT,
                "privacy use request is invalid",
            )

    def _validate_consent_contract(self, grant: ConsentGrant) -> None:
        self._validate_id_fields(
            grant.consent_id,
            grant.approver_id,
            grant.owner_id,
            grant.subject_id,
            grant.nonce,
            *grant.providers,
        )
        try:
            issued = datetime.fromisoformat(grant.issued_at)
            expires = datetime.fromisoformat(grant.expires_at)
        except ValueError as exc:
            raise PrivacyError(
                PrivacyFailureCode.CONSENT_INVALID,
                "consent timestamps are invalid",
            ) from exc
        if (
            grant.schema_version != _SCHEMA_VERSION
            or grant.policy_version <= 0
            or not grant.classifications
            or not grant.purposes
            or not grant.providers
            or issued.tzinfo is None
            or expires.tzinfo is None
            or expires <= issued
        ):
            raise PrivacyError(
                PrivacyFailureCode.CONSENT_INVALID,
                "consent contract is invalid",
            )

    @staticmethod
    def _validate_id_fields(*values: str) -> None:
        if any(
            not isinstance(value, str) or not _SAFE_ID.fullmatch(value)
            for value in values
        ):
            raise PrivacyError(
                PrivacyFailureCode.INVALID_INPUT,
                "privacy identifier is invalid",
            )

    def _load_or_create_salt(self) -> bytes:
        with self._connection:
            row = self._connection.execute(
                "SELECT value FROM privacy_metadata WHERE key = 'kdf_salt'"
            ).fetchone()
            if row is None:
                salt = os.urandom(16)
                self._connection.execute(
                    "INSERT INTO privacy_metadata(key, value) VALUES ('kdf_salt', ?)",
                    (_encode(salt),),
                )
                return salt
        salt = _decode(row["value"])
        if len(salt) != 16:
            raise PrivacyError(
                PrivacyFailureCode.CORRUPT_DATA,
                "privacy KDF metadata is corrupt",
            )
        return salt

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS privacy_metadata(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS privacy_consents(
                    consent_id TEXT PRIMARY KEY,
                    nonce TEXT NOT NULL UNIQUE,
                    grant_json TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    status TEXT NOT NULL,
                    installed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS privacy_vault(
                    data_id TEXT PRIMARY KEY,
                    descriptor_json TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    ciphertext TEXT NOT NULL,
                    row_digest TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS privacy_audit(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_sha256 TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL UNIQUE
                );
                """
            )


class PrivacyMemoryCodec:
    """Store episodic payloads as encrypted references in the privacy vault."""

    def __init__(self, privacy: SovereignPrivacy, retention_seconds: int = 2_592_000):
        self.privacy = privacy
        self.retention_seconds = retention_seconds

    def encode_event(self, event: Any) -> str:
        data_id = f"memory:{event.event_id}"
        self.privacy.store(
            actor_id=str(event.session_id),
            owner_id=str(event.session_id),
            subject_id=str(event.session_id),
            data_id=data_id,
            classification=DataClassification.CONFIDENTIAL,
            allowed_purposes=(DataPurpose.MEMORY, DataPurpose.CORE_REASONING),
            payload=event.payload,
            retention_seconds=self.retention_seconds,
        )
        return json.dumps({"privacy_ref": data_id}, sort_keys=True)

    def decode_payload(self, stored: str, owner_id: str) -> dict[str, Any]:
        try:
            reference = json.loads(stored)["privacy_ref"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise PrivacyError(
                PrivacyFailureCode.CORRUPT_DATA,
                "episodic privacy reference is invalid",
            ) from exc
        return self.privacy.retrieve(
            actor_id=owner_id,
            data_id=str(reference),
            purpose=DataPurpose.MEMORY,
        )


def create_consent_grant(
    *,
    approver_id: str,
    owner_id: str,
    subject_id: str,
    classifications: Sequence[DataClassification],
    purposes: Sequence[DataPurpose],
    providers: Sequence[str],
    issued_at: str,
    expires_at: str,
    signer: Callable[[bytes], bytes],
    consent_id: str | None = None,
    nonce: str | None = None,
) -> ConsentGrant:
    unsigned = ConsentGrant(
        consent_id=consent_id or f"consent-{uuid.uuid4()}",
        approver_id=approver_id,
        owner_id=owner_id,
        subject_id=subject_id,
        classifications=tuple(classifications),
        purposes=tuple(purposes),
        providers=tuple(providers),
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce or f"nonce-{uuid.uuid4()}",
        signature="",
    )
    signature = signer(unsigned.signed_payload())
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise PrivacyError(
            PrivacyFailureCode.CONSENT_INVALID,
            "consent signer returned an invalid signature",
        )
    return replace(unsigned, signature=_encode(signature))


__all__ = [
    "ConsentGrant",
    "DataClassification",
    "DataDestination",
    "DataPurpose",
    "PrivacyDecision",
    "PrivacyEffect",
    "PrivacyError",
    "PrivacyFailureCode",
    "PrivacyMemoryCodec",
    "PrivacyUseRequest",
    "SovereignPrivacy",
    "create_consent_grant",
    "redact_private",
]
