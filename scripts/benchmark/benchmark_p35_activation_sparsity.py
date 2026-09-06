#!/usr/bin/env python3
"""Benchmark suite for Pillar 35: Activation Sparsity."""

from __future__ import annotations

import argparse
import gc
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
from jaya_core.pillars.activation_sparsity import (  # noqa: E402
    SPARSE_CAPABILITY_ID,
    ActivationSparsityCapability,
)


def run_benchmark(iterations: int = 100) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_p35_"))
    db_path = temp_dir / "sparse_bench.sqlite3"

    cap = ActivationSparsityCapability(database_path=db_path)
    probe = cap.probe_hardware()

    latencies_ms: list[float] = []
    compute_reductions: list[float] = []
    achieved_sparsities: list[float] = []
    regressions: list[float] = []

    process = psutil.Process()
    rss_initial = process.memory_info().rss

    meter = None
    start_sample = None
    try:
        meter = WindowsEmiEnergyMeter()
        start_sample = meter.sample()
        energy_method = "windows_emi"
    except Exception:
        meter = None
        energy_method = "simulated_tdp"

    start_wall = time.perf_counter()
    rng = np.random.default_rng(12345)
    successful = 0
    ops = ["relu", "gelu", "square", "abs", "identity"]

    for i in range(iterations):
        # 50 activation elements per sample
        raw_vals = rng.standard_normal(50).tolist()
        op = ops[i % len(ops)]
        top_k = int(rng.integers(5, 25))  # 10% to 50% density (50% to 90% sparsity)

        t0 = time.perf_counter()
        try:
            res = cap.execute({
                "action": "run",
                "values": raw_vals,
                "top_k": top_k,
                "operation": op,
                "maximum_quality_regression": 1.0,
            })
            dur = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(dur)
            compute_reductions.append(res.data["compute_reduction"])
            achieved_sparsities.append(res.data["achieved_sparsity"])
            regressions.append(res.data["quality_regression"])
            successful += 1
        except Exception:
            dur = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(dur)

    total_bench_duration_s = time.perf_counter() - start_wall

    energy_joules = total_bench_duration_s * 28.0
    if meter is not None and start_sample is not None:
        try:
            end_sample = meter.sample()
            measured = meter.measure(start_sample, end_sample)
            energy_joules = float(measured.joules or (total_bench_duration_s * 28.0))
        except EnergyMeterError:
            pass

    rss_final = process.memory_info().rss
    rss_growth = max(0, rss_final - rss_initial)
    db_bytes = db_path.stat().st_size if db_path.exists() else 0

    results = {
        "pillar_id": 35,
        "capability_id": SPARSE_CAPABILITY_ID,
        "iterations": iterations,
        "successful": successful,
        "completion_rate": round(successful / iterations, 4),
        "hardware_probe": probe,
        "latency_cycle_ms": {
            "mean": round(float(np.mean(latencies_ms)), 3),
            "median": round(float(np.median(latencies_ms)), 3),
            "p95": round(float(np.percentile(latencies_ms, 95)), 3),
            "p99": round(float(np.percentile(latencies_ms, 99)), 3),
            "min": round(float(np.min(latencies_ms)), 3),
            "max": round(float(np.max(latencies_ms)), 3),
        },
        "compute_reduction": {
            "mean": round(float(np.mean(compute_reductions)), 4),
            "median": round(float(np.median(compute_reductions)), 4),
            "min": round(float(np.min(compute_reductions)), 4),
            "max": round(float(np.max(compute_reductions)), 4),
        },
        "achieved_sparsity": {
            "mean": round(float(np.mean(achieved_sparsities)), 4),
            "median": round(float(np.median(achieved_sparsities)), 4),
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

    cap.close()
    del cap
    gc.collect()
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Pillar 35 Activation Sparsity Benchmark Suite")
    parser.add_argument("--iterations", type=int, default=100, help="Number of benchmark iterations (default: 100)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path for benchmark results")
    args = parser.parse_args()

    print(f"Starting Pillar 35 Activation Sparsity benchmark ({args.iterations} iterations)...")
    results = run_benchmark(iterations=args.iterations)

    print("\n" + "=" * 65)
    print("  PILAR 35: ACTIVATION SPARSITY BENCHMARK RESULTS")
    print("=" * 65)
    print(f"  Iterations:          {results['iterations']}")
    print(f"  Completion Rate:     {results['completion_rate'] * 100:.1f}%")
    print(f"  Throughput:          {results['throughput']['cycles_per_sec']} cycles/sec")
    print(f"  Cycle Latency Mean:  {results['latency_cycle_ms']['mean']:.3f} ms")
    print(f"  Cycle Latency p50:   {results['latency_cycle_ms']['median']:.3f} ms")
    print(f"  Cycle Latency p95:   {results['latency_cycle_ms']['p95']:.3f} ms")
    print(f"  Compute Reduction:   {results['compute_reduction']['mean'] * 100:.1f}%")
    print(f"  Achieved Sparsity:   {results['achieved_sparsity']['mean'] * 100:.1f}%")
    print(f"  Regression Mean:     {results['quality_regression']['mean']:.6f}")
    print(f"  RSS Growth:          {results['resource']['rss_growth_bytes'] / (1024 * 1024):.2f} MB")
    print(f"  Energy Consumption:  {results['energy']['total_joules']} J ({results['energy']['joules_per_cycle']} J/cycle, {results['energy']['method']})")
    print("=" * 65)

    out_file = Path(args.output) if args.output else ROOT / "artifacts" / "benchmark_p35_activation_sparsity.json"
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
