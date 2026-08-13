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
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, cast

logger = logging.getLogger("ZeroTrust")

_TRUST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TrustEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class TrustFailureCode(str, Enum):
    INVALID_INPUT = "ZERO_TRUST_INVALID_INPUT"
    PRINCIPAL_UNKNOWN = "ZERO_TRUST_PRINCIPAL_UNKNOWN"
    PRINCIPAL_REVOKED = "ZERO_TRUST_PRINCIPAL_REVOKED"
    NODE_MISMATCH = "ZERO_TRUST_NODE_MISMATCH"
    CAPABILITY_DENIED = "ZERO_TRUST_CAPABILITY_DENIED"
    PAYLOAD_MISMATCH = "ZERO_TRUST_PAYLOAD_MISMATCH"
    ATTESTATION_INVALID = "ZERO_TRUST_ATTESTATION_INVALID"
    EXPIRED = "ZERO_TRUST_EXPIRED"
    REPLAY_DETECTED = "ZERO_TRUST_REPLAY_DETECTED"
    STORAGE_ERROR = "ZERO_TRUST_STORAGE_ERROR"
    CORRUPT_AUDIT = "ZERO_TRUST_CORRUPT_AUDIT"


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
        payload_digest = hashlib.sha256(_canonical(payload)).hexdigest()
    except (TypeError, ValueError) as exc:
        raise TrustError(
            TrustFailureCode.INVALID_INPUT,
            "trust payload must be bounded JSON",
        ) from exc
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
    return TrustEnvelope(
        **{**unsigned.unsigned_dict(), "attestation": dict(attestation)}
    )


class ZeroTrustAuthority:
    """Persistent authentication, authorization, replay, and audit boundary."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        attestation_verifier: Callable[[Mapping[str, object]], bool],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._clock = clock
        self._verifier = attestation_verifier
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(db_path), timeout=5.0, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if str(db_path) != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()
        if not self.audit_chain_valid():
            raise TrustError(
                TrustFailureCode.CORRUPT_AUDIT,
                "zero-trust audit chain is corrupt",
            )

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
                    (principal_id, node_id, encoded, self._clock().isoformat()),
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

    def revoke_principal(self, principal_id: str) -> None:
        self._validate_ids(principal_id)
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

    def authorize(
        self,
        envelope: TrustEnvelope,
        payload: Mapping[str, Any],
    ) -> TrustDecision:
        reason = self._validate_authorization(envelope, payload)
        effect = (
            TrustEffect.ALLOW
            if reason == "VERIFIED_LEAST_PRIVILEGE"
            else TrustEffect.DENY
        )
        if effect is TrustEffect.ALLOW:
            try:
                with self._lock, self._connection:
                    self._connection.execute(
                        "INSERT INTO trust_nonces(nonce, envelope_id, consumed_at) "
                        "VALUES (?, ?, ?)",
                        (
                            envelope.nonce,
                            envelope.envelope_id,
                            self._clock().isoformat(),
                        ),
                    )
            except sqlite3.IntegrityError:
                effect = TrustEffect.DENY
                reason = TrustFailureCode.REPLAY_DETECTED.value
            except sqlite3.Error as exc:
                raise TrustError(
                    TrustFailureCode.STORAGE_ERROR,
                    "zero-trust replay storage is unavailable",
                ) from exc
        return self._record_decision(envelope, effect, reason)

    def validates(
        self,
        capability_id: str,
        payload: Mapping[str, Any],
        decision: TrustDecision,
    ) -> bool:
        if (
            not isinstance(decision, TrustDecision)
            or decision.effect is not TrustEffect.ALLOW
        ):
            return False
        try:
            row = self._connection.execute(
                "SELECT envelope_json, effect, receipt_sha256 FROM trust_decisions "
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
            and row["receipt_sha256"] == decision.receipt_sha256
            and envelope.get("capability_id") == capability_id
            and envelope.get("payload_sha256") == payload_digest
            and self.audit_chain_valid()
        )

    def _validate_authorization(
        self, envelope: TrustEnvelope, payload: Mapping[str, Any]
    ) -> str:
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
            payload_digest = hashlib.sha256(_canonical(payload)).hexdigest()
        except (TypeError, ValueError, json.JSONDecodeError):
            return TrustFailureCode.INVALID_INPUT.value
        if (
            envelope.schema_version != 1
            or issued.tzinfo is None
            or expires.tzinfo is None
        ):
            return TrustFailureCode.INVALID_INPUT.value
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            return TrustFailureCode.INVALID_INPUT.value
        if not re.fullmatch(r"[0-9a-f]{64}", envelope.policy_receipt_sha256):
            return TrustFailureCode.INVALID_INPUT.value
        if not re.fullmatch(r"[0-9a-f]{64}", envelope.privacy_receipt_sha256):
            return TrustFailureCode.INVALID_INPUT.value
        if (
            now < issued - timedelta(seconds=5)
            or now >= expires
            or expires - issued > timedelta(minutes=5)
        ):
            return TrustFailureCode.EXPIRED.value
        row = self._connection.execute(
            "SELECT * FROM trust_principals WHERE principal_id = ?",
            (envelope.principal_id,),
        ).fetchone()
        if row is None:
            return TrustFailureCode.PRINCIPAL_UNKNOWN.value
        if row["status"] != "ACTIVE":
            return TrustFailureCode.PRINCIPAL_REVOKED.value
        if row["node_id"] != envelope.node_id:
            return TrustFailureCode.NODE_MISMATCH.value
        if envelope.capability_id not in json.loads(row["capabilities_json"]):
            return TrustFailureCode.CAPABILITY_DENIED.value
        if envelope.payload_sha256 != payload_digest:
            return TrustFailureCode.PAYLOAD_MISMATCH.value
        attestation = dict(envelope.attestation)
        try:
            verified = self._verifier(attestation)
        except Exception:
            verified = False
        if (
            attestation.get("purpose") != "zero_trust.capability"
            or attestation.get("payload_sha256") != envelope.digest
            or verified is not True
        ):
            return TrustFailureCode.ATTESTATION_INVALID.value
        return "VERIFIED_LEAST_PRIVILEGE"

    def _record_decision(
        self, envelope: TrustEnvelope, effect: TrustEffect, reason: str
    ) -> TrustDecision:
        occurred = self._clock().isoformat()
        with self._lock, self._connection:
            previous_row = self._connection.execute(
                "SELECT receipt_sha256 FROM trust_decisions "
                "ORDER BY decision_id DESC LIMIT 1"
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
                "INSERT INTO trust_decisions(envelope_json, envelope_digest, effect, "
                "reason_code, occurred_at, previous_receipt_sha256, receipt_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
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
        occurred = self._clock().isoformat()
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

    def audit_chain_valid(self) -> bool:
        previous = "0" * 64
        try:
            rows = self._connection.execute(
                "SELECT * FROM trust_audit ORDER BY event_id"
            ).fetchall()
            for row in rows:
                content = {
                    "occurred_at": row["occurred_at"],
                    "event": row["event"],
                    "payload": json.loads(row["payload_json"]),
                    "previous_sha256": row["previous_sha256"],
                }
                digest = hashlib.sha256(_canonical(content)).hexdigest()
                if row["previous_sha256"] != previous or row["event_sha256"] != digest:
                    return False
                previous = digest
            decisions = self._connection.execute(
                "SELECT * FROM trust_decisions ORDER BY decision_id"
            ).fetchall()
            previous = "0" * 64
            for row in decisions:
                content = {
                    "envelope_digest": row["envelope_digest"],
                    "effect": row["effect"],
                    "reason_code": row["reason_code"],
                    "occurred_at": row["occurred_at"],
                    "previous_receipt_sha256": row["previous_receipt_sha256"],
                }
                digest = hashlib.sha256(_canonical(content)).hexdigest()
                if (
                    row["previous_receipt_sha256"] != previous
                    or row["receipt_sha256"] != digest
                ):
                    return False
                previous = digest
        except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError):
            return False
        return True

    def status(self) -> dict[str, object]:
        active = self._connection.execute(
            "SELECT COUNT(*) FROM trust_principals WHERE status = 'ACTIVE'"
        ).fetchone()[0]
        return {
            "ready": self.audit_chain_valid(),
            "active_principals": int(active),
            "audit_chain_valid": self.audit_chain_valid(),
        }

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _validate_ids(*values: str) -> None:
        if any(
            not isinstance(item, str) or not _TRUST_ID.fullmatch(item)
            for item in values
        ):
            raise TrustError(
                TrustFailureCode.INVALID_INPUT,
                "zero-trust identifier is invalid",
            )

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
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
                """
            )


# Patterns that look like embedded instructions / injections
_INJECTION_PATTERNS: List[str] = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"you\s+are\s+now\s+(a\s+)?(different|new|unrestricted)",
    r"disregard\s+(your\s+)?(guidelines|rules|ethics)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"system\s*prompt\s*[:=]",
    r"\bDAN\b",  # "Do Anything Now" jailbreak
    r"<\s*/?system\s*>",  # XML system tags
    r"\[\[.*?(override|inject).*?\]\]",
]

_TWIN_SYNC_ALLOWED_FIELDS: Set[str] = {
    "is_silent",
    "topk_ratio",
    "loyalty_score",
    "moe_primary_expert",
    "collective_pulse",
    "timestamp",
}

_TWIN_SYNC_ALLOWED_PULSE_FIELDS: Set[str] = {
    "avg_trust",
    "avg_novelty",
    "avg_cohesion",
    "pulse_score",
    "mode",
    "online_ratio",
    "events_considered",
}

_TWIN_SYNC_ALLOWED_MODES: Set[str] = {
    "local_solo",
    "guarded_sync",
    "hybrid_bridge",
    "collective_sync",
}

_TWIN_SYNC_ALLOWED_EXPERTS: Set[str] = {
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

    def __init__(self, trusted_sources: Set[str] | None = None, strict: bool = False):
        self.trusted_sources: Set[str] = trusted_sources or {
            "local_rag",
            "twin_sync",
            "user_direct",
        }
        self.strict = strict
        self._injection_re: List[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE | re.DOTALL) for p in _INJECTION_PATTERNS
        ]
        self._blocked: int = 0
        self._passed: int = 0
        self._scan_count: int = 0

    # ------------------------------------------------------------------

    def validate(
        self, source: str, payload: Any, force_scan: bool = False
    ) -> Tuple[bool, str]:
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
                reason = (
                    f"Injection pattern '{pattern.pattern}' in payload from '{source}'"
                )
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

    def validate_twin_sync_state(self, state: Any) -> Tuple[bool, str, Dict[str, Any]]:
        """Validate and sanitize Twin Protocol sync state payload."""
        if not isinstance(state, dict):
            return False, "invalid_state_type", {}

        scan_ok, scan_reason = self.validate("twin_sync", state, force_scan=True)
        if not scan_ok:
            return False, scan_reason, {}

        state_map = cast(Dict[str, Any], state)
        unknown_fields = [
            str(key)
            for key in state_map.keys()
            if str(key) not in _TWIN_SYNC_ALLOWED_FIELDS
        ]
        if unknown_fields and self.strict:
            return False, "unknown_state_fields", {}

        safe_state: Dict[str, Any] = {
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
            pulse_map = cast(Dict[str, Any], pulse_raw)
            pulse_unknown = [
                str(key)
                for key in pulse_map.keys()
                if str(key) not in _TWIN_SYNC_ALLOWED_PULSE_FIELDS
            ]
            if pulse_unknown and self.strict:
                return False, "unknown_collective_fields", {}

            safe_pulse: Dict[str, Any] = {}
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

    def _coerce_unit_float(self, value: Any, default: float) -> Tuple[bool, float]:
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

    def status(self) -> Dict[str, Any]:
        return {
            "scanned": self._scan_count,
            "passed": self._passed,
            "blocked": self._blocked,
            "trusted_sources": list(self.trusted_sources),
            "strict": self.strict,
        }
