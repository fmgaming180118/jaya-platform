"""Signed expert routing and sparse-kernel tests for P34/P35."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.foundation_capabilities import (
    SPARSE_CAPABILITY_ID,
    ActivationSparsityCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.moe_capability import MOE_CAPABILITY_ID, DynamicSparsityMoECapability

EXPERT_KEY = b"expert-artifact-signing-key-with-at-least-32-bytes"


def _write_expert(
    root: Path,
    expert_id: str,
    *,
    weights: list[list[float]],
    routing: list[float],
) -> None:
    manifest = {
        "schema_version": 1,
        "expert_id": expert_id,
        "version": "1.0",
        "task_kinds": ["RESEARCH_SCORE"],
        "input_dimension": 3,
        "output_dimension": 2,
        "weight_matrix": weights,
        "bias": [0.1, -0.1],
        "routing_vector": routing,
        "capacity": 64,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    wrapper = {
        "manifest": manifest,
        "signature": hmac.new(EXPERT_KEY, canonical, hashlib.sha256).hexdigest(),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{expert_id}.expert.json").write_text(
        json.dumps(wrapper, sort_keys=True), encoding="utf-8"
    )


def _experts(root: Path) -> None:
    _write_expert(
        root,
        "logic-expert",
        weights=[[1.0, 0.0, 0.2], [0.0, 1.0, -0.2]],
        routing=[1.0, 0.1, 0.0],
    )
    _write_expert(
        root,
        "evidence-expert",
        weights=[[0.8, 0.1, 0.0], [0.1, 0.9, 0.1]],
        routing=[0.2, 1.0, 0.1],
    )
    _write_expert(
        root,
        "risk-expert",
        weights=[[0.5, 0.2, 0.4], [0.3, 0.4, 0.7]],
        routing=[0.0, 0.2, 1.0],
    )


def test_p034_routes_and_executes_multiple_signed_experts_with_metrics(tmp_path: Path) -> None:
    root = tmp_path / "experts"
    _experts(root)
    database = tmp_path / "moe.sqlite3"
    moe = DynamicSparsityMoECapability(
        expert_root=root, database_path=database, signing_key=EXPERT_KEY
    )
    result = moe.execute(
        {
            "action": "run",
            "task_kind": "research_score",
            "vector": [0.9, 0.6, 0.2],
            "top_k": 2,
            "maximum_quality_regression": 1.0,
        }
    )
    restarted = DynamicSparsityMoECapability(
        expert_root=root, database_path=database, signing_key=EXPERT_KEY
    )

    assert restarted.health_check() is True
    assert result.data["experts_executed"] == 2
    assert result.data["experts_available"] == 3
    assert len(result.data["output"]) == 2
    assert result.data["quality_regression"] >= 0
    assert all(item["artifact_digest"].startswith("sha256:") for item in result.data["selected_experts"])
    assert all(item["latency_ns"] > 0 for item in result.data["selected_experts"])


def test_p034_rejects_corrupt_signature_insufficient_experts_and_quality_budget(tmp_path: Path) -> None:
    root = tmp_path / "experts"
    _write_expert(
        root,
        "only-expert",
        weights=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        routing=[1.0, 0.0, 0.0],
    )
    moe = DynamicSparsityMoECapability(
        expert_root=root, database_path=tmp_path / "one.sqlite3", signing_key=EXPERT_KEY
    )
    assert moe.health_check() is False
    with pytest.raises(LocalPillarError) as unavailable:
        moe.execute(
            {"action": "run", "task_kind": "RESEARCH_SCORE", "vector": [1, 2, 3], "top_k": 2}
        )
    assert unavailable.value.code == "EXPERT_UNAVAILABLE"
    wrapper = json.loads((root / "only-expert.expert.json").read_text(encoding="utf-8"))
    wrapper["signature"] = "0" * 64
    (root / "only-expert.expert.json").write_text(json.dumps(wrapper), encoding="utf-8")
    assert moe.health_check() is False
    with pytest.raises(LocalPillarError) as signature:
        moe.experts()
    assert signature.value.code == "EXPERT_SIGNATURE_INVALID"


def test_p035_executes_only_selected_operations_and_enforces_dense_quality_budget() -> None:
    sparse = ActivationSparsityCapability()
    result = sparse.execute(
        {
            "action": "run",
            "values": [-5.0, 4.0, 0.1, -0.2],
            "top_k": 2,
            "operation": "relu",
            "maximum_quality_regression": 1.0,
        }
    )
    assert result.data["operations_executed"] == 2
    assert result.data["dense_operations"] == 4
    assert result.data["compute_reduction"] == 0.5
    assert result.data["values"] == [0.0, 4.0, 0.0, 0.0]
    assert result.data["environment"]["numpy"]
    with pytest.raises(LocalPillarError) as quality:
        sparse.execute(
            {
                "action": "run",
                "values": [1.0, 1.0, 1.0, 1.0],
                "top_k": 1,
                "operation": "identity",
                "maximum_quality_regression": 0.1,
            }
        )
    assert quality.value.code == "QUALITY_BUDGET_EXCEEDED"


def test_runtime_dispatches_p034_and_dependency_gated_p035(tmp_path: Path) -> None:
    root = tmp_path / "experts"
    _experts(root)
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
        local_expert_root=root,
        lineage_signing_key=EXPERT_KEY,
    )
    try:
        moe = runtime.execute_local_pillar(
            MOE_CAPABILITY_ID,
            {
                "action": "run",
                "task_kind": "RESEARCH_SCORE",
                "vector": [0.9, 0.4, 0.2],
                "top_k": 2,
                "maximum_quality_regression": 1.0,
            },
        )
        sparse = runtime.execute_local_pillar(
            SPARSE_CAPABILITY_ID,
            {
                "action": "run",
                "values": [1.0, -8.0, 2.0],
                "top_k": 1,
                "operation": "square",
                "maximum_quality_regression": 1.0,
            },
        )
        health = runtime.operational_snapshot()["local_pillar_capabilities"]["capabilities"]
        assert moe.data["experts_executed"] == 2
        assert sparse.data["values"] == [0.0, 64.0, 0.0]
        assert health[MOE_CAPABILITY_ID] == "HEALTHY"
        assert health[SPARSE_CAPABILITY_ID] == "HEALTHY"
    finally:
        runtime.close()
