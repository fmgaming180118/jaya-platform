"""Unit and integration tests for Pillar 28 Self Bootstrapping."""

from __future__ import annotations

import hashlib
import hmac
import math
import shutil
import tempfile
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.maintenance_capabilities import (
    BOOTSTRAP_CAPABILITY_ID,
    SelfBootstrappingCapability,
)

SIGNING_KEY = bytes(range(32))


def _sign(key: bytes, material: bytes) -> str:
    return hmac.new(key, material, hashlib.sha256).hexdigest()


@pytest.fixture
def test_env():
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_test_bootstrap_"))
    bootstrap_root = temp_dir / "bootstrap"
    bootstrap_root.mkdir(parents=True, exist_ok=True)
    db_path = bootstrap_root / "bootstrap.sqlite3"
    rag_db = temp_dir / "rag.sqlite3"

    rag = AgenticRAGCapability(rag_db, None)
    rag.execute({
        "action": "ingest",
        "source_ref": "audit:test-gap",
        "title": "Test evidence",
        "content": "Evidence needed for test calculations and operations.",
    })
    evidence_id = rag.retrieve("Test evidence", 1)[0]["evidence_id"]

    service = SelfBootstrappingCapability(bootstrap_root, db_path, SIGNING_KEY, rag)
    yield bootstrap_root, db_path, service, rag, evidence_id
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_bootstrap_full_lifecycle(test_env):
    root, db_path, service, rag, evidence_id = test_env

    # 1. Propose
    prop = service.propose({
        "action": "propose",
        "candidate_id": "test-sum-v1",
        "capability_id": "math.sum.test",
        "capability_gap": "Need sum calculator for tests",
        "operation": "sum",
        "evidence_ids": [evidence_id],
        "acceptance_cases": [
            {"values": [1.0, 2.0, 3.0], "expected": 6.0},
            {"values": [10.0, 20.0], "expected": 30.0},
        ],
    })
    assert prop.code == "BOOTSTRAP_CANDIDATE_PROPOSED"
    art_digest = prop.data["artifact_digest"]

    # 2. Plan Dependencies
    plan = service.plan_dependencies({
        "action": "plan_dependencies",
        "candidate_id": "test-sum-v1",
        "dependencies": [
            {"capability_id": "base.pkg", "depends_on": []},
            {"capability_id": "math.sum.test", "depends_on": ["base.pkg"]},
        ],
    })
    assert plan.code == "DEPENDENCY_PLAN_COMPUTED"
    assert plan.data["execution_order"] == ["base.pkg", "math.sum.test"]

    # 3. Validate
    val = service.validate({"action": "validate", "candidate_id": "test-sum-v1"})
    assert val.code == "BOOTSTRAP_CANDIDATE_VALIDATED"
    assert val.data["passed"] is True
    val_digest = val.data["validation_digest"]

    # 4. Stage
    stage = service.stage({"action": "stage", "candidate_id": "test-sum-v1"})
    assert stage.code == "BOOTSTRAP_CANDIDATE_STAGED"
    assert (root / "staged" / "test-sum-v1.candidate.json").exists()

    # 5. Install
    material = f"install|test-sum-v1|{art_digest}|{val_digest}|app-1|admin".encode()
    sig = _sign(SIGNING_KEY, material)
    inst = service.install({
        "action": "install",
        "candidate_id": "test-sum-v1",
        "approval_id": "app-1",
        "approved_by": "admin",
        "signature": sig,
    })
    assert inst.code == "BOOTSTRAP_CANDIDATE_INSTALLED"
    assert inst.data["canary"] == "PASSED"
    assert (root / "installed" / "test-sum-v1.candidate.json").exists()

    # 6. Invoke
    inv = service.invoke({
        "action": "invoke",
        "candidate_id": "test-sum-v1",
        "values": [5.0, 15.0, 30.0],
    })
    assert inv.code == "INSTALLED_CAPABILITY_EXECUTED"
    assert math.isclose(inv.data["result"], 50.0)

    # 7. Metrics
    met = service.metrics()
    assert met.data["installed"] >= 1

    # 8. Rollback
    rb_mat = f"rollback_bootstrap|test-sum-v1|{art_digest}|rb-1|admin".encode()
    rb_sig = _sign(SIGNING_KEY, rb_mat)
    rb = service.rollback({
        "action": "rollback",
        "candidate_id": "test-sum-v1",
        "rollback_id": "rb-1",
        "approved_by": "admin",
        "signature": rb_sig,
    })
    assert rb.code == "BOOTSTRAP_CANDIDATE_ROLLED_BACK"


def test_ungrounded_evidence_rejected(test_env):
    root, db_path, service, rag, evidence_id = test_env
    with pytest.raises(LocalPillarError) as exc_info:
        service.propose({
            "action": "propose",
            "candidate_id": "fake-cand",
            "capability_id": "fake.cap",
            "capability_gap": "Ungrounded gap",
            "operation": "sum",
            "evidence_ids": ["evidence:does-not-exist"],
            "acceptance_cases": [{"values": [1, 2], "expected": 3}],
        })
    assert exc_info.value.code == "INVALID_EVIDENCE"


def test_dependency_cycle_detection(test_env):
    root, db_path, service, rag, evidence_id = test_env
    with pytest.raises(LocalPillarError) as exc_info:
        service.plan_dependencies({
            "action": "plan_dependencies",
            "candidate_id": "cand-cycle",
            "dependencies": [
                {"capability_id": "cycle.a", "depends_on": ["cycle.b"]},
                {"capability_id": "cycle.b", "depends_on": ["cycle.c"]},
                {"capability_id": "cycle.c", "depends_on": ["cycle.a"]},
            ],
        })
    assert exc_info.value.code == "DEPENDENCY_CYCLE"


def test_missing_dependency_detection(test_env):
    root, db_path, service, rag, evidence_id = test_env
    with pytest.raises(LocalPillarError) as exc_info:
        service.plan_dependencies({
            "action": "plan_dependencies",
            "candidate_id": "cand-missing",
            "dependencies": [
                {"capability_id": "orphan.pkg", "depends_on": ["missing.nonexistent.lib"]},
            ],
        })
    assert exc_info.value.code == "MISSING_DEPENDENCY"


def test_offline_network_download_prohibited(test_env):
    root, db_path, service, rag, evidence_id = test_env
    with pytest.raises(LocalPillarError) as exc_info:
        service.plan_dependencies({
            "action": "plan_dependencies",
            "candidate_id": "cand-net",
            "dependencies": [
                {"capability_id": "remote.lib", "depends_on": [], "source": "https://remote.server/lib"},
            ],
            "offline_policy": "DEFAULT_DENY",
        })
    assert exc_info.value.code == "NETWORK_DISALLOWED"


def test_validation_rejects_failing_cases(test_env):
    root, db_path, service, rag, evidence_id = test_env
    service.propose({
        "action": "propose",
        "candidate_id": "bad-math",
        "capability_id": "bad.calc",
        "capability_gap": "Wrong expectation",
        "operation": "sum",
        "evidence_ids": [evidence_id],
        "acceptance_cases": [{"values": [1, 2], "expected": 999.0}],
    })
    val = service.validate({"action": "validate", "candidate_id": "bad-math"})
    assert val.data["passed"] is False

    # Attempting to install rejected candidate fails
    with pytest.raises(LocalPillarError) as exc_info:
        service.install({
            "action": "install",
            "candidate_id": "bad-math",
            "approval_id": "app-fake",
            "approved_by": "admin",
            "signature": "fake",
        })
    assert exc_info.value.code == "CANDIDATE_NOT_VALIDATED"


def test_install_rejects_tampered_or_invalid_signature(test_env):
    root, db_path, service, rag, evidence_id = test_env
    prop = service.propose({
        "action": "propose",
        "candidate_id": "sig-test",
        "capability_id": "sig.cap",
        "capability_gap": "Signature verification test",
        "operation": "max",
        "evidence_ids": [evidence_id],
        "acceptance_cases": [{"values": [5, 10], "expected": 10.0}],
    })
    service.validate({"action": "validate", "candidate_id": "sig-test"})

    with pytest.raises(LocalPillarError) as exc_info:
        service.install({
            "action": "install",
            "candidate_id": "sig-test",
            "approval_id": "app-bad",
            "approved_by": "admin",
            "signature": "invalid_hex_signature_deadbeef",
        })
    assert exc_info.value.code == "SIGNATURE_INVALID"


def test_invoke_validates_numeric_and_finite_inputs(test_env):
    root, db_path, service, rag, evidence_id = test_env
    prop = service.propose({
        "action": "propose",
        "candidate_id": "input-val",
        "capability_id": "input.val",
        "capability_gap": "Input validation test",
        "operation": "min",
        "evidence_ids": [evidence_id],
        "acceptance_cases": [{"values": [1, 2], "expected": 1.0}],
    })
    val = service.validate({"action": "validate", "candidate_id": "input-val"})
    mat = f"install|input-val|{prop.data['artifact_digest']}|{val.data['validation_digest']}|app|admin".encode()
    service.install({
        "action": "install",
        "candidate_id": "input-val",
        "approval_id": "app",
        "approved_by": "admin",
        "signature": _sign(SIGNING_KEY, mat),
    })

    # Non-finite input
    with pytest.raises(LocalPillarError) as exc_info:
        service.invoke({
            "action": "invoke",
            "candidate_id": "input-val",
            "values": [1.0, float("inf")],
        })
    assert exc_info.value.code == "INVALID_INPUT"


def test_retired_candidate_cannot_be_invoked(test_env):
    root, db_path, service, rag, evidence_id = test_env
    prop = service.propose({
        "action": "propose",
        "candidate_id": "retire-test",
        "capability_id": "retire.cap",
        "capability_gap": "Retire candidate test",
        "operation": "sum",
        "evidence_ids": [evidence_id],
        "acceptance_cases": [{"values": [1, 2], "expected": 3.0}],
    })
    val = service.validate({"action": "validate", "candidate_id": "retire-test"})
    mat = f"install|retire-test|{prop.data['artifact_digest']}|{val.data['validation_digest']}|app|admin".encode()
    service.install({
        "action": "install",
        "candidate_id": "retire-test",
        "approval_id": "app",
        "approved_by": "admin",
        "signature": _sign(SIGNING_KEY, mat),
    })

    # Rollback
    rb_mat = f"rollback_bootstrap|retire-test|{prop.data['artifact_digest']}|rb|admin".encode()
    service.rollback({
        "action": "rollback",
        "candidate_id": "retire-test",
        "rollback_id": "rb",
        "approved_by": "admin",
        "signature": _sign(SIGNING_KEY, rb_mat),
    })

    with pytest.raises(LocalPillarError) as exc_info:
        service.invoke({
            "action": "invoke",
            "candidate_id": "retire-test",
            "values": [1, 2],
        })
    assert exc_info.value.code == "CANDIDATE_CORRUPT"


def test_restart_durability(test_env):
    root, db_path, service, rag, evidence_id = test_env
    prop = service.propose({
        "action": "propose",
        "candidate_id": "durable-cand",
        "capability_id": "durable.cap",
        "capability_gap": "Restart durability test",
        "operation": "mean",
        "evidence_ids": [evidence_id],
        "acceptance_cases": [{"values": [10, 20], "expected": 15.0}],
    })
    val = service.validate({"action": "validate", "candidate_id": "durable-cand"})

    # Create new instance
    restarted = SelfBootstrappingCapability(root, db_path, SIGNING_KEY, rag)
    assert restarted.health_check() is True
    inspect = restarted.inspect_candidate({"action": "inspect", "candidate_id": "durable-cand"})
    assert inspect.data["status"] == "VALIDATED"
    assert inspect.data["validation_digest"] == val.data["validation_digest"]


def test_core_runtime_integration(test_env):
    root, db_path, service, rag, evidence_id = test_env
    runtime_dir = root / "runtime_dir"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    runtime = JayaCoreRuntime(
        db_path=runtime_dir / "core.sqlite3",
        local_pillar_data_dir=runtime_dir / "local-pillars",
        lineage_signing_key=SIGNING_KEY,
    )
    try:
        rt_rag = runtime.advanced_pillar_capabilities.rag
        rt_rag.execute({
            "action": "ingest",
            "source_ref": "audit:rt-gap-test",
            "title": "Runtime Test Evidence",
            "content": "Runtime gap evidence for max calculation.",
        })
        rt_ev = rt_rag.retrieve("Runtime Test Evidence", 1)[0]["evidence_id"]

        rt_prop = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {
                "action": "propose",
                "candidate_id": "rt-max-calc",
                "capability_id": "runtime.math.max",
                "capability_gap": "Max calculation gap",
                "operation": "max",
                "evidence_ids": [rt_ev],
                "acceptance_cases": [{"values": [3.0, 9.0, 5.0], "expected": 9.0}],
            },
        )
        assert rt_prop.code == "BOOTSTRAP_CANDIDATE_PROPOSED"

        rt_val = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {"action": "validate", "candidate_id": "rt-max-calc"},
        )
        assert rt_val.code == "BOOTSTRAP_CANDIDATE_VALIDATED"

        rt_mat = f"install|rt-max-calc|{rt_prop.data['artifact_digest']}|{rt_val.data['validation_digest']}|rt-app|admin".encode()
        rt_inst = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {
                "action": "install",
                "candidate_id": "rt-max-calc",
                "approval_id": "rt-app",
                "approved_by": "admin",
                "signature": _sign(SIGNING_KEY, rt_mat),
            },
        )
        assert rt_inst.code == "BOOTSTRAP_CANDIDATE_INSTALLED"

        rt_inv = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {"action": "invoke", "candidate_id": "rt-max-calc", "values": [12.0, 48.0, 36.0]},
        )
        assert rt_inv.code == "INSTALLED_CAPABILITY_EXECUTED"
        assert math.isclose(rt_inv.data["result"], 48.0)
    finally:
        runtime.close()
