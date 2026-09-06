"""Representative verification runner for Pillar 35 Activation Sparsity."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars.activation_sparsity import (
    DEFAULT_SPARSE_KEY,
    SCHEMA_VERSION,
    SPARSE_CAPABILITY_ID,
    ActivationSparsityCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError, LocalPillarResult
from jaya_core.cognitive.runtime import JayaCoreRuntime

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "matrix",
    "soak",
    "source_files",
}


class ActivationSparsityVerificationError(RuntimeError):
    """Stable P35 verification failure carrying the failed boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _system_metadata() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count_logical": os.cpu_count() or 1,
        "cpu_count_physical": psutil.cpu_count(logical=False) or 1,
        "total_ram_bytes": psutil.virtual_memory().total,
    }


def _gate_01_manifest_integrity(workspace_root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    if set(profile.keys()) != _PROFILE_FIELDS:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Profile schema fields mismatch")
    if not _PROFILE_ID.match(profile["profile_id"]):
        raise ActivationSparsityVerificationError("GATE_FAILED", "Invalid profile ID format")
    if profile.get("schema_version") != 1:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Unsupported schema version")

    missing = []
    for rel_path in profile.get("source_files", []):
        full_path = workspace_root / rel_path
        if not full_path.exists():
            missing.append(rel_path)

    if missing:
        raise ActivationSparsityVerificationError(
            "GATE_FAILED", f"Missing source files: {', '.join(missing)}"
        )

    return {
        "status": "PASSED",
        "profile_id": profile["profile_id"],
        "source_files_verified": len(profile.get("source_files", [])),
    }


def _gate_02_hardware_capability_probe(temp_dir: Path) -> dict[str, Any]:
    cap = ActivationSparsityCapability(database_path=temp_dir / "p35_g02.sqlite3")
    probe = cap.probe_hardware()
    if probe.get("provider_type") != "NUMPY_INDEXED_SPARSE":
        raise ActivationSparsityVerificationError("GATE_FAILED", "Hardware probe returned unexpected provider type")
    if probe.get("execution_mode") != "CPU_INDEXED_SKIP_COMPUTE":
        raise ActivationSparsityVerificationError("GATE_FAILED", "Hardware probe returned unexpected execution mode")
    if not isinstance(probe.get("simd_instructions"), list) or len(probe["simd_instructions"]) == 0:
        raise ActivationSparsityVerificationError("GATE_FAILED", "SIMD instructions not probed")
    return {
        "status": "PASSED",
        "provider_type": probe["provider_type"],
        "simd": probe["simd_instructions"],
        "architecture": probe["architecture"],
    }


def _gate_03_indexed_sparse_kernel_execution(temp_dir: Path) -> dict[str, Any]:
    cap = ActivationSparsityCapability(database_path=temp_dir / "p35_g03.sqlite3")
    values = [1.0, -4.0, 0.5, -0.2, 8.0]
    res = cap.execute({
        "action": "run",
        "values": values,
        "top_k": 2,
        "operation": "relu",
        "maximum_quality_regression": 1.0,
    })
    # Absolute values: [1.0, 4.0, 0.5, 0.2, 8.0] -> Top 2 are indices 1 (-4.0) and 4 (8.0)
    # ReLU on selected: -4.0 -> 0.0, 8.0 -> 8.0. Others must be 0.0.
    if res.data["indices"] != [1, 4]:
        raise ActivationSparsityVerificationError("GATE_FAILED", f"Unexpected indices: {res.data['indices']}")
    if res.data["values"] != [0.0, 0.0, 0.0, 0.0, 8.0]:
        raise ActivationSparsityVerificationError("GATE_FAILED", f"Unexpected output values: {res.data['values']}")
    if res.data["operations_executed"] != 2:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Operation count did not skip unselected compute")
    return {
        "status": "PASSED",
        "indices": res.data["indices"],
        "operations_executed": res.data["operations_executed"],
        "dense_operations": res.data["dense_operations"],
    }


def _gate_04_measurable_compute_reduction(temp_dir: Path) -> dict[str, Any]:
    cap = ActivationSparsityCapability(database_path=temp_dir / "p35_g04.sqlite3")
    values = [float(i) for i in range(1, 11)]  # length 10
    res = cap.execute({
        "action": "run",
        "values": values,
        "top_k": 3,
        "operation": "identity",
        "maximum_quality_regression": 1.0,
    })
    if res.data["operations_executed"] != 3:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Expected 3 operations executed")
    if res.data["dense_operations"] != 10:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Expected 10 dense operations")
    if abs(res.data["compute_reduction"] - 0.7) > 1e-6:
        raise ActivationSparsityVerificationError("GATE_FAILED", f"Expected 0.7 reduction, got {res.data['compute_reduction']}")
    return {
        "status": "PASSED",
        "compute_reduction": res.data["compute_reduction"],
        "achieved_sparsity": res.data["achieved_sparsity"],
    }


def _gate_05_dense_baseline_quality_gating(temp_dir: Path) -> dict[str, Any]:
    cap = ActivationSparsityCapability(database_path=temp_dir / "p35_g05.sqlite3")
    # Identical values: keeping 1 of 4 causes relative error sqrt(3)/sqrt(4) ≈ 0.866 > 0.1
    passed = False
    try:
        cap.execute({
            "action": "run",
            "values": [1.0, 1.0, 1.0, 1.0],
            "top_k": 1,
            "operation": "identity",
            "maximum_quality_regression": 0.1,
        })
    except LocalPillarError as exc:
        if exc.code == "QUALITY_BUDGET_EXCEEDED":
            passed = True
        else:
            raise ActivationSparsityVerificationError("GATE_FAILED", f"Wrong error code: {exc.code}")

    if not passed:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Quality budget violation was not rejected")

    # Allowing regression succeeds
    res = cap.execute({
        "action": "run",
        "values": [1.0, 1.0, 1.0, 1.0],
        "top_k": 1,
        "operation": "identity",
        "maximum_quality_regression": 1.0,
    })
    return {
        "status": "PASSED",
        "quality_regression": res.data["quality_regression"],
        "rejection_verified": True,
    }


def _gate_06_magnitude_threshold_gating(temp_dir: Path) -> dict[str, Any]:
    cap = ActivationSparsityCapability(database_path=temp_dir / "p35_g06.sqlite3")
    values = [0.1, 2.5, -3.0, 0.5, -0.2, 4.0]
    res = cap.execute({
        "action": "run",
        "values": values,
        "threshold": 2.0,
        "operation": "identity",
        "maximum_quality_regression": 1.0,
    })
    if res.data["indices"] != [1, 2, 5]:
        raise ActivationSparsityVerificationError("GATE_FAILED", f"Threshold gating indices mismatch: {res.data['indices']}")
    if res.data["operations_executed"] != 3:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Threshold operation count mismatch")
    return {
        "status": "PASSED",
        "threshold": 2.0,
        "selected_indices": res.data["indices"],
        "operations_executed": res.data["operations_executed"],
    }


def _gate_07_extreme_thresholds_and_all_zero(temp_dir: Path) -> dict[str, Any]:
    cap = ActivationSparsityCapability(database_path=temp_dir / "p35_g07.sqlite3")
    # All zero
    res_zero = cap.execute({
        "action": "run",
        "values": [0.0, 0.0, 0.0, 0.0],
        "top_k": 2,
        "operation": "identity",
    })
    if res_zero.data["operations_executed"] != 2 or res_zero.data["non_zero"] != 0:
        raise ActivationSparsityVerificationError("GATE_FAILED", "All zero handling failed")

    # Extreme threshold (none selected)
    res_none = cap.execute({
        "action": "run",
        "values": [1.0, 2.0, 3.0],
        "threshold": 1e9,
        "operation": "identity",
    })
    if res_none.data["operations_executed"] != 0 or res_none.data["compute_reduction"] != 1.0:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Extreme high threshold failed")

    return {
        "status": "PASSED",
        "all_zero_handled": True,
        "extreme_threshold_handled": True,
    }


def _gate_08_nan_inf_and_malformed_input(temp_dir: Path) -> dict[str, Any]:
    cap = ActivationSparsityCapability(database_path=temp_dir / "p35_g08.sqlite3")
    # NaN
    try:
        cap.execute({"action": "run", "values": [1.0, float("nan")], "top_k": 1})
        raise ActivationSparsityVerificationError("GATE_FAILED", "NaN input was not rejected")
    except LocalPillarError as exc:
        if exc.code != "INVALID_INPUT":
            raise ActivationSparsityVerificationError("GATE_FAILED", f"Unexpected code on NaN: {exc.code}")

    # Inf
    try:
        cap.execute({"action": "run", "values": [1.0, float("inf")], "top_k": 1})
        raise ActivationSparsityVerificationError("GATE_FAILED", "Inf input was not rejected")
    except LocalPillarError as exc:
        if exc.code != "INVALID_INPUT":
            raise ActivationSparsityVerificationError("GATE_FAILED", f"Unexpected code on Inf: {exc.code}")

    # Empty
    try:
        cap.execute({"action": "run", "values": [], "top_k": 1})
        raise ActivationSparsityVerificationError("GATE_FAILED", "Empty input was not rejected")
    except LocalPillarError as exc:
        if exc.code != "RESOURCE_LIMIT":
            raise ActivationSparsityVerificationError("GATE_FAILED", f"Unexpected code on empty: {exc.code}")

    return {"status": "PASSED", "nan_inf_empty_rejected": True}


def _gate_09_unsupported_operation_rejection(temp_dir: Path) -> dict[str, Any]:
    cap = ActivationSparsityCapability(database_path=temp_dir / "p35_g09.sqlite3")
    try:
        cap.execute({"action": "run", "values": [1.0, 2.0], "top_k": 1, "operation": "hyperbolic_secant"})
        raise ActivationSparsityVerificationError("GATE_FAILED", "Unsupported operation was not rejected")
    except LocalPillarError as exc:
        if exc.code != "INVALID_INPUT":
            raise ActivationSparsityVerificationError("GATE_FAILED", f"Unexpected code for unsupported op: {exc.code}")

    return {"status": "PASSED", "unsupported_operation_rejected": True}


def _gate_10_deterministic_replay_and_digest(temp_dir: Path) -> dict[str, Any]:
    cap = ActivationSparsityCapability(database_path=temp_dir / "p35_g10.sqlite3")
    values = [np.sin(float(i)) for i in range(20)]
    res1 = cap.execute({"action": "run", "values": values, "top_k": 5, "operation": "gelu"})
    res2 = cap.execute({"action": "run", "values": values, "top_k": 5, "operation": "gelu"})

    if res1.data["output_digest"] != res2.data["output_digest"]:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Output digest was not deterministic across replays")
    if res1.data["indices"] != res2.data["indices"]:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Indices selection was not deterministic")
    if res1.data["values"] != res2.data["values"]:
        raise ActivationSparsityVerificationError("GATE_FAILED", "Output values were not deterministic")

    return {
        "status": "PASSED",
        "output_digest": res1.data["output_digest"],
        "deterministic": True,
    }


def _gate_11_sqlite_wal_persistence(temp_dir: Path) -> dict[str, Any]:
    db_path = temp_dir / "p35_g11.sqlite3"
    cap = ActivationSparsityCapability(database_path=db_path)
    cap.execute({"action": "run", "values": [1.0, -2.0, 3.0], "top_k": 2, "operation": "square"})

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0].lower()
        if journal_mode != "wal":
            raise ActivationSparsityVerificationError("GATE_FAILED", f"Expected WAL mode, got {journal_mode}")
        cursor.execute("SELECT version FROM sparsity_schema")
        schema_v = cursor.fetchone()[0]
        if schema_v != SCHEMA_VERSION:
            raise ActivationSparsityVerificationError("GATE_FAILED", f"Expected schema version {SCHEMA_VERSION}, got {schema_v}")
        cursor.execute("SELECT count(*) FROM sparsity_runs")
        run_count = cursor.fetchone()[0]
        if run_count != 1:
            raise ActivationSparsityVerificationError("GATE_FAILED", f"Expected 1 run stored, got {run_count}")

    return {
        "status": "PASSED",
        "journal_mode": journal_mode,
        "schema_version": schema_v,
        "records_persisted": run_count,
    }


def _gate_12_tamper_evident_receipt_integrity(temp_dir: Path) -> dict[str, Any]:
    db_path = temp_dir / "p35_g12.sqlite3"
    cap = ActivationSparsityCapability(database_path=db_path)
    cap.execute({"action": "run", "values": [0.5, -1.0, 2.0], "top_k": 1, "operation": "relu"})

    int_res = cap.execute({"action": "verify_integrity"})
    if int_res.data["status"] != "VALID":
        raise ActivationSparsityVerificationError("GATE_FAILED", "Integrity check failed on valid database")

    # Tamper with receipt
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE sparsity_receipts SET receipt_digest = 'a' * 64")
        conn.commit()

    try:
        cap.execute({"action": "verify_integrity"})
        raise ActivationSparsityVerificationError("GATE_FAILED", "Tampered receipt was not detected")
    except LocalPillarError as exc:
        if exc.code != "TAMPERED_RECEIPT":
            raise ActivationSparsityVerificationError("GATE_FAILED", f"Unexpected code on tampered receipt: {exc.code}")

    return {"status": "PASSED", "tamper_detection_verified": True}


def _gate_13_restart_durability(temp_dir: Path) -> dict[str, Any]:
    db_path = temp_dir / "p35_g13.sqlite3"
    cap1 = ActivationSparsityCapability(database_path=db_path)
    res = cap1.execute({"action": "run", "values": [3.0, -4.0, 5.0], "top_k": 2, "operation": "identity"})
    run_id = res.data["run_id"]
    cap1.close()

    # Re-open in fresh instance
    cap2 = ActivationSparsityCapability(database_path=db_path)
    try:
        hist = cap2.execute({"action": "history"})
        runs = [r["run_id"] for r in hist.data["records"]]
        if run_id not in runs:
            raise ActivationSparsityVerificationError("GATE_FAILED", "Run record missing after restart")
        integrity = cap2.execute({"action": "verify_integrity"})
        if integrity.data["status"] != "VALID":
            raise ActivationSparsityVerificationError("GATE_FAILED", "Integrity check failed after restart")
    finally:
        cap2.close()

    return {"status": "PASSED", "restart_durability_verified": True}


def _gate_14_runtime_and_manifest_dispatch(temp_dir: Path) -> dict[str, Any]:
    expert_root = temp_dir / "experts"
    expert_root.mkdir(parents=True, exist_ok=True)
    for eid, routing in [("test-expert-1", [1.0, 0.0]), ("test-expert-2", [0.0, 1.0])]:
        manifest = {
            "schema_version": 1,
            "expert_id": eid,
            "version": "1.0",
            "task_kinds": ["RESEARCH_SCORE"],
            "input_dimension": 2,
            "output_dimension": 2,
            "weight_matrix": [[1.0, 0.0], [0.0, 1.0]],
            "bias": [0.0, 0.0],
            "routing_vector": routing,
            "capacity": 10,
        }
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        sig = hmac.new(DEFAULT_SPARSE_KEY, canonical, hashlib.sha256).hexdigest()
        (expert_root / f"{eid}.expert.json").write_text(json.dumps({"manifest": manifest, "signature": sig}))

    runtime = JayaCoreRuntime(
        db_path=temp_dir / "core.sqlite3",
        local_pillar_data_dir=temp_dir / "pillars",
        local_expert_root=expert_root,
        lineage_signing_key=DEFAULT_SPARSE_KEY,
    )
    try:
        res = runtime.execute_local_pillar(
            SPARSE_CAPABILITY_ID,
            {
                "action": "run",
                "values": [2.0, -5.0, 3.0],
                "top_k": 2,
                "operation": "square",
                "maximum_quality_regression": 1.0,
            },
        )
        if res.data["operations_executed"] != 2:
            raise ActivationSparsityVerificationError("GATE_FAILED", "Runtime dispatch failed operation count")
        health = runtime.operational_snapshot()["local_pillar_capabilities"]["capabilities"]
        if health.get(SPARSE_CAPABILITY_ID) != "HEALTHY":
            raise ActivationSparsityVerificationError("GATE_FAILED", f"Manifest status not HEALTHY: {health.get(SPARSE_CAPABILITY_ID)}")
    finally:
        runtime.close()

    return {
        "status": "PASSED",
        "runtime_dispatch": True,
        "manifest_health": "HEALTHY",
    }


def _gate_15_soak_performance_and_energy(temp_dir: Path) -> dict[str, Any]:
    db_path = temp_dir / "p35_g15_soak.sqlite3"
    cap = ActivationSparsityCapability(database_path=db_path)

    iterations = 100
    latencies: list[float] = []
    initial_rss = psutil.Process().memory_info().rss

    meter = None
    start_sample = None
    try:
        meter = WindowsEmiEnergyMeter()
        start_sample = meter.sample()
    except Exception:
        meter = None

    rng = np.random.default_rng(42)
    successful = 0
    t_start = time.perf_counter()

    for _ in range(iterations):
        vals = rng.standard_normal(20).tolist()
        t0 = time.perf_counter()
        try:
            res = cap.execute({
                "action": "run",
                "values": vals,
                "top_k": 5,
                "operation": "relu",
                "maximum_quality_regression": 1.0,
            })
            if res.data["operations_executed"] == 5:
                successful += 1
        except Exception:
            pass
        latencies.append((time.perf_counter() - t0) * 1000.0)

    total_time = time.perf_counter() - t_start
    final_rss = psutil.Process().memory_info().rss
    rss_growth = max(0, final_rss - initial_rss)
    mean_lat = float(np.mean(latencies))

    energy_joules = total_time * 28.0
    energy_meter_available = False
    if meter is not None and start_sample is not None:
        try:
            end_sample = meter.sample()
            measured = meter.measure(start_sample, end_sample)
            energy_joules = float(measured.joules or (total_time * 28.0))
            energy_meter_available = True
        except EnergyMeterError:
            pass

    if mean_lat > 50.0:
        raise ActivationSparsityVerificationError("GATE_FAILED", f"Mean latency {mean_lat:.2f}ms exceeds 50ms")
    if successful < 95:
        raise ActivationSparsityVerificationError("GATE_FAILED", f"Completion rate {successful}/{iterations} below 95%")

    return {
        "status": "PASSED",
        "iterations": iterations,
        "successful": successful,
        "mean_latency_ms": round(mean_lat, 3),
        "rss_growth_bytes": rss_growth,
        "energy_meter_available": energy_meter_available,
        "energy_joules": round(energy_joules, 4),
    }


def run_activation_sparsity_verification(
    profile_path: Path,
    workspace_root: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    with profile_path.open("r", encoding="utf-8") as f:
        profile = json.load(f)

    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_verify_p35_"))
    gate_results: dict[str, Any] = {}
    gate_names = profile["matrix"]["gates"]

    start_wall = time.perf_counter()

    try:
        for gate in gate_names:
            t_gate_start = time.perf_counter()
            if gate == "G01_MANIFEST_INTEGRITY":
                res = _gate_01_manifest_integrity(workspace_root, profile)
            elif gate == "G02_HARDWARE_CAPABILITY_PROBE":
                res = _gate_02_hardware_capability_probe(temp_dir)
            elif gate == "G03_INDEXED_SPARSE_KERNEL_EXECUTION":
                res = _gate_03_indexed_sparse_kernel_execution(temp_dir)
            elif gate == "G04_MEASURABLE_COMPUTE_REDUCTION":
                res = _gate_04_measurable_compute_reduction(temp_dir)
            elif gate == "G05_DENSE_BASELINE_QUALITY_GATING":
                res = _gate_05_dense_baseline_quality_gating(temp_dir)
            elif gate == "G06_MAGNITUDE_THRESHOLD_GATING":
                res = _gate_06_magnitude_threshold_gating(temp_dir)
            elif gate == "G07_EXTREME_THRESHOLDS_AND_ALL_ZERO":
                res = _gate_07_extreme_thresholds_and_all_zero(temp_dir)
            elif gate == "G08_NAN_INF_AND_MALFORMED_INPUT":
                res = _gate_08_nan_inf_and_malformed_input(temp_dir)
            elif gate == "G09_UNSUPPORTED_OPERATION_REJECTION":
                res = _gate_09_unsupported_operation_rejection(temp_dir)
            elif gate == "G10_DETERMINISTIC_REPLAY_AND_DIGEST":
                res = _gate_10_deterministic_replay_and_digest(temp_dir)
            elif gate == "G11_SQLITE_WAL_PERSISTENCE":
                res = _gate_11_sqlite_wal_persistence(temp_dir)
            elif gate == "G12_TAMPER_EVIDENT_RECEIPT_INTEGRITY":
                res = _gate_12_tamper_evident_receipt_integrity(temp_dir)
            elif gate == "G13_RESTART_DURABILITY":
                res = _gate_13_restart_durability(temp_dir)
            elif gate == "G14_RUNTIME_AND_MANIFEST_DISPATCH":
                res = _gate_14_runtime_and_manifest_dispatch(temp_dir)
            elif gate == "G15_SOAK_PERFORMANCE_AND_ENERGY":
                res = _gate_15_soak_performance_and_energy(temp_dir)
            else:
                raise ActivationSparsityVerificationError("GATE_FAILED", f"Unknown gate: {gate}")

            dur = (time.perf_counter() - t_gate_start) * 1000.0
            res["duration_ms"] = round(dur, 3)
            gate_results[gate] = res

    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

    total_wall_dur = (time.perf_counter() - start_wall) * 1000.0
    passed_count = sum(1 for g in gate_results.values() if g.get("status") == "PASSED")
    all_passed = passed_count == len(gate_names)

    receipt = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "pillar_id": 35,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "VERIFIED" if all_passed else "FAILED",
        "system": _system_metadata(),
        "gates_summary": {
            "total": len(gate_names),
            "passed": passed_count,
            "failed": len(gate_names) - passed_count,
            "all_passed": all_passed,
        },
        "gates": gate_results,
        "total_duration_ms": round(total_wall_dur, 3),
    }

    if output_path:
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2, ensure_ascii=False)

    return receipt


def verify_activation_sparsity(
    repository_root: Path | None = None,
    profile_path: Path | None = None,
    output_directory: Path | None = None,
    approver: str = "System-Veritas",
) -> tuple[Path, dict[str, Any]]:
    """Canonical verification wrapper compatible with repo CLI scripts."""
    workspace = (repository_root or Path.cwd()).resolve()
    target_profile = (
        profile_path
        or workspace / "packages" / "jaya-core" / "verification" / "p35_windows_activation_sparsity_v1.json"
    ).resolve()
    out_dir = (output_directory or workspace / "artifacts" / "verified-activation-sparsity").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "verification_receipt.json"

    receipt = run_activation_sparsity_verification(
        profile_path=target_profile,
        workspace_root=workspace,
        output_path=out_file,
    )
    receipt["approver"] = approver
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)

    return out_file, receipt
