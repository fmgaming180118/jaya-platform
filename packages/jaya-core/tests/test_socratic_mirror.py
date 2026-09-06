from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from jaya_core.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyRequest,
    PolicyRisk,
)
from jaya_core.brain_v2.soul.socratic import (
    CandidateDecision,
    SQLiteLibraryEvidenceResolver,
    SocraticAuditStore,
    SocraticMirror,
)
from jaya_core.reasoning.pure_logic import LogicRule, LogicTheory, Literal


def _library(path: Path) -> None:
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            """
            CREATE TABLE documents (
                doc_id TEXT PRIMARY KEY,
                source_id TEXT,
                content TEXT,
                metadata_json TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?)",
            (
                "evidence-1",
                "test-source",
                "Measured evidence content.",
                '{"type":"measurement"}',
            ),
        )
    connection.close()


def _request(action: str, request_id: str = "policy-request") -> PolicyRequest:
    return PolicyRequest(
        request_id=request_id,
        actor_brain_id="UNENROLLED",
        node_id="test-node",
        capability_id="core.logic.evaluate",
        risk_class=PolicyRisk.READ_ONLY,
        permissions=(),
        payload_sha256=hashlib.sha256(action.encode()).hexdigest(),
        purpose="socratic.review",
    )


def _mirror(tmp_path: Path) -> SocraticMirror:
    library = tmp_path / "library.db"
    _library(library)
    return SocraticMirror(
        evidence_resolver=SQLiteLibraryEvidenceResolver(library),
        ethical_heart=EthicalHeart(tmp_path / "ethical.db"),
        audit_store=SocraticAuditStore(tmp_path / "socratic.db"),
    )


def _proved_logic() -> tuple[LogicTheory, Literal]:
    theory = LogicTheory(
        facts=(Literal("evidence.present"),),
        rules=(
            LogicRule(
                "evidence-supports-action",
                (Literal("evidence.present"),),
                Literal("action.supported"),
            ),
        ),
    )
    return theory, Literal("action.supported")


def test_high_risk_decision_requires_evidence_and_logic(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    action = "evaluate candidate"
    result = mirror.review(
        CandidateDecision(
            decision_id="missing-support",
            action=action,
            policy_request=_request(action),
            risk=0.9,
            uncertainty=0.8,
            novelty=0.8,
            impact=0.9,
            claims=("candidate is safe",),
        )
    )
    assert result["ok"] is False
    review = result["receipt"]["review"]
    assert "UNSUPPORTED_CLAIM" in review["issues"]
    assert "LOGIC_PROOF_REQUIRED" in review["issues"]
    mirror.close()


def test_catalog_evidence_and_proof_allow_policy_permitted_decision(
    tmp_path: Path,
) -> None:
    mirror = _mirror(tmp_path)
    theory, query = _proved_logic()
    action = "evaluate candidate"
    result = mirror.review(
        CandidateDecision(
            decision_id="supported-decision",
            action=action,
            policy_request=_request(action, "supported-policy-request"),
            risk=0.9,
            uncertainty=0.8,
            novelty=0.8,
            impact=0.9,
            claims=("candidate is supported",),
            claim_evidence={"candidate is supported": ("evidence-1",)},
            logic_theory=theory,
            logic_query=query,
        )
    )
    assert result["ok"] is True
    review = result["receipt"]["review"]
    assert review["status"] == "ALLOWED"
    assert review["proof"]["status"] == "PROVED"
    assert review["evidence"][0]["ref_id"] == "evidence-1"
    mirror.close()


def test_unknown_logic_result_is_not_promoted(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    action = "evaluate unknown candidate"
    result = mirror.review(
        CandidateDecision(
            decision_id="unknown-proof",
            action=action,
            policy_request=_request(action, "unknown-policy-request"),
            risk=0.9,
            uncertainty=0.9,
            novelty=0.9,
            impact=0.9,
            logic_theory=LogicTheory(facts=(Literal("other.fact"),), rules=()),
            logic_query=Literal("action.supported"),
        )
    )
    assert result["ok"] is False
    assert "LOGIC_UNKNOWN" in result["receipt"]["review"]["issues"]
    mirror.close()


def test_duplicate_decision_replays_durable_receipt(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    action = "read only check"
    decision = CandidateDecision(
        decision_id="repeat-review",
        action=action,
        policy_request=_request(action, "repeat-policy-request"),
        risk=0.1,
        uncertainty=0.1,
        novelty=0.1,
        impact=0.1,
    )
    first = mirror.review(decision)
    second = mirror.review(decision)
    assert first["ok"] is True
    assert second["status"] == "REPLAYED_REVIEW"
    mirror.close()


def test_raw_command_review_fails_closed(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    assert mirror.review_command("delete all") == "SOCRATIC_TYPED_DECISION_REQUIRED"
    mirror.close()


def test_contradiction_logic_is_rejected(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    action = "contradicted candidate"
    theory = LogicTheory(
        facts=(Literal("fact.conflict"),),
        rules=(
            LogicRule(
                "conflict-disproves-action",
                (Literal("fact.conflict"),),
                Literal("action.supported", negated=True),
            ),
        ),
    )
    result = mirror.review(
        CandidateDecision(
            decision_id="disproved-candidate",
            action=action,
            policy_request=_request(action, "disproved-policy"),
            risk=0.8,
            uncertainty=0.7,
            novelty=0.8,
            impact=0.8,
            claims=("candidate is supported",),
            claim_evidence={"candidate is supported": ("evidence-1",)},
            logic_theory=theory,
            logic_query=Literal("action.supported"),
        )
    )
    assert result["ok"] is False
    assert result["verdict"] == "REJECT"
    review = result["receipt"]["review"]
    assert "LOGIC_DISPROVED" in review["issues"]
    assert review["proof"]["status"] == "DISPROVED"
    mirror.close()


def test_unsupported_claim_has_insufficient_evidence_verdict(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    action = "unsupported claim"
    result = mirror.review(
        CandidateDecision(
            decision_id="insufficient-ev-candidate",
            action=action,
            policy_request=_request(action, "insufficient-policy"),
            risk=0.7,
            uncertainty=0.7,
            novelty=0.7,
            impact=0.7,
            claims=("unbacked claim",),
            claim_evidence={"unbacked claim": ("missing-ref-999",)},
        )
    )
    assert result["ok"] is False
    assert result["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "EVIDENCE_NOT_FOUND" in result["receipt"]["review"]["issues"]
    mirror.close()


def test_corrupt_audit_detection(tmp_path: Path) -> None:
    import pytest
    from jaya_core.brain_v2.soul.socratic import SocraticError

    db_path = tmp_path / "socratic_audit.db"
    store = SocraticAuditStore(db_path)
    action = "tamper check"
    decision = CandidateDecision(
        decision_id="tamper-candidate",
        action=action,
        policy_request=_request(action, "tamper-policy"),
        risk=0.1,
        uncertainty=0.1,
        novelty=0.1,
        impact=0.1,
    )
    from jaya_core.brain_v2.soul.socratic import SocraticReview
    review = SocraticReview(
        review_id="rev-tamper-1",
        decision_id="tamper-candidate",
        status="ALLOWED",
        triggered_by=(),
        issues=(),
        questions=(),
        evidence=(),
        proof=None,
        approval_id=None,
        elapsed_ms=1.5,
        reviewed_at="2026-09-06T00:00:00Z",
        verdict="ACCEPT",
    )
    store.append(decision, review)

    # Directly tamper with review_json in database
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute(
            "UPDATE socratic_reviews SET review_json = '{\"status\":\"CORRUPTED\"}' WHERE decision_id = 'tamper-candidate'"
        )
    conn.close()

    with pytest.raises(SocraticError) as exc:
        store.by_decision_id("tamper-candidate")
    assert exc.value.code == "AUDIT_CORRUPT"
    store.close()


def test_bounded_critique_loop_success_and_rejection(tmp_path: Path) -> None:
    mirror = _mirror(tmp_path)
    theory, query = _proved_logic()

    # Sequence where iteration 1 fails (unsupported), iteration 2 succeeds
    action = "loop candidate"
    v1 = CandidateDecision(
        decision_id="loop-cand-1",
        action=action,
        policy_request=_request(action, "loop-pol-1"),
        risk=0.8,
        uncertainty=0.8,
        novelty=0.8,
        impact=0.8,
        claims=("unsupported claim",),
        claim_evidence={},
    )
    v2 = CandidateDecision(
        decision_id="loop-cand-2",
        action=action,
        policy_request=_request(action, "loop-pol-2"),
        risk=0.8,
        uncertainty=0.8,
        novelty=0.8,
        impact=0.8,
        claims=("candidate is supported",),
        claim_evidence={"candidate is supported": ("evidence-1",)},
        logic_theory=theory,
        logic_query=query,
    )

    loop_result = mirror.critique_loop([v1, v2], max_iterations=3)
    assert loop_result["ok"] is True
    assert loop_result["status"] == "ACCEPTED"
    assert loop_result["iterations"] == 2
    mirror.close()

