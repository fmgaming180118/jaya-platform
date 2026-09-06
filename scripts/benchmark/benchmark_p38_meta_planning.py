#!/usr/bin/env python3
"""Benchmark suite for Pillar 38: Meta Cognitive Planning."""

from __future__ import annotations

import argparse
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
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability  # noqa: E402
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability  # noqa: E402
from jaya_core.pillars.reasoning_capabilities import (  # noqa: E402
    MetaPlanningCapability,
    SpeculativeReasoningCapability,
)


def run_benchmark(iterations: int = 100) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_p38_"))
    db_path = temp_dir / "meta_planning_bench.sqlite3"
    spec_db_path = temp_dir / "speculative_bench.sqlite3"
    rag_db_path = temp_dir / "rag_bench.sqlite3"

    rag = AgenticRAGCapability(rag_db_path, None)
    rag.ingest({
        "action": "ingest",
        "source_ref": "ref_quantum_cooling_bench",
        "title": "Cryogenic Bench Reference",
        "content": "Cryogenic bench reference cryocooler power output maintains 4.2 Kelvin at 1.5 Watts electrical load.",
    })
    rag.ingest({
        "action": "ingest",
        "source_ref": "ref_solid_state_bench",
        "title": "Solid State Bench Reference",
        "content": "Solid state bench reference thermoelectric Peltier cascades provide thermal dissipation.",
    })

    sandbox = SandboxedImaginationCapability()
    speculative = SpeculativeReasoningCapability(spec_db_path, rag, sandbox)

    # Cold boot measurement
    t_cold_start = time.perf_counter()
    planner = MetaPlanningCapability(db_path, rag, sandbox, speculative)
    cold_boot_ms = (time.perf_counter() - t_cold_start) * 1000.0

    # Warm boot measurement
    t_warm_start = time.perf_counter()
    planner.health_check()
    warm_boot_ms = (time.perf_counter() - t_warm_start) * 1000.0

    meter = None
    start_sample = None
    if sys.platform.startswith("win"):
        try:
            meter = WindowsEmiEnergyMeter()
            start_sample = meter.sample()
        except EnergyMeterError:
            meter = None
            start_sample = None

    proc = psutil.Process(os.getpid())
    rss_initial = proc.memory_info().rss

    # 1. Multi-Step Execution Benchmark
    latencies_ms: list[float] = []
    recovery_latencies_ms: list[float] = []
    completed_count = 0
    recoveries_count = 0

    t_bench_start = time.perf_counter()
    for idx in range(iterations):
        # 80% nominal plans, 20% plans requiring recovery/replan
        with_recovery = (idx % 5 == 0)
        t_start = time.perf_counter()
        if with_recovery:
            res = planner.run({
                "action": "run",
                "request_id": f"bench-p38-{idx}",
                "goal": f"Benchmark plan with recovery iteration {idx}",
                "invariants": ["100 <= 200"],
                "allow_dynamic_replan": True,
                "max_replans": 2,
                "steps": [
                    {"type": "sandbox", "expression": f"{idx} * 3 == {idx * 3}"},
                    {"type": "retrieve", "query": "absent_document_query_trigger_recovery", "minimum_results": 5},
                    {"type": "sandbox", "expression": "100 <= 200"},
                ],
                "dynamic_replan_steps": [
                    {"type": "retrieve", "query": "Cryogenic Bench Reference", "minimum_results": 1}
                ],
            })
            dur = (time.perf_counter() - t_start) * 1000.0
            recovery_latencies_ms.append(dur)
        else:
            res = planner.run({
                "action": "run",
                "request_id": f"bench-p38-{idx}",
                "goal": f"Benchmark nominal plan iteration {idx}",
                "invariants": ["100 <= 200"],
                "steps": [
                    {"type": "sandbox", "expression": f"{idx} * 3 == {idx * 3}"},
                    {"type": "retrieve", "query": "Cryogenic Bench Reference", "minimum_results": 1},
                    {"type": "sandbox", "expression": "100 <= 200"},
                ],
            })
            dur = (time.perf_counter() - t_start) * 1000.0

        latencies_ms.append(dur)
        if res.data["status"] == "COMPLETED":
            completed_count += 1
        if res.data.get("recoveries", 0) > 0:
            recoveries_count += 1

    total_bench_duration_s = time.perf_counter() - t_bench_start
    rss_final = proc.memory_info().rss
    rss_growth = max(0, rss_final - rss_initial)

    energy_joules = 0.0
    energy_method = "SOFTWARE_FALLBACK"
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
        "benchmark_profile": "P38_WINDOWS_META_COGNITIVE_PLANNING",
        "iterations": iterations,
        "cold_boot_ms": round(cold_boot_ms, 3),
        "warm_boot_ms": round(warm_boot_ms, 3),
        "total_duration_seconds": round(total_bench_duration_s, 3),
        "throughput_plans_per_sec": round(iterations / max(0.001, total_bench_duration_s), 2),
        "completion_rate": round(completed_count / iterations, 4),
        "recoveries_total": recoveries_count,
        "latency_ms": {
            "mean": round(float(np.mean(latencies_ms)), 3),
            "std": round(float(np.std(latencies_ms)), 3),
            "p50": round(float(np.percentile(latencies_ms, 50)), 3),
            "p95": round(float(np.percentile(latencies_ms, 95)), 3),
            "p99": round(float(np.percentile(latencies_ms, 99)), 3),
            "min": round(float(np.min(latencies_ms)), 3),
            "max": round(float(np.max(latencies_ms)), 3),
        },
        "recovery_latency_ms": {
            "mean": round(float(np.mean(recovery_latencies_ms)), 3) if recovery_latencies_ms else 0.0,
            "p95": round(float(np.percentile(recovery_latencies_ms, 95)), 3) if recovery_latencies_ms else 0.0,
            "count": len(recovery_latencies_ms),
        },
        "resource_footprint": {
            "initial_rss_bytes": rss_initial,
            "final_rss_bytes": rss_final,
            "rss_growth_bytes": rss_growth,
            "rss_growth_mb": round(rss_growth / (1024 * 1024), 2),
            "database_size_bytes": db_bytes,
            "database_bytes_per_plan": round(db_bytes / max(1, iterations), 2),
        },
        "energy_consumption": {
            "total_joules": round(energy_joules, 4),
            "joules_per_plan": round(energy_joules / max(1, iterations), 5),
            "measurement_method": energy_method,
        },
    }

    planner.close()
    speculative.close()
    rag.close()
    shutil.rmtree(temp_dir, ignore_errors=True)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=100, help="Number of benchmark iterations")
    parser.add_argument(
        "--output",
        default=str(ROOT / "artifacts" / "benchmark_p38_meta_planning.json"),
        help="Path to save benchmark JSON output",
    )
    args = parser.parse_args()

    print(f"Running P38 Meta Cognitive Planning benchmark ({args.iterations} iterations)...")
    res = run_benchmark(args.iterations)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("  PILAR 38: META COGNITIVE PLANNING BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Iterations:            {res['iterations']}")
    print(f"  Throughput:            {res['throughput_plans_per_sec']} plans/sec")
    print(f"  Completion Rate:       {res['completion_rate'] * 100:.1f}%")
    print(f"  Recoveries Executed:   {res['recoveries_total']}")
    print(f"  Mean Latency:          {res['latency_ms']['mean']} ms")
    print(f"  P95 Latency:           {res['latency_ms']['p95']} ms")
    print(f"  Recovery Mean Latency: {res['recovery_latency_ms']['mean']} ms")
    print(f"  Cold Boot Time:        {res['cold_boot_ms']} ms")
    print(f"  RSS Memory Growth:     {res['resource_footprint']['rss_growth_mb']} MB")
    print(f"  DB Bytes / Plan:       {res['resource_footprint']['database_bytes_per_plan']} bytes")
    print(f"  Energy Total:          {res['energy_consumption']['total_joules']} J ({res['energy_consumption']['measurement_method']})")
    print(f"  Energy / Plan:         {res['energy_consumption']['joules_per_plan']} J")
    print(f"  Saved report to:       {out_path}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
