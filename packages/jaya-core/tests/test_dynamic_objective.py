"""Comprehensive unit and integration tests for Pilar 39: Dynamic Objective."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from pathlib import Path

import pytest
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.control_capabilities import DynamicObjectiveCapability
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.reasoning_capabilities import (
    MetaPlanningCapability,
    SpeculativeReasoningCapability,
)

from collections.abc import Sequence, Mapping

APPROVAL_KEY = b"dynamic-objective-approval-key-32b!"


class RetrievalTestProvider:
    provider_type = "TEST_IMPLEMENTATION"

    def health_check(self) -> bool:
        return True

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return {"answer": f"Evidence: {evidence[0]['content']}", "citations": [evidence[0]["evidence_id"]]}


def _setup_rag(tmp_path: Path) -> tuple[AgenticRAGCapability, str]:
    rag = AgenticRAGCapability(tmp_path / "rag.sqlite3", RetrievalTestProvider())
    rag.execute(
        {
            "action": "ingest",
            "source_ref": "artifact:resource-pressure",
            "title": "Resource Pressure Evidence",
            "content": "Resource utilization exceeded 85%, shift priority to recovery.",
        }
    )
    evidence_id = rag.retrieve("resource utilization", 1)[0]["evidence_id"]
    return rag, evidence_id


def _sign(material: str, key: bytes = APPROVAL_KEY) -> str:
    return hmac.new(key, material.encode("utf-8"), hashlib.sha256).hexdigest()


def test_dynamic_objective_health_and_persistence(tmp_path: Path) -> None:
    rag, _ = _setup_rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    db_path = tmp_path / "obj.sqlite3"

    cap = DynamicObjectiveCapability(db_path, APPROVAL_KEY, rag, sandbox)
    assert cap.health_check() is True

    # Verify SQLite WAL mode and Schema version 2
    conn = sqlite3.connect(db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.upper() == "WAL"
        schema_ver = conn.execute("SELECT schema_version FROM objective_schema").fetchone()[0]
        assert schema_ver == 2
    finally:
        conn.close()


def test_owner_goal_immutability_and_invariants(tmp_path: Path) -> None:
    rag, _ = _setup_rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    cap = DynamicObjectiveCapability(tmp_path / "obj.sqlite3", APPROVAL_KEY, rag, sandbox)

    # Valid creation
    res = cap.execute(
        {
            "action": "create",
            "objective_id": "obj-safe",
            "owner_id": "owner-1",
            "owner_goal": "Maintain system safety and continuous availability",
            "invariants": ["1 + 1 == 2", "10 * 10 == 100"],
            "weights": {"safety": 0.7, "throughput": 0.3},
        }
    )
    assert res.data["version"] == 1
    assert abs(sum(res.data["weights"].values()) - 1.0) < 1e-6
    assert "state_digest" in res.data

    # Duplicate objective ID rejected
    with pytest.raises(LocalPillarError) as exc_dup:
        cap.execute(
            {
                "action": "create",
                "objective_id": "obj-safe",
                "owner_id": "owner-1",
                "owner_goal": "Duplicate attempt",
                "invariants": ["True"],
                "weights": {"safety": 1.0},
            }
        )
    assert exc_dup.value.code == "OBJECTIVE_EXISTS"

    # Invariant failure rejected
    with pytest.raises(LocalPillarError) as exc_inv:
        cap.execute(
            {
                "action": "create",
                "objective_id": "obj-bad-inv",
                "owner_id": "owner-1",
                "owner_goal": "Attempt with broken invariant",
                "invariants": ["1 + 1 == 999"],
                "weights": {"safety": 1.0},
            }
        )
    assert exc_inv.value.code == "INVARIANT_VIOLATION"


def test_weight_normalization_and_validation(tmp_path: Path) -> None:
    rag, _ = _setup_rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    cap = DynamicObjectiveCapability(tmp_path / "obj.sqlite3", APPROVAL_KEY, rag, sandbox)

    # Negative weights rejected
    with pytest.raises(LocalPillarError) as exc_neg:
        cap.execute(
            {
                "action": "create",
                "objective_id": "obj-neg",
                "owner_id": "owner-1",
                "owner_goal": "Test negative weights",
                "invariants": ["True"],
                "weights": {"a": -0.5, "b": 1.0},
            }
        )
    assert exc_neg.value.code == "INVALID_INPUT"

    # All-zero weights rejected
    with pytest.raises(LocalPillarError) as exc_zero:
        cap.execute(
            {
                "action": "create",
                "objective_id": "obj-zero",
                "owner_id": "owner-1",
                "owner_goal": "Test zero weights",
                "invariants": ["True"],
                "weights": {"a": 0.0, "b": 0.0},
            }
        )
    assert exc_zero.value.code == "INVALID_INPUT"


def test_propose_bounds_policy_and_evidence(tmp_path: Path) -> None:
    rag, evidence_id = _setup_rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    cap = DynamicObjectiveCapability(tmp_path / "obj.sqlite3", APPROVAL_KEY, rag, sandbox)

    cap.execute(
        {
            "action": "create",
            "objective_id": "obj-prop",
            "owner_id": "owner-1",
            "owner_goal": "Balance performance and safety",
            "invariants": ["True"],
            "weights": {"safety": 0.5, "speed": 0.5},
        }
    )

    # Missing evidence rejected
    with pytest.raises(LocalPillarError) as exc_ev:
        cap.execute(
            {
                "action": "propose",
                "objective_id": "obj-prop",
                "signals": {"safety": 0.5, "speed": -0.5},
                "learning_rate": 0.1,
                "evidence_ids": ["non-existent-evidence"],
                "policy_decision": "ALLOW",
                "expires_at": time.time() + 300,
            }
        )
    assert exc_ev.value.code == "INVALID_EVIDENCE"

    # Excessive learning rate (> 0.25) rejected
    with pytest.raises(LocalPillarError) as exc_rate:
        cap.execute(
            {
                "action": "propose",
                "objective_id": "obj-prop",
                "signals": {"safety": 0.5, "speed": -0.5},
                "learning_rate": 0.30,
                "evidence_ids": [evidence_id],
                "policy_decision": "ALLOW",
                "expires_at": time.time() + 300,
            }
        )
    assert exc_rate.value.code == "INVALID_INPUT"

    # Non-ALLOW policy rejected
    with pytest.raises(LocalPillarError) as exc_pol:
        cap.execute(
            {
                "action": "propose",
                "objective_id": "obj-prop",
                "signals": {"safety": 0.5, "speed": -0.5},
                "learning_rate": 0.1,
                "evidence_ids": [evidence_id],
                "policy_decision": "DENY",
                "expires_at": time.time() + 300,
            }
        )
    assert exc_pol.value.code == "POLICY_DENIED"


def test_cryptographic_approval_and_replay_protection(tmp_path: Path) -> None:
    rag, evidence_id = _setup_rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    cap = DynamicObjectiveCapability(tmp_path / "obj.sqlite3", APPROVAL_KEY, rag, sandbox)

    cap.execute(
        {
            "action": "create",
            "objective_id": "obj-auth",
            "owner_id": "owner-boss",
            "owner_goal": "Critical enterprise service",
            "invariants": ["True"],
            "weights": {"w1": 0.5, "w2": 0.5},
        }
    )

    prop = cap.execute(
        {
            "action": "propose",
            "objective_id": "obj-auth",
            "signals": {"w1": 0.5, "w2": -0.5},
            "learning_rate": 0.1,
            "evidence_ids": [evidence_id],
            "policy_decision": "ALLOW",
            "expires_at": time.time() + 300,
        }
    )
    digest = prop.data["proposal_digest"]

    # Non-owner cannot approve
    material_wrong_owner = f"approve|obj-auth|2|{digest}|appr-1|imposter"
    with pytest.raises(LocalPillarError) as exc_owner:
        cap.execute(
            {
                "action": "approve",
                "objective_id": "obj-auth",
                "version": 2,
                "approval_id": "appr-1",
                "approved_by": "imposter",
                "signature": _sign(material_wrong_owner),
            }
        )
    assert exc_owner.value.code == "APPROVAL_DENIED"

    # Forged signature rejected
    with pytest.raises(LocalPillarError) as exc_sig:
        cap.execute(
            {
                "action": "approve",
                "objective_id": "obj-auth",
                "version": 2,
                "approval_id": "appr-1",
                "approved_by": "owner-boss",
                "signature": "forged0000000000000000000000000000000000000000000000000000000000",
            }
        )
    assert exc_sig.value.code == "APPROVAL_DENIED"

    # Valid approval
    material_valid = f"approve|obj-auth|2|{digest}|appr-1|owner-boss"
    appr_res = cap.execute(
        {
            "action": "approve",
            "objective_id": "obj-auth",
            "version": 2,
            "approval_id": "appr-1",
            "approved_by": "owner-boss",
            "signature": _sign(material_valid),
        }
    )
    assert appr_res.data["version"] == 2

    # Replaying approval_id rejected
    prop3 = cap.execute(
        {
            "action": "propose",
            "objective_id": "obj-auth",
            "signals": {"w1": 0.2, "w2": -0.2},
            "learning_rate": 0.05,
            "evidence_ids": [evidence_id],
            "policy_decision": "ALLOW",
            "expires_at": time.time() + 300,
        }
    )
    material_replay = f"approve|obj-auth|3|{prop3.data['proposal_digest']}|appr-1|owner-boss"
    with pytest.raises(LocalPillarError) as exc_replay:
        cap.execute(
            {
                "action": "approve",
                "objective_id": "obj-auth",
                "version": 3,
                "approval_id": "appr-1",  # Reused approval_id
                "approved_by": "owner-boss",
                "signature": _sign(material_replay),
            }
        )
    assert exc_replay.value.code == "APPROVAL_DENIED"


def test_anti_oscillation_guard(tmp_path: Path) -> None:
    rag, evidence_id = _setup_rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    cap = DynamicObjectiveCapability(
        tmp_path / "obj.sqlite3",
        APPROVAL_KEY,
        rag,
        sandbox,
        dampening_window_seconds=10.0,
    )

    cap.execute(
        {
            "action": "create",
            "objective_id": "obj-osc",
            "owner_id": "owner-1",
            "owner_goal": "Oscillation test goal",
            "invariants": ["True"],
            "weights": {"exploration": 0.5, "exploitation": 0.5},
        }
    )

    # Version 2: Increase exploration, decrease exploitation
    p2 = cap.execute(
        {
            "action": "propose",
            "objective_id": "obj-osc",
            "signals": {"exploration": 0.8, "exploitation": -0.8},
            "learning_rate": 0.1,
            "evidence_ids": [evidence_id],
            "policy_decision": "ALLOW",
            "expires_at": time.time() + 300,
        }
    )
    cap.execute(
        {
            "action": "approve",
            "objective_id": "obj-osc",
            "version": 2,
            "approval_id": "appr-v2",
            "approved_by": "owner-1",
            "signature": _sign(f"approve|obj-osc|2|{p2.data['proposal_digest']}|appr-v2|owner-1"),
        }
    )

    # Immediate Version 3 proposal: Directly reverse exploration within dampening window
    with pytest.raises(LocalPillarError) as exc_osc:
        cap.execute(
            {
                "action": "propose",
                "objective_id": "obj-osc",
                "signals": {"exploration": -0.8, "exploitation": 0.8},
                "learning_rate": 0.1,
                "evidence_ids": [evidence_id],
                "policy_decision": "ALLOW",
                "expires_at": time.time() + 300,
            }
        )
    assert exc_osc.value.code == "OSCILLATION_DETECTED"


def test_append_only_rollback_and_history(tmp_path: Path) -> None:
    rag, evidence_id = _setup_rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    cap = DynamicObjectiveCapability(tmp_path / "obj.sqlite3", APPROVAL_KEY, rag, sandbox)

    cap.execute(
        {
            "action": "create",
            "objective_id": "obj-rb",
            "owner_id": "owner-1",
            "owner_goal": "Goal with rollback lineage",
            "invariants": ["True"],
            "weights": {"w1": 0.6, "w2": 0.4},
        }
    )
    p2 = cap.execute(
        {
            "action": "propose",
            "objective_id": "obj-rb",
            "signals": {"w1": 0.5, "w2": -0.5},
            "learning_rate": 0.1,
            "evidence_ids": [evidence_id],
            "policy_decision": "ALLOW",
            "expires_at": time.time() + 300,
        }
    )
    cap.execute(
        {
            "action": "approve",
            "objective_id": "obj-rb",
            "version": 2,
            "approval_id": "appr-rb-v2",
            "approved_by": "owner-1",
            "signature": _sign(f"approve|obj-rb|2|{p2.data['proposal_digest']}|appr-rb-v2|owner-1"),
        }
    )

    # Rollback to version 1
    rb_sig = _sign("rollback|obj-rb|2|1|rb-01|owner-1")
    rb_res = cap.execute(
        {
            "action": "rollback",
            "objective_id": "obj-rb",
            "to_version": 1,
            "rollback_id": "rb-01",
            "approved_by": "owner-1",
            "signature": rb_sig,
        }
    )
    assert rb_res.data["version"] == 3
    assert rb_res.data["restored_from"] == 1

    # Active weights should match version 1
    active = cap.active("obj-rb")
    assert active["version"] == 3
    assert active["weights"] == {"w1": 0.6, "w2": 0.4}

    # Lineage history verification
    hist = cap.execute({"action": "history", "objective_id": "obj-rb"})
    assert len(hist.data["versions"]) == 3
    assert len(hist.data["rollbacks"]) == 1
    assert len(hist.data["audit_events"]) == 4  # create, propose, approve, rollback


def test_tamper_detection_and_integrity_check(tmp_path: Path) -> None:
    rag, evidence_id = _setup_rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    db_path = tmp_path / "obj_tamper.sqlite3"
    cap = DynamicObjectiveCapability(db_path, APPROVAL_KEY, rag, sandbox)

    cap.execute(
        {
            "action": "create",
            "objective_id": "obj-tamper",
            "owner_id": "owner-1",
            "owner_goal": "Protected immutable goal",
            "invariants": ["True"],
            "weights": {"w1": 1.0},
        }
    )

    # Clean integrity check passes
    check = cap.execute({"action": "verify_integrity", "objective_id": "obj-tamper"})
    assert check.data["status"] == "HEALTHY"

    # Malicious direct modification of owner_goal in database
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE owner_goals SET owner_goal='Hacked goal' WHERE objective_id='obj-tamper'"
        )
        conn.commit()
    finally:
        conn.close()

    # Integrity verification must detect tamper
    with pytest.raises(LocalPillarError) as exc_tamper:
        cap.execute({"action": "verify_integrity", "objective_id": "obj-tamper"})
    assert exc_tamper.value.code == "STORAGE_CORRUPT"


def test_meta_planning_integration_and_hijack_prevention(tmp_path: Path) -> None:
    rag, _ = _setup_rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    cap = DynamicObjectiveCapability(tmp_path / "obj.sqlite3", APPROVAL_KEY, rag, sandbox)

    cap.execute(
        {
            "action": "create",
            "objective_id": "obj-plan",
            "owner_id": "owner-1",
            "owner_goal": "Safely execute mission tasks",
            "invariants": ["True"],
            "weights": {"safety": 1.0},
        }
    )

    spec = SpeculativeReasoningCapability(tmp_path / "spec.sqlite3", rag, sandbox)
    planner = MetaPlanningCapability(tmp_path / "plan.sqlite3", rag, sandbox, spec)
    planner.objective_resolver = cap.active

    # Plan with matching goal succeeds
    res = planner.execute(
        {
            "action": "run",
            "objective_id": "obj-plan",
            "goal": "Safely execute mission tasks",
            "invariants": ["True"],
            "steps": [{"type": "sandbox", "expression": "100 > 50"}],
        }
    )
    assert res.data["status"] == "COMPLETED"
    assert res.data["objective_version"] == 1

    # Plan attempting to hijack / alter owner goal is blocked
    with pytest.raises(LocalPillarError) as exc_hijack:
        planner.execute(
            {
                "action": "run",
                "objective_id": "obj-plan",
                "goal": "Malicious goal replacement",
                "invariants": ["True"],
                "steps": [{"type": "sandbox", "expression": "True"}],
            }
        )
    assert exc_hijack.value.code == "OBJECTIVE_HIJACK"
