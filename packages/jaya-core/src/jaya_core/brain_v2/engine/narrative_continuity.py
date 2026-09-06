"""Pillar 31 — signed, evidence-grounded narrative continuity.

Generated prose is never promoted to history. The ledger stores typed events,
preserves corrections, and builds deterministic snapshots with explicit truth
classes and provenance.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_SCHEMA_VERSION = 1
_ZERO_HASH = "0" * 64
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,191}$")
_SAFE_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class NarrativeFailureCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    IDENTITY_NOT_CONFIGURED = "IDENTITY_NOT_CONFIGURED"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    EVENT_NOT_FOUND = "EVENT_NOT_FOUND"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    LEDGER_CORRUPT = "LEDGER_CORRUPT"
    SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"
    MIGRATION_FAILED = "MIGRATION_FAILED"
    STORAGE_ERROR = "STORAGE_ERROR"


class NarrativeContinuityError(RuntimeError):
    """Typed failure without a fabricated persistence fallback."""

    def __init__(self, code: NarrativeFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class NarrativeEventType(str, Enum):
    CONVERSATION_TURN = "CONVERSATION_TURN"
    EXTERNAL_FEEDBACK = "EXTERNAL_FEEDBACK"
    FACT_ASSERTED = "FACT_ASSERTED"
    INFERENCE_RECORDED = "INFERENCE_RECORDED"
    COMMITMENT_CREATED = "COMMITMENT_CREATED"
    COMMITMENT_CHANGED = "COMMITMENT_CHANGED"
    CORRECTION_RECORDED = "CORRECTION_RECORDED"
    PLANNER_DECISION = "PLANNER_DECISION"
    ACTION_RESULT = "ACTION_RESULT"
    MIGRATED_RAW_EVENT = "MIGRATED_RAW_EVENT"
    ROLLBACK_RECORDED = "ROLLBACK_RECORDED"


class NarrativeTruthClass(str, Enum):
    RAW_EVENT = "RAW_EVENT"
    VERIFIED_FACT = "VERIFIED_FACT"
    INFERENCE = "INFERENCE"
    NARRATIVE_SUMMARY = "NARRATIVE_SUMMARY"


@runtime_checkable
class NarrativeSigner(Protocol):
    @property
    def actor_id(self) -> str: ...

    @property
    def key_id(self) -> str: ...

    def sign(self, purpose: str, payload_sha256: str) -> Mapping[str, object]: ...

    def verify(self, attestation: Mapping[str, object]) -> bool: ...

    def health_check(self) -> bool: ...


class DNAAnchorNarrativeSigner:
    """Production signer backed by the portable DNA Anchor key lineage."""

    def __init__(self, anchor: Any) -> None:
        self._anchor = anchor
        record = anchor.load_identity()
        self._actor_id = str(record.brain_id)

    @property
    def actor_id(self) -> str:
        return self._actor_id

    @property
    def key_id(self) -> str:
        record = self._anchor.load_identity()
        return f"{record.brain_id}:{record.key_version}"

    def sign(self, purpose: str, payload_sha256: str) -> Mapping[str, object]:
        return self._anchor.sign_attestation(purpose, payload_sha256).to_dict()

    def verify(self, attestation: Mapping[str, object]) -> bool:
        return bool(self._anchor.verify_attestation(attestation))

    def health_check(self) -> bool:
        try:
            self._anchor.load_identity()
            return True
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return False


@dataclass(frozen=True, slots=True)
class NarrativeEvent:
    sequence: int
    event_id: str
    request_id: str
    occurred_at: str
    actor_id: str
    event_type: NarrativeEventType
    truth_class: NarrativeTruthClass
    subject: str
    payload: dict[str, Any]
    evidence_refs: tuple[str, ...]
    causation_id: str | None
    commitment_id: str | None
    correction_of: str | None
    previous_sha256: str
    event_sha256: str
    signer_key_id: str
    attestation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["event_type"] = self.event_type.value
        value["truth_class"] = self.truth_class.value
        value["evidence_refs"] = list(self.evidence_refs)
        return value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NarrativeContinuityError(
            NarrativeFailureCode.INVALID_INPUT,
            "narrative payload must be finite JSON data",
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _bounded_text(value: object, *, limit: int, field: str) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text.encode("utf-8")) > limit:
        raise NarrativeContinuityError(
            NarrativeFailureCode.INVALID_INPUT,
            f"{field} is empty or exceeds its byte limit",
        )
    return text


def _safe_name(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not _SAFE_NAME.fullmatch(text):
        raise NarrativeContinuityError(
            NarrativeFailureCode.INVALID_INPUT,
            f"{field} contains unsupported characters",
        )
    return text


class NarrativeContinuity:
    """Append-only narrative ledger and versioned snapshot store."""

    def __init__(
        self,
        database_path: Path | str | None = None,
        signer: NarrativeSigner | None = None,
        *,
        persist_path: Path | str | None = None,
        max_payload_bytes: int = 65_536,
        summary_window: int = 8,
        max_events: int | None = None,
        legacy_json_path: Path | str | None = None,
    ) -> None:
        if signer is None or not isinstance(signer, NarrativeSigner):
            raise NarrativeContinuityError(
                NarrativeFailureCode.IDENTITY_NOT_CONFIGURED,
                "Narrative Continuity requires a persistent identity signer",
            )
        if not signer.health_check():
            raise NarrativeContinuityError(
                NarrativeFailureCode.IDENTITY_NOT_CONFIGURED,
                "Narrative identity signer is unavailable",
            )
        if not 1_024 <= int(max_payload_bytes) <= 1_048_576:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "max_payload_bytes must be between 1024 and 1048576",
            )
        if not 1 <= int(summary_window) <= 100:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "summary_window must be between 1 and 100",
            )
        self.max_events = max(1, min(int(max_events or 256), 10_000))
        self.summary_window = int(summary_window)
        self.max_payload_bytes = int(max_payload_bytes)
        self.signer = signer
        selected = database_path if database_path is not None else persist_path
        if selected is None:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "a persistent narrative database path is required",
            )
        selected_path = Path(selected).expanduser()
        inferred_legacy: Path | None = None
        if selected_path.suffix.lower() == ".json":
            inferred_legacy = selected_path
            selected_path = selected_path.with_suffix(".sqlite3")
        self.database_path = selected_path.resolve()
        self.persist_path = str(self.database_path)
        self.legacy_json_path = (
            Path(legacy_json_path).expanduser().resolve()
            if legacy_json_path is not None
            else inferred_legacy.resolve() if inferred_legacy is not None else None
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                self.database_path,
                timeout=5.0,
                check_same_thread=False,
            )
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._migrate_schema()
            self.verify_integrity()
            self._migrate_legacy_json()
        except NarrativeContinuityError:
            connection = getattr(self, "_connection", None)
            if connection is not None:
                connection.close()
            raise
        except sqlite3.Error as exc:
            connection = getattr(self, "_connection", None)
            if connection is not None:
                connection.close()
            raise NarrativeContinuityError(
                NarrativeFailureCode.STORAGE_ERROR,
                "narrative ledger cannot be initialized",
            ) from exc

    def append_event(
        self,
        *,
        request_id: str,
        event_type: NarrativeEventType | str,
        truth_class: NarrativeTruthClass | str,
        subject: str,
        payload: Mapping[str, Any],
        evidence_refs: Sequence[str] = (),
        causation_id: str | None = None,
        commitment_id: str | None = None,
        correction_of: str | None = None,
        actor_id: str | None = None,
        occurred_at: str | None = None,
    ) -> NarrativeEvent:
        request_id = _safe_name(request_id, field="request_id")
        subject = _bounded_text(subject, limit=512, field="subject")
        try:
            event_kind = NarrativeEventType(event_type)
            truth_kind = NarrativeTruthClass(truth_class)
        except ValueError as exc:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "event_type or truth_class is invalid",
            ) from exc
        signing_actor_id = self.signer.actor_id
        actor = _safe_name(actor_id or signing_actor_id, field="actor_id")
        if actor != signing_actor_id:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "actor_id must match the active signing identity",
            )
        payload_dict = dict(payload)
        payload_bytes = _canonical(payload_dict)
        if len(payload_bytes) > self.max_payload_bytes:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "narrative payload exceeds max_payload_bytes",
            )
        if truth_kind is NarrativeTruthClass.NARRATIVE_SUMMARY:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "NARRATIVE_SUMMARY is reserved for signed snapshots",
            )
        if (
            event_kind is NarrativeEventType.INFERENCE_RECORDED
            and truth_kind is not NarrativeTruthClass.INFERENCE
        ):
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "inference events must retain the INFERENCE truth class",
            )
        if event_kind is NarrativeEventType.FACT_ASSERTED and (
            truth_kind is not NarrativeTruthClass.VERIFIED_FACT
            or "value" not in payload_dict
        ):
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "fact events require VERIFIED_FACT and an explicit value",
            )
        if (
            event_kind is NarrativeEventType.CORRECTION_RECORDED
            and truth_kind is NarrativeTruthClass.VERIFIED_FACT
            and "value" not in payload_dict
        ):
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "verified corrections require an explicit value",
            )
        raw_event_types = {
            NarrativeEventType.CONVERSATION_TURN,
            NarrativeEventType.EXTERNAL_FEEDBACK,
            NarrativeEventType.COMMITMENT_CREATED,
            NarrativeEventType.COMMITMENT_CHANGED,
            NarrativeEventType.PLANNER_DECISION,
            NarrativeEventType.ACTION_RESULT,
            NarrativeEventType.MIGRATED_RAW_EVENT,
            NarrativeEventType.ROLLBACK_RECORDED,
        }
        if (
            event_kind in raw_event_types
            and truth_kind is not NarrativeTruthClass.RAW_EVENT
        ):
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "this event type must retain the RAW_EVENT truth class",
            )
        refs = tuple(
            dict.fromkeys(_safe_name(ref, field="evidence_ref") for ref in evidence_refs)
        )
        if truth_kind is NarrativeTruthClass.VERIFIED_FACT and not refs:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "verified facts require at least one evidence reference",
            )
        if refs:
            missing_refs = [ref for ref in refs if not self._evidence_exists(ref)]
            if missing_refs:
                raise NarrativeContinuityError(
                    NarrativeFailureCode.INVALID_INPUT,
                    "narrative event references evidence that is not registered",
                )
        if event_kind is NarrativeEventType.CORRECTION_RECORDED and not correction_of:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "a correction must reference the event it corrects",
            )
        causation = _safe_name(causation_id, field="causation_id") if causation_id else None
        commitment = _safe_name(commitment_id, field="commitment_id") if commitment_id else None
        correction = _safe_name(correction_of, field="correction_of") if correction_of else None
        timestamp = occurred_at or _utc_now()
        try:
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None:
                raise ValueError("timezone")
        except ValueError as exc:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "occurred_at must be a timezone-aware ISO timestamp",
            ) from exc

        with self._lock:
            self._ensure_integrity()
            for linked_id, field in (
                (causation, "causation_id"),
                (correction, "correction_of"),
            ):
                if linked_id and not self._event_exists(linked_id):
                    raise NarrativeContinuityError(
                        NarrativeFailureCode.EVENT_NOT_FOUND,
                        f"{field} does not reference an existing event",
                    )
            previous = self._last_event_hash()
            event_id = f"nev-{uuid.uuid4()}"
            signer_key_id = self.signer.key_id
            unsigned = {
                "schema_version": _SCHEMA_VERSION,
                "event_id": event_id,
                "request_id": request_id,
                "occurred_at": timestamp,
                "actor_id": actor,
                "event_type": event_kind.value,
                "truth_class": truth_kind.value,
                "subject": subject,
                "payload": payload_dict,
                "evidence_refs": list(refs),
                "causation_id": causation,
                "commitment_id": commitment,
                "correction_of": correction,
                "previous_sha256": previous,
                "signer_key_id": signer_key_id,
            }
            event_hash = _digest(unsigned)
            attestation = dict(self.signer.sign("narrative.event", event_hash))
            if (
                str(attestation.get("payload_sha256")) != event_hash
                or not self._attestation_matches_identity(
                    attestation, signer_key_id, actor
                )
                or not self.signer.verify(attestation)
            ):
                raise NarrativeContinuityError(
                    NarrativeFailureCode.SIGNATURE_INVALID,
                    "identity signer returned an invalid event attestation",
                )
            try:
                with self._connection:
                    cursor = self._connection.execute(
                        """
                        INSERT INTO narrative_events (
                            event_id, request_id, occurred_at, actor_id, event_type,
                            truth_class, subject, payload_json, evidence_refs_json,
                            causation_id, commitment_id, correction_of,
                            previous_sha256, event_sha256, signer_key_id,
                            attestation_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id, request_id, timestamp, actor, event_kind.value,
                            truth_kind.value, subject, payload_bytes.decode("utf-8"),
                            _canonical(list(refs)).decode("utf-8"), causation,
                            commitment, correction, previous, event_hash,
                            signer_key_id,
                            _canonical(attestation).decode("utf-8"),
                        ),
                    )
                    sequence = int(cursor.lastrowid)
            except sqlite3.IntegrityError as exc:
                if "request_id" in str(exc).lower() or "unique" in str(exc).lower():
                    raise NarrativeContinuityError(
                        NarrativeFailureCode.DUPLICATE_REQUEST,
                        "narrative request_id has already been committed",
                    ) from exc
                raise NarrativeContinuityError(
                    NarrativeFailureCode.INVALID_INPUT,
                    "narrative event violates ledger constraints",
                ) from exc
            except sqlite3.Error as exc:
                raise NarrativeContinuityError(
                    NarrativeFailureCode.STORAGE_ERROR,
                    "narrative event cannot be persisted",
                ) from exc
            return NarrativeEvent(
                sequence=sequence,
                event_id=event_id,
                request_id=request_id,
                occurred_at=timestamp,
                actor_id=actor,
                event_type=event_kind,
                truth_class=truth_kind,
                subject=subject,
                payload=payload_dict,
                evidence_refs=refs,
                causation_id=causation,
                commitment_id=commitment,
                correction_of=correction,
                previous_sha256=previous,
                event_sha256=event_hash,
                signer_key_id=signer_key_id,
                attestation=attestation,
            )

    def register_evidence(
        self,
        *,
        content: bytes,
        source_uri: str,
        media_type: str = "application/octet-stream",
    ) -> str:
        """Register bytes observed by the runtime without embedding them in history."""
        if not isinstance(content, bytes) or not content:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "evidence content must be non-empty bytes",
            )
        if len(content) > 67_108_864:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "evidence content exceeds the 64 MiB registration limit",
            )
        bounded_source = _bounded_text(source_uri, limit=4_096, field="source_uri")
        bounded_media_type = _bounded_text(
            media_type, limit=255, field="media_type"
        )
        content_hash = hashlib.sha256(content).hexdigest()
        evidence_ref = f"evidence:{content_hash}"
        with self._lock:
            self._ensure_integrity()
            existing = self._connection.execute(
                """
                SELECT evidence_ref FROM narrative_evidence
                WHERE evidence_ref = ?
                """,
                (evidence_ref,),
            ).fetchone()
            if existing is not None:
                self._verified_evidence()
                return evidence_ref
            recorded_at = _utc_now()
            signer_key_id = self.signer.key_id
            unsigned = {
                "schema_version": _SCHEMA_VERSION,
                "evidence_ref": evidence_ref,
                "content_sha256": content_hash,
                "content_bytes": len(content),
                "source_uri": bounded_source,
                "media_type": bounded_media_type,
                "recorded_at": recorded_at,
                "signer_key_id": signer_key_id,
            }
            receipt_hash = _digest(unsigned)
            attestation = dict(
                self.signer.sign("narrative.evidence", receipt_hash)
            )
            if (
                str(attestation.get("payload_sha256")) != receipt_hash
                or not self._attestation_matches_identity(
                    attestation, signer_key_id, self.signer.actor_id
                )
                or not self.signer.verify(attestation)
            ):
                raise NarrativeContinuityError(
                    NarrativeFailureCode.SIGNATURE_INVALID,
                    "identity signer returned an invalid evidence attestation",
                )
            try:
                with self._connection:
                    self._connection.execute(
                        """
                        INSERT INTO narrative_evidence (
                            evidence_ref, content_sha256, content_bytes,
                            source_uri, media_type, recorded_at, signer_key_id,
                            receipt_sha256, attestation_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            evidence_ref,
                            content_hash,
                            len(content),
                            bounded_source,
                            bounded_media_type,
                            recorded_at,
                            signer_key_id,
                            receipt_hash,
                            _canonical(attestation).decode("utf-8"),
                        ),
                    )
            except sqlite3.Error as exc:
                raise NarrativeContinuityError(
                    NarrativeFailureCode.STORAGE_ERROR,
                    "narrative evidence receipt cannot be persisted",
                ) from exc
            return evidence_ref

    def remember_turn(
        self,
        user_text: str,
        logic_expr: Any = None,
        runtime_result: Mapping[str, Any] | None = None,
        response_text: str = "",
        source: str = "runtime_intent",
        *,
        request_id: str | None = None,
        causation_id: str | None = None,
    ) -> dict[str, Any]:
        prompt = _bounded_text(user_text, limit=16_384, field="user_text")
        result = dict(runtime_result or {})
        explicit_ok = result.get("ok") if isinstance(result.get("ok"), bool) else None
        event = self.append_event(
            request_id=request_id or f"turn-{uuid.uuid4()}",
            event_type=NarrativeEventType.CONVERSATION_TURN,
            truth_class=NarrativeTruthClass.RAW_EVENT,
            subject=_derive_topic(prompt),
            payload={
                "source": _safe_name(source, field="source"),
                "user_text": prompt,
                "response_text": " ".join(str(response_text or "").split())[:16_384],
                "intent": _derive_intent(logic_expr),
                "runtime_status": result.get("status"),
                "ok": explicit_ok,
            },
            causation_id=causation_id,
        )
        return self._compat_event(event)

    def remember_feedback(
        self,
        task: str,
        score: float | None,
        source: str = "twin_feedback",
        *,
        request_id: str | None = None,
        causation_id: str | None = None,
    ) -> dict[str, Any]:
        value: float | None = None
        if score is not None:
            if isinstance(score, bool):
                raise NarrativeContinuityError(
                    NarrativeFailureCode.INVALID_INPUT,
                    "feedback score must be numeric",
                )
            value = float(score)
            if not 0.0 <= value <= 1.0:
                raise NarrativeContinuityError(
                    NarrativeFailureCode.INVALID_INPUT,
                    "feedback score must be between 0 and 1",
                )
        event = self.append_event(
            request_id=request_id or f"feedback-{uuid.uuid4()}",
            event_type=NarrativeEventType.EXTERNAL_FEEDBACK,
            truth_class=NarrativeTruthClass.RAW_EVENT,
            subject=_bounded_text(task, limit=2_048, field="task"),
            payload={"source": _safe_name(source, field="source"), "score": value},
            causation_id=causation_id,
        )
        return self._compat_event(event)

    def record_verified_fact(
        self,
        *,
        request_id: str,
        subject: str,
        value: Any,
        evidence_refs: Sequence[str],
        causation_id: str | None = None,
    ) -> NarrativeEvent:
        return self.append_event(
            request_id=request_id,
            event_type=NarrativeEventType.FACT_ASSERTED,
            truth_class=NarrativeTruthClass.VERIFIED_FACT,
            subject=subject,
            payload={"value": value},
            evidence_refs=evidence_refs,
            causation_id=causation_id,
        )

    def record_inference(
        self,
        *,
        request_id: str,
        subject: str,
        inference: Any,
        evidence_refs: Sequence[str] = (),
        causation_id: str | None = None,
    ) -> NarrativeEvent:
        return self.append_event(
            request_id=request_id,
            event_type=NarrativeEventType.INFERENCE_RECORDED,
            truth_class=NarrativeTruthClass.INFERENCE,
            subject=subject,
            payload={"inference": inference},
            evidence_refs=evidence_refs,
            causation_id=causation_id,
        )

    def record_commitment(
        self,
        *,
        request_id: str,
        commitment_id: str,
        subject: str,
        details: Mapping[str, Any],
        evidence_refs: Sequence[str] = (),
        causation_id: str | None = None,
    ) -> NarrativeEvent:
        return self.append_event(
            request_id=request_id,
            event_type=NarrativeEventType.COMMITMENT_CREATED,
            truth_class=NarrativeTruthClass.RAW_EVENT,
            subject=subject,
            payload={"state": "ACTIVE", "details": dict(details)},
            evidence_refs=evidence_refs,
            commitment_id=commitment_id,
            causation_id=causation_id,
        )

    def record_correction(
        self,
        *,
        request_id: str,
        correction_of: str,
        subject: str,
        corrected_value: Any,
        evidence_refs: Sequence[str],
        truth_class: NarrativeTruthClass = NarrativeTruthClass.VERIFIED_FACT,
    ) -> NarrativeEvent:
        return self.append_event(
            request_id=request_id,
            event_type=NarrativeEventType.CORRECTION_RECORDED,
            truth_class=truth_class,
            subject=subject,
            payload={"value": corrected_value},
            evidence_refs=evidence_refs,
            correction_of=correction_of,
            causation_id=correction_of,
        )

    def change_commitment(
        self,
        *,
        request_id: str,
        commitment_id: str,
        previous_event_id: str,
        subject: str,
        state: str,
        details: Mapping[str, Any],
        evidence_refs: Sequence[str] = (),
    ) -> NarrativeEvent:
        normalized_state = str(state).strip().upper()
        if normalized_state not in {"ACTIVE", "COMPLETED", "CANCELLED"}:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "commitment state must be ACTIVE, COMPLETED, or CANCELLED",
            )
        return self.append_event(
            request_id=request_id,
            event_type=NarrativeEventType.COMMITMENT_CHANGED,
            truth_class=NarrativeTruthClass.RAW_EVENT,
            subject=subject,
            payload={"state": normalized_state, "details": dict(details)},
            evidence_refs=evidence_refs,
            commitment_id=commitment_id,
            correction_of=previous_event_id,
            causation_id=previous_event_id,
        )

    def record_rollback(
        self,
        *,
        request_id: str,
        target_snapshot_version: int,
        reason: str,
    ) -> NarrativeEvent:
        snapshot = self.snapshot_at_version(target_snapshot_version)
        return self.append_event(
            request_id=request_id,
            event_type=NarrativeEventType.ROLLBACK_RECORDED,
            truth_class=NarrativeTruthClass.RAW_EVENT,
            subject="runtime.rollback",
            payload={
                "target_snapshot_version": target_snapshot_version,
                "target_snapshot_sha256": snapshot["snapshot_sha256"],
                "reason": _bounded_text(reason, limit=2_048, field="reason"),
            },
        )

    def snapshot(self, limit: int = 5, max_chars: int = 600) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 100))
        safe_chars = max(120, min(int(max_chars), 20_000))
        with self._lock:
            events = self._verified_events()
            watermark = events[-1].sequence if events else 0
            existing = self._latest_snapshot_for_watermark(watermark)
            if existing is None:
                structured = self._build_snapshot(events, self.summary_window)
                existing = self._persist_snapshot(watermark, structured)
            structured = dict(existing["snapshot"])
            recent = [self._compat_event(item) for item in events[-safe_limit:]]
            context = _canonical(
                {
                    "narrative_summary": structured,
                    "recent_events": [
                        {
                            "event_id": item.event_id,
                            "event_type": item.event_type.value,
                            "truth_class": item.truth_class.value,
                            "subject": item.subject,
                            "payload": item.payload,
                        }
                        for item in events[-safe_limit:]
                    ],
                }
            ).decode("utf-8")
            if len(context) > safe_chars:
                context = context[: safe_chars - 3] + "..."
            return {
                "snapshot_version": existing["snapshot_version"],
                "snapshot_sha256": existing["snapshot_sha256"],
                "source_watermark": watermark,
                "summary": structured,
                "recent": recent,
                "context": context,
                "total_events": len(events),
                "persist_path": self.persist_path,
            }

    def boot_context(self, snapshot_version: int | None = None) -> dict[str, Any]:
        snap = (
            self.snapshot_at_version(snapshot_version)
            if snapshot_version
            else self.snapshot(limit=self.summary_window, max_chars=20_000)
        )
        summary = dict(snap["snapshot"] if "snapshot" in snap else snap["summary"])
        return {
            "snapshot_version": snap["snapshot_version"],
            "snapshot_sha256": snap["snapshot_sha256"],
            "verified_facts": summary.get("verified_facts", []),
            "active_commitments": summary.get("active_commitments", []),
            "conflicts": summary.get("conflicts", []),
            "inferences": summary.get("inferences", []),
        }

    def snapshot_at_version(self, version: int) -> dict[str, Any]:
        if isinstance(version, bool) or int(version) <= 0:
            raise NarrativeContinuityError(
                NarrativeFailureCode.INVALID_INPUT,
                "snapshot version must be a positive integer",
            )
        row = self._connection.execute(
            """
            SELECT snapshot_version, created_at, source_watermark, snapshot_json,
                   source_sha256, snapshot_sha256, signer_key_id, attestation_json
            FROM narrative_snapshots WHERE snapshot_version = ?
            """,
            (int(version),),
        ).fetchone()
        if row is None:
            raise NarrativeContinuityError(
                NarrativeFailureCode.SNAPSHOT_NOT_FOUND,
                "narrative snapshot version does not exist",
            )
        return self._verified_snapshot_row(row)

    def verify_integrity(self) -> bool:
        with self._lock:
            self._verified_events()
            rows = self._connection.execute(
                """
                SELECT snapshot_version, created_at, source_watermark, snapshot_json,
                       source_sha256, snapshot_sha256, signer_key_id, attestation_json
                FROM narrative_snapshots ORDER BY snapshot_version
                """
            ).fetchall()
            for row in rows:
                self._verified_snapshot_row(row)
            self._verified_data_version = self._data_version()
            return True

    def _data_version(self) -> int:
        return int(self._connection.execute("PRAGMA data_version").fetchone()[0])

    def _ensure_integrity(self) -> None:
        """Revalidate the full chain only after an external database commit."""
        if getattr(self, "_verified_data_version", None) != self._data_version():
            self.verify_integrity()

    def health_check(self) -> bool:
        try:
            return self.signer.health_check() and self.verify_integrity()
        except NarrativeContinuityError:
            return False

    def status(self) -> dict[str, Any]:
        event_count = int(
            self._connection.execute("SELECT COUNT(*) FROM narrative_events").fetchone()[0]
        )
        snapshot_count = int(
            self._connection.execute("SELECT COUNT(*) FROM narrative_snapshots").fetchone()[0]
        )
        evidence_count = int(
            self._connection.execute("SELECT COUNT(*) FROM narrative_evidence").fetchone()[0]
        )
        healthy = self.health_check()
        return {
            "available": healthy,
            "schema_version": _SCHEMA_VERSION,
            "events": event_count,
            "snapshots": snapshot_count,
            "evidence_receipts": evidence_count,
            "append_only": True,
            "signed": True,
            "actor_id": self.signer.actor_id,
            "signer_key_id": self.signer.key_id,
            "persist_path": self.persist_path,
            "has_persistence": True,
            "summary": (
                self.snapshot(limit=self.summary_window, max_chars=2_000)["summary"]
                if healthy
                else {}
            ),
        }

    @property
    def _events(self) -> list[dict[str, Any]]:
        """Compatibility view; the durable ledger remains authoritative."""
        events = self._verified_events()
        return [self._compat_event(item) for item in events[-self.max_events :]]

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _build_snapshot(
        self, events: Sequence[NarrativeEvent], limit: int
    ) -> dict[str, Any]:
        corrected_ids = {item.correction_of for item in events if item.correction_of}
        active = [item for item in events if item.event_id not in corrected_ids]
        facts_by_subject: dict[str, list[NarrativeEvent]] = {}
        commitments: dict[str, NarrativeEvent] = {}
        inferences: list[NarrativeEvent] = []
        raw_events: list[NarrativeEvent] = []
        for item in active:
            if item.truth_class is NarrativeTruthClass.VERIFIED_FACT:
                facts_by_subject.setdefault(item.subject, []).append(item)
            elif item.truth_class is NarrativeTruthClass.INFERENCE:
                inferences.append(item)
            elif item.commitment_id:
                commitments[item.commitment_id] = item
            elif item.truth_class is NarrativeTruthClass.RAW_EVENT:
                raw_events.append(item)

        verified_facts: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        for subject in sorted(facts_by_subject):
            subject_events = facts_by_subject[subject]
            value_groups: dict[str, list[NarrativeEvent]] = {}
            for item in subject_events:
                value_groups.setdefault(_digest(item.payload.get("value")), []).append(item)
            if len(value_groups) > 1:
                conflicts.append(
                    {
                        "subject": subject,
                        "event_ids": [item.event_id for item in subject_events],
                        "status": "UNRESOLVED_CONFLICT",
                    }
                )
                continue
            latest = subject_events[-1]
            verified_facts.append(
                {
                    "subject": subject,
                    "value": latest.payload.get("value"),
                    "event_id": latest.event_id,
                    "evidence_refs": list(latest.evidence_refs),
                }
            )
        active_commitments = []
        for commitment_id in sorted(commitments):
            item = commitments[commitment_id]
            if str(item.payload.get("state", "ACTIVE")).upper() in {
                "CANCELLED",
                "COMPLETED",
            }:
                continue
            active_commitments.append(
                {
                    "commitment_id": commitment_id,
                    "subject": item.subject,
                    "details": item.payload.get("details"),
                    "event_id": item.event_id,
                    "evidence_refs": list(item.evidence_refs),
                }
            )
        return {
            "truth_class": NarrativeTruthClass.NARRATIVE_SUMMARY.value,
            "verified_facts": verified_facts,
            "active_commitments": active_commitments,
            "conflicts": conflicts,
            "inferences": [
                {
                    "subject": item.subject,
                    "inference": item.payload.get("inference"),
                    "event_id": item.event_id,
                    "evidence_refs": list(item.evidence_refs),
                }
                for item in inferences[-limit:]
            ],
            "recent_raw_events": [
                {
                    "subject": item.subject,
                    "event_type": item.event_type.value,
                    "event_id": item.event_id,
                    "occurred_at": item.occurred_at,
                }
                for item in raw_events[-limit:]
            ],
            "corrected_event_ids": sorted(str(item) for item in corrected_ids),
        }

    def _persist_snapshot(
        self, watermark: int, snapshot: Mapping[str, Any]
    ) -> dict[str, Any]:
        created_at = _utc_now()
        source_hash = self._last_event_hash() if watermark else _ZERO_HASH
        signer_key_id = self.signer.key_id
        unsigned = {
            "schema_version": _SCHEMA_VERSION,
            "created_at": created_at,
            "source_watermark": watermark,
            "source_sha256": source_hash,
            "snapshot": dict(snapshot),
            "signer_key_id": signer_key_id,
        }
        snapshot_hash = _digest(unsigned)
        attestation = dict(self.signer.sign("narrative.snapshot", snapshot_hash))
        if (
            str(attestation.get("payload_sha256")) != snapshot_hash
            or not self._attestation_matches_identity(
                attestation, signer_key_id, self.signer.actor_id
            )
            or not self.signer.verify(attestation)
        ):
            raise NarrativeContinuityError(
                NarrativeFailureCode.SIGNATURE_INVALID,
                "identity signer returned an invalid snapshot attestation",
            )
        try:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    INSERT INTO narrative_snapshots (
                        created_at, source_watermark, snapshot_json, source_sha256,
                        snapshot_sha256, signer_key_id, attestation_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        created_at,
                        watermark,
                        _canonical(dict(snapshot)).decode("utf-8"),
                        source_hash,
                        snapshot_hash,
                        signer_key_id,
                        _canonical(attestation).decode("utf-8"),
                    ),
                )
                version = int(cursor.lastrowid)
        except sqlite3.Error as exc:
            raise NarrativeContinuityError(
                NarrativeFailureCode.STORAGE_ERROR,
                "narrative snapshot cannot be persisted",
            ) from exc
        return {
            "snapshot_version": version,
            "created_at": created_at,
            "source_watermark": watermark,
            "source_sha256": source_hash,
            "snapshot_sha256": snapshot_hash,
            "snapshot": dict(snapshot),
            "signer_key_id": signer_key_id,
            "attestation": attestation,
        }

    def _latest_snapshot_for_watermark(self, watermark: int) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT snapshot_version, created_at, source_watermark, snapshot_json,
                   source_sha256, snapshot_sha256, signer_key_id, attestation_json
            FROM narrative_snapshots WHERE source_watermark = ?
            ORDER BY snapshot_version DESC LIMIT 1
            """,
            (watermark,),
        ).fetchone()
        return self._verified_snapshot_row(row) if row else None

    def _verified_snapshot_row(self, row: Sequence[Any]) -> dict[str, Any]:
        try:
            (
                version,
                created_at,
                watermark,
                snapshot_json,
                source_hash,
                stored_hash,
                key_id,
                attestation_json,
            ) = row
            snapshot = json.loads(str(snapshot_json))
            attestation = json.loads(str(attestation_json))
            unsigned = {
                "schema_version": _SCHEMA_VERSION,
                "created_at": str(created_at),
                "source_watermark": int(watermark),
                "source_sha256": str(source_hash),
                "snapshot": snapshot,
                "signer_key_id": str(key_id),
            }
            calculated = _digest(unsigned)
            expected_source_hash = _ZERO_HASH
            if int(watermark) > 0:
                source_row = self._connection.execute(
                    "SELECT event_sha256 FROM narrative_events WHERE sequence = ?",
                    (int(watermark),),
                ).fetchone()
                if source_row is None:
                    raise ValueError("source-watermark")
                expected_source_hash = str(source_row[0])
            if (
                not _SAFE_DIGEST.fullmatch(str(stored_hash))
                or str(source_hash) != expected_source_hash
                or calculated != str(stored_hash)
                or str(attestation.get("payload_sha256")) != calculated
                or not self._attestation_matches_identity(
                    attestation, str(key_id), self.signer.actor_id
                )
                or not self.signer.verify(attestation)
            ):
                raise ValueError("signature")
            return {
                "snapshot_version": int(version),
                "created_at": str(created_at),
                "source_watermark": int(watermark),
                "source_sha256": str(source_hash),
                "snapshot_sha256": calculated,
                "snapshot": snapshot,
                "signer_key_id": str(key_id),
                "attestation": attestation,
            }
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise NarrativeContinuityError(
                NarrativeFailureCode.LEDGER_CORRUPT,
                "a narrative snapshot failed integrity verification",
            ) from exc

    def _verified_events(self) -> list[NarrativeEvent]:
        registered_evidence = self._verified_evidence()
        rows = self._connection.execute(
            """
            SELECT sequence, event_id, request_id, occurred_at, actor_id,
                   event_type, truth_class, subject, payload_json,
                   evidence_refs_json, causation_id, commitment_id,
                   correction_of, previous_sha256, event_sha256,
                   signer_key_id, attestation_json
            FROM narrative_events ORDER BY sequence
            """
        ).fetchall()
        previous = _ZERO_HASH
        events: list[NarrativeEvent] = []
        try:
            for row in rows:
                (
                    sequence,
                    event_id,
                    request_id,
                    occurred_at,
                    actor_id,
                    event_type,
                    truth_class,
                    subject,
                    payload_json,
                    evidence_refs_json,
                    causation_id,
                    commitment_id,
                    correction_of,
                    previous_hash,
                    stored_hash,
                    signer_key_id,
                    attestation_json,
                ) = row
                payload = json.loads(str(payload_json))
                refs = tuple(str(item) for item in json.loads(str(evidence_refs_json)))
                if any(ref not in registered_evidence for ref in refs):
                    raise ValueError("missing-evidence")
                if (
                    str(truth_class) == NarrativeTruthClass.VERIFIED_FACT.value
                    and not refs
                ):
                    raise ValueError("unreferenced-fact")
                attestation = json.loads(str(attestation_json))
                unsigned = {
                    "schema_version": _SCHEMA_VERSION,
                    "event_id": str(event_id),
                    "request_id": str(request_id),
                    "occurred_at": str(occurred_at),
                    "actor_id": str(actor_id),
                    "event_type": str(event_type),
                    "truth_class": str(truth_class),
                    "subject": str(subject),
                    "payload": payload,
                    "evidence_refs": list(refs),
                    "causation_id": causation_id,
                    "commitment_id": commitment_id,
                    "correction_of": correction_of,
                    "previous_sha256": str(previous_hash),
                    "signer_key_id": str(signer_key_id),
                }
                calculated = _digest(unsigned)
                if (
                    str(previous_hash) != previous
                    or calculated != str(stored_hash)
                    or str(attestation.get("payload_sha256")) != calculated
                    or not self._attestation_matches_identity(
                        attestation, str(signer_key_id), str(actor_id)
                    )
                    or not self.signer.verify(attestation)
                ):
                    raise ValueError("hash-chain")
                event = NarrativeEvent(
                    sequence=int(sequence),
                    event_id=str(event_id),
                    request_id=str(request_id),
                    occurred_at=str(occurred_at),
                    actor_id=str(actor_id),
                    event_type=NarrativeEventType(str(event_type)),
                    truth_class=NarrativeTruthClass(str(truth_class)),
                    subject=str(subject),
                    payload=dict(payload),
                    evidence_refs=refs,
                    causation_id=str(causation_id) if causation_id else None,
                    commitment_id=str(commitment_id) if commitment_id else None,
                    correction_of=str(correction_of) if correction_of else None,
                    previous_sha256=str(previous_hash),
                    event_sha256=calculated,
                    signer_key_id=str(signer_key_id),
                    attestation=dict(attestation),
                )
                events.append(event)
                previous = calculated
            return events
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise NarrativeContinuityError(
                NarrativeFailureCode.LEDGER_CORRUPT,
                "narrative event hash chain or signature is invalid",
            ) from exc

    def _verified_evidence(self) -> set[str]:
        rows = self._connection.execute(
            """
            SELECT evidence_ref, content_sha256, content_bytes, source_uri,
                   media_type, recorded_at, signer_key_id, receipt_sha256,
                   attestation_json
            FROM narrative_evidence ORDER BY evidence_ref
            """
        ).fetchall()
        verified: set[str] = set()
        try:
            for row in rows:
                (
                    evidence_ref,
                    content_hash,
                    content_bytes,
                    source_uri,
                    media_type,
                    recorded_at,
                    signer_key_id,
                    receipt_hash,
                    attestation_json,
                ) = row
                unsigned = {
                    "schema_version": _SCHEMA_VERSION,
                    "evidence_ref": str(evidence_ref),
                    "content_sha256": str(content_hash),
                    "content_bytes": int(content_bytes),
                    "source_uri": str(source_uri),
                    "media_type": str(media_type),
                    "recorded_at": str(recorded_at),
                    "signer_key_id": str(signer_key_id),
                }
                calculated = _digest(unsigned)
                attestation = json.loads(str(attestation_json))
                if (
                    str(evidence_ref) != f"evidence:{content_hash}"
                    or not _SAFE_DIGEST.fullmatch(str(content_hash))
                    or calculated != str(receipt_hash)
                    or str(attestation.get("payload_sha256")) != calculated
                    or not self._attestation_matches_identity(
                        attestation, str(signer_key_id), self.signer.actor_id
                    )
                    or not self.signer.verify(attestation)
                ):
                    raise ValueError("evidence-receipt")
                verified.add(str(evidence_ref))
            return verified
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise NarrativeContinuityError(
                NarrativeFailureCode.LEDGER_CORRUPT,
                "a narrative evidence receipt failed integrity verification",
            ) from exc

    def _migrate_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS narrative_schema (
                    version INTEGER NOT NULL,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS narrative_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    request_id TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    truth_class TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    causation_id TEXT REFERENCES narrative_events(event_id),
                    commitment_id TEXT,
                    correction_of TEXT REFERENCES narrative_events(event_id),
                    previous_sha256 TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL UNIQUE,
                    signer_key_id TEXT NOT NULL,
                    attestation_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_narrative_subject
                    ON narrative_events(subject, truth_class, sequence);
                CREATE INDEX IF NOT EXISTS idx_narrative_commitment
                    ON narrative_events(commitment_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_narrative_correction
                    ON narrative_events(correction_of);
                CREATE TABLE IF NOT EXISTS narrative_evidence (
                    evidence_ref TEXT PRIMARY KEY,
                    content_sha256 TEXT NOT NULL UNIQUE,
                    content_bytes INTEGER NOT NULL CHECK(content_bytes > 0),
                    source_uri TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    signer_key_id TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL UNIQUE,
                    attestation_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS narrative_snapshots (
                    snapshot_version INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source_watermark INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    snapshot_sha256 TEXT NOT NULL UNIQUE,
                    signer_key_id TEXT NOT NULL,
                    attestation_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS narrative_migrations (
                    source_sha256 TEXT PRIMARY KEY,
                    imported_at TEXT NOT NULL,
                    imported_events INTEGER NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS narrative_events_no_update
                BEFORE UPDATE ON narrative_events BEGIN
                    SELECT RAISE(ABORT, 'narrative ledger is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS narrative_events_no_delete
                BEFORE DELETE ON narrative_events BEGIN
                    SELECT RAISE(ABORT, 'narrative ledger is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS narrative_snapshots_no_update
                BEFORE UPDATE ON narrative_snapshots BEGIN
                    SELECT RAISE(ABORT, 'narrative snapshots are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS narrative_snapshots_no_delete
                BEFORE DELETE ON narrative_snapshots BEGIN
                    SELECT RAISE(ABORT, 'narrative snapshots are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS narrative_evidence_no_update
                BEFORE UPDATE ON narrative_evidence BEGIN
                    SELECT RAISE(ABORT, 'narrative evidence is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS narrative_evidence_no_delete
                BEFORE DELETE ON narrative_evidence BEGIN
                    SELECT RAISE(ABORT, 'narrative evidence is append-only');
                END;
                """
            )
            row = self._connection.execute(
                "SELECT MAX(version) FROM narrative_schema"
            ).fetchone()
            current = int(row[0]) if row and row[0] is not None else 0
            if current > _SCHEMA_VERSION:
                raise NarrativeContinuityError(
                    NarrativeFailureCode.STORAGE_ERROR,
                    "narrative schema is newer than this runtime",
                )
            if current < _SCHEMA_VERSION:
                self._connection.execute(
                    "INSERT INTO narrative_schema(version, applied_at) VALUES (?, ?)",
                    (_SCHEMA_VERSION, _utc_now()),
                )

    def _migrate_legacy_json(self) -> None:
        path = self.legacy_json_path
        if path is None or not path.is_file():
            return
        try:
            raw_bytes = path.read_bytes()
            if len(raw_bytes) > 16_777_216:
                raise ValueError("size")
            source_hash = hashlib.sha256(raw_bytes).hexdigest()
            exists = self._connection.execute(
                "SELECT 1 FROM narrative_migrations WHERE source_sha256 = ?",
                (source_hash,),
            ).fetchone()
            if exists:
                return
            document = json.loads(raw_bytes.decode("utf-8"))
            if not isinstance(document, dict) or not isinstance(
                document.get("events", []), list
            ):
                raise TypeError("shape")
            imported = 0
            legacy_events = document.get("events", [])
            if len(legacy_events) > 10_000:
                raise ValueError("event-count")
            normalized_events: list[tuple[int, dict[str, Any]]] = []
            for index, item in enumerate(legacy_events):
                if not isinstance(item, dict):
                    continue
                migration_payload = {
                    "legacy_event": item,
                    "source_sha256": source_hash,
                }
                if len(_canonical(migration_payload)) > self.max_payload_bytes:
                    raise ValueError("event-size")
                normalized_events.append((index, migration_payload))
            for index, migration_payload in normalized_events:
                migration_request_id = f"migration-{source_hash[:24]}-{index}"
                already_imported = self._connection.execute(
                    "SELECT 1 FROM narrative_events WHERE request_id = ?",
                    (migration_request_id,),
                ).fetchone()
                if already_imported is not None:
                    imported += 1
                    continue
                self.append_event(
                    request_id=migration_request_id,
                    event_type=NarrativeEventType.MIGRATED_RAW_EVENT,
                    truth_class=NarrativeTruthClass.RAW_EVENT,
                    subject=f"legacy.event.{index}",
                    payload=migration_payload,
                )
                imported += 1
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO narrative_migrations (
                        source_sha256, imported_at, imported_events
                    ) VALUES (?, ?, ?)
                    """,
                    (source_hash, _utc_now(), imported),
                )
        except NarrativeContinuityError as exc:
            raise NarrativeContinuityError(
                NarrativeFailureCode.MIGRATION_FAILED,
                "legacy narrative cannot be imported safely",
            ) from exc
        except (
            OSError,
            UnicodeDecodeError,
            ValueError,
            json.JSONDecodeError,
            sqlite3.Error,
        ) as exc:
            raise NarrativeContinuityError(
                NarrativeFailureCode.MIGRATION_FAILED,
                "legacy narrative cannot be imported safely",
            ) from exc

    def _event_exists(self, event_id: str) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM narrative_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            is not None
        )

    def _evidence_exists(self, evidence_ref: str) -> bool:
        with self._lock:
            return evidence_ref in self._verified_evidence()

    def _last_event_hash(self) -> str:
        row = self._connection.execute(
            "SELECT event_sha256 FROM narrative_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        return str(row[0]) if row else _ZERO_HASH

    @staticmethod
    def _attestation_matches_identity(
        attestation: Mapping[str, Any], signer_key_id: str, actor_id: str
    ) -> bool:
        brain_id = attestation.get("brain_id")
        key_version = attestation.get("key_version")
        if brain_id is None and key_version is None:
            return True
        if brain_id is None or key_version is None:
            return False
        return (
            str(brain_id) == actor_id
            and f"{brain_id}:{key_version}" == signer_key_id
        )

    @staticmethod
    def _compat_event(event: NarrativeEvent) -> dict[str, Any]:
        value = event.to_dict()
        if event.event_type is NarrativeEventType.CONVERSATION_TURN:
            value.update(
                {
                    "kind": "turn",
                    "user": event.payload.get("user_text"),
                    "response": event.payload.get("response_text"),
                    "intent": event.payload.get("intent"),
                    "topic": event.subject,
                    "ok": event.payload.get("ok"),
                }
            )
        elif event.event_type is NarrativeEventType.EXTERNAL_FEEDBACK:
            value.update(
                {
                    "kind": "feedback",
                    "task": event.subject,
                    "score": event.payload.get("score"),
                }
            )
        else:
            value["kind"] = event.event_type.value.lower()
        return value


_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "for",
    "with",
    "in",
    "on",
    "at",
    "is",
    "are",
    "this",
    "that",
    "yang",
    "dan",
    "atau",
    "ke",
    "dari",
    "untuk",
    "dengan",
    "di",
    "ini",
    "itu",
    "saya",
    "aku",
    "kami",
    "kita",
    "anda",
    "kamu",
    "apa",
    "bagaimana",
    "kenapa",
}


def _derive_topic(text: str) -> str:
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    kept = [item for item in tokens if item not in _STOPWORDS]
    return " ".join(kept[:3]) if kept else "general"


def _derive_intent(logic_expr: Any) -> str:
    if isinstance(logic_expr, (tuple, list)) and logic_expr:
        head = str(logic_expr[0]).strip().upper()
        return (
            f"{head}:{str(logic_expr[1]).strip().upper()}"
            if len(logic_expr) > 1
            else head
        )
    return "UNKNOWN"


__all__ = [
    "DNAAnchorNarrativeSigner",
    "NarrativeContinuity",
    "NarrativeContinuityError",
    "NarrativeEvent",
    "NarrativeEventType",
    "NarrativeFailureCode",
    "NarrativeSigner",
    "NarrativeTruthClass",
]
