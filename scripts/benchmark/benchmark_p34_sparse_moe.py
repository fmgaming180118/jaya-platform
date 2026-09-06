#!/usr/bin/env python3
"""Benchmark suite for Pillar 34: Dynamic Sparsity MoE."""

from __future__ import annotations

import argparse
import gc
import hashlib
import hmac
import json
import os
import shutil
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

from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter  # noqa: E402
from jaya_core.pillars.moe_capability import (  # noqa: E402
    MOE_CAPABILITY_ID,
    DynamicSparsityMoECapability,
)

BENCH_SIGNING_KEY = b"benchmark-sparse-moe-signing-key-32b!"


def _write_bench_expert(
    root: Path,
    expert_id: str,
    *,
    weights: list[list[float]],
    bias: list[float],
    routing: list[float],
    capacity: int = 50,
) -> Path:
    manifest = {
        "schema_version": 1,
        "expert_id": expert_id,
        "version": "1.0",
        "task_kinds": ["RESEARCH_SCORE"],
        "input_dimension": len(routing),
        "output_dimension": len(bias),
        "weight_matrix": weights,
        "bias": bias,
        "routing_vector": routing,
        "capacity": capacity,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(BENCH_SIGNING_KEY, canonical, hashlib.sha256).hexdigest()
    wrapper = {"manifest": manifest, "signature": sig}

    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{expert_id}.expert.json"
    target.write_text(json.dumps(wrapper, indent=2), encoding="utf-8")
    return target


def run_benchmark(iterations: int = 100) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_p34_"))
    expert_root = temp_dir / "experts"
    db_path = temp_dir / "moe_bench.sqlite3"

    # Setup 4 distinct benchmark experts
    _write_bench_expert(
        expert_root,
        "bench-expert-0",
        weights=[[1.5, 0.1, 0.0, 0.0], [0.0, 1.2, -0.1, 0.1]],
        bias=[0.1, -0.1],
        routing=[1.0, 0.1, 0.0, 0.0],
        capacity=50,
    )
    _write_bench_expert(
        expert_root,
        "bench-expert-1",
        weights=[[0.2, 1.4, 0.1, 0.0], [0.1, 1.0, 0.2, 0.0]],
        bias=[0.0, 0.2],
        routing=[0.1, 1.0, 0.1, 0.0],
        capacity=50,
    )
    _write_bench_expert(
        expert_root,
        "bench-expert-2",
        weights=[[0.1, 0.2, 1.6, 0.1], [0.3, 0.1, 0.9, 0.2]],
        bias=[-0.1, 0.0],
        routing=[0.0, 0.1, 1.0, 0.1],
        capacity=50,
    )
    _write_bench_expert(
        expert_root,
        "bench-expert-3",
        weights=[[0.0, 0.1, 0.2, 1.5], [0.1, 0.0, 0.3, 1.1]],
        bias=[0.0, 0.1],
        routing=[0.0, 0.0, 0.1, 1.0],
        capacity=50,
    )

    # Cold boot measurement
    t_cold_start = time.perf_counter()
    moe = DynamicSparsityMoECapability(
        expert_root=expert_root, database_path=db_path, signing_key=BENCH_SIGNING_KEY
    )
    cold_boot_ms = (time.perf_counter() - t_cold_start) * 1000.0

    # Warm boot measurement
    t_warm_start = time.perf_counter()
    moe.health_check()
    warm_boot_ms = (time.perf_counter() - t_warm_start) * 1000.0

    proc = psutil.Process()
    rss_initial = proc.memory_info().rss

    meter: WindowsEmiEnergyMeter | None = None
    start_sample = None
    try:
        meter = WindowsEmiEnergyMeter()
        start_sample = meter.sample()
    except Exception:
        meter = None

    cycle_latencies_ms: list[float] = []
    regressions: list[float] = []

    t_bench_start = time.perf_counter()

    for idx in range(iterations):
        cycle_start = time.perf_counter()

        # Dynamic vector cycling through domain emphases
        vec = [
            float((idx * 3 + 1) % 10) / 10.0,
            float((idx * 5 + 2) % 10) / 10.0,
            float((idx * 7 + 3) % 10) / 10.0,
            float((idx * 11 + 4) % 10) / 10.0,
        ]

        # Trigger occasional capacity load to test overflow handling
        if (idx + 1) % 10 == 0:
            moe.set_expert_load("bench-expert-0", 100)
        else:
            moe.set_expert_load("bench-expert-0", 0)

        res = moe.execute(
            {
                "action": "run",
                "task_kind": "RESEARCH_SCORE",
                "vector": vec,
                "top_k": 2,
                "maximum_quality_regression": 1.0,
                "temperature": 0.8,
            }
        )
        regressions.append(res.data["quality_regression"])
        cycle_latencies_ms.append((time.perf_counter() - cycle_start) * 1000.0)

    total_bench_duration_s = time.perf_counter() - t_bench_start
    rss_final = proc.memory_info().rss
    rss_growth = max(0, rss_final - rss_initial)

    energy_joules = 0.0
    energy_method = "ESTIMATED_TDP"
    if meter is not None and start_sample is not None:
        try:
            end_sample = meter.sample()
            measured = meter.measure(start_sample, end_sample)
            energy_joules = float(measured.joules or (total_bench_duration_s * 28.0))
            energy_method = "WINDOWS_EMI"
        except EnergyMeterError:
            energy_joules = round(total_bench_duration_s * 28.0, 4)
    else:
        energy_joules = round(total_bench_duration_s * 28.0, 4)

    db_bytes = db_path.stat().st_size if db_path.is_file() else 0

    results: dict[str, Any] = {
        "benchmark_profile": "P34_WINDOWS_DYNAMIC_SPARSITY_MOE",
        "iterations": iterations,
        "completed_cycles": iterations,
        "completion_rate": 1.0,
        "startup": {
            "cold_boot_ms": round(cold_boot_ms, 3),
            "warm_boot_ms": round(warm_boot_ms, 3),
        },
        "latency_cycle_ms": {
            "mean": round(float(np.mean(cycle_latencies_ms)), 3),
            "median": round(float(np.median(cycle_latencies_ms)), 3),
            "p90": round(float(np.percentile(cycle_latencies_ms, 90)), 3),
            "p95": round(float(np.percentile(cycle_latencies_ms, 95)), 3),
            "p99": round(float(np.percentile(cycle_latencies_ms, 99)), 3),
            "min": round(float(np.min(cycle_latencies_ms)), 3),
            "max": round(float(np.max(cycle_latencies_ms)), 3),
        },
        "quality_regression": {
            "mean": round(float(np.mean(regressions)), 6),
            "median": round(float(np.median(regressions)), 6),
            "min": round(float(np.min(regressions)), 6),
            "max": round(float(np.max(regressions)), 6),
        },
        "throughput": {
            "cycles_per_sec": round(iterations / total_bench_duration_s, 2),
            "total_duration_seconds": round(total_bench_duration_s, 3),
        },
        "resource": {
            "initial_rss_bytes": rss_initial,
            "final_rss_bytes": rss_final,
            "rss_growth_bytes": rss_growth,
            "database_size_bytes": db_bytes,
            "database_bytes_per_cycle": round(db_bytes / max(1, iterations), 2),
        },
        "energy": {
            "total_joules": round(energy_joules, 4),
            "joules_per_cycle": round(energy_joules / max(1, iterations), 6),
            "method": energy_method,
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    del moe
    gc.collect()
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Pillar 34 Dynamic Sparsity MoE Benchmark Suite")
    parser.add_argument("--iterations", type=int, default=100, help="Number of benchmark iterations (default: 100)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path for benchmark results")
    args = parser.parse_args()

    print(f"Starting Pillar 34 Dynamic Sparsity MoE benchmark ({args.iterations} iterations)...")
    results = run_benchmark(iterations=args.iterations)

    print("\n" + "=" * 65)
    print("  PILAR 34: DYNAMIC SPARSITY MOE BENCHMARK RESULTS")
    print("=" * 65)
    print(f"  Iterations:          {results['iterations']}")
    print(f"  Completion Rate:     {results['completion_rate'] * 100:.1f}%")
    print(f"  Throughput:          {results['throughput']['cycles_per_sec']} cycles/sec")
    print(f"  Cycle Latency Mean:  {results['latency_cycle_ms']['mean']:.3f} ms")
    print(f"  Cycle Latency p50:   {results['latency_cycle_ms']['median']:.3f} ms")
    print(f"  Cycle Latency p95:   {results['latency_cycle_ms']['p95']:.3f} ms")
    print(f"  Regression Mean:     {results['quality_regression']['mean']:.6f}")
    print(f"  RSS Growth:          {results['resource']['rss_growth_bytes'] / (1024 * 1024):.2f} MB")
    print(f"  Energy Consumption:  {results['energy']['total_joules']} J ({results['energy']['joules_per_cycle']} J/cycle, {results['energy']['method']})")
    print("=" * 65)

    out_file = Path(args.output) if args.output else ROOT / "artifacts" / "benchmark_p34_sparse_moe.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to: {out_file}")

    scratch_out = Path("outputs") / f"{Path(__file__).stem}.json"
    scratch_out.parent.mkdir(parents=True, exist_ok=True)
    with scratch_out.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
