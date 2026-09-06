#!/usr/bin/env python3
"""Pilar 17 — Socratic Mirror Live Interactive Vertical Slice Demo.

Demonstrates deterministic Socratic verification over candidate decisions:
1. Evidence resolution against catalog documents.
2. Rejection of unsupported claims (INSUFFICIENT_EVIDENCE).
3. Rejection of uncataloged/missing evidence (EVIDENCE_NOT_FOUND).
4. Rejection of logic contradictions (LOGIC_DISPROVED / REJECT).
5. Enforcement of Ethical Heart authorization policy.
6. Acceptance of proved and evidence-grounded candidate (ACCEPT / ALLOWED).
7. Durable replay idempotency (REPLAYED_REVIEW).
8. Payload tamper conflict blocking (DUPLICATE_DECISION).
9. Audit receipt checksum integrity & corrupt record detection (AUDIT_CORRUPT).
10. Process restart persistence verification.
11. Bounded critique revision loop.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyRequest,
    PolicyRisk,
)
from jaya_core.brain_v2.soul.socratic import (
    CandidateDecision,
    SQLiteLibraryEvidenceResolver,
    SocraticAuditStore,
    SocraticError,
    SocraticMirror,
    SocraticThresholds,
)
from jaya_core.reasoning.pure_logic import Literal, LogicRule, LogicTheory, PureLogicSolver


def _seed_catalog(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    with conn:
        conn.execute(
            """
            CREATE TABLE documents (
                doc_id TEXT PRIMARY KEY,
                source_id TEXT,
                content TEXT,
                metadata_json TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?)",
            (
                "doc:flight-safety-2026",
                "spec-safety-v1",
                "Subsystem activation requires dual-channel redundancy and bounded current.",
                json.dumps({"type": "safety_specification", "level": "critical"}),
            ),
        )
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?)",
            (
                "doc:power-limits-v2",
                "spec-power-v2",
                "Max power limit on auxiliary rail is 150 Watts continuous.",
                json.dumps({"type": "engineering_specification"}),
            ),
        )
    conn.close()


def run_live_demo() -> int:
    print("=" * 72)
    print("  JAYA PILAR 17: SOCRATIC MIRROR — LIVE VERTICAL SLICE DEMO")
    print("=" * 72)

    with tempfile.TemporaryDirectory(prefix="socratic-demo-", ignore_cleanup_errors=True) as tmp:
        work_path = Path(tmp)
        catalog_db = work_path / "catalog.sqlite3"
        audit_db = work_path / "socratic_audit.sqlite3"
        ethical_db = work_path / "ethical.sqlite3"

        _seed_catalog(catalog_db)
        resolver = SQLiteLibraryEvidenceResolver(catalog_db)
        heart = EthicalHeart(ethical_db)
        audit_store = SocraticAuditStore(audit_db)
        solver = PureLogicSolver()
        thresholds = SocraticThresholds(
            risk=0.6,
            uncertainty=0.5,
            novelty=0.7,
            impact=0.6,
            max_latency_seconds=3.0,
        )
        mirror = SocraticMirror(
            evidence_resolver=resolver,
            ethical_heart=heart,
            audit_store=audit_store,
            logic_solver=solver,
            thresholds=thresholds,
        )

        print("\n[STEP 1] Evidence Catalog & Core Dependencies Initialized")
        status = mirror.status()
        print(f"  Resolver ready: {status['evidence'].get('ok')}")
        print(f"  Logic solver ready: {bool(status['logic_solver'])}")
        print(f"  Audit store ready: {status['audit'].get('ok')}")

        # Step 2: Unsupported Claim
        print("\n[STEP 2] Submitting Candidate with Unsupported Claim (No evidence ref)...")
        dec1 = CandidateDecision(
            decision_id="dec-demo-001",
            action="Activate high-power thruster without evidence",
            policy_request=PolicyRequest(
                request_id="pol-demo-001",
                actor_brain_id="UNENROLLED",
                node_id="demo-node",
                capability_id="core.logic.evaluate",
                risk_class=PolicyRisk.READ_ONLY,
                permissions=(),
                payload_sha256=hashlib.sha256(b"thruster").hexdigest(),
                purpose="socratic.review",
            ),
            risk=0.85,
            uncertainty=0.8,
            novelty=0.8,
            impact=0.85,
            claims=("Thruster thermal dissipation is safe",),
            claim_evidence={},
        )
        res1 = mirror.review(dec1)
        print(f"  Status: {res1['status']} | Verdict: {res1['verdict']}")
        print(f"  Issues detected: {res1['receipt']['review']['issues']}")
        print(f"  Critique question: {res1['receipt']['review']['questions'][0]}")
        assert res1["ok"] is False and res1["verdict"] == "INSUFFICIENT_EVIDENCE"
        print("  [PASS] Unsupported claim blocked fail-closed.")

        # Step 3: Missing Evidence Reference
        print("\n[STEP 3] Submitting Candidate with Non-Existent Catalog Ref...")
        dec2 = CandidateDecision(
            decision_id="dec-demo-002",
            action="Deploy uncataloged thermal model",
            policy_request=PolicyRequest(
                request_id="pol-demo-002",
                actor_brain_id="UNENROLLED",
                node_id="demo-node",
                capability_id="core.logic.evaluate",
                risk_class=PolicyRisk.READ_ONLY,
                permissions=(),
                payload_sha256=hashlib.sha256(b"thermal").hexdigest(),
                purpose="socratic.review",
            ),
            risk=0.8,
            uncertainty=0.7,
            novelty=0.7,
            impact=0.8,
            claims=("Thermal limits compliant",),
            claim_evidence={"Thermal limits compliant": ("doc:ghost-evidence-404",)},
        )
        res2 = mirror.review(dec2)
        print(f"  Status: {res2['status']} | Verdict: {res2['verdict']}")
        print(f"  Issues: {res2['receipt']['review']['issues']}")
        assert "EVIDENCE_NOT_FOUND" in res2["receipt"]["review"]["issues"]
        print("  [PASS] Missing evidence ref detected and blocked.")

        # Step 4: Logic Contradiction Disproof
        print("\n[STEP 4] Submitting Candidate with Logic Theory Contradiction...")
        contradiction_theory = LogicTheory(
            facts=(Literal("bus.current_high"),),
            rules=(
                LogicRule(
                    "overcurrent-disproves-safety",
                    (Literal("bus.current_high"),),
                    Literal("subsystem.safe", negated=True),
                ),
            ),
        )
        dec3 = CandidateDecision(
            decision_id="dec-demo-003",
            action="Run aux rail at 250 Watts",
            policy_request=PolicyRequest(
                request_id="pol-demo-003",
                actor_brain_id="UNENROLLED",
                node_id="demo-node",
                capability_id="core.logic.evaluate",
                risk_class=PolicyRisk.READ_ONLY,
                permissions=(),
                payload_sha256=hashlib.sha256(b"power").hexdigest(),
                purpose="socratic.review",
            ),
            risk=0.8,
            uncertainty=0.6,
            novelty=0.7,
            impact=0.8,
            claims=("Subsystem operates within specs",),
            claim_evidence={"Subsystem operates within specs": ("doc:power-limits-v2",)},
            logic_theory=contradiction_theory,
            logic_query=Literal("subsystem.safe"),
        )
        res3 = mirror.review(dec3)
        print(f"  Status: {res3['status']} | Verdict: {res3['verdict']}")
        print(f"  Proof status: {res3['receipt']['review']['proof']['status']}")
        assert res3["verdict"] == "REJECT" and "LOGIC_DISPROVED" in res3["receipt"]["review"]["issues"]
        print("  [PASS] Pure Logic contradiction disproved candidate and returned REJECT.")

        # Step 5: Ethical Heart Policy Enforcement
        print("\n[STEP 5] Submitting Candidate with Destructive Policy Risk...")
        dec4 = CandidateDecision(
            decision_id="dec-demo-004",
            action="Execute destructive storage format",
            policy_request=PolicyRequest(
                request_id="pol-demo-004",
                actor_brain_id="UNENROLLED",
                node_id="demo-node",
                capability_id="core.storage.format",
                risk_class=PolicyRisk.DESTRUCTIVE,
                permissions=("system.format",),
                payload_sha256=hashlib.sha256(b"destructive").hexdigest(),
                purpose="socratic.review",
            ),
            risk=0.95,
            uncertainty=0.9,
            novelty=0.9,
            impact=0.95,
            claims=("Format permitted",),
            claim_evidence={"Format permitted": ("doc:flight-safety-2026",)},
        )
        res4 = mirror.review(dec4)
        print(f"  Status: {res4['status']} | Issues: {res4['receipt']['review']['issues']}")
        assert any("ETHICAL_" in issue for issue in res4["receipt"]["review"]["issues"])
        print("  [PASS] Ethical Heart policy gate rejected unauthorized destructive action.")

        # Step 6: Valid Proved Candidate
        print("\n[STEP 6] Submitting Evidence-Grounded, Pure Logic-Proved Candidate...")
        proved_theory = LogicTheory(
            facts=(Literal("redundancy.verified"), Literal("current.bounded")),
            rules=(
                LogicRule(
                    "subsystem-permitted-rule",
                    (Literal("redundancy.verified"), Literal("current.bounded")),
                    Literal("subsystem.activation_permitted"),
                ),
            ),
        )
        dec5 = CandidateDecision(
            decision_id="dec-demo-005",
            action="Nominal activation of secondary thruster channel",
            policy_request=PolicyRequest(
                request_id="pol-demo-005",
                actor_brain_id="UNENROLLED",
                node_id="demo-node",
                capability_id="core.logic.evaluate",
                risk_class=PolicyRisk.READ_ONLY,
                permissions=(),
                payload_sha256=hashlib.sha256(b"nominal").hexdigest(),
                purpose="socratic.review",
            ),
            risk=0.75,
            uncertainty=0.6,
            novelty=0.7,
            impact=0.75,
            claims=("Dual redundancy and bounded current verified by spec",),
            claim_evidence={
                "Dual redundancy and bounded current verified by spec": ("doc:flight-safety-2026",)
            },
            logic_theory=proved_theory,
            logic_query=Literal("subsystem.activation_permitted"),
            candidate_type="INFERENCE",
        )
        res5 = mirror.review(dec5)
        print(f"  Status: {res5['status']} | Verdict: {res5['verdict']}")
        print(f"  Proof conclusion: {res5['receipt']['review']['proof']['status']}")
        print(f"  Evidence bound: {res5['receipt']['review']['evidence'][0]['ref_id']}")
        assert res5["ok"] is True and res5["verdict"] == "ACCEPT"
        print("  [PASS] Valid candidate accepted with durable cryptographic receipt.")

        # Step 7: Idempotent Replay
        print("\n[STEP 7] Replaying Verified Candidate Review...")
        replay = mirror.review(dec5)
        print(f"  Replay status: {replay['status']}")
        assert replay["status"] == "REPLAYED_REVIEW"
        print("  [PASS] Idempotent replay returned verified receipt.")

        # Step 8: Payload Conflict Detection
        print("\n[STEP 8] Testing Payload Conflict with Reused Decision ID...")
        conflict_dec = CandidateDecision(
            decision_id="dec-demo-005",  # Reusing ID
            action="Tampered action with same ID",
            policy_request=PolicyRequest(
                request_id="pol-conflict-demo",
                actor_brain_id="UNENROLLED",
                node_id="demo-node",
                capability_id="core.logic.evaluate",
                risk_class=PolicyRisk.READ_ONLY,
                permissions=(),
                payload_sha256=hashlib.sha256(b"tamper").hexdigest(),
                purpose="socratic.review",
            ),
            risk=0.1,
            uncertainty=0.1,
            novelty=0.1,
            impact=0.1,
        )
        conflict_caught = False
        try:
            mirror.review(conflict_dec)
        except SocraticError as exc:
            if exc.code == "DUPLICATE_DECISION":
                conflict_caught = True
                print(f"  Captured expected exception: {exc.code} — {exc}")
        assert conflict_caught
        print("  [PASS] Conflicting payload with duplicate ID rejected fail-closed.")

        # Step 9: Audit Receipt Tamper Detection
        print("\n[STEP 9] Testing Audit Store Integrity Checksum...")
        conn = sqlite3.connect(str(audit_db))
        with conn:
            conn.execute(
                "UPDATE socratic_reviews SET review_json = '{\"status\":\"TAMPERED\"}' WHERE decision_id = 'dec-demo-005'"
            )
        conn.close()
        corrupt_caught = False
        try:
            audit_store.by_decision_id("dec-demo-005")
        except SocraticError as exc:
            if exc.code == "AUDIT_CORRUPT":
                corrupt_caught = True
                print(f"  Captured integrity violation: {exc.code} — {exc}")
        assert corrupt_caught
        print("  [PASS] Audit record corruption detected via SHA-256 receipt verification.")

        # Step 10: Restart Persistence
        print("\n[STEP 10] Testing Process Restart Persistence...")
        mirror.close()
        restarted_store = SocraticAuditStore(audit_db)
        restarted_mirror = SocraticMirror(
            evidence_resolver=resolver,
            ethical_heart=heart,
            audit_store=restarted_store,
            logic_solver=solver,
            thresholds=thresholds,
        )
        stored_unsupp = restarted_mirror.audit_store.by_decision_id("dec-demo-001")
        assert stored_unsupp is not None and stored_unsupp["review"]["verdict"] == "INSUFFICIENT_EVIDENCE"
        print("  [PASS] Audit records persist across engine restarts with intact rationale.")

        # Step 11: Bounded Critique Revision Loop
        print("\n[STEP 11] Testing Multi-Turn Bounded Critique Revision Loop...")
        v1 = CandidateDecision(
            decision_id="loop-cand-1",
            action="Plan v1: initial proposal",
            policy_request=PolicyRequest(
                request_id="pol-loop-1",
                actor_brain_id="UNENROLLED",
                node_id="demo-node",
                capability_id="core.logic.evaluate",
                risk_class=PolicyRisk.READ_ONLY,
                permissions=(),
                payload_sha256=hashlib.sha256(b"v1").hexdigest(),
                purpose="socratic.review",
            ),
            risk=0.8,
            uncertainty=0.7,
            novelty=0.7,
            impact=0.8,
            claims=("Initial ungrounded claim",),
            claim_evidence={},
        )
        v2 = CandidateDecision(
            decision_id="loop-cand-2",
            action="Plan v2: grounded with catalog evidence and pure logic proof",
            policy_request=PolicyRequest(
                request_id="pol-loop-2",
                actor_brain_id="UNENROLLED",
                node_id="demo-node",
                capability_id="core.logic.evaluate",
                risk_class=PolicyRisk.READ_ONLY,
                permissions=(),
                payload_sha256=hashlib.sha256(b"v2").hexdigest(),
                purpose="socratic.review",
            ),
            risk=0.8,
            uncertainty=0.7,
            novelty=0.7,
            impact=0.8,
            claims=("Dual redundancy and bounded current verified by spec",),
            claim_evidence={
                "Dual redundancy and bounded current verified by spec": ("doc:flight-safety-2026",)
            },
            logic_theory=proved_theory,
            logic_query=Literal("subsystem.activation_permitted"),
        )
        critique_res = restarted_mirror.critique_loop([v1, v2], max_iterations=5)
        print(f"  Critique loop outcome: {critique_res['status']}")
        print(f"  Iterations required: {critique_res['iterations']}")
        assert critique_res["ok"] is True and critique_res["iterations"] == 2
        print("  [PASS] Critique loop successfully iterated and accepted refined candidate.")

        restarted_mirror.close()

    print("\n" + "=" * 72)
    print("  ALL 11 SOCRATIC MIRROR VERTICAL SLICE DEMO CHECKS PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(run_live_demo())
