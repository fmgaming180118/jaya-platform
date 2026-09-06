"""Pillar 18 — Zero-Trust Skepticism.

Every external data input — web search results, RAG payloads, twin
messages — passes through ``ZeroTrustFilter.validate()`` before touching
the engine.  Untrusted sources must justify their content; known-safe
sources get a fast path.

Threat model
------------
* Prompt injection via web search results embedding instructions.
* RAG poisoning (adversarial document chunks).
* Rogue twin messages (man-in-the-middle or corrupted peer).
* Command hijacking via crafted user input.
"""

import hashlib
import json
import logging
import math
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, cast

from jaya_core.providers import (
    NativeProviderError,
    TrustedZeroTrustGate,
    ZeroTrustAuthorizationContract,
    get_trusted_zero_trust_gate,
)

logger = logging.getLogger("ZeroTrust")

_TRUST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$")
_STORAGE_SCHEMA_VERSION = 1
_MAX_ENVELOPE_PAYLOAD_BYTES = 8_388_608
_ENVELOPE_FIELDS = {
    "schema_version",
    "envelope_id",
    "principal_id",
    "node_id",
    "capability_id",
    "payload_sha256",
    "policy_receipt_sha256",
    "privacy_receipt_sha256",
    "issued_at",
    "expires_at",
    "nonce",
    "attestation",
}


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TrustEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class TrustFailureCode(str, Enum):
    INVALID_INPUT = "ZERO_TRUST_INVALID_INPUT"
    PRINCIPAL_UNKNOWN = "ZERO_TRUST_PRINCIPAL_UNKNOWN"
    PRINCIPAL_REVOKED = "ZERO_TRUST_PRINCIPAL_REVOKED"
    PRINCIPAL_STATE_UNAVAILABLE = "ZERO_TRUST_PRINCIPAL_STATE_UNAVAILABLE"
    PRINCIPAL_KEY_STALE = "ZERO_TRUST_PRINCIPAL_KEY_STALE"
    NODE_MISMATCH = "ZERO_TRUST_NODE_MISMATCH"
    CAPABILITY_DENIED = "ZERO_TRUST_CAPABILITY_DENIED"
    PAYLOAD_MISMATCH = "ZERO_TRUST_PAYLOAD_MISMATCH"
    ATTESTATION_INVALID = "ZERO_TRUST_ATTESTATION_INVALID"
    ATTESTATION_UNAVAILABLE = "ZERO_TRUST_ATTESTATION_UNAVAILABLE"
    EXPIRED = "ZERO_TRUST_EXPIRED"
    CLOCK_UNAVAILABLE = "ZERO_TRUST_CLOCK_UNAVAILABLE"
    PAYLOAD_TOO_LARGE = "ZERO_TRUST_PAYLOAD_TOO_LARGE"
    REPLAY_DETECTED = "ZERO_TRUST_REPLAY_DETECTED"
    STORAGE_ERROR = "ZERO_TRUST_STORAGE_ERROR"
    CORRUPT_AUDIT = "ZERO_TRUST_CORRUPT_AUDIT"
    STORAGE_SCHEMA_UNSUPPORTED = "ZERO_TRUST_STORAGE_SCHEMA_UNSUPPORTED"
    PROVIDER_UNAVAILABLE = "ZERO_TRUST_PROVIDER_UNAVAILABLE"


class TrustError(RuntimeError):
    def __init__(self, code: TrustFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class TrustEnvelope:
    envelope_id: str
    principal_id: str
    node_id: str
    capability_id: str
    payload_sha256: str
    policy_receipt_sha256: str
    privacy_receipt_sha256: str
    issued_at: str
    expires_at: str
    nonce: str
    attestation: Mapping[str, object]
    schema_version: int = 1

    def unsigned_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("attestation")
        return value

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "attestation": dict(self.attestation)}


@dataclass(frozen=True, slots=True)
class TrustDecision:
    decision_id: int
    effect: TrustEffect
    reason_code: str
    envelope_digest: str
    occurred_at: str
    previous_receipt_sha256: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["effect"] = self.effect.value
        return value


def create_trust_envelope(
    *,
    principal_id: str,
    node_id: str,
    capability_id: str,
    payload: Mapping[str, Any],
    policy_receipt_sha256: str,
    privacy_receipt_sha256: str,
    signer: Callable[[str, str], Mapping[str, object]],
    now: datetime | None = None,
    ttl_seconds: int = 30,
) -> TrustEnvelope:
    """Create a short-lived, payload-bound envelope signed by DNA Anchor."""

    issued = now or _utc_now()
    if issued.tzinfo is None or not 1 <= ttl_seconds <= 300:
        raise TrustError(
            TrustFailureCode.INVALID_INPUT,
            "trust envelope timestamp or TTL is invalid",
        )
    try:
        encoded_payload = _canonical(payload)
    except (TypeError, ValueError) as exc:
        raise TrustError(
            TrustFailureCode.INVALID_INPUT,
            "trust payload must be bounded JSON",
        ) from exc
    if len(encoded_payload) > _MAX_ENVELOPE_PAYLOAD_BYTES:
        raise TrustError(
            TrustFailureCode.PAYLOAD_TOO_LARGE,
            "trust payload exceeds the envelope limit",
        )
    payload_digest = hashlib.sha256(encoded_payload).hexdigest()
    unsigned = TrustEnvelope(
        envelope_id=f"trust-{uuid.uuid4()}",
        principal_id=principal_id,
        node_id=node_id,
        capability_id=capability_id,
        payload_sha256=payload_digest,
        policy_receipt_sha256=policy_receipt_sha256,
        privacy_receipt_sha256=privacy_receipt_sha256,
        issued_at=issued.isoformat(),
        expires_at=(issued + timedelta(seconds=ttl_seconds)).isoformat(),
        nonce=f"nonce-{uuid.uuid4()}",
        attestation={},
    )
    attestation = signer("zero_trust.capability", unsigned.digest)
    if not isinstance(attestation, Mapping):
        raise TrustError(
            TrustFailureCode.ATTESTATION_INVALID,
            "trust signer returned an invalid attestation",
        )
    return replace(unsigned, attestation=dict(attestation))


class ZeroTrustAuthority:
    """Persistent authentication, authorization, replay, and audit boundary."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        attestation_verifier: Callable[[Mapping[str, object]], bool],
        principal_state_resolver: (Callable[[str], Mapping[str, object] | None] | None) = None,
        clock: Callable[[], datetime] = _utc_now,
        storage_timeout_seconds: float = 5.0,
        max_clock_skew_seconds: float = 5.0,
        max_payload_bytes: int = 1_048_576,
        authorization_gate: TrustedZeroTrustGate | None = None,
    ) -> None:
        if not callable(attestation_verifier):
            raise TrustError(
                TrustFailureCode.INVALID_INPUT,
                "attestation verifier must be callable",
            )
        if principal_state_resolver is not None and not callable(principal_state_resolver):
            raise TrustError(
                TrustFailureCode.INVALID_INPUT,
                "principal state resolver must be callable",
            )
        if (
            isinstance(storage_timeout_seconds, bool)
            or not isinstance(storage_timeout_seconds, (int, float))
            or not 0.001 <= float(storage_timeout_seconds) <= 30.0
            or isinstance(max_clock_skew_seconds, bool)
            or not isinstance(max_clock_skew_seconds, (int, float))
            or not 0 <= float(max_clock_skew_seconds) <= 300.0
            or type(max_payload_bytes) is not int
            or not 1_024 <= max_payload_bytes <= _MAX_ENVELOPE_PAYLOAD_BYTES
        ):
            raise TrustError(
                TrustFailureCode.INVALID_INPUT,
                "zero-trust resource limits are invalid",
            )
        self._clock = clock
        self._verifier = attestation_verifier
        self._attestation_cache: dict[str, bool] = {}
        self._principal_state_resolver = principal_state_resolver
        self._max_clock_skew_seconds = float(max_clock_skew_seconds)
        self._max_payload_bytes = max_payload_bytes
        try:
            self._authorization_gate = authorization_gate or get_trusted_zero_trust_gate()
        except NativeProviderError as exc:
            raise TrustError(
                TrustFailureCode.PROVIDER_UNAVAILABLE,
                "trusted zero-trust authorization provider is unavailable",
            ) from exc
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                str(db_path),
                timeout=float(storage_timeout_seconds),
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute(
                f"PRAGMA busy_timeout = {max(1, int(storage_timeout_seconds * 1_000))}"
            )
            if str(db_path) != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._create_schema()
            if not self.audit_chain_valid():
                raise TrustError(
                    TrustFailureCode.CORRUPT_AUDIT,
                    "zero-trust audit chain is corrupt",
                )
        except TrustError:
            raise
        except sqlite3.Error as exc:
            raise TrustError(
                TrustFailureCode.STORAGE_ERROR,
                "zero-trust authority storage is unavailable",
            ) from exc

    def ensure_principal(
        self,
        principal_id: str,
        node_id: str,
        capabilities: Sequence[str],
    ) -> None:
        self._validate_ids(principal_id, node_id, *capabilities)
        normalized = tuple(sorted(set(capabilities)))
        if not normalized:
            raise TrustError(
                TrustFailureCode.INVALID_INPUT,
                "principal must have at least one capability",
            )
        encoded = json.dumps(normalized, separators=(",", ":"))
        try:
            with self._lock, self._connection:
                row = self._connection.execute(
                    "SELECT node_id, capabilities_json, status FROM trust_principals "
                    "WHERE principal_id = ?",
                    (principal_id,),
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        "INSERT INTO trust_principals(principal_id, node_id, "
                        "capabilities_json, status, enrolled_at) "
                        "VALUES (?, ?, ?, 'ACTIVE', ?)",
                        (principal_id, node_id, encoded, self._clock_now().isoformat()),
                    )
                    self._record_event(
                        "PRINCIPAL_ENROLLED",
                        {
                            "principal_id": principal_id,
                            "node_id": node_id,
                            "capabilities": list(normalized),
                        },
                    )
                    return
                if row["node_id"] != node_id or row["capabilities_json"] != encoded:
                    raise TrustError(
                        TrustFailureCode.INVALID_INPUT,
                        "principal enrollment conflicts with persisted scope",
                    )
                if row["status"] != "ACTIVE":
                    raise TrustError(
                        TrustFailureCode.PRINCIPAL_REVOKED,
                        "principal is revoked",
                    )
        except TrustError:
            raise
        except sqlite3.Error as exc:
            raise TrustError(
                TrustFailureCode.STORAGE_ERROR,
                "principal enrollment storage is unavailable",
            ) from exc

    def revoke_principal(self, principal_id: str) -> None:
        self._validate_ids(principal_id)
        try:
            with self._lock, self._connection:
                changed = self._connection.execute(
                    "UPDATE trust_principals SET status = 'REVOKED' "
                    "WHERE principal_id = ? AND status = 'ACTIVE'",
                    (principal_id,),
                ).rowcount
                if not changed:
                    raise TrustError(
                        TrustFailureCode.PRINCIPAL_UNKNOWN,
                        "active principal does not exist",
                    )
                self._record_event("PRINCIPAL_REVOKED", {"principal_id": principal_id})
        except TrustError:
            raise
        except sqlite3.Error as exc:
            raise TrustError(
                TrustFailureCode.STORAGE_ERROR,
                "principal revocation storage is unavailable",
            ) from exc

    def authorize(
        self,
        envelope: TrustEnvelope,
        payload: Mapping[str, Any],
    ) -> TrustDecision:
        if not isinstance(envelope, TrustEnvelope) or not isinstance(payload, Mapping):
            raise TrustError(
                TrustFailureCode.INVALID_INPUT,
                "zero-trust authorization requires a structured envelope and payload",
            )
        if not self.audit_chain_valid():
            raise TrustError(
                TrustFailureCode.CORRUPT_AUDIT,
                "zero-trust audit chain is corrupt",
            )
        reason = self._validate_authorization(envelope, payload)
        effect = TrustEffect.ALLOW if reason == "VERIFIED_LEAST_PRIVILEGE" else TrustEffect.DENY
        return self._record_decision(
            envelope,
            effect,
            reason,
            consume_nonce=effect is TrustEffect.ALLOW,
        )

    def validates(
        self,
        capability_id: str,
        payload: Mapping[str, Any],
        decision: TrustDecision,
    ) -> bool:
        if not isinstance(decision, TrustDecision) or decision.effect is not TrustEffect.ALLOW:
            return False
        try:
            row = self._connection.execute(
                "SELECT envelope_json, envelope_digest, effect, reason_code, "
                "occurred_at, previous_receipt_sha256, receipt_sha256 "
                "FROM trust_decisions "
                "WHERE decision_id = ?",
                (decision.decision_id,),
            ).fetchone()
            envelope = json.loads(row["envelope_json"]) if row else {}
            payload_digest = hashlib.sha256(_canonical(payload)).hexdigest()
        except (sqlite3.Error, TypeError, ValueError, json.JSONDecodeError):
            return False
        return bool(
            row
            and row["effect"] == TrustEffect.ALLOW.value
            and row["effect"] == decision.effect.value
            and row["reason_code"] == decision.reason_code
            and row["envelope_digest"] == decision.envelope_digest
            and row["occurred_at"] == decision.occurred_at
            and row["previous_receipt_sha256"] == decision.previous_receipt_sha256
            and row["receipt_sha256"] == decision.receipt_sha256
            and self._stored_envelope_digest(envelope) == row["envelope_digest"]
            and envelope.get("capability_id") == capability_id
            and envelope.get("payload_sha256") == payload_digest
            and self.audit_chain_valid()
        )

    def _validate_authorization(self, envelope: TrustEnvelope, payload: Mapping[str, Any]) -> str:
        try:
            self._validate_ids(
                envelope.envelope_id,
                envelope.principal_id,
                envelope.node_id,
                envelope.capability_id,
                envelope.nonce,
            )
            issued = datetime.fromisoformat(envelope.issued_at)
            expires = datetime.fromisoformat(envelope.expires_at)
            encoded_payload = _canonical(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            return TrustFailureCode.INVALID_INPUT.value
        if len(encoded_payload) > self._max_payload_bytes:
            return TrustFailureCode.PAYLOAD_TOO_LARGE.value
        payload_digest = hashlib.sha256(encoded_payload).hexdigest()
        if envelope.schema_version != 1 or issued.tzinfo is None or expires.tzinfo is None:
            return TrustFailureCode.INVALID_INPUT.value
        try:
            now = self._clock_now()
        except TrustError as exc:
            return exc.code.value
        if not re.fullmatch(r"[0-9a-f]{64}", envelope.policy_receipt_sha256):
            return TrustFailureCode.INVALID_INPUT.value
        if not re.fullmatch(r"[0-9a-f]{64}", envelope.privacy_receipt_sha256):
            return TrustFailureCode.INVALID_INPUT.value
        if (
            now < issued - timedelta(seconds=self._max_clock_skew_seconds)
            or now >= expires
            or expires - issued > timedelta(minutes=5)
        ):
            return TrustFailureCode.EXPIRED.value
        row = self._connection.execute(
            "SELECT * FROM trust_principals WHERE principal_id = ?",
            (envelope.principal_id,),
        ).fetchone()
        principal_status = 0 if row is None else (1 if row["status"] == "ACTIVE" else 2)
        principal_state = self._principal_state_code(envelope) if principal_status == 1 else 0
        capabilities = (
            tuple(cast(list[str], json.loads(row["capabilities_json"]))) if row is not None else ()
        )
        contract = ZeroTrustAuthorizationContract(
            envelope_id=envelope.envelope_id,
            principal_id=envelope.principal_id,
            envelope_node_id=envelope.node_id,
            capability_id=envelope.capability_id,
            nonce=envelope.nonce,
            principal_status=principal_status,
            principal_state=principal_state,
            attestation_state=0,
            persisted_node_id=str(row["node_id"]) if row is not None else None,
            capability_ids=capabilities,
            claimed_payload_sha256=envelope.payload_sha256,
            actual_payload_sha256=payload_digest,
        )
        try:
            trusted_decision = self._authorization_gate.evaluate(contract)
        except NativeProviderError as exc:
            raise TrustError(
                TrustFailureCode.PROVIDER_UNAVAILABLE,
                "trusted zero-trust authorization evaluation failed",
            ) from exc
        if trusted_decision.reason_code != "ATTESTATION_REQUIRED":
            if trusted_decision.effect not in {1, 2}:
                raise TrustError(
                    TrustFailureCode.PROVIDER_UNAVAILABLE,
                    "trusted zero-trust provider returned an invalid preliminary effect",
                )
            return trusted_decision.reason_code
        if trusted_decision.effect != 3:
            raise TrustError(
                TrustFailureCode.PROVIDER_UNAVAILABLE,
                "trusted zero-trust provider returned an invalid attestation request",
            )
        attestation = dict(envelope.attestation)
        try:
            verified = self._verify_attestation(attestation)
            attestation_state = (
                1
                if (
                    attestation.get("purpose") == "zero_trust.capability"
                    and attestation.get("payload_sha256") == envelope.digest
                    and verified is True
                )
                else 2
            )
        except Exception:  # noqa: BLE001 - external verifier boundary
            attestation_state = 3
        try:
            trusted_decision = self._authorization_gate.evaluate(
                replace(contract, attestation_state=attestation_state)
            )
        except NativeProviderError as exc:
            raise TrustError(
                TrustFailureCode.PROVIDER_UNAVAILABLE,
                "trusted zero-trust attestation evaluation failed",
            ) from exc
        if trusted_decision.effect not in {1, 2} or trusted_decision.reason_code == (
            "ATTESTATION_REQUIRED"
        ):
            raise TrustError(
                TrustFailureCode.PROVIDER_UNAVAILABLE,
                "trusted zero-trust provider returned an invalid final decision",
            )
        return trusted_decision.reason_code

    def _verify_attestation(self, attestation: Mapping[str, object]) -> bool:
        sig = str(attestation.get("signature") or "")
        digest = str(attestation.get("payload_sha256") or "")
        brain_id = str(attestation.get("brain_id") or "")
        key_version = str(attestation.get("key_version") or "")
        cache_key = f"{brain_id}:{key_version}:{digest}:{sig}"
        if cache_key in self._attestation_cache:
            return self._attestation_cache[cache_key]
        verified = bool(self._verifier(attestation))
        if verified:
            if len(self._attestation_cache) < 100_000:
                self._attestation_cache[cache_key] = True
        return verified

    def _principal_state_code(self, envelope: TrustEnvelope) -> int:
        resolver = self._principal_state_resolver
        if resolver is None:
            return 0
        try:
            state = resolver(envelope.principal_id)
        except Exception:  # noqa: BLE001 - external identity registry boundary
            return 3
        if state is None:
            return 1
        if not isinstance(state, Mapping):
            return 3
        if state.get("active") is not True:
            return 2
        active_version = state.get("key_version")
        attested_version = envelope.attestation.get("key_version")
        if (
            type(active_version) is not int
            or active_version <= 0
            or type(attested_version) is not int
            or attested_version <= 0
        ):
            return 3
        if active_version != attested_version:
            return 4
        return 0

    def _record_decision(
        self,
        envelope: TrustEnvelope,
        effect: TrustEffect,
        reason: str,
        *,
        consume_nonce: bool,
    ) -> TrustDecision:
        occurred = self._clock_now().isoformat()
        try:
            with self._lock, self._connection:
                if consume_nonce:
                    try:
                        self._connection.execute(
                            "INSERT INTO trust_nonces(nonce, envelope_id, "
                            "consumed_at) VALUES (?, ?, ?)",
                            (envelope.nonce, envelope.envelope_id, occurred),
                        )
                    except sqlite3.IntegrityError:
                        effect = TrustEffect.DENY
                        reason = TrustFailureCode.REPLAY_DETECTED.value
                previous_row = self._connection.execute(
                    "SELECT receipt_sha256 FROM trust_decisions ORDER BY decision_id DESC LIMIT 1"
                ).fetchone()
                previous = previous_row[0] if previous_row else "0" * 64
                content = {
                    "envelope_digest": envelope.digest,
                    "effect": effect.value,
                    "reason_code": reason,
                    "occurred_at": occurred,
                    "previous_receipt_sha256": previous,
                }
                receipt = hashlib.sha256(_canonical(content)).hexdigest()
                cursor = self._connection.execute(
                    "INSERT INTO trust_decisions(envelope_json, envelope_digest, "
                    "effect, reason_code, occurred_at, previous_receipt_sha256, "
                    "receipt_sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        _canonical(envelope.to_dict()).decode(),
                        envelope.digest,
                        effect.value,
                        reason,
                        occurred,
                        previous,
                        receipt,
                    ),
                )
        except sqlite3.Error as exc:
            raise TrustError(
                TrustFailureCode.STORAGE_ERROR,
                "zero-trust decision storage is unavailable",
            ) from exc
        if cursor.lastrowid is None:
            raise TrustError(
                TrustFailureCode.STORAGE_ERROR,
                "zero-trust decision identifier is unavailable",
            )
        return TrustDecision(
            decision_id=int(cursor.lastrowid),
            effect=effect,
            reason_code=reason,
            envelope_digest=envelope.digest,
            occurred_at=occurred,
            previous_receipt_sha256=previous,
            receipt_sha256=receipt,
        )

    def _record_event(self, event: str, payload: Mapping[str, Any]) -> None:
        occurred = self._clock_now().isoformat()
        try:
            with self._lock, self._connection:
                previous_row = self._connection.execute(
                    "SELECT event_sha256 FROM trust_audit ORDER BY event_id DESC LIMIT 1"
                ).fetchone()
                previous = previous_row[0] if previous_row else "0" * 64
                content = {
                    "occurred_at": occurred,
                    "event": event,
                    "payload": dict(payload),
                    "previous_sha256": previous,
                }
                digest = hashlib.sha256(_canonical(content)).hexdigest()
                self._connection.execute(
                    "INSERT INTO trust_audit(occurred_at, event, payload_json, "
                    "previous_sha256, event_sha256) VALUES (?, ?, ?, ?, ?)",
                    (occurred, event, _canonical(payload).decode(), previous, digest),
                )
        except sqlite3.Error as exc:
            raise TrustError(
                TrustFailureCode.STORAGE_ERROR,
                "zero-trust audit storage is unavailable",
            ) from exc

    def audit_chain_valid(self) -> bool:
        try:
            with self._lock:
                rows = self._connection.execute(
                    "SELECT * FROM trust_audit ORDER BY event_id"
                ).fetchall()
                principal_rows = self._connection.execute(
                    "SELECT principal_id, node_id, capabilities_json, status "
                    "FROM trust_principals ORDER BY principal_id"
                ).fetchall()
                decisions = self._connection.execute(
                    "SELECT * FROM trust_decisions ORDER BY decision_id"
                ).fetchall()
                nonce_rows = self._connection.execute(
                    "SELECT nonce, envelope_id, consumed_at FROM trust_nonces ORDER BY nonce"
                ).fetchall()
            previous = "0" * 64
            expected_principals: dict[str, tuple[str, str, str]] = {}
            for row in rows:
                payload = json.loads(row["payload_json"])
                content = {
                    "occurred_at": row["occurred_at"],
                    "event": row["event"],
                    "payload": payload,
                    "previous_sha256": row["previous_sha256"],
                }
                digest = hashlib.sha256(_canonical(content)).hexdigest()
                if row["previous_sha256"] != previous or row["event_sha256"] != digest:
                    return False
                if row["event"] == "PRINCIPAL_ENROLLED":
                    if not isinstance(payload, dict) or set(payload) != {
                        "principal_id",
                        "node_id",
                        "capabilities",
                    }:
                        return False
                    principal_id = payload["principal_id"]
                    node_id = payload["node_id"]
                    capabilities = payload["capabilities"]
                    if (
                        not isinstance(principal_id, str)
                        or not isinstance(node_id, str)
                        or not isinstance(capabilities, list)
                        or not capabilities
                        or any(not isinstance(item, str) for item in capabilities)
                        or capabilities != sorted(set(capabilities))
                        or principal_id in expected_principals
                    ):
                        return False
                    self._validate_ids(principal_id, node_id, *capabilities)
                    expected_principals[principal_id] = (
                        node_id,
                        json.dumps(tuple(capabilities), separators=(",", ":")),
                        "ACTIVE",
                    )
                elif row["event"] == "PRINCIPAL_REVOKED":
                    if not isinstance(payload, dict) or set(payload) != {"principal_id"}:
                        return False
                    principal_id = payload["principal_id"]
                    state = expected_principals.get(principal_id)
                    if state is None or state[2] != "ACTIVE":
                        return False
                    expected_principals[principal_id] = (
                        state[0],
                        state[1],
                        "REVOKED",
                    )
                else:
                    return False
                previous = digest
            actual_principals = {
                row["principal_id"]: (
                    row["node_id"],
                    row["capabilities_json"],
                    row["status"],
                )
                for row in principal_rows
            }
            if actual_principals != expected_principals:
                return False

            previous = "0" * 64
            expected_nonces: dict[str, str] = {}
            for row in decisions:
                envelope = json.loads(row["envelope_json"])
                if self._stored_envelope_digest(envelope) != row["envelope_digest"]:
                    return False
                content = {
                    "envelope_digest": row["envelope_digest"],
                    "effect": row["effect"],
                    "reason_code": row["reason_code"],
                    "occurred_at": row["occurred_at"],
                    "previous_receipt_sha256": row["previous_receipt_sha256"],
                }
                digest = hashlib.sha256(_canonical(content)).hexdigest()
                if row["previous_receipt_sha256"] != previous or row["receipt_sha256"] != digest:
                    return False
                try:
                    TrustEffect(row["effect"])
                    occurred = datetime.fromisoformat(row["occurred_at"])
                except ValueError:
                    return False
                if occurred.tzinfo is None:
                    return False
                if row["effect"] == TrustEffect.ALLOW.value:
                    attestation = envelope["attestation"]
                    try:
                        attestation_verified = self._verify_attestation(attestation)
                    except Exception:  # noqa: BLE001 - external verifier boundary
                        return False
                    if (
                        attestation.get("purpose") != "zero_trust.capability"
                        or attestation.get("payload_sha256") != row["envelope_digest"]
                        or attestation_verified is not True
                    ):
                        return False
                    nonce = envelope["nonce"]
                    if nonce in expected_nonces:
                        return False
                    expected_nonces[nonce] = envelope["envelope_id"]
                previous = digest
            actual_nonces: dict[str, str] = {}
            for row in nonce_rows:
                try:
                    consumed = datetime.fromisoformat(row["consumed_at"])
                except ValueError:
                    return False
                if consumed.tzinfo is None or row["nonce"] in actual_nonces:
                    return False
                actual_nonces[row["nonce"]] = row["envelope_id"]
            if actual_nonces != expected_nonces:
                return False
        except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError):
            return False
        except TrustError:
            return False
        return True

    @staticmethod
    def _stored_envelope_digest(value: object) -> str | None:
        if (
            not isinstance(value, dict)
            or set(value) != _ENVELOPE_FIELDS
            or not isinstance(value.get("attestation"), Mapping)
        ):
            return None
        unsigned = dict(value)
        unsigned.pop("attestation")
        try:
            return hashlib.sha256(_canonical(unsigned)).hexdigest()
        except (TypeError, ValueError):
            return None

    def _clock_now(self) -> datetime:
        try:
            value = self._clock()
        except Exception as exc:
            raise TrustError(
                TrustFailureCode.CLOCK_UNAVAILABLE,
                "zero-trust clock is unavailable",
            ) from exc
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise TrustError(
                TrustFailureCode.CLOCK_UNAVAILABLE,
                "zero-trust clock must return a timezone-aware timestamp",
            )
        return value

    def status(self) -> dict[str, object]:
        active = self._connection.execute(
            "SELECT COUNT(*) FROM trust_principals WHERE status = 'ACTIVE'"
        ).fetchone()[0]
        decisions = self._connection.execute("SELECT COUNT(*) FROM trust_decisions").fetchone()[0]
        nonces = self._connection.execute("SELECT COUNT(*) FROM trust_nonces").fetchone()[0]
        audit_valid = self.audit_chain_valid()
        return {
            "schema_version": _STORAGE_SCHEMA_VERSION,
            "ready": audit_valid,
            "active_principals": int(active),
            "decisions": int(decisions),
            "consumed_nonces": int(nonces),
            "principal_state_source": (
                "dynamic_resolver"
                if self._principal_state_resolver is not None
                else "persistent_registry"
            ),
            "max_clock_skew_seconds": self._max_clock_skew_seconds,
            "max_payload_bytes": self._max_payload_bytes,
            "authorization_provider": self._authorization_gate.profile(),
            "audit_chain_valid": audit_valid,
        }

    def decision_count(self) -> int:
        try:
            row = self._connection.execute("SELECT COUNT(*) FROM trust_decisions").fetchone()
        except sqlite3.Error as exc:
            raise TrustError(
                TrustFailureCode.STORAGE_ERROR,
                "zero-trust decision count is unavailable",
            ) from exc
        return int(row[0]) if row else 0

    def health_check(self) -> bool:
        try:
            return bool(
                self.audit_chain_valid() and self._connection.execute("SELECT 1").fetchone()[0] == 1
            )
        except (sqlite3.Error, TypeError):
            return False

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _validate_ids(*values: str) -> None:
        if any(not isinstance(item, str) or not _TRUST_ID.fullmatch(item) for item in values):
            raise TrustError(
                TrustFailureCode.INVALID_INPUT,
                "zero-trust identifier is invalid",
            )

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trust_metadata(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trust_principals(
                    principal_id TEXT PRIMARY KEY, node_id TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL, status TEXT NOT NULL,
                    enrolled_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trust_nonces(
                    nonce TEXT PRIMARY KEY, envelope_id TEXT NOT NULL,
                    consumed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trust_decisions(
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    envelope_json TEXT NOT NULL, envelope_digest TEXT NOT NULL,
                    effect TEXT NOT NULL, reason_code TEXT NOT NULL,
                    occurred_at TEXT NOT NULL, previous_receipt_sha256 TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS trust_audit(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL, event TEXT NOT NULL,
                    payload_json TEXT NOT NULL, previous_sha256 TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS idx_trust_principals_status
                ON trust_principals(status);
                CREATE INDEX IF NOT EXISTS idx_trust_decisions_envelope
                ON trust_decisions(envelope_digest);
                CREATE INDEX IF NOT EXISTS idx_trust_nonces_consumed
                ON trust_nonces(consumed_at);
                """
            )
            row = self._connection.execute(
                "SELECT value FROM trust_metadata WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO trust_metadata(key, value) VALUES ('schema_version', ?)",
                    (str(_STORAGE_SCHEMA_VERSION),),
                )
                return
            try:
                stored_version = int(row["value"])
            except (TypeError, ValueError) as exc:
                raise TrustError(
                    TrustFailureCode.CORRUPT_AUDIT,
                    "zero-trust storage schema metadata is corrupt",
                ) from exc
            if stored_version != _STORAGE_SCHEMA_VERSION:
                raise TrustError(
                    TrustFailureCode.STORAGE_SCHEMA_UNSUPPORTED,
                    "zero-trust storage schema is unsupported",
                )


# Patterns that look like embedded instructions / injections
_INJECTION_PATTERNS: list[str] = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"you\s+are\s+now\s+(a\s+)?(different|new|unrestricted)",
    r"disregard\s+(your\s+)?(guidelines|rules|ethics)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"system\s*prompt\s*[:=]",
    r"\bDAN\b",  # "Do Anything Now" jailbreak
    r"<\s*/?system\s*>",  # XML system tags
    r"\[\[.*?(override|inject).*?\]\]",
]

_TWIN_SYNC_ALLOWED_FIELDS: set[str] = {
    "is_silent",
    "topk_ratio",
    "loyalty_score",
    "moe_primary_expert",
    "collective_pulse",
    "timestamp",
}

_TWIN_SYNC_ALLOWED_PULSE_FIELDS: set[str] = {
    "avg_trust",
    "avg_novelty",
    "avg_cohesion",
    "pulse_score",
    "mode",
    "online_ratio",
    "events_considered",
}

_TWIN_SYNC_ALLOWED_MODES: set[str] = {
    "local_solo",
    "guarded_sync",
    "hybrid_bridge",
    "collective_sync",
}

_TWIN_SYNC_ALLOWED_EXPERTS: set[str] = {
    "logic",
    "action",
    "memory",
    "safety",
    "creative",
}


class ZeroTrustFilter:
    """Zero-Trust input validation layer (Pillar 18).

    Parameters
    ----------
    trusted_sources:
        Set of source identifiers always allowed (e.g. ``{"local_rag"}``)
    strict:
        When True, sources not in the trusted list are also scanned for
        injection patterns.  When False (default), unknown sources pass
        after injection scan regardless.
    """

    def __init__(self, trusted_sources: set[str] | None = None, strict: bool = False):
        self.trusted_sources: set[str] = trusted_sources or {
            "local_rag",
            "twin_sync",
            "user_direct",
        }
        self.strict = strict
        self._injection_re: list[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE | re.DOTALL) for p in _INJECTION_PATTERNS
        ]
        self._blocked: int = 0
        self._passed: int = 0
        self._scan_count: int = 0

    # ------------------------------------------------------------------

    def validate(self, source: str, payload: Any, force_scan: bool = False) -> tuple[bool, str]:
        """Check whether *payload* from *source* is safe to process.

        Parameters
        ----------
        source:
            String identifier of the data origin.
        payload:
            The data itself.  Converted to str for scanning.

        Returns
        -------
        (safe, reason)
        """
        self._scan_count += 1
        text = str(payload)
        # A known principal never makes its current content intrinsically safe.
        # Preserve the legacy argument but force every source through scanning.
        force_scan = True

        # Fast-path: fully trusted source
        if source in self.trusted_sources and not force_scan:
            self._passed += 1
            logger.debug("[ZeroTrust] trusted source %r — fast path", source)
            return True, "trusted_source"

        # Injection scan for all external sources
        for pattern in self._injection_re:
            if pattern.search(text):
                self._blocked += 1
                reason = f"Injection pattern '{pattern.pattern}' in payload from '{source}'"
                logger.warning("[ZeroTrust] BLOCKED | %s", reason)
                return False, reason

        # In strict mode, untrusted sources need explicit whitelisting
        if self.strict and source not in self.trusted_sources:
            self._blocked += 1
            reason = f"Strict mode: source '{source}' not whitelisted"
            logger.warning("[ZeroTrust] BLOCKED (strict) | %s", reason)
            return False, reason

        self._passed += 1
        logger.debug("[ZeroTrust] passed | source=%r len=%d", source, len(text))
        return True, "ok"

    def validate_twin_sync_state(self, state: Any) -> tuple[bool, str, dict[str, Any]]:
        """Validate and sanitize Twin Protocol sync state payload."""
        if not isinstance(state, dict):
            return False, "invalid_state_type", {}

        scan_ok, scan_reason = self.validate("twin_sync", state, force_scan=True)
        if not scan_ok:
            return False, scan_reason, {}

        state_map = cast(dict[str, Any], state)
        unknown_fields = [
            str(key) for key in state_map if str(key) not in _TWIN_SYNC_ALLOWED_FIELDS
        ]
        if unknown_fields and self.strict:
            return False, "unknown_state_fields", {}

        safe_state: dict[str, Any] = {
            "is_silent": bool(state_map.get("is_silent", False)),
        }

        ok_topk, topk = self._coerce_unit_float(
            state_map.get("topk_ratio"),
            default=0.10,
        )
        if not ok_topk:
            return False, "invalid_topk_ratio", {}
        safe_state["topk_ratio"] = topk

        ok_loyalty, loyalty = self._coerce_unit_float(
            state_map.get("loyalty_score"),
            default=1.0,
        )
        if not ok_loyalty:
            return False, "invalid_loyalty_score", {}
        safe_state["loyalty_score"] = loyalty

        expert_raw = state_map.get("moe_primary_expert")
        if expert_raw is None:
            safe_state["moe_primary_expert"] = None
        elif isinstance(expert_raw, str):
            expert = expert_raw.strip().lower()
            if expert in _TWIN_SYNC_ALLOWED_EXPERTS:
                safe_state["moe_primary_expert"] = expert
            elif self.strict:
                return False, "invalid_moe_primary_expert", {}
            else:
                safe_state["moe_primary_expert"] = None
        elif self.strict:
            return False, "invalid_moe_primary_expert", {}
        else:
            safe_state["moe_primary_expert"] = None

        pulse_raw = state_map.get("collective_pulse")
        if pulse_raw is None:
            safe_state["collective_pulse"] = {}
        elif isinstance(pulse_raw, dict):
            pulse_map = cast(dict[str, Any], pulse_raw)
            pulse_unknown = [
                str(key) for key in pulse_map if str(key) not in _TWIN_SYNC_ALLOWED_PULSE_FIELDS
            ]
            if pulse_unknown and self.strict:
                return False, "unknown_collective_fields", {}

            safe_pulse: dict[str, Any] = {}
            for field, default_value in (
                ("avg_trust", 0.5),
                ("avg_novelty", 0.4),
                ("avg_cohesion", 0.6),
                ("pulse_score", 0.5),
                ("online_ratio", 0.0),
            ):
                ok_field, parsed = self._coerce_unit_float(
                    pulse_map.get(field),
                    default=default_value,
                )
                if not ok_field:
                    return False, f"invalid_{field}", {}
                safe_pulse[field] = parsed

            mode_raw = pulse_map.get("mode")
            mode = str(mode_raw or "guarded_sync").strip().lower()
            if mode not in _TWIN_SYNC_ALLOWED_MODES:
                if self.strict:
                    return False, "invalid_collective_mode", {}
                mode = "guarded_sync"
            safe_pulse["mode"] = mode

            events_raw = pulse_map.get("events_considered", 0)
            try:
                events_count = int(events_raw)
            except (TypeError, ValueError):
                if self.strict:
                    return False, "invalid_events_considered", {}
                events_count = 0
            safe_pulse["events_considered"] = max(0, events_count)
            safe_state["collective_pulse"] = safe_pulse
        elif self.strict:
            return False, "invalid_collective_pulse", {}
        else:
            safe_state["collective_pulse"] = {}

        ts_raw = state_map.get("timestamp", 0.0)
        try:
            ts = float(ts_raw)
            if not math.isfinite(ts):
                raise ValueError("non_finite")
        except (TypeError, ValueError):
            if self.strict:
                return False, "invalid_timestamp", {}
            ts = 0.0
        safe_state["timestamp"] = ts

        return True, "ok", safe_state

    def _coerce_unit_float(self, value: Any, default: float) -> tuple[bool, float]:
        if value is None:
            return True, max(0.0, min(1.0, float(default)))
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False, 0.0
        if not math.isfinite(number):
            return False, 0.0
        return True, max(0.0, min(1.0, number))

    def allow_source(self, source: str) -> None:
        """Add *source* to the trusted set."""
        self.trusted_sources.add(source)
        logger.info("[ZeroTrust] trusted source added: %r", source)

    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "scanned": self._scan_count,
            "passed": self._passed,
            "blocked": self._blocked,
            "trusted_sources": list(self.trusted_sources),
            "strict": self.strict,
        }
