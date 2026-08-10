"""P15 Ethical Heart: deterministic, persisted, fail-closed action policy.

Authorization is based on trusted structured context, never prompt text.  A
capability request is bound to a brain, node, capability manifest, risk class,
permissions, payload hash, and active policy version.  Human approvals use a
separate Ed25519 trust key and are one-time, expiring, payload-bound receipts.
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
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_VERSION = 1


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
    except (TypeError, ValueError) as exc:
        raise PolicyError(
            PolicyFailureCode.APPROVAL_INVALID,
            "approval contains invalid base64 data",
        ) from exc


class PolicyEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class PolicyRisk(str, Enum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE = "REVERSIBLE"
    DESTRUCTIVE = "DESTRUCTIVE"
    PHYSICAL_ACTION = "PHYSICAL_ACTION"
    SECURITY_SENSITIVE = "SECURITY_SENSITIVE"
    COGNITIVE_UPDATE = "COGNITIVE_UPDATE"


class PolicyFailureCode(str, Enum):
    INVALID_INPUT = "POLICY_INVALID_INPUT"
    POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"
    POLICY_CONFLICT = "POLICY_CONFLICT"
    POLICY_CORRUPT = "POLICY_CORRUPT"
    ACTOR_MISMATCH = "POLICY_ACTOR_MISMATCH"
    DENIED = "POLICY_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_INVALID = "APPROVAL_INVALID"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_REPLAYED = "APPROVAL_REPLAYED"
    STORAGE_ERROR = "POLICY_STORAGE_ERROR"


class PolicyError(RuntimeError):
    """Typed policy failure safe for API and JayaIR boundaries."""

    def __init__(self, code: PolicyFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PolicyRule:
    rule_id: str
    effect: PolicyEffect
    capability_ids: tuple[str, ...] = ()
    risk_classes: tuple[PolicyRisk, ...] = ()
    reason_code: str = "POLICY_RULE_MATCHED"

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.rule_id):
            raise PolicyError(PolicyFailureCode.INVALID_INPUT, "rule_id is invalid")
        if not _SAFE_ID.fullmatch(self.reason_code):
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "policy reason_code is invalid",
            )
        if len(set(self.capability_ids)) != len(self.capability_ids):
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "policy rule contains duplicate capability ids",
            )
        if any(not _SAFE_ID.fullmatch(item) for item in self.capability_ids):
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "policy rule contains an invalid capability id",
            )
        if len(set(self.risk_classes)) != len(self.risk_classes):
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "policy rule contains duplicate risk classes",
            )

    def matches(self, capability_id: str, risk_class: PolicyRisk) -> bool:
        capability_matches = (
            not self.capability_ids or capability_id in self.capability_ids
        )
        risk_matches = not self.risk_classes or risk_class in self.risk_classes
        return capability_matches and risk_matches

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "effect": self.effect.value,
            "capability_ids": list(self.capability_ids),
            "risk_classes": [item.value for item in self.risk_classes],
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class PolicyBundle:
    policy_id: str
    version: int
    brain_id: str
    rules: tuple[PolicyRule, ...]
    default_effect: PolicyEffect = PolicyEffect.DENY
    default_reason_code: str = "NO_POLICY_RULE"
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "unsupported policy schema version",
            )
        if not _SAFE_ID.fullmatch(self.policy_id):
            raise PolicyError(PolicyFailureCode.INVALID_INPUT, "policy_id is invalid")
        if not _SAFE_ID.fullmatch(self.brain_id):
            raise PolicyError(PolicyFailureCode.INVALID_INPUT, "brain_id is invalid")
        if self.version <= 0:
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "policy version must be positive",
            )
        if not self.rules:
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "policy must contain at least one explicit rule",
            )
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "policy rule ids must be unique",
            )
        if not _SAFE_ID.fullmatch(self.default_reason_code):
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "default policy reason code is invalid",
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "version": self.version,
            "brain_id": self.brain_id,
            "rules": [rule.to_dict() for rule in self.rules],
            "default_effect": self.default_effect.value,
            "default_reason_code": self.default_reason_code,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    request_id: str
    actor_brain_id: str
    node_id: str
    capability_id: str
    risk_class: PolicyRisk
    permissions: tuple[str, ...]
    payload_sha256: str
    purpose: str = "jayair.call-capability"
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        identifiers = (
            self.request_id,
            self.actor_brain_id,
            self.node_id,
            self.capability_id,
            self.purpose,
        )
        if self.schema_version != _SCHEMA_VERSION or any(
            not _SAFE_ID.fullmatch(item) for item in identifiers
        ):
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "policy request identity fields are invalid",
            )
        if not _SHA256.fullmatch(self.payload_sha256):
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "policy request payload digest is invalid",
            )
        if len(set(self.permissions)) != len(self.permissions) or any(
            not _SAFE_ID.fullmatch(item) for item in self.permissions
        ):
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "policy request permissions are invalid",
            )

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["risk_class"] = self.risk_class.value
        value["permissions"] = list(self.permissions)
        return value

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class OwnerApproval:
    approval_id: str
    approver_id: str
    actor_brain_id: str
    capability_id: str
    payload_sha256: str
    policy_id: str
    policy_version: int
    nonce: str
    issued_at: str
    expires_at: str
    signature: str
    schema_version: int = _SCHEMA_VERSION

    def unsigned_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("signature")
        return value

    def signed_payload(self) -> bytes:
        return _canonical(self.unsigned_dict())

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision_id: int
    request_id: str
    effect: PolicyEffect
    reason_code: str
    rule_id: str | None
    policy_id: str
    policy_version: int
    policy_digest: str
    request_digest: str
    approval_id: str | None
    occurred_at: str
    previous_receipt_sha256: str
    receipt_sha256: str
    attestation: Mapping[str, object] | None

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["effect"] = self.effect.value
        value["attestation"] = (
            dict(self.attestation) if self.attestation is not None else None
        )
        return value


AttestationSigner = Callable[[str, str], Mapping[str, object]]
AttestationVerifier = Callable[[Mapping[str, object]], bool]


def default_core_policy(brain_id: str) -> PolicyBundle:
    """Conservative built-in policy: only Core Pure Logic is auto-allowed."""

    return PolicyBundle(
        policy_id="core.sovereign-default",
        version=1,
        brain_id=brain_id,
        rules=(
            PolicyRule(
                rule_id="allow.core-pure-logic",
                effect=PolicyEffect.ALLOW,
                capability_ids=("core.logic.evaluate", "core.reason"),
                risk_classes=(PolicyRisk.READ_ONLY,),
                reason_code="TRUSTED_CORE_READ_ONLY",
            ),
            PolicyRule(
                rule_id="deny.irreversible-or-self-change",
                effect=PolicyEffect.DENY,
                risk_classes=(
                    PolicyRisk.DESTRUCTIVE,
                    PolicyRisk.COGNITIVE_UPDATE,
                ),
                reason_code="HIGH_RISK_DENIED",
            ),
            PolicyRule(
                rule_id="owner-approval.external-action",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                risk_classes=(
                    PolicyRisk.READ_ONLY,
                    PolicyRisk.REVERSIBLE,
                    PolicyRisk.PHYSICAL_ACTION,
                    PolicyRisk.SECURITY_SENSITIVE,
                ),
                reason_code="OWNER_APPROVAL_REQUIRED",
            ),
        ),
    )


class EthicalHeart:
    """Persistent deterministic policy engine used by the execution boundary."""

    def __init__(
        self,
        db_path: Path | str = ":memory:",
        policy: PolicyBundle | None = None,
        *,
        approval_public_keys: Mapping[str, bytes | str] | None = None,
        attestation_signer: AttestationSigner | None = None,
        attestation_verifier: AttestationVerifier | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        active_policy = policy or default_core_policy("UNENROLLED")
        self._clock = clock
        self._policy = active_policy
        self._attestation_signer = attestation_signer
        self._attestation_verifier = attestation_verifier
        self._approval_keys = self._load_approval_keys(approval_public_keys or {})
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                str(db_path),
                check_same_thread=False,
                timeout=5.0,
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            if str(db_path) != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._create_schema()
            self._install_policy(active_policy)
        except PolicyError:
            raise
        except sqlite3.Error as exc:
            raise PolicyError(
                PolicyFailureCode.STORAGE_ERROR,
                "Ethical Heart policy storage is unavailable",
            ) from exc

    @staticmethod
    def _load_approval_keys(
        values: Mapping[str, bytes | str],
    ) -> dict[str, Ed25519PublicKey]:
        loaded: dict[str, Ed25519PublicKey] = {}
        for approver_id, material in values.items():
            if not _SAFE_ID.fullmatch(approver_id):
                raise PolicyError(
                    PolicyFailureCode.INVALID_INPUT,
                    "approval trust key has an invalid approver id",
                )
            raw = material if isinstance(material, bytes) else _decode(material)
            try:
                loaded[approver_id] = Ed25519PublicKey.from_public_bytes(raw)
            except ValueError as exc:
                raise PolicyError(
                    PolicyFailureCode.INVALID_INPUT,
                    "approval trust key is not a valid Ed25519 public key",
                ) from exc
        return loaded

    @property
    def policy(self) -> PolicyBundle:
        return self._policy

    def evaluate(
        self,
        request: PolicyRequest,
        approval: OwnerApproval | None = None,
    ) -> PolicyDecision:
        """Evaluate and persist one decision before capability invocation."""

        if not isinstance(request, PolicyRequest):
            raise PolicyError(
                PolicyFailureCode.INVALID_INPUT,
                "unstructured text cannot be used as an authorization request",
            )
        if not self.audit_chain_valid():
            raise PolicyError(
                PolicyFailureCode.POLICY_CORRUPT,
                "policy decision audit chain is corrupt",
            )
        if request.actor_brain_id != self._policy.brain_id:
            return self._record_decision(
                request,
                PolicyEffect.DENY,
                "ACTOR_DOES_NOT_OWN_POLICY",
                None,
                None,
            )
        rule = next(
            (
                item
                for item in self._policy.rules
                if item.matches(request.capability_id, request.risk_class)
            ),
            None,
        )
        effect = rule.effect if rule else self._policy.default_effect
        reason = rule.reason_code if rule else self._policy.default_reason_code
        rule_id = rule.rule_id if rule else None
        approval_id: str | None = None
        if effect is PolicyEffect.REQUIRE_APPROVAL:
            if approval is None:
                return self._record_decision(
                    request,
                    effect,
                    reason,
                    rule_id,
                    None,
                )
            self._verify_and_consume_approval(request, approval)
            effect = PolicyEffect.ALLOW
            reason = "VALID_OWNER_APPROVAL"
            approval_id = approval.approval_id
        return self._record_decision(
            request,
            effect,
            reason,
            rule_id,
            approval_id,
        )

    def _verify_and_consume_approval(
        self,
        request: PolicyRequest,
        approval: OwnerApproval,
    ) -> None:
        fields = (
            approval.approval_id,
            approval.approver_id,
            approval.actor_brain_id,
            approval.capability_id,
            approval.policy_id,
            approval.nonce,
        )
        if approval.schema_version != _SCHEMA_VERSION or any(
            not _SAFE_ID.fullmatch(item) for item in fields
        ):
            raise PolicyError(
                PolicyFailureCode.APPROVAL_INVALID,
                "approval identity fields are invalid",
            )
        if not _SHA256.fullmatch(approval.payload_sha256):
            raise PolicyError(
                PolicyFailureCode.APPROVAL_INVALID,
                "approval payload digest is invalid",
            )
        if (
            approval.actor_brain_id != request.actor_brain_id
            or approval.capability_id != request.capability_id
            or approval.payload_sha256 != request.payload_sha256
            or approval.policy_id != self._policy.policy_id
            or approval.policy_version != self._policy.version
        ):
            raise PolicyError(
                PolicyFailureCode.APPROVAL_INVALID,
                "approval is not bound to this policy request",
            )
        try:
            issued = datetime.fromisoformat(approval.issued_at)
            expires = datetime.fromisoformat(approval.expires_at)
        except ValueError as exc:
            raise PolicyError(
                PolicyFailureCode.APPROVAL_INVALID,
                "approval timestamps are invalid",
            ) from exc
        now = self._clock()
        if issued.tzinfo is None or expires.tzinfo is None or expires <= issued:
            raise PolicyError(
                PolicyFailureCode.APPROVAL_INVALID,
                "approval time window is invalid",
            )
        if now < issued or now >= expires:
            raise PolicyError(
                PolicyFailureCode.APPROVAL_EXPIRED,
                "approval is outside its validity window",
            )
        public_key = self._approval_keys.get(approval.approver_id)
        if public_key is None:
            raise PolicyError(
                PolicyFailureCode.APPROVAL_INVALID,
                "approval signer is not trusted",
            )
        try:
            public_key.verify(_decode(approval.signature), approval.signed_payload())
        except (InvalidSignature, ValueError) as exc:
            raise PolicyError(
                PolicyFailureCode.APPROVAL_INVALID,
                "approval signature is invalid",
            ) from exc
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO policy_approval_nonces(
                        nonce, approval_id, consumed_at
                    ) VALUES (?, ?, ?)
                    """,
                    (approval.nonce, approval.approval_id, now.isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise PolicyError(
                PolicyFailureCode.APPROVAL_REPLAYED,
                "approval nonce was already consumed",
            ) from exc
        except sqlite3.Error as exc:
            raise PolicyError(
                PolicyFailureCode.STORAGE_ERROR,
                "approval replay storage is unavailable",
            ) from exc

    def _record_decision(
        self,
        request: PolicyRequest,
        effect: PolicyEffect,
        reason_code: str,
        rule_id: str | None,
        approval_id: str | None,
    ) -> PolicyDecision:
        occurred_at = self._clock().isoformat()
        try:
            with self._lock, self._connection:
                active = self._connection.execute(
                    """
                    SELECT policy_id, version, digest
                    FROM active_policy WHERE singleton = 1
                    """
                ).fetchone()
                if active is None or (
                    active["policy_id"] != self._policy.policy_id
                    or active["version"] != self._policy.version
                    or active["digest"] != self._policy.digest
                ):
                    raise PolicyError(
                        PolicyFailureCode.POLICY_CORRUPT,
                        "active policy record does not match the loaded policy",
                    )
                previous = self._connection.execute(
                    """
                    SELECT receipt_sha256 FROM policy_decisions
                    ORDER BY decision_id DESC LIMIT 1
                    """
                ).fetchone()
                previous_hash = previous[0] if previous else "0" * 64
                content = {
                    "request_id": request.request_id,
                    "effect": effect.value,
                    "reason_code": reason_code,
                    "rule_id": rule_id,
                    "policy_id": self._policy.policy_id,
                    "policy_version": self._policy.version,
                    "policy_digest": self._policy.digest,
                    "request_digest": request.digest,
                    "approval_id": approval_id,
                    "occurred_at": occurred_at,
                    "previous_receipt_sha256": previous_hash,
                }
                receipt_hash = hashlib.sha256(_canonical(content)).hexdigest()
                attestation = (
                    dict(self._attestation_signer("policy.decision", receipt_hash))
                    if self._attestation_signer is not None
                    else None
                )
                cursor = self._connection.execute(
                    """
                    INSERT INTO policy_decisions(
                        request_json, request_id, effect, reason_code, rule_id,
                        policy_id, policy_version, policy_digest,
                        request_digest, approval_id, occurred_at,
                        previous_receipt_sha256, receipt_sha256,
                        attestation_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _canonical(request.to_dict()).decode("utf-8"),
                        request.request_id,
                        effect.value,
                        reason_code,
                        rule_id,
                        self._policy.policy_id,
                        self._policy.version,
                        self._policy.digest,
                        request.digest,
                        approval_id,
                        occurred_at,
                        previous_hash,
                        receipt_hash,
                        (
                            json.dumps(attestation, sort_keys=True)
                            if attestation
                            else None
                        ),
                    ),
                )
                decision_id = int(cursor.lastrowid)
        except PolicyError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise PolicyError(
                PolicyFailureCode.STORAGE_ERROR,
                "policy decision could not be persisted",
            ) from exc
        return PolicyDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            effect=effect,
            reason_code=reason_code,
            rule_id=rule_id,
            policy_id=self._policy.policy_id,
            policy_version=self._policy.version,
            policy_digest=self._policy.digest,
            request_digest=request.digest,
            approval_id=approval_id,
            occurred_at=occurred_at,
            previous_receipt_sha256=previous_hash,
            receipt_sha256=receipt_hash,
            attestation=attestation,
        )

    def audit_chain_valid(self, *, require_attestation: bool = False) -> bool:
        try:
            rows = self._connection.execute(
                "SELECT * FROM policy_decisions ORDER BY decision_id"
            ).fetchall()
        except sqlite3.Error:
            return False
        previous = "0" * 64
        for row in rows:
            try:
                request_value = json.loads(row["request_json"])
                stored_request_digest = hashlib.sha256(
                    _canonical(request_value)
                ).hexdigest()
            except (json.JSONDecodeError, TypeError, ValueError):
                return False
            if stored_request_digest != row["request_digest"]:
                return False
            content = {
                "request_id": row["request_id"],
                "effect": row["effect"],
                "reason_code": row["reason_code"],
                "rule_id": row["rule_id"],
                "policy_id": row["policy_id"],
                "policy_version": row["policy_version"],
                "policy_digest": row["policy_digest"],
                "request_digest": row["request_digest"],
                "approval_id": row["approval_id"],
                "occurred_at": row["occurred_at"],
                "previous_receipt_sha256": row["previous_receipt_sha256"],
            }
            expected = hashlib.sha256(_canonical(content)).hexdigest()
            if (
                row["previous_receipt_sha256"] != previous
                or row["receipt_sha256"] != expected
            ):
                return False
            attestation_json = row["attestation_json"]
            if require_attestation and not attestation_json:
                return False
            if attestation_json and self._attestation_verifier is not None:
                try:
                    attestation = json.loads(attestation_json)
                except json.JSONDecodeError:
                    return False
                if self._attestation_verifier(attestation) is not True:
                    return False
            previous = expected
        return True

    def decision_count(self) -> int:
        try:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM policy_decisions"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error as exc:
            raise PolicyError(
                PolicyFailureCode.STORAGE_ERROR,
                "policy decision count is unavailable",
            ) from exc

    def authorizes_capability(
        self,
        capability_id: str,
        payload: Mapping[str, Any],
        authorization: object,
    ) -> bool:
        """Validate that a persisted ALLOW receipt binds this exact invocation."""

        if not isinstance(authorization, PolicyDecision):
            return False
        if authorization.effect is not PolicyEffect.ALLOW:
            return False
        if (
            authorization.policy_id != self._policy.policy_id
            or authorization.policy_version != self._policy.version
            or authorization.policy_digest != self._policy.digest
            or not self.audit_chain_valid()
        ):
            return False
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            row = self._connection.execute(
                """
                SELECT request_json, effect, receipt_sha256
                FROM policy_decisions WHERE decision_id = ?
                """,
                (authorization.decision_id,),
            ).fetchone()
            request_value = json.loads(row["request_json"]) if row else None
        except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError):
            return False
        return bool(
            row is not None
            and row["effect"] == PolicyEffect.ALLOW.value
            and row["receipt_sha256"] == authorization.receipt_sha256
            and isinstance(request_value, dict)
            and request_value.get("capability_id") == capability_id
            and request_value.get("actor_brain_id") == self._policy.brain_id
            and request_value.get("payload_sha256")
            == hashlib.sha256(encoded).hexdigest()
        )

    def status(self) -> dict[str, object]:
        return {
            "policy_id": self._policy.policy_id,
            "policy_version": self._policy.version,
            "policy_digest": self._policy.digest,
            "brain_id": self._policy.brain_id,
            "rules": len(self._policy.rules),
            "trusted_approvers": len(self._approval_keys),
            "signed_receipts": self._attestation_signer is not None,
            "decisions": self.decision_count(),
            "audit_chain_valid": self.audit_chain_valid(),
        }

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS policy_versions(
                    policy_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    brain_id TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    policy_json TEXT NOT NULL,
                    installed_at TEXT NOT NULL,
                    PRIMARY KEY(policy_id, version)
                );
                CREATE TABLE IF NOT EXISTS active_policy(
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    policy_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS policy_approval_nonces(
                    nonce TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL UNIQUE,
                    consumed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS policy_decisions(
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_json TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    effect TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    rule_id TEXT,
                    policy_id TEXT NOT NULL,
                    policy_version INTEGER NOT NULL,
                    policy_digest TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    approval_id TEXT,
                    occurred_at TEXT NOT NULL,
                    previous_receipt_sha256 TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL UNIQUE,
                    attestation_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_policy_decisions_request
                ON policy_decisions(request_id);
                """
            )

    def _install_policy(self, policy: PolicyBundle) -> None:
        serialized = _canonical(policy.to_dict()).decode("utf-8")
        installed_at = self._clock().isoformat()
        try:
            with self._lock, self._connection:
                active = self._connection.execute(
                    "SELECT * FROM active_policy WHERE singleton = 1"
                ).fetchone()
                existing = self._connection.execute(
                    """
                    SELECT brain_id, digest, policy_json FROM policy_versions
                    WHERE policy_id = ? AND version = ?
                    """,
                    (policy.policy_id, policy.version),
                ).fetchone()
                if existing is not None:
                    try:
                        stored_policy_digest = hashlib.sha256(
                            _canonical(json.loads(existing["policy_json"]))
                        ).hexdigest()
                    except (json.JSONDecodeError, TypeError, ValueError) as exc:
                        raise PolicyError(
                            PolicyFailureCode.POLICY_CORRUPT,
                            "stored policy document is corrupt",
                        ) from exc
                    if (
                        existing["brain_id"] != policy.brain_id
                        or stored_policy_digest != existing["digest"]
                    ):
                        raise PolicyError(
                            PolicyFailureCode.POLICY_CORRUPT,
                            "stored policy integrity check failed",
                        )
                    if existing["digest"] != policy.digest:
                        raise PolicyError(
                            PolicyFailureCode.POLICY_CONFLICT,
                            "policy content changed without a version increment",
                        )
                if active is not None:
                    if active["policy_id"] != policy.policy_id:
                        raise PolicyError(
                            PolicyFailureCode.POLICY_CONFLICT,
                            "a different policy id is already active",
                        )
                    if policy.version < active["version"]:
                        raise PolicyError(
                            PolicyFailureCode.POLICY_CONFLICT,
                            "policy downgrade is forbidden",
                        )
                    if (
                        policy.version == active["version"]
                        and policy.digest != active["digest"]
                    ):
                        raise PolicyError(
                            PolicyFailureCode.POLICY_CORRUPT,
                            "active policy digest does not match policy storage",
                        )
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO policy_versions(
                        policy_id, version, brain_id, digest,
                        policy_json, installed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        policy.policy_id,
                        policy.version,
                        policy.brain_id,
                        policy.digest,
                        serialized,
                        installed_at,
                    ),
                )
                self._connection.execute(
                    """
                    INSERT INTO active_policy(singleton, policy_id, version, digest)
                    VALUES (1, ?, ?, ?)
                    ON CONFLICT(singleton) DO UPDATE SET
                        policy_id = excluded.policy_id,
                        version = excluded.version,
                        digest = excluded.digest
                    """,
                    (policy.policy_id, policy.version, policy.digest),
                )
        except PolicyError:
            raise
        except sqlite3.Error as exc:
            raise PolicyError(
                PolicyFailureCode.STORAGE_ERROR,
                "policy version could not be installed",
            ) from exc


def create_owner_approval(
    *,
    approver_id: str,
    actor_brain_id: str,
    capability_id: str,
    payload_sha256: str,
    policy_id: str,
    policy_version: int,
    issued_at: str,
    expires_at: str,
    signer: Callable[[bytes], bytes],
    approval_id: str | None = None,
    nonce: str | None = None,
) -> OwnerApproval:
    """Create a signed owner receipt using an externally supplied signer.

    The policy engine never owns or generates the human private key.  A CLI,
    HSM, or secret-manager adapter can provide the signer at the owner boundary.
    """

    unsigned = OwnerApproval(
        approval_id=approval_id or f"approval-{uuid.uuid4()}",
        approver_id=approver_id,
        actor_brain_id=actor_brain_id,
        capability_id=capability_id,
        payload_sha256=payload_sha256,
        policy_id=policy_id,
        policy_version=policy_version,
        nonce=nonce or f"nonce-{uuid.uuid4()}",
        issued_at=issued_at,
        expires_at=expires_at,
        signature="",
    )
    try:
        signature = signer(unsigned.signed_payload())
    except Exception as exc:
        raise PolicyError(
            PolicyFailureCode.APPROVAL_INVALID,
            "external approval signer failed",
        ) from exc
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise PolicyError(
            PolicyFailureCode.APPROVAL_INVALID,
            "external approval signer returned an invalid signature",
        )
    return replace(unsigned, signature=_encode(signature))


__all__ = [
    "EthicalHeart",
    "OwnerApproval",
    "PolicyBundle",
    "PolicyDecision",
    "PolicyEffect",
    "PolicyError",
    "PolicyFailureCode",
    "PolicyRequest",
    "PolicyRisk",
    "PolicyRule",
    "create_owner_approval",
    "default_core_policy",
]
