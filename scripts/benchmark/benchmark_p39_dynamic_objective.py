#!/usr/bin/env python3
"""Benchmark suite for Pillar 39: Dynamic Objective."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
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
from jaya_core.pillars.control_capabilities import (  # noqa: E402
    OBJECTIVE_CAPABILITY_ID,
    DynamicObjectiveCapability,
)
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability  # noqa: E402
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402
from jaya_core.pillars.reasoning_capabilities import (  # noqa: E402
    MetaPlanningCapability,
    SpeculativeReasoningCapability,
)

APPROVAL_KEY = b"benchmark-dynamic-objective-approval-key-32b!"


class BenchRetrievalProvider:
    provider_type = "TEST_IMPLEMENTATION"

    def health_check(self) -> bool:
        return True

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return {"answer": f"Evidence: {evidence[0]['content']}", "citations": [evidence[0]["evidence_id"]]}


def _sign(material: str, key: bytes = APPROVAL_KEY) -> str:
    return hmac.new(key, material.encode("utf-8"), hashlib.sha256).hexdigest()


def run_benchmark(iterations: int = 100) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_p39_"))
    db_path = temp_dir / "objective_bench.sqlite3"
    rag_db = temp_dir / "rag_bench.sqlite3"
    spec_db = temp_dir / "spec_bench.sqlite3"
    plan_db = temp_dir / "plan_bench.sqlite3"

    rag = AgenticRAGCapability(rag_db, BenchRetrievalProvider())
    rag.execute(
        {
            "action": "ingest",
            "source_ref": "bench:signal-01",
            "title": "Benchmark Signal",
            "content": "Resource load profile updated. Dynamic reprioritization requested.",
        }
    )
    evidence_id = rag.retrieve("resource load profile", 1)[0]["evidence_id"]
    sandbox = SandboxedImaginationCapability()

    # Cold boot measurement
    t_cold_start = time.perf_counter()
    cap = DynamicObjectiveCapability(
        db_path, APPROVAL_KEY, rag, sandbox, dampening_window_seconds=0.0
    )
    cold_boot_ms = (time.perf_counter() - t_cold_start) * 1000.0

    # Warm boot measurement
    t_warm_start = time.perf_counter()
    cap.health_check()
    warm_boot_ms = (time.perf_counter() - t_warm_start) * 1000.0

    # Initial creation
    owner_id = "bench-owner"
    objective_id = "bench-objective"
    cap.execute(
        {
            "action": "create",
            "objective_id": objective_id,
            "owner_id": owner_id,
            "owner_goal": "Optimize throughput under deterministic safety bounds",
            "invariants": ["1 + 1 == 2"],
            "weights": {"throughput": 0.5, "latency": 0.5},
        }
    )

    spec = SpeculativeReasoningCapability(spec_db, rag, sandbox)
    planner = MetaPlanningCapability(plan_db, rag, sandbox, spec)
    planner.objective_resolver = cap.active

    meter: WindowsEmiEnergyMeter | None = None
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

    latencies_propose_ms: list[float] = []
    latencies_approve_ms: list[float] = []
    latencies_plan_ms: list[float] = []
    latencies_rollback_ms: list[float] = []
    total_cycle_latencies_ms: list[float] = []

    current_ver = 1
    t_bench_start = time.perf_counter()

    for idx in range(iterations):
        cycle_start = time.perf_counter()

        # Step 1: Propose
        sig_tp = 0.5 if (idx % 2 == 0) else -0.5
        sig_lat = -sig_tp
        t_prop_start = time.perf_counter()
        prop = cap.execute(
            {
                "action": "propose",
                "objective_id": objective_id,
                "signals": {"throughput": sig_tp, "latency": sig_lat},
                "learning_rate": 0.05,
                "evidence_ids": [evidence_id],
                "policy_decision": "ALLOW",
                "expires_at": time.time() + 600,
            }
        )
        t_prop_end = time.perf_counter()
        latencies_propose_ms.append((t_prop_end - t_prop_start) * 1000.0)
        v = prop.data["version"]

        # Step 2: Approve
        appr_id = f"bench-appr-{idx}"
        mat = f"approve|{objective_id}|{v}|{prop.data['proposal_digest']}|{appr_id}|{owner_id}"
        sig = _sign(mat)
        t_appr_start = time.perf_counter()
        cap.execute(
            {
                "action": "approve",
                "objective_id": objective_id,
                "version": v,
                "approval_id": appr_id,
                "approved_by": owner_id,
                "signature": sig,
            }
        )
        t_appr_end = time.perf_counter()
        latencies_approve_ms.append((t_appr_end - t_appr_start) * 1000.0)
        current_ver = v

        # Step 3: Meta Planner Run
        t_plan_start = time.perf_counter()
        planner.execute(
            {
                "action": "run",
                "objective_id": objective_id,
                "goal": "Optimize throughput under deterministic safety bounds",
                "invariants": ["True"],
                "steps": [{"type": "sandbox", "expression": "100 > 1"}],
            }
        )
        t_plan_end = time.perf_counter()
        latencies_plan_ms.append((t_plan_end - t_plan_start) * 1000.0)

        # Step 4: Periodic Rollback (every 10 iterations)
        if (idx + 1) % 10 == 0:
            rb_id = f"bench-rb-{idx}"
            rb_mat = f"rollback|{objective_id}|{current_ver}|1|{rb_id}|{owner_id}"
            rb_sig = _sign(rb_mat)
            t_rb_start = time.perf_counter()
            rb_res = cap.execute(
                {
                    "action": "rollback",
                    "objective_id": objective_id,
                    "to_version": 1,
                    "rollback_id": rb_id,
                    "approved_by": owner_id,
                    "signature": rb_sig,
                }
            )
            t_rb_end = time.perf_counter()
            latencies_rollback_ms.append((t_rb_end - t_rb_start) * 1000.0)
            current_ver = rb_res.data["version"]

        total_cycle_latencies_ms.append((time.perf_counter() - cycle_start) * 1000.0)

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
        "benchmark_profile": "P39_WINDOWS_DYNAMIC_OBJECTIVE",
        "iterations": iterations,
        "completed_cycles": iterations,
        "completion_rate": 1.0,
        "startup": {
            "cold_boot_ms": round(cold_boot_ms, 3),
            "warm_boot_ms": round(warm_boot_ms, 3),
        },
        "latency_cycle_ms": {
            "mean": round(float(np.mean(total_cycle_latencies_ms)), 3),
            "median": round(float(np.median(total_cycle_latencies_ms)), 3),
            "p90": round(float(np.percentile(total_cycle_latencies_ms, 90)), 3),
            "p95": round(float(np.percentile(total_cycle_latencies_ms, 95)), 3),
            "p99": round(float(np.percentile(total_cycle_latencies_ms, 99)), 3),
            "min": round(float(np.min(total_cycle_latencies_ms)), 3),
            "max": round(float(np.max(total_cycle_latencies_ms)), 3),
        },
        "latency_by_phase_ms": {
            "propose_mean": round(float(np.mean(latencies_propose_ms)), 3),
            "approve_mean": round(float(np.mean(latencies_approve_ms)), 3),
            "plan_mean": round(float(np.mean(latencies_plan_ms)), 3),
            "rollback_mean": round(float(np.mean(latencies_rollback_ms)), 3) if latencies_rollback_ms else 0.0,
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

    del cap, planner, spec
    import gc
    gc.collect()
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Pillar 39 Dynamic Objective Benchmark Suite")
    parser.add_argument("--iterations", type=int, default=100, help="Number of benchmark iterations (default: 100)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path for benchmark results")
    args = parser.parse_args()

    print(f"Starting Pillar 39 Dynamic Objective benchmark ({args.iterations} iterations)...")
    results = run_benchmark(iterations=args.iterations)

    print("\n" + "=" * 60)
    print("  PILAR 39: DYNAMIC OBJECTIVE BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Iterations:          {results['iterations']}")
    print(f"  Completion Rate:     {results['completion_rate'] * 100:.1f}%")
    print(f"  Throughput:          {results['throughput']['cycles_per_sec']} cycles/sec")
    print(f"  Cycle Latency Mean:  {results['latency_cycle_ms']['mean']:.3f} ms")
    print(f"  Cycle Latency p50:   {results['latency_cycle_ms']['median']:.3f} ms")
    print(f"  Cycle Latency p95:   {results['latency_cycle_ms']['p95']:.3f} ms")
    print(f"  Propose Phase Mean:  {results['latency_by_phase_ms']['propose_mean']:.3f} ms")
    print(f"  Approve Phase Mean:  {results['latency_by_phase_ms']['approve_mean']:.3f} ms")
    print(f"  Planner Phase Mean:  {results['latency_by_phase_ms']['plan_mean']:.3f} ms")
    print(f"  Rollback Phase Mean: {results['latency_by_phase_ms']['rollback_mean']:.3f} ms")
    print(f"  RSS Growth:          {results['resource']['rss_growth_bytes'] / (1024 * 1024):.2f} MB")
    print(f"  Energy Consumption:  {results['energy']['total_joules']} J ({results['energy']['joules_per_cycle']} J/cycle, {results['energy']['method']})")
    print("=" * 60)

    out_file = Path(args.output) if args.output else ROOT / "artifacts" / "benchmark_p39_dynamic_objective.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to: {out_file}")

    # Also save to conversation scratch directory
    scratch_out = Path("outputs") / f"{Path(__file__).stem}.json"
    scratch_out.parent.mkdir(parents=True, exist_ok=True)
    with scratch_out.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
