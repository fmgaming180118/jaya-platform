#!/usr/bin/env python3
"""Dedicated benchmark suite for Pillar 28 Self Bootstrapping."""

from __future__ import annotations

import hmac
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.maintenance_capabilities import SelfBootstrappingCapability

SIGNING_KEY = bytes(range(32))


def _sign(key: bytes, material: bytes) -> str:
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def run_benchmark(iterations: int = 500) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_bootstrap_"))
    bootstrap_root = temp_dir / "bootstrap"
    bootstrap_root.mkdir(parents=True, exist_ok=True)
    db_path = bootstrap_root / "bootstrap.sqlite3"
    rag_db = temp_dir / "rag.sqlite3"

    rag = AgenticRAGCapability(rag_db, None)
    rag.execute({
        "action": "ingest",
        "source_ref": "bench:source",
        "title": "Benchmark evidence",
        "content": "Evidence for benchmark aggregation capabilities.",
    })
    evidence_id = rag.retrieve("Benchmark evidence", 1)[0]["evidence_id"]

    # Cold boot measurement
    t_cold_start = time.perf_counter()
    service = SelfBootstrappingCapability(bootstrap_root, db_path, SIGNING_KEY, rag)
    service.health_check()
    cold_boot_ms = (time.perf_counter() - t_cold_start) * 1000.0

    # Warm boot measurement
    t_warm_start = time.perf_counter()
    service.health_check()
    warm_boot_ms = (time.perf_counter() - t_warm_start) * 1000.0

    proc = psutil.Process()
    rss_start = proc.memory_info().rss

    energy_meter = WindowsEmiEnergyMeter()
    energy_start = None
    try:
        energy_start = energy_meter.sample()
    except EnergyMeterError:
        energy_start = None

    # 1. Propose & Validate Benchmark
    propose_latencies = []
    validate_latencies = []
    t_prop_start = time.perf_counter()
    for i in range(min(iterations, 200)):
        cid = f"cand-{i:04d}"
        t0 = time.perf_counter()
        prop = service.propose({
            "action": "propose",
            "candidate_id": cid,
            "capability_id": f"math.calc.{i}",
            "capability_gap": f"Gap observation {i}",
            "operation": "mean",
            "evidence_ids": [evidence_id],
            "acceptance_cases": [
                {"values": [1.0, 2.0, 3.0], "expected": 2.0},
                {"values": [10.0, 20.0], "expected": 15.0},
            ],
        })
        propose_latencies.append((time.perf_counter() - t0) * 1000.0)

        t1 = time.perf_counter()
        val = service.validate({"action": "validate", "candidate_id": cid})
        validate_latencies.append((time.perf_counter() - t1) * 1000.0)

    t_prop_elapsed = time.perf_counter() - t_prop_start

    # 2. Dependency Planning Benchmark
    dep_latencies = []
    t_dep_start = time.perf_counter()
    for i in range(min(iterations, 200)):
        t0 = time.perf_counter()
        service.plan_dependencies({
            "action": "plan_dependencies",
            "candidate_id": f"cand-{i:04d}",
            "dependencies": [
                {"capability_id": "core.base", "depends_on": []},
                {"capability_id": "pkg.parser", "depends_on": ["core.base"]},
                {"capability_id": "pkg.aggregator", "depends_on": ["pkg.parser"]},
            ],
        })
        dep_latencies.append((time.perf_counter() - t0) * 1000.0)
    t_dep_elapsed = time.perf_counter() - t_dep_start

    # 3. Staging and Installation Benchmark
    stage_latencies = []
    install_latencies = []
    t_inst_start = time.perf_counter()
    for i in range(min(iterations, 100)):
        cid = f"cand-{i:04d}"
        t0 = time.perf_counter()
        service.stage({"action": "stage", "candidate_id": cid})
        stage_latencies.append((time.perf_counter() - t0) * 1000.0)

        row = service.inspect_candidate({"action": "inspect", "candidate_id": cid}).data
        mat = f"install|{cid}|{row['artifact_digest']}|{row['validation_digest']}|app-{i}|admin".encode()
        sig = _sign(SIGNING_KEY, mat)

        t1 = time.perf_counter()
        service.install({
            "action": "install",
            "candidate_id": cid,
            "approval_id": f"app-{i}",
            "approved_by": "admin",
            "signature": sig,
        })
        install_latencies.append((time.perf_counter() - t1) * 1000.0)
    t_inst_elapsed = time.perf_counter() - t_inst_start

    # 4. Invocation Benchmark (Fast Path)
    invoke_latencies = []
    t_inv_start = time.perf_counter()
    sample_values = [float(j) for j in range(100)]
    for i in range(iterations):
        target_cid = f"cand-{i % 100:04d}"
        t0 = time.perf_counter()
        service.invoke({
            "action": "invoke",
            "candidate_id": target_cid,
            "values": sample_values,
        })
        invoke_latencies.append((time.perf_counter() - t0) * 1000.0)
    t_inv_elapsed = time.perf_counter() - t_inv_start

    # 5. Rollback Benchmark
    rollback_latencies = []
    t_rb_start = time.perf_counter()
    for i in range(min(iterations // 10, 20)):
        cid = f"cand-{i:04d}"
        row = service.inspect_candidate({"action": "inspect", "candidate_id": cid}).data
        mat = f"rollback_bootstrap|{cid}|{row['artifact_digest']}|rb-{i}|admin".encode()
        sig = _sign(SIGNING_KEY, mat)

        t0 = time.perf_counter()
        service.rollback({
            "action": "rollback",
            "candidate_id": cid,
            "rollback_id": f"rb-{i}",
            "approved_by": "admin",
            "signature": sig,
        })
        rollback_latencies.append((time.perf_counter() - t0) * 1000.0)
    t_rb_elapsed = time.perf_counter() - t_rb_start

    metrics_result = service.metrics().data

    # Resources
    rss_end = proc.memory_info().rss
    rss_growth = max(0, rss_end - rss_start)
    db_size = db_path.stat().st_size
    bytes_per_record = db_size / iterations if iterations > 0 else 0.0

    package_joules = 0.0
    if energy_start is not None:
        try:
            energy_end = energy_meter.sample()
            measured = energy_meter.measure(energy_start, energy_end)
            if measured.joules is not None:
                package_joules = measured.joules
        except EnergyMeterError:
            package_joules = 0.0001

    shutil.rmtree(temp_dir, ignore_errors=True)

    results = {
        "pillar": "P028",
        "name": "Self Bootstrapping",
        "iterations": iterations,
        "boot_latency_ms": {
            "cold_boot_ms": round(cold_boot_ms, 4),
            "warm_boot_ms": round(warm_boot_ms, 4),
        },
        "propose": {
            "elapsed_seconds": round(t_prop_elapsed, 4),
            "throughput_ops_sec": round(len(propose_latencies) / t_prop_elapsed, 2),
            "mean_ms": round(float(np.mean(propose_latencies)), 4),
            "p50_ms": round(float(np.percentile(propose_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(propose_latencies, 95)), 4),
            "p99_ms": round(float(np.percentile(propose_latencies, 99)), 4),
        },
        "validate": {
            "mean_ms": round(float(np.mean(validate_latencies)), 4),
            "p50_ms": round(float(np.percentile(validate_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(validate_latencies, 95)), 4),
            "p99_ms": round(float(np.percentile(validate_latencies, 99)), 4),
        },
        "dependency_planning": {
            "elapsed_seconds": round(t_dep_elapsed, 4),
            "throughput_ops_sec": round(len(dep_latencies) / t_dep_elapsed, 2),
            "mean_ms": round(float(np.mean(dep_latencies)), 4),
            "p50_ms": round(float(np.percentile(dep_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(dep_latencies, 95)), 4),
        },
        "stage": {
            "mean_ms": round(float(np.mean(stage_latencies)), 4),
            "p50_ms": round(float(np.percentile(stage_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(stage_latencies, 95)), 4),
        },
        "install": {
            "elapsed_seconds": round(t_inst_elapsed, 4),
            "throughput_ops_sec": round(len(install_latencies) / t_inst_elapsed, 2),
            "mean_ms": round(float(np.mean(install_latencies)), 4),
            "p50_ms": round(float(np.percentile(install_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(install_latencies, 95)), 4),
        },
        "invoke": {
            "elapsed_seconds": round(t_inv_elapsed, 4),
            "throughput_ops_sec": round(iterations / t_inv_elapsed, 2),
            "mean_ms": round(float(np.mean(invoke_latencies)), 4),
            "p50_ms": round(float(np.percentile(invoke_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(invoke_latencies, 95)), 4),
            "p99_ms": round(float(np.percentile(invoke_latencies, 99)), 4),
        },
        "rollback": {
            "elapsed_seconds": round(t_rb_elapsed, 4),
            "throughput_ops_sec": round(len(rollback_latencies) / t_rb_elapsed, 2),
            "mean_ms": round(float(np.mean(rollback_latencies)), 4),
            "p50_ms": round(float(np.percentile(rollback_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(rollback_latencies, 95)), 4),
        },
        "catalog_metrics": metrics_result,
        "resources": {
            "rss_growth_bytes": rss_growth,
            "database_bytes_total": db_size,
            "database_bytes_per_record": round(bytes_per_record, 2),
            "package_joules_total": round(package_joules, 4),
            "package_joules_per_record": round(package_joules / iterations if iterations > 0 else 0.0, 6),
        },
    }
    return results


def main() -> int:
    print("=" * 75)
    print(" JAYA ARCHITECTURE — PILAR 28: SELF BOOTSTRAPPING BENCHMARK")
    print("=" * 75)
    results = run_benchmark(iterations=500)
    print(json.dumps(results, indent=2))

    out_path = ROOT / "artifacts" / "benchmark_p28_self_bootstrapping.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nArtifact saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
