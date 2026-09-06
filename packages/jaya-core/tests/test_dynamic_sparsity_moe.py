"""Comprehensive unit and integration test suite for Pillar 34: Dynamic Sparsity MoE."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.moe_capability import MOE_CAPABILITY_ID, DynamicSparsityMoECapability

SIGNING_KEY = b"test-moe-expert-signing-key-32b-length!"


def _write_signed_expert(
    root: Path,
    expert_id: str,
    *,
    weights: list[list[float]],
    bias: list[float],
    routing: list[float],
    task_kinds: list[str] | None = None,
    capacity: int = 10,
    key: bytes = SIGNING_KEY,
) -> Path:
    tasks = task_kinds or ["RESEARCH_SCORE", "REASONING"]
    manifest = {
        "schema_version": 1,
        "expert_id": expert_id,
        "version": "1.0",
        "task_kinds": tasks,
        "input_dimension": len(routing),
        "output_dimension": len(bias),
        "weight_matrix": weights,
        "bias": bias,
        "routing_vector": routing,
        "capacity": capacity,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    wrapper = {"manifest": manifest, "signature": sig}

    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{expert_id}.expert.json"
    target.write_text(json.dumps(wrapper, indent=2), encoding="utf-8")
    return target


def _setup_standard_experts(root: Path) -> None:
    # Expert 1: Logic expert (high weight on dimension 0)
    _write_signed_expert(
        root,
        "logic-expert-01",
        weights=[[1.2, 0.1, 0.0], [0.0, 0.9, -0.1]],
        bias=[0.1, -0.1],
        routing=[1.0, 0.1, 0.0],
        capacity=5,
    )
    # Expert 2: Evidence expert (high weight on dimension 1)
    _write_signed_expert(
        root,
        "evidence-expert-02",
        weights=[[0.2, 1.1, 0.1], [0.1, 0.8, 0.2]],
        bias=[0.0, 0.2],
        routing=[0.1, 1.0, 0.1],
        capacity=5,
    )
    # Expert 3: Risk expert (high weight on dimension 2)
    _write_signed_expert(
        root,
        "risk-expert-03",
        weights=[[0.1, 0.2, 1.3], [0.3, 0.1, 0.7]],
        bias=[-0.1, 0.0],
        routing=[0.0, 0.2, 1.0],
        capacity=5,
    )


def test_moe_initialization_and_wal(tmp_path: Path) -> None:
    expert_root = tmp_path / "experts"
    _setup_standard_experts(expert_root)
    db_path = tmp_path / "moe.sqlite3"

    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=db_path, signing_key=SIGNING_KEY
    )
    assert moe.health_check() is True

    # Verify SQLite WAL mode and Schema Version 2
    conn = sqlite3.connect(db_path)
    try:
        jmode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert jmode.upper() == "WAL"

        ver = conn.execute("SELECT schema_version FROM moe_schema").fetchone()[0]
        assert ver == 2

        # Check required tables exist
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "moe_schema",
            "expert_utilization",
            "moe_runs",
            "moe_audit_log",
            "moe_receipts",
        }.issubset(tables)
    finally:
        conn.close()


def test_multi_expert_distinct_computation(tmp_path: Path) -> None:
    expert_root = tmp_path / "experts"
    _setup_standard_experts(expert_root)
    db_path = tmp_path / "moe.sqlite3"
    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=db_path, signing_key=SIGNING_KEY
    )

    # Input strongly aligned with dimension 0 (Logic)
    res_logic = moe.execute(
        {
            "action": "run",
            "task_kind": "RESEARCH_SCORE",
            "vector": [1.0, 0.0, 0.0],
            "top_k": 2,
            "maximum_quality_regression": 1.0,
        }
    )
    # Input strongly aligned with dimension 2 (Risk)
    res_risk = moe.execute(
        {
            "action": "run",
            "task_kind": "RESEARCH_SCORE",
            "vector": [0.0, 0.0, 1.0],
            "top_k": 2,
            "maximum_quality_regression": 1.0,
        }
    )

    # Selected experts should differ based on routing vectors
    sel_logic = [e["expert_id"] for e in res_logic.data["selected_experts"]]
    sel_risk = [e["expert_id"] for e in res_risk.data["selected_experts"]]
    assert sel_logic[0] == "logic-expert-01"
    assert sel_risk[0] == "risk-expert-03"

    # Outputs must be mathematically distinct
    out_logic = np.array(res_logic.data["output"])
    out_risk = np.array(res_risk.data["output"])
    assert not np.allclose(out_logic, out_risk)


def test_signature_verification_and_tamper_rejection(tmp_path: Path) -> None:
    expert_root = tmp_path / "experts"
    expert_root.mkdir(parents=True)
    _write_signed_expert(
        expert_root,
        "valid-expert-01",
        weights=[[1.0, 0.0], [0.0, 1.0]],
        bias=[0.0, 0.0],
        routing=[1.0, 0.0],
    )
    tampered_file = _write_signed_expert(
        expert_root,
        "tampered-expert-02",
        weights=[[0.5, 0.5], [0.5, 0.5]],
        bias=[0.1, 0.1],
        routing=[0.0, 1.0],
    )

    # Maliciously modify the weights without updating the signature
    wrapper = json.loads(tampered_file.read_text(encoding="utf-8"))
    wrapper["manifest"]["weight_matrix"] = [[99.0, 99.0], [99.0, 99.0]]
    tampered_file.write_text(json.dumps(wrapper), encoding="utf-8")

    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=tmp_path / "moe.sqlite3", signing_key=SIGNING_KEY
    )
    with pytest.raises(LocalPillarError) as exc:
        moe.experts()
    assert exc.value.code == "EXPERT_SIGNATURE_INVALID"


def test_top_k_sparse_routing_and_weights(tmp_path: Path) -> None:
    expert_root = tmp_path / "experts"
    _setup_standard_experts(expert_root)
    db_path = tmp_path / "moe.sqlite3"
    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=db_path, signing_key=SIGNING_KEY
    )

    res = moe.execute(
        {
            "action": "run",
            "task_kind": "RESEARCH_SCORE",
            "vector": [0.8, 0.5, 0.1],
            "top_k": 2,
            "maximum_quality_regression": 1.0,
            "temperature": 0.5,
        }
    )
    assert res.data["experts_executed"] == 2
    weights = [e["routing_weight"] for e in res.data["selected_experts"]]
    assert len(weights) == 2
    assert np.isclose(sum(weights), 1.0)
    assert all(0.0 <= w <= 1.0 for w in weights)


def test_dense_baseline_quality_gating(tmp_path: Path) -> None:
    expert_root = tmp_path / "experts"
    _setup_standard_experts(expert_root)
    db_path = tmp_path / "moe.sqlite3"
    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=db_path, signing_key=SIGNING_KEY
    )

    # Generous budget passes
    res = moe.execute(
        {
            "action": "run",
            "task_kind": "RESEARCH_SCORE",
            "vector": [0.5, 0.5, 0.5],
            "top_k": 2,
            "maximum_quality_regression": 1.0,
        }
    )
    assert "dense_baseline" in res.data
    assert res.data["quality_regression"] >= 0.0

    # Extremely strict regression budget fails
    with pytest.raises(LocalPillarError) as exc:
        moe.execute(
            {
                "action": "run",
                "task_kind": "RESEARCH_SCORE",
                "vector": [0.5, 0.5, 0.5],
                "top_k": 2,
                "maximum_quality_regression": 1e-9,
            }
        )
    assert exc.value.code == "QUALITY_BUDGET_EXCEEDED"


def test_capacity_overflow_and_dynamic_rerouting(tmp_path: Path) -> None:
    expert_root = tmp_path / "experts"
    _setup_standard_experts(expert_root)
    db_path = tmp_path / "moe.sqlite3"
    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=db_path, signing_key=SIGNING_KEY
    )

    # Vector pointing towards logic-expert-01
    vector = [1.0, 0.0, 0.0]

    # Set logic-expert-01 load to exceed its capacity (capacity = 5)
    moe.set_expert_load("logic-expert-01", 10)

    res = moe.execute(
        {
            "action": "run",
            "task_kind": "RESEARCH_SCORE",
            "vector": vector,
            "top_k": 2,
            "maximum_quality_regression": 1.0,
        }
    )
    selected_ids = [e["expert_id"] for e in res.data["selected_experts"]]

    # logic-expert-01 was at capacity, so it should NOT be selected!
    assert "logic-expert-01" not in selected_ids
    assert "evidence-expert-02" in selected_ids
    assert "risk-expert-03" in selected_ids

    # Overflow should be recorded
    assert len(res.data["overflows"]) == 1
    assert res.data["overflows"][0]["expert_id"] == "logic-expert-01"

    # Check database utilization has recorded overflow_count
    utils = moe.utilization()
    logic_util = next(u for u in utils if u["expert_id"] == "logic-expert-01")
    assert logic_util["overflow_count"] >= 1


def test_capacity_exhaustion_failure(tmp_path: Path) -> None:
    expert_root = tmp_path / "experts"
    _setup_standard_experts(expert_root)
    db_path = tmp_path / "moe.sqlite3"
    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=db_path, signing_key=SIGNING_KEY
    )

    # Exhaust capacity on ALL experts
    moe.set_expert_load("logic-expert-01", 10)
    moe.set_expert_load("evidence-expert-02", 10)
    moe.set_expert_load("risk-expert-03", 10)

    with pytest.raises(LocalPillarError) as exc:
        moe.execute(
            {
                "action": "run",
                "task_kind": "RESEARCH_SCORE",
                "vector": [1.0, 0.0, 0.0],
                "top_k": 2,
            }
        )
    assert exc.value.code == "CAPACITY_EXCEEDED"


def test_unavailable_and_incompatible_experts(tmp_path: Path) -> None:
    expert_root = tmp_path / "experts"
    _setup_standard_experts(expert_root)
    db_path = tmp_path / "moe.sqlite3"
    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=db_path, signing_key=SIGNING_KEY
    )

    # Task kind with 0 experts
    with pytest.raises(LocalPillarError) as exc_unavail:
        moe.execute(
            {
                "action": "run",
                "task_kind": "NONEXISTENT_TASK",
                "vector": [1.0, 0.0, 0.0],
                "top_k": 2,
            }
        )
    assert exc_unavail.value.code == "EXPERT_UNAVAILABLE"

    # Add an expert with mismatched output dimension (3 instead of 2)
    _write_signed_expert(
        expert_root,
        "mismatched-expert-04",
        weights=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        bias=[0.0, 0.0, 0.0],
        routing=[0.5, 0.5, 0.5],
        task_kinds=["RESEARCH_SCORE"],
    )
    with pytest.raises(LocalPillarError) as exc_incompat:
        moe.execute(
            {
                "action": "run",
                "task_kind": "RESEARCH_SCORE",
                "vector": [1.0, 0.0, 0.0],
                "top_k": 2,
            }
        )
    assert exc_incompat.value.code == "EXPERT_INCOMPATIBLE"


def test_corrupt_weights_and_shapes(tmp_path: Path) -> None:
    expert_root = tmp_path / "experts"
    expert_root.mkdir()

    # Create expert with NaN in weights
    _write_signed_expert(
        expert_root,
        "nan-expert",
        weights=[[float("nan"), 0.0], [0.0, 1.0]],
        bias=[0.0, 0.0],
        routing=[1.0, 0.0],
    )
    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=tmp_path / "moe.sqlite3", signing_key=SIGNING_KEY
    )
    with pytest.raises(LocalPillarError) as exc:
        moe.experts()
    assert exc.value.code == "CORRUPT_EXPERT"


def test_sqlite_restart_durability_and_receipt_integrity(tmp_path: Path) -> None:
    expert_root = tmp_path / "experts"
    _setup_standard_experts(expert_root)
    db_path = tmp_path / "moe.sqlite3"

    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=db_path, signing_key=SIGNING_KEY
    )

    res = moe.execute(
        {
            "action": "run",
            "task_kind": "RESEARCH_SCORE",
            "vector": [0.6, 0.8, 0.1],
            "top_k": 2,
            "maximum_quality_regression": 1.0,
        }
    )
    run_id = res.data["run_id"]
    receipt_id = res.data["receipt_id"]
    result_digest = res.data["result_digest"]

    # Initial integrity check passes
    check_res = moe.execute({"action": "verify_integrity"})
    assert check_res.data["status"] == "HEALTHY"
    assert check_res.data["receipts_checked"] == 1

    # Restart capability instance with same SQLite database
    restarted_moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=db_path, signing_key=SIGNING_KEY
    )
    hist = restarted_moe.history(limit=10)
    assert len(hist["runs"]) == 1
    assert hist["runs"][0]["run_id"] == run_id
    assert hist["runs"][0]["result_digest"] == result_digest
    assert len(hist["receipts"]) == 1
    assert hist["receipts"][0]["receipt_id"] == receipt_id

    # Tampering test: maliciously corrupt the result_digest in moe_runs
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE moe_runs SET result_digest='tampered_bad_digest' WHERE run_id=?", (run_id,))
    conn.commit()
    conn.close()

    with pytest.raises(LocalPillarError) as exc:
        restarted_moe.execute({"action": "verify_integrity"})
    assert exc.value.code == "STORAGE_CORRUPT"
