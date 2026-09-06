"""Unit and integration tests for Pillar 35 Activation Sparsity."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from jaya_core.pillars.activation_sparsity import (
    DEFAULT_SPARSE_KEY,
    SCHEMA_VERSION,
    SPARSE_CAPABILITY_ID,
    ActivationSparsityCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError


def test_activation_sparsity_initialization_and_health_check(tmp_path: Path) -> None:
    db_path = tmp_path / "sparse.sqlite3"
    cap = ActivationSparsityCapability(database_path=db_path)
    assert cap.health_check() is True

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM sparsity_schema")
        assert cursor.fetchone()[0] == SCHEMA_VERSION
        cursor.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0].lower() == "wal"


def test_activation_sparsity_hardware_probe() -> None:
    cap = ActivationSparsityCapability()
    probe = cap.probe_hardware()
    assert probe["provider_type"] == "NUMPY_INDEXED_SPARSE"
    assert probe["execution_mode"] == "CPU_INDEXED_SKIP_COMPUTE"
    assert isinstance(probe["simd_instructions"], list)
    assert len(probe["simd_instructions"]) > 0
    assert probe["cpu_count_logical"] >= 1
    assert probe["labeled_dense_fallback_available"] is True


def test_activation_sparsity_top_k_execution_and_operations(tmp_path: Path) -> None:
    db_path = tmp_path / "sparse.sqlite3"
    cap = ActivationSparsityCapability(database_path=db_path)

    values = [-10.0, 5.0, 0.2, -0.1, 8.0]

    # 1. ReLU
    res_relu = cap.execute({
        "action": "run",
        "values": values,
        "top_k": 2,
        "operation": "relu",
        "maximum_quality_regression": 1.0,
    })
    assert res_relu.data["operations_executed"] == 2
    assert res_relu.data["dense_operations"] == 5
    assert res_relu.data["compute_reduction"] == 0.6
    assert res_relu.data["achieved_sparsity"] == 0.6
    assert res_relu.data["indices"] == [0, 4]
    # -10 is relu'd to 0.0, 8.0 is relu'd to 8.0, others are 0.0
    assert res_relu.data["values"] == [0.0, 0.0, 0.0, 0.0, 8.0]
    assert res_relu.data["receipt_id"].startswith("rcpt-sparse-")

    # 2. GELU
    res_gelu = cap.execute({
        "action": "run",
        "values": [2.0, -2.0, 0.0],
        "top_k": 2,
        "operation": "gelu",
        "maximum_quality_regression": 1.0,
    })
    assert res_gelu.data["operations_executed"] == 2
    assert res_gelu.data["compute_reduction"] == pytest.approx(1.0 / 3.0)

    # 3. Square
    res_sq = cap.execute({
        "action": "run",
        "values": [1.0, -3.0, 2.0],
        "top_k": 1,
        "operation": "square",
        "maximum_quality_regression": 1.0,
    })
    assert res_sq.data["values"] == [0.0, 9.0, 0.0]

    # 4. Abs
    res_abs = cap.execute({
        "action": "run",
        "values": [1.0, -3.0, 2.0],
        "top_k": 1,
        "operation": "abs",
        "maximum_quality_regression": 1.0,
    })
    assert res_abs.data["values"] == [0.0, 3.0, 0.0]


def test_activation_sparsity_threshold_gating(tmp_path: Path) -> None:
    cap = ActivationSparsityCapability(database_path=tmp_path / "sparse.sqlite3")

    values = [0.1, 2.5, -3.0, 0.5, -0.2, 4.0]
    res = cap.execute({
        "action": "run",
        "values": values,
        "threshold": 2.0,
        "operation": "identity",
        "maximum_quality_regression": 1.0,
    })

    # Magnitudes: [0.1, 2.5, 3.0, 0.5, 0.2, 4.0]
    # Indices >= 2.0 are: index 1 (2.5), index 2 (-3.0), index 5 (4.0) -> 3 operations
    assert res.data["indices"] == [1, 2, 5]
    assert res.data["operations_executed"] == 3
    assert res.data["dense_operations"] == 6
    assert res.data["compute_reduction"] == 0.5
    assert res.data["values"] == [0.0, 2.5, -3.0, 0.0, 0.0, 4.0]
    assert res.data["verified_against"] == "PYTHON_SCALAR_THRESHOLD"


def test_activation_sparsity_dense_quality_budget(tmp_path: Path) -> None:
    cap = ActivationSparsityCapability(database_path=tmp_path / "sparse.sqlite3")

    # 4 uniform values, keeping only 1 should have high relative L2 regression
    with pytest.raises(LocalPillarError) as exc_info:
        cap.execute({
            "action": "run",
            "values": [1.0, 1.0, 1.0, 1.0],
            "top_k": 1,
            "operation": "identity",
            "maximum_quality_regression": 0.05,
        })
    assert exc_info.value.code == "QUALITY_BUDGET_EXCEEDED"


def test_activation_sparsity_extreme_thresholds_and_all_zero(tmp_path: Path) -> None:
    cap = ActivationSparsityCapability(database_path=tmp_path / "sparse.sqlite3")

    # 1. All zero input with top_k=2
    res_zero = cap.execute({
        "action": "run",
        "values": [0.0, 0.0, 0.0, 0.0],
        "top_k": 2,
        "operation": "identity",
        "maximum_quality_regression": 1.0,
    })
    assert res_zero.data["operations_executed"] == 2
    assert res_zero.data["non_zero"] == 0

    # 2. Extreme high threshold: 0 items selected
    res_high = cap.execute({
        "action": "run",
        "values": [1.0, 2.0, 3.0],
        "threshold": 1000.0,
        "operation": "identity",
        "maximum_quality_regression": 1.0,
    })
    assert res_high.data["operations_executed"] == 0
    assert res_high.data["compute_reduction"] == 1.0
    assert res_high.data["values"] == [0.0, 0.0, 0.0]

    # 3. Zero threshold: all items selected
    res_low = cap.execute({
        "action": "run",
        "values": [1.0, 2.0, 3.0],
        "threshold": 0.0,
        "operation": "identity",
        "maximum_quality_regression": 1.0,
    })
    assert res_low.data["operations_executed"] == 3
    assert res_low.data["compute_reduction"] == 0.0


def test_activation_sparsity_input_validation(tmp_path: Path) -> None:
    cap = ActivationSparsityCapability(database_path=tmp_path / "sparse.sqlite3")

    # NaN rejection
    with pytest.raises(LocalPillarError) as exc_nan:
        cap.execute({"action": "run", "values": [1.0, float("nan"), 3.0], "top_k": 1})
    assert exc_nan.value.code == "INVALID_INPUT"

    # Inf rejection
    with pytest.raises(LocalPillarError) as exc_inf:
        cap.execute({"action": "run", "values": [1.0, float("inf"), 3.0], "top_k": 1})
    assert exc_inf.value.code == "INVALID_INPUT"

    # Empty values list
    with pytest.raises(LocalPillarError) as exc_empty:
        cap.execute({"action": "run", "values": [], "top_k": 1})
    assert exc_empty.value.code == "RESOURCE_LIMIT"

    # Invalid operation
    with pytest.raises(LocalPillarError) as exc_op:
        cap.execute({"action": "run", "values": [1.0, 2.0], "top_k": 1, "operation": "cube"})
    assert exc_op.value.code == "INVALID_INPUT"

    # Out of bounds top_k
    with pytest.raises(LocalPillarError) as exc_k:
        cap.execute({"action": "run", "values": [1.0, 2.0], "top_k": 5})
    assert exc_k.value.code == "INVALID_INPUT"

    # Negative threshold
    with pytest.raises(LocalPillarError) as exc_thresh:
        cap.execute({"action": "run", "values": [1.0, 2.0], "threshold": -0.5})
    assert exc_thresh.value.code == "INVALID_INPUT"


def test_activation_sparsity_wal_persistence_and_receipts(tmp_path: Path) -> None:
    db_path = tmp_path / "sparse.sqlite3"
    cap = ActivationSparsityCapability(database_path=db_path)

    run_res = cap.execute({
        "action": "run",
        "values": [0.5, -4.0, 3.2, -0.1],
        "top_k": 2,
        "operation": "relu",
        "maximum_quality_regression": 1.0,
    })
    run_id = run_res.data["run_id"]
    receipt_id = run_res.data["receipt_id"]

    # Check history
    hist = cap.execute({"action": "history", "limit": 10})
    assert hist.data["count"] == 1
    record = hist.data["records"][0]
    assert record["run_id"] == run_id
    assert record["receipt_id"] == receipt_id
    assert record["operation"] == "relu"
    assert record["selected_count"] == 2
    assert record["compute_reduction"] == 0.5


def test_activation_sparsity_verify_integrity_and_tamper_detection(tmp_path: Path) -> None:
    db_path = tmp_path / "sparse.sqlite3"
    cap = ActivationSparsityCapability(database_path=db_path)

    cap.execute({
        "action": "run",
        "values": [1.0, -2.0, 3.0, 4.0],
        "top_k": 2,
        "operation": "square",
    })

    # Valid check
    int_res = cap.execute({"action": "verify_integrity"})
    assert int_res.data["status"] == "VALID"
    assert int_res.data["receipts_checked"] == 1

    # Tamper with receipt
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE sparsity_receipts SET receipt_digest = '0' * 64")
        conn.commit()

    with pytest.raises(LocalPillarError) as exc_tamper:
        cap.execute({"action": "verify_integrity"})
    assert exc_tamper.value.code == "TAMPERED_RECEIPT"


def test_activation_sparsity_restart_durability(tmp_path: Path) -> None:
    db_path = tmp_path / "durability.sqlite3"
    cap1 = ActivationSparsityCapability(database_path=db_path)

    res = cap1.execute({
        "action": "run",
        "values": [10.0, 20.0, -30.0],
        "top_k": 2,
        "operation": "relu",
    })
    run_id = res.data["run_id"]
    cap1.close()

    # Re-open in fresh instance
    cap2 = ActivationSparsityCapability(database_path=db_path)
    try:
        assert cap2.health_check() is True
        hist = cap2.execute({"action": "history"})
        # 1 from explicit run + 1 from health check = 2
        assert hist.data["count"] >= 1
        runs = [r["run_id"] for r in hist.data["records"]]
        assert run_id in runs
        integrity = cap2.execute({"action": "verify_integrity"})
        assert integrity.data["status"] == "VALID"
    finally:
        cap2.close()
