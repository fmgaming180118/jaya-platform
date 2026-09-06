"""Comprehensive tests for Pilar 38 Meta Cognitive Planning."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability
from jaya_core.pillars.local_capabilities import LocalPillarError, LocalPillarResult
from jaya_core.pillars.reasoning_capabilities import (
    META_PLANNING_CAPABILITY_ID,
    MetaPlanningCapability,
    PlanExecutionAuthority,
    PlanProgressEvaluator,
    SpeculativeReasoningCapability,
)
from jaya_core.pillars.advanced_capabilities import AdvancedPillarCapabilityService


def _setup_planner(tmp_path: Path) -> tuple[MetaPlanningCapability, AgenticRAGCapability, SandboxedImaginationCapability, SpeculativeReasoningCapability]:
    rag = AgenticRAGCapability(tmp_path / "rag.sqlite3", None)
    rag.ingest({
        "action": "ingest",
        "source_ref": "ref_quantum_1",
        "title": "Cryogenic Quantum",
        "content": "Quantum processor thermal noise reduces 95 percent at 4 Kelvin.",
    })
    rag.ingest({
        "action": "ingest",
        "source_ref": "ref_thermal_2",
        "title": "Thermal Management",
        "content": "Peltier solid state modules provide localized micro-cooling.",
    })
    sandbox = SandboxedImaginationCapability()
    speculative = SpeculativeReasoningCapability(tmp_path / "spec.sqlite3", rag, sandbox)
    planner = MetaPlanningCapability(tmp_path / "plans.sqlite3", rag, sandbox, speculative)
    return planner, rag, sandbox, speculative


def test_authority_allowlist_and_validation(tmp_path: Path) -> None:
    planner, rag, sandbox, speculative = _setup_planner(tmp_path)
    authority = PlanExecutionAuthority(rag, sandbox, speculative)

    # Valid tools
    res_sandbox = authority.execute_step({"type": "sandbox", "expression": "10 * 5 == 50"})
    assert res_sandbox["result"] is True

    res_retrieve = authority.execute_step({"type": "retrieve", "query": "Quantum", "minimum_results": 1})
    assert len(res_retrieve["evidence"]) >= 1

    res_logic = authority.execute_step({"type": "logic", "expression": "True and not False"})
    assert res_logic["result"] is True

    res_socratic = authority.execute_step({"type": "socratic", "reflection": "Are boundaries respected?"})
    assert res_socratic["status"] == "REFLECTED"

    # Unallowlisted tool rejected
    with pytest.raises(LocalPillarError) as exc_info:
        authority.execute_step({"type": "raw_shell", "command": "rm -rf /"})
    assert exc_info.value.code == "TOOL_UNAVAILABLE"

    # Malformed inputs
    with pytest.raises(LocalPillarError) as exc_info:
        authority.execute_step({"type": "sandbox", "expression": ""})
    assert exc_info.value.code == "INVALID_INPUT"

    planner.close()
    rag.close()


def test_evaluator_invariants_loops_and_no_progress(tmp_path: Path) -> None:
    sandbox = SandboxedImaginationCapability()
    evaluator = PlanProgressEvaluator(sandbox)

    # Invariants check
    assert evaluator.check_invariants(["1 + 1 == 2", "10 > 5"]) is True
    assert evaluator.check_invariants(["1 + 1 == 3"]) is False
    assert evaluator.check_invariants(["invalid syntax == @@"]) is False

    # Loop detection: consecutive duplicate failure
    history = [
        {"type": "retrieve", "params": {"query": "x"}, "status": "FAILED"},
        {"type": "retrieve", "params": {"query": "x"}, "status": "FAILED"},
    ]
    assert evaluator.detect_loop(history) is True

    # Loop detection: 2-step cycle (A B A B)
    history_cycle = [
        {"type": "sandbox", "params": {"expression": "1"}, "status": "ATTEMPTED"},
        {"type": "sandbox", "params": {"expression": "2"}, "status": "ATTEMPTED"},
        {"type": "sandbox", "params": {"expression": "1"}, "status": "ATTEMPTED"},
        {"type": "sandbox", "params": {"expression": "2"}, "status": "ATTEMPTED"},
    ]
    assert evaluator.detect_loop(history_cycle) is True

    # No-progress detection: 3 identical outputs
    obs_stagnant = [
        {"step": 0, "status": "SUCCESS", "output": {"result": 42}},
        {"step": 1, "status": "SUCCESS", "output": {"result": 42}},
        {"step": 2, "status": "SUCCESS", "output": {"result": 42}},
    ]
    assert evaluator.detect_no_progress(obs_stagnant) is True


def test_planner_multistep_execution_and_status(tmp_path: Path) -> None:
    planner, rag, sandbox, speculative = _setup_planner(tmp_path)
    res = planner.execute({
        "action": "run",
        "goal": "Verify thermal stabilization calculation",
        "invariants": ["100 <= 200"],
        "steps": [
            {"type": "retrieve", "query": "Quantum", "minimum_results": 1},
            {"type": "sandbox", "expression": "4 * 25 == 100"},
            {"type": "logic", "expression": "100 <= 200"},
        ],
    })
    assert res.code == "META_PLAN_EXECUTED"
    assert res.data["status"] == "COMPLETED"
    assert res.data["steps_used"] == 3
    assert res.data["decision"] == "STOP_SUCCESS"
    assert "receipt_sha256" in res.data

    # Check status action
    st = planner.execute({"action": "status"})
    assert st.code == "HEALTHY"
    assert st.data["total_plans"] >= 1
    assert st.data["completed_plans"] >= 1

    planner.close()
    rag.close()


def test_planner_dynamic_replan_and_fallback(tmp_path: Path) -> None:
    planner, rag, sandbox, speculative = _setup_planner(tmp_path)
    res = planner.execute({
        "action": "run",
        "goal": "Dynamic replan on failed retrieval step",
        "invariants": ["True"],
        "allow_dynamic_replan": True,
        "max_replans": 2,
        "steps": [
            {"type": "sandbox", "expression": "10 > 5"},
            {"type": "retrieve", "query": "missing_ghost_doc_xyz", "minimum_results": 10},
            {"type": "sandbox", "expression": "20 > 10"},
        ],
        "dynamic_replan_steps": [
            {"type": "retrieve", "query": "Cryogenic Quantum", "minimum_results": 1}
        ],
    })
    assert res.data["status"] == "COMPLETED"
    assert res.data["recoveries"] == 1
    assert res.data["replans"] == 1
    assert res.data["observations"][1]["status"] == "RECOVERED"
    assert res.data["observations"][1]["replan"] is True

    planner.close()
    rag.close()


def test_planner_cancellation_and_resume_durability(tmp_path: Path) -> None:
    db_path = tmp_path / "durability_plans.sqlite3"
    rag = AgenticRAGCapability(tmp_path / "dur_rag.sqlite3", None)
    sandbox = SandboxedImaginationCapability()
    speculative = SpeculativeReasoningCapability(tmp_path / "dur_spec.sqlite3", rag, sandbox)
    planner = MetaPlanningCapability(db_path, rag, sandbox, speculative)

    # Run initial plan
    init_res = planner.execute({
        "action": "run",
        "goal": "Multi-step plan for cancellation and resume",
        "invariants": ["True"],
        "steps": [
            {"type": "sandbox", "expression": "1 + 1 == 2"},
            {"type": "sandbox", "expression": "2 + 2 == 4"},
            {"type": "sandbox", "expression": "3 + 3 == 6"},
        ],
    })
    plan_id = init_res.data["plan_id"]

    # Cancel plan
    cancel_res = planner.execute({"action": "cancel", "plan_id": plan_id})
    assert cancel_res.code == "META_PLAN_CANCELLED"
    assert cancel_res.data["cancelled"] is True

    # Close capability simulating shutdown
    planner.close()

    # Recreate capability simulating restart
    restarted_planner = MetaPlanningCapability(db_path, rag, sandbox, speculative)
    resume_res = restarted_planner.execute({"action": "resume", "plan_id": plan_id})
    assert resume_res.code in ("META_PLAN_RESUMED", "META_PLAN_ALREADY_COMPLETED")

    # Get details
    get_res = restarted_planner.execute({"action": "get", "plan_id": plan_id})
    assert get_res.code == "META_PLAN_RETRIEVED"
    assert len(get_res.data["steps"]) >= 1

    restarted_planner.close()
    rag.close()


def test_planner_tamper_detection(tmp_path: Path) -> None:
    planner, rag, sandbox, speculative = _setup_planner(tmp_path)
    res = planner.execute({
        "action": "run",
        "goal": "Tamper testing plan",
        "invariants": ["True"],
        "steps": [{"type": "sandbox", "expression": "100 == 100"}],
    })
    plan_id = res.data["plan_id"]

    # Tamper with goal in DB
    conn = sqlite3.connect(str(tmp_path / "plans.sqlite3"))
    with conn:
        conn.execute("UPDATE meta_plans SET goal='MODIFIED_TAMPERED_GOAL' WHERE plan_id=?", (plan_id,))
    conn.close()

    # Retrieval must fail with STORAGE_CORRUPT
    with pytest.raises(LocalPillarError) as exc_info:
        planner.execute({"action": "get", "plan_id": plan_id})
    assert exc_info.value.code == "STORAGE_CORRUPT"

    planner.close()
    rag.close()


def test_planner_deterministic_replay(tmp_path: Path) -> None:
    planner, rag, sandbox, speculative = _setup_planner(tmp_path)
    req_id = f"req-test-replay-{uuid.uuid4().hex[:8]}"

    run1 = planner.execute({
        "action": "run",
        "request_id": req_id,
        "goal": "Replay test goal",
        "invariants": ["True"],
        "steps": [{"type": "sandbox", "expression": "50 * 2 == 100"}],
    })
    assert run1.code == "META_PLAN_EXECUTED"

    run2 = planner.execute({
        "action": "run",
        "request_id": req_id,
        "goal": "Replay test goal",
        "invariants": ["True"],
        "steps": [{"type": "sandbox", "expression": "50 * 2 == 100"}],
    })
    assert run2.code == "REPLAYED_META_PLAN"
    assert run1.data["plan_id"] == run2.data["plan_id"]
    assert run1.data["receipt_sha256"] == run2.data["receipt_sha256"]

    replay_action = planner.execute({"action": "replay", "request_id": req_id})
    assert replay_action.code == "REPLAYED_META_PLAN"
    assert replay_action.data["plan_id"] == run1.data["plan_id"]

    planner.close()
    rag.close()


def test_advanced_service_runtime_wiring(tmp_path: Path) -> None:
    svc_dir = tmp_path / "adv_service"
    svc_dir.mkdir(parents=True, exist_ok=True)
    svc = AdvancedPillarCapabilityService(svc_dir)

    manifest_ids = [m.capability_id for m in svc.manifests()]
    assert META_PLANNING_CAPABILITY_ID in manifest_ids

    # Execute plan via service
    svc.rag.ingest({
        "action": "ingest",
        "source_ref": "svc_test_ref",
        "title": "Service Wiring Test",
        "content": "P38 runtime service wiring integration test.",
    })
    res = svc.execute(
        META_PLANNING_CAPABILITY_ID,
        {
            "action": "run",
            "goal": "Advanced capability service test plan",
            "invariants": ["True"],
            "steps": [
                {"type": "sandbox", "expression": "100 + 100 == 200"},
                {"type": "retrieve", "query": "Service Wiring", "minimum_results": 1},
            ],
        },
    )
    assert isinstance(res, LocalPillarResult)
    assert res.pillar_id == "P038"
    assert res.code == "META_PLAN_EXECUTED"
    assert res.data["status"] == "COMPLETED"

    svc.close()
