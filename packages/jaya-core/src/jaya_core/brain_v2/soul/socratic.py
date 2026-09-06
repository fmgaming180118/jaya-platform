"""Pillar 17 — evidence- and proof-backed Socratic Mirror."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from jaya_core.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    OwnerApproval,
    PolicyError,
    PolicyEffect,
    PolicyRequest,
)
from jaya_core.reasoning.pure_logic import (
    LogicResult,
    LogicStatus,
    LogicTheory,
    Literal,
    PureLogicError,
    PureLogicSolver,
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class SocraticError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    ref_id: str
    source_id: str
    content_sha256: str
    source_type: str

    def as_dict(self) -> dict[str, str]:
        return {
            "ref_id": self.ref_id,
            "source_id": self.source_id,
            "content_sha256": self.content_sha256,
            "source_type": self.source_type,
        }


class EvidenceResolver(Protocol):
    def resolve(self, refs: Sequence[str]) -> tuple[tuple[EvidenceRecord, ...], tuple[str, ...]]: ...

    def healthcheck(self) -> Mapping[str, object]: ...


class SQLiteLibraryEvidenceResolver:
    """Read-only resolver over the production JAYA Library catalog."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).expanduser().resolve(strict=False)

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise SocraticError("EVIDENCE_STORE_UNAVAILABLE", "library database does not exist")
        uri_path = str(self.db_path).replace("\\", "/")
        return sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True, timeout=5.0)

    def resolve(
        self,
        refs: Sequence[str],
    ) -> tuple[tuple[EvidenceRecord, ...], tuple[str, ...]]:
        unique_refs = tuple(dict.fromkeys(str(ref).strip() for ref in refs))
        if any(not _SAFE_ID.fullmatch(ref) for ref in unique_refs):
            raise SocraticError("INVALID_EVIDENCE_REF", "evidence reference is invalid")
        if not unique_refs:
            return (), ()
        placeholders = ",".join("?" for _ in unique_refs)
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT doc_id, source_id, content, metadata_json
                    FROM documents WHERE doc_id IN ({placeholders})
                    """,
                    unique_refs,
                ).fetchall()
        except sqlite3.Error as exc:
            raise SocraticError("EVIDENCE_STORE_FAILED", "evidence lookup failed") from exc

        records: list[EvidenceRecord] = []
        found: set[str] = set()
        for doc_id, source_id, content, metadata_json in rows:
            ref_id = str(doc_id)
            found.add(ref_id)
            source_type = "document"
            try:
                metadata = json.loads(str(metadata_json or "{}"))
                if isinstance(metadata, dict):
                    source_type = str(metadata.get("type") or source_type)
            except json.JSONDecodeError:
                source_type = "document"
            records.append(
                EvidenceRecord(
                    ref_id=ref_id,
                    source_id=str(source_id),
                    content_sha256=hashlib.sha256(str(content).encode("utf-8")).hexdigest(),
                    source_type=source_type,
                )
            )
        missing = tuple(ref for ref in unique_refs if ref not in found)
        return tuple(records), missing

    def healthcheck(self) -> Mapping[str, object]:
        try:
            with self._connect() as connection:
                connection.execute("SELECT doc_id FROM documents LIMIT 1").fetchone()
            return {"ok": True, "db_path": str(self.db_path), "read_only": True}
        except (sqlite3.Error, SocraticError) as exc:
            return {"ok": False, "error": exc.code if isinstance(exc, SocraticError) else "EVIDENCE_STORE_FAILED"}


class DictEvidenceResolver:
    """In-memory resolver mapping ref_ids to EvidenceRecord instances."""

    def __init__(self, records: Mapping[str, EvidenceRecord] | None = None) -> None:
        self._records = dict(records or {})

    def register(self, record: EvidenceRecord) -> None:
        self._records[record.ref_id] = record

    def resolve(
        self,
        refs: Sequence[str],
    ) -> tuple[tuple[EvidenceRecord, ...], tuple[str, ...]]:
        unique_refs = tuple(dict.fromkeys(str(ref).strip() for ref in refs))
        if any(not _SAFE_ID.fullmatch(ref) for ref in unique_refs):
            raise SocraticError("INVALID_EVIDENCE_REF", "evidence reference is invalid")
        found = [self._records[ref] for ref in unique_refs if ref in self._records]
        missing = [ref for ref in unique_refs if ref not in self._records]
        return tuple(found), tuple(missing)

    def healthcheck(self) -> Mapping[str, object]:
        return {"ok": True, "type": "dict", "records_count": len(self._records)}


@dataclass(frozen=True, slots=True)
class SocraticThresholds:
    risk: float = 0.60
    uncertainty: float = 0.50
    novelty: float = 0.70
    impact: float = 0.60
    max_claims: int = 64
    max_evidence_refs: int = 256
    max_latency_seconds: float = 3.0

    def __post_init__(self) -> None:
        ratios = (self.risk, self.uncertainty, self.novelty, self.impact)
        if any(not 0.0 <= value <= 1.0 for value in ratios):
            raise ValueError("Socratic thresholds must be in [0, 1]")
        if self.max_claims <= 0 or self.max_evidence_refs <= 0:
            raise ValueError("Socratic collection limits must be positive")
        if not 0.01 <= self.max_latency_seconds <= 300:
            raise ValueError("max_latency_seconds must be between 0.01 and 300")


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    decision_id: str
    action: str
    policy_request: PolicyRequest
    risk: float
    uncertainty: float
    novelty: float
    impact: float
    claims: tuple[str, ...] = ()
    claim_evidence: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    logic_theory: LogicTheory | None = None
    logic_query: Literal | None = None
    candidate_type: str = "INFERENCE"

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.decision_id):
            raise ValueError("decision_id is invalid")
        if not self.action.strip() or len(self.action) > 2_000:
            raise ValueError("action is empty or too large")
        if not self.candidate_type.strip():
            raise ValueError("candidate_type must not be empty")
        ratios = (self.risk, self.uncertainty, self.novelty, self.impact)
        if any(not 0.0 <= value <= 1.0 for value in ratios):
            raise ValueError("decision trigger ratios must be in [0, 1]")

    def audit_payload(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "action_sha256": hashlib.sha256(self.action.encode("utf-8")).hexdigest(),
            "policy_request": self.policy_request.to_dict(),
            "risk": self.risk,
            "uncertainty": self.uncertainty,
            "novelty": self.novelty,
            "impact": self.impact,
            "claims": list(self.claims),
            "claim_evidence": {
                claim: list(refs) for claim, refs in self.claim_evidence.items()
            },
            "logic_query": self.logic_query.key if self.logic_query else None,
            "candidate_type": self.candidate_type,
        }


@dataclass(frozen=True, slots=True)
class SocraticReview:
    review_id: str
    decision_id: str
    status: str
    triggered_by: tuple[str, ...]
    issues: tuple[str, ...]
    questions: tuple[str, ...]
    evidence: tuple[EvidenceRecord, ...]
    proof: LogicResult | None
    approval_id: str | None
    elapsed_ms: float
    reviewed_at: str
    verdict: str = "ACCEPT"

    def as_dict(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "decision_id": self.decision_id,
            "status": self.status,
            "verdict": self.verdict,
            "triggered_by": list(self.triggered_by),
            "issues": list(self.issues),
            "questions": list(self.questions),
            "evidence": [record.as_dict() for record in self.evidence],
            "proof": self.proof.to_dict() if self.proof else None,
            "approval_id": self.approval_id,
            "elapsed_ms": self.elapsed_ms,
            "reviewed_at": self.reviewed_at,
        }


class SocraticAuditStore:
    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).expanduser().resolve(strict=False)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                str(self.db_path), timeout=5.0, check_same_thread=False
            )
            with self._connection:
                self._connection.execute("PRAGMA journal_mode = WAL")
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS socratic_reviews (
                        review_id TEXT PRIMARY KEY,
                        decision_id TEXT NOT NULL UNIQUE,
                        input_sha256 TEXT NOT NULL,
                        decision_json TEXT NOT NULL,
                        review_json TEXT NOT NULL,
                        receipt_sha256 TEXT NOT NULL
                    )
                    """
                )
        except (OSError, sqlite3.Error) as exc:
            raise SocraticError("AUDIT_STORAGE_UNAVAILABLE", "cannot initialize Socratic audit") from exc

    def append(self, decision: CandidateDecision, review: SocraticReview) -> dict[str, object]:
        decision_json = _canonical_json(decision.audit_payload())
        review_json = _canonical_json(review.as_dict())
        input_sha256 = _digest(decision.audit_payload())
        receipt_sha256 = _digest(
            [review.review_id, decision.decision_id, input_sha256, decision_json, review_json]
        )
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO socratic_reviews (
                        review_id, decision_id, input_sha256, decision_json,
                        review_json, receipt_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review.review_id,
                        decision.decision_id,
                        input_sha256,
                        decision_json,
                        review_json,
                        receipt_sha256,
                    ),
                )
        except sqlite3.IntegrityError:
            existing = self.by_decision_id(decision.decision_id)
            if existing is None or existing["input_sha256"] != input_sha256:
                raise SocraticError("DUPLICATE_DECISION", "decision_id payload conflict")
            return existing
        except sqlite3.Error as exc:
            raise SocraticError("AUDIT_STORAGE_FAILED", "cannot persist Socratic review") from exc
        return {
            "input_sha256": input_sha256,
            "receipt_sha256": receipt_sha256,
            "review": review.as_dict(),
        }

    def by_decision_id(self, decision_id: str) -> dict[str, object] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT review_id, decision_id, input_sha256, decision_json,
                       review_json, receipt_sha256
                FROM socratic_reviews WHERE decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
        if row is None:
            return None
        expected = _digest([row[0], row[1], row[2], row[3], row[4]])
        if expected != str(row[5]):
            raise SocraticError("AUDIT_CORRUPT", "Socratic receipt integrity failed")
        try:
            return {
                "review_id": str(row[0]),
                "decision_id": str(row[1]),
                "input_sha256": str(row[2]),
                "decision": json.loads(str(row[3])),
                "review": json.loads(str(row[4])),
                "receipt_sha256": str(row[5]),
            }
        except json.JSONDecodeError as exc:
            raise SocraticError("AUDIT_CORRUPT", "Socratic receipt payload is invalid") from exc

    def healthcheck(self) -> Mapping[str, object]:
        try:
            with self._lock:
                self._connection.execute("SELECT 1").fetchone()
            return {"ok": True, "db_path": str(self.db_path)}
        except sqlite3.Error as exc:
            return {"ok": False, "error": str(exc)}

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class SocraticMirror:
    """Deterministic review gate for high-impact candidate decisions."""

    def __init__(
        self,
        *,
        evidence_resolver: EvidenceResolver,
        ethical_heart: EthicalHeart,
        audit_store: SocraticAuditStore,
        logic_solver: PureLogicSolver | None = None,
        thresholds: SocraticThresholds | None = None,
    ) -> None:
        self.evidence_resolver = evidence_resolver
        self.ethical_heart = ethical_heart
        self.audit_store = audit_store
        self.logic_solver = logic_solver or PureLogicSolver()
        self.thresholds = thresholds or SocraticThresholds()
        self._review_count = 0

    def _triggers(self, decision: CandidateDecision) -> tuple[str, ...]:
        triggered: list[str] = []
        for name, value, threshold in (
            ("risk", decision.risk, self.thresholds.risk),
            ("uncertainty", decision.uncertainty, self.thresholds.uncertainty),
            ("novelty", decision.novelty, self.thresholds.novelty),
            ("impact", decision.impact, self.thresholds.impact),
        ):
            if value >= threshold:
                triggered.append(name)
        return tuple(triggered)

    def review(
        self,
        decision: CandidateDecision,
        approval: OwnerApproval | None = None,
    ) -> dict[str, object]:
        started = time.monotonic()
        existing = self.audit_store.by_decision_id(decision.decision_id)
        if existing is not None:
            if existing["input_sha256"] != _digest(decision.audit_payload()):
                raise SocraticError("DUPLICATE_DECISION", "decision_id payload conflict")
            return {"ok": True, "status": "REPLAYED_REVIEW", "receipt": existing}
        if len(decision.claims) > self.thresholds.max_claims:
            raise SocraticError("CLAIM_LIMIT_EXCEEDED", "too many claims")
        all_refs = tuple(
            dict.fromkeys(
                ref
                for refs in decision.claim_evidence.values()
                for ref in refs
            )
        )
        if len(all_refs) > self.thresholds.max_evidence_refs:
            raise SocraticError("EVIDENCE_LIMIT_EXCEEDED", "too many evidence references")

        triggers = self._triggers(decision)
        issues: list[str] = []
        questions: list[str] = []
        records: tuple[EvidenceRecord, ...] = ()
        missing: tuple[str, ...] = ()
        try:
            records, missing = self.evidence_resolver.resolve(all_refs)
        except SocraticError as exc:
            issues.append(exc.code)
        if missing:
            issues.append("EVIDENCE_NOT_FOUND")
            questions.append("Provide catalog-backed evidence for every referenced claim.")
        for claim in decision.claims:
            refs = decision.claim_evidence.get(claim, ())
            if not refs:
                issues.append("UNSUPPORTED_CLAIM")
                questions.append(f"What evidence supports claim digest {_digest(claim)[:12]}?")

        proof: LogicResult | None = None
        if triggers:
            if decision.logic_theory is None or decision.logic_query is None:
                issues.append("LOGIC_PROOF_REQUIRED")
                questions.append("Provide a bounded logic theory and explicit decision query.")
            else:
                try:
                    proof = self.logic_solver.solve(
                        f"socratic:{decision.decision_id}",
                        decision.logic_theory,
                        decision.logic_query,
                    )
                    if proof.status is not LogicStatus.PROVED:
                        issues.append(f"LOGIC_{proof.status.value}")
                        questions.append("Revise the decision until the required conclusion is proved.")
                except PureLogicError as exc:
                    issues.append(f"LOGIC_{exc.code.value}")

        approval_id: str | None = None
        try:
            policy_decision = self.ethical_heart.evaluate(decision.policy_request, approval)
            if policy_decision.effect is not PolicyEffect.ALLOW:
                issues.append(f"ETHICAL_{policy_decision.effect.value}")
                if policy_decision.effect is PolicyEffect.REQUIRE_APPROVAL:
                    questions.append("Obtain a valid, payload-bound owner approval.")
            approval_id = policy_decision.approval_id
        except PolicyError as exc:
            issues.append(exc.code.value)
            if "APPROVAL" in exc.code.value:
                questions.append("Obtain a valid, payload-bound owner approval.")

        elapsed = time.monotonic() - started
        if elapsed > self.thresholds.max_latency_seconds:
            issues.append("SOCRATIC_TIMEOUT")
        unique_issues = tuple(dict.fromkeys(issues))
        unique_questions = tuple(dict.fromkeys(questions))
        if "SOCRATIC_TIMEOUT" in unique_issues:
            status = "BLOCKED_TIMEOUT"
            verdict = "TIMEOUT"
        elif not unique_issues:
            status = "ALLOWED"
            verdict = "ACCEPT"
        elif "ETHICAL_DENY" in unique_issues or "LOGIC_DISPROVED" in unique_issues:
            status = "REVISE_OR_ESCALATE" if triggers else "BLOCKED"
            verdict = "REJECT"
        elif "EVIDENCE_NOT_FOUND" in unique_issues or "UNSUPPORTED_CLAIM" in unique_issues:
            status = "REVISE_OR_ESCALATE" if triggers else "BLOCKED"
            verdict = "INSUFFICIENT_EVIDENCE"
        else:
            status = "REVISE_OR_ESCALATE" if triggers else "BLOCKED"
            verdict = "REVISE"
        review = SocraticReview(
            review_id=str(uuid.uuid4()),
            decision_id=decision.decision_id,
            status=status,
            triggered_by=triggers,
            issues=unique_issues,
            questions=unique_questions,
            evidence=records,
            proof=proof,
            approval_id=approval_id,
            elapsed_ms=elapsed * 1_000.0,
            reviewed_at=_utc_now(),
            verdict=verdict,
        )
        receipt = self.audit_store.append(decision, review)
        self._review_count += 1
        return {"ok": status == "ALLOWED", "status": status, "verdict": verdict, "receipt": receipt}

    def critique_loop(
        self,
        candidate_generator: Any,
        *,
        max_iterations: int = 5,
        approval: OwnerApproval | None = None,
    ) -> dict[str, object]:
        """Execute a bounded critique loop up to max_iterations.

        candidate_generator can be a sequence of CandidateDecision or a callable
        taking (iteration_index, previous_review) -> CandidateDecision.
        """
        if max_iterations <= 0 or max_iterations > 50:
            raise SocraticError("INVALID_ITERATION_LIMIT", "max_iterations must be between 1 and 50")
        history: list[dict[str, object]] = []
        last_review: dict[str, object] | None = None
        for i in range(max_iterations):
            if callable(candidate_generator):
                decision = candidate_generator(i, last_review)
            elif isinstance(candidate_generator, Sequence) and i < len(candidate_generator):
                decision = candidate_generator[i]
            else:
                break
            review_result = self.review(decision, approval)
            history.append(review_result)
            last_review = review_result
            if review_result.get("ok"):
                return {
                    "ok": True,
                    "status": "ACCEPTED",
                    "iterations": i + 1,
                    "final_review": review_result,
                    "history": history,
                }
            receipt = review_result.get("receipt", {})
            review_dict = receipt.get("review", {}) if isinstance(receipt, dict) else {}
            if review_dict.get("verdict") == "REJECT":
                return {
                    "ok": False,
                    "status": "REJECTED",
                    "iterations": i + 1,
                    "final_review": review_result,
                    "history": history,
                }
        return {
            "ok": False,
            "status": "ITERATION_LIMIT_EXCEEDED",
            "iterations": len(history),
            "final_review": last_review,
            "history": history,
        }

    def review_command(self, command: str) -> str:
        """Legacy raw-string calls fail closed because they lack typed evidence."""
        if not isinstance(command, str) or not command.strip():
            return "SOCRATIC_INVALID_INPUT"
        return "SOCRATIC_TYPED_DECISION_REQUIRED"

    def status(self) -> dict[str, object]:
        return {
            "available": True,
            "review_count": self._review_count,
            "evidence": dict(self.evidence_resolver.healthcheck()),
            "logic_solver": self.logic_solver.health_check(),
            "audit": dict(self.audit_store.healthcheck()),
            "thresholds": {
                "risk": self.thresholds.risk,
                "uncertainty": self.thresholds.uncertainty,
                "novelty": self.thresholds.novelty,
                "impact": self.thresholds.impact,
                "max_latency_seconds": self.thresholds.max_latency_seconds,
            },
        }

    def close(self) -> None:
        self.audit_store.close()


__all__ = [
    "CandidateDecision",
    "DictEvidenceResolver",
    "EvidenceRecord",
    "EvidenceResolver",
    "SQLiteLibraryEvidenceResolver",
    "SocraticAuditStore",
    "SocraticError",
    "SocraticMirror",
    "SocraticReview",
    "SocraticThresholds",
]
