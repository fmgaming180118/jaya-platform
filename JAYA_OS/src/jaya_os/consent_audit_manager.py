"""
consent_audit_manager.py — Consent record management, permission gating, and audit log.

JAYA_OS owns authorization.  This module adds a consent lifecycle layer on top
of CapabilitySandbox so that every grant issuance is backed by an active,
unexpired ConsentRecord and every execution is appended to a durable AuditLog.

Key invariants:
    - No grant is issued without an active ConsentRecord.
    - Revoked subjects cannot obtain new grants.
    - Every AuditReceipt produced by CapabilitySandbox is appended to AuditLog.
    - AuditLog can be exported to JSON for compliance review.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional


# ---------------------------------------------------------------------------
# Consent Record
# ---------------------------------------------------------------------------


@dataclass
class ConsentRecord:
    """
    Explicit, bounded consent granted by the device owner for a set of actions.

    Fields:
        consent_id      — unique identifier for this consent record
        subject         — the agent or user identity that was granted consent
        action_set      — frozenset of OS actions covered by this consent
        reference       — human-readable consent provenance (e.g. "user-tapped-allow-2026-08-02")
        granted_at      — epoch seconds when consent was recorded
        expires_at      — epoch seconds when consent expires (mandatory TTL)
    """

    consent_id: str
    subject: str
    action_set: frozenset
    reference: str
    granted_at: float
    expires_at: float

    def is_active(self, *, clock: float | None = None) -> bool:
        """Return True if this consent record has not yet expired."""
        now = clock if clock is not None else time.time()
        return now < self.expires_at

    def covers(self, action: str) -> bool:
        return action in self.action_set

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["action_set"] = sorted(self.action_set)
        return d


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


@dataclass
class AuditLogEntry:
    entry_id: str
    event_type: str  # "GRANT_ISSUED" | "EXECUTION" | "REVOCATION" | "CONSENT_CREATED"
    subject: str
    action: Optional[str]
    timestamp: float
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuditLog:
    """
    Append-only audit log for all capability lifecycle events.

    All grant issuances, executions, revocations, and consent creations
    are recorded here.  The log is kept in memory and can be exported to JSON.
    """

    def __init__(self, max_entries: int = 5000) -> None:
        if not 10 <= max_entries <= 100_000:
            raise ValueError("max_entries must be between 10 and 100 000")
        self._max_entries = max_entries
        self._entries: List[AuditLogEntry] = []

    def append_entry(self, entry: AuditLogEntry) -> None:
        """Append a new entry; oldest entries are evicted when the log is full."""
        if len(self._entries) >= self._max_entries:
            self._entries.pop(0)
        self._entries.append(entry)

    def append_receipt(self, receipt: Dict[str, Any], subject: str) -> None:
        """Convenience: convert an AuditReceipt dict to a log entry."""
        entry = AuditLogEntry(
            entry_id=str(uuid.uuid4()),
            event_type="EXECUTION",
            subject=subject,
            action=receipt.get("action"),
            timestamp=receipt.get("started_at", time.time()),
            details={
                "receipt_id": receipt.get("receipt_id"),
                "status": receipt.get("status"),
                "duration_ms": receipt.get("duration_ms"),
                "error_code": receipt.get("error_code"),
            },
        )
        self.append_entry(entry)

    def query_by_subject(self, subject: str) -> List[AuditLogEntry]:
        return [e for e in self._entries if e.subject == subject]

    def query_by_event_type(self, event_type: str) -> List[AuditLogEntry]:
        return [e for e in self._entries if e.event_type == event_type]

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def export_json(self, *, indent: int = 2) -> str:
        return json.dumps([e.to_dict() for e in self._entries], indent=indent)


# ---------------------------------------------------------------------------
# Permission Manager
# ---------------------------------------------------------------------------


class PermissionDenied(PermissionError):
    """Raised when permission is denied at the consent layer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class PermissionManager:
    """
    Consent-gated wrapper around CapabilitySandbox.issue_grant().

    Rules:
        1. Subject must have an active ConsentRecord covering all requested actions.
        2. Subject must not be in the revocation list.
        3. Every grant issuance is recorded in the AuditLog.
        4. Every OS execution receipt is appended to the AuditLog by the caller.
    """

    def __init__(
        self,
        sandbox: Any,  # CapabilitySandbox instance from JAYA_OS
        *,
        audit_log: AuditLog | None = None,
        clock: Any = None,
    ) -> None:
        self._sandbox = sandbox
        self._audit_log = audit_log or AuditLog()
        self._clock = clock or time.time
        self._consent_records: Dict[str, List[ConsentRecord]] = {}
        self._revoked_subjects: set[str] = set()

    # ------------------------------------------------------------------
    # Consent management
    # ------------------------------------------------------------------

    def record_consent(
        self,
        subject: str,
        action_set: Iterable[str],
        reference: str,
        *,
        ttl_seconds: float = 3600.0,
    ) -> ConsentRecord:
        """
        Record explicit consent from the device owner for a subject and action set.

        Args:
            subject     : Agent / user identity receiving consent.
            action_set  : OS actions covered.
            reference   : Human-readable consent provenance (≤ 200 chars).
            ttl_seconds : How long consent is valid (max 24 h).

        Returns:
            A new ConsentRecord.
        """
        if not subject or len(subject) > 200:
            raise ValueError("subject must be 1–200 characters")
        if not reference or len(reference) > 200:
            raise ValueError("reference must be 1–200 characters")
        if not 1.0 <= ttl_seconds <= 86_400.0:
            raise ValueError("ttl_seconds must be between 1 and 86400 (24 h)")

        clean_actions = frozenset(str(a) for a in action_set)
        if not clean_actions:
            raise ValueError("action_set must contain at least one action")

        now = self._clock()
        record = ConsentRecord(
            consent_id=str(uuid.uuid4()),
            subject=subject,
            action_set=clean_actions,
            reference=reference,
            granted_at=now,
            expires_at=now + ttl_seconds,
        )
        self._consent_records.setdefault(subject, []).append(record)

        self._audit_log.append_entry(
            AuditLogEntry(
                entry_id=str(uuid.uuid4()),
                event_type="CONSENT_CREATED",
                subject=subject,
                action=None,
                timestamp=now,
                details={
                    "consent_id": record.consent_id,
                    "action_set": sorted(clean_actions),
                    "expires_at": record.expires_at,
                    "reference": reference,
                },
            )
        )
        return record

    def revoke_subject(self, subject: str, *, reason: str = "") -> None:
        """Permanently revoke all grant-issuance rights for a subject."""
        self._revoked_subjects.add(subject)
        self._audit_log.append_entry(
            AuditLogEntry(
                entry_id=str(uuid.uuid4()),
                event_type="REVOCATION",
                subject=subject,
                action=None,
                timestamp=self._clock(),
                details={"reason": reason or "unspecified"},
            )
        )

    def has_active_consent(self, subject: str, action: str) -> bool:
        """Return True if the subject has a live, unexpired consent covering action."""
        now = self._clock()
        for record in self._consent_records.get(subject, []):
            if record.is_active(clock=now) and record.covers(action):
                return True
        return False

    # ------------------------------------------------------------------
    # Grant issuance
    # ------------------------------------------------------------------

    def issue_grant(
        self,
        *,
        subject: str,
        actions: Iterable[str],
        resources: Mapping[str, Iterable[str]],
        ttl_seconds: float,
        max_uses: int = 1,
        consented_actions: Iterable[str] = (),
        consent_reference: str | None = None,
    ) -> str:
        """
        Issue a capability grant if and only if the subject has active consent.

        Raises:
            PermissionDenied(SUBJECT_REVOKED)     if subject is in the revocation list.
            PermissionDenied(CONSENT_NOT_FOUND)   if no active consent covers all actions.
        """
        if subject in self._revoked_subjects:
            raise PermissionDenied(
                "SUBJECT_REVOKED",
                f"Subject '{subject}' has been revoked and cannot obtain new grants",
            )

        action_list = list(actions)
        for action in action_list:
            if not self.has_active_consent(subject, action):
                raise PermissionDenied(
                    "CONSENT_NOT_FOUND",
                    f"No active consent record found for subject '{subject}' "
                    f"covering action '{action}'; explicit owner consent is required",
                )

        grant_token = self._sandbox.issue_grant(
            subject=subject,
            actions=action_list,
            resources=resources,
            ttl_seconds=ttl_seconds,
            max_uses=max_uses,
            consented_actions=consented_actions,
            consent_reference=consent_reference,
        )

        self._audit_log.append_entry(
            AuditLogEntry(
                entry_id=str(uuid.uuid4()),
                event_type="GRANT_ISSUED",
                subject=subject,
                action=",".join(sorted(action_list)),
                timestamp=self._clock(),
                details={
                    "ttl_seconds": ttl_seconds,
                    "max_uses": max_uses,
                    "grant_token_prefix": grant_token[:8] + "...",
                },
            )
        )

        return grant_token

    @property
    def audit_log(self) -> AuditLog:
        return self._audit_log
