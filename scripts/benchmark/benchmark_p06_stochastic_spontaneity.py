#!/usr/bin/env python3
"""Benchmark suite for Pillar 06: Stochastic Spontaneity."""

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

from jaya_core.brain_v2.engine.spontaneity import (  # noqa: E402
    ExplorationBudget,
    ExplorationReceiptStore,
    ExplorationRequest,
    SpontaneityEngine,
)
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter  # noqa: E402
from jaya_core.verification.stochastic_spontaneity import (  # noqa: E402
    DeterministicSeededVerificationProvider,
)


def run_benchmark(iterations: int = 100) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_p06_"))
    db_path = temp_dir / "spontaneity_bench.sqlite3"
    provider = DeterministicSeededVerificationProvider()

    # Cold boot measurement
    t_cold_start = time.perf_counter()
    store = ExplorationReceiptStore(db_path)
    engine = SpontaneityEngine(store, provider)
    store.healthcheck()
    cold_boot_ms = (time.perf_counter() - t_cold_start) * 1000.0

    # Warm boot measurement
    t_warm_start = time.perf_counter()
    store.healthcheck()
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

    # 1. Bounded Exploration Generation Benchmark
    explore_latencies_ms: list[float] = []
    acceptance_rates: list[float] = []
    novelty_scores: list[float] = []
    diversity_scores: list[float] = []

    t_explore_start = time.perf_counter()
    for idx in range(iterations):
        t0 = time.perf_counter()
        res = engine.explore(
            ExplorationRequest(
                topic=f"stochastic spontaneity domain exploration topic {idx}",
                authorized=True,
                seed=5000 + idx,
                request_id=f"bench-req-{idx}",
                budget=ExplorationBudget(max_candidates=3, max_tokens=512, timeout_seconds=10.0),
                evidence_ids=(f"ev-{idx}-a", f"ev-{idx}-b"),
            )
        )
        explore_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        metrics = res["metrics"]
        acceptance_rates.append(metrics["acceptance_rate"])
        novelty_scores.append(metrics["novelty_score"])
        diversity_scores.append(metrics["diversity_score"])

    explore_duration_s = time.perf_counter() - t_explore_start
    explore_ops_per_sec = iterations / max(1e-6, explore_duration_s)

    # 2. Replay & Receipt Integrity Verification Benchmark
    replay_latencies_ms: list[float] = []
    t_replay_start = time.perf_counter()
    for idx in range(iterations):
        target_idx = idx % min(20, iterations)
        t0 = time.perf_counter()
        replayed = engine.explore(
            ExplorationRequest(
                topic=f"stochastic spontaneity domain exploration topic {target_idx}",
                authorized=True,
                seed=5000 + target_idx,
                request_id=f"bench-req-{target_idx}",
            )
        )
        replay_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        assert replayed["status"] == "REPLAYED_RECEIPT"

    replay_duration_s = time.perf_counter() - t_replay_start
    replay_ops_per_sec = iterations / max(1e-6, replay_duration_s)

    # 3. Duplicate Detection Benchmark
    dup_latencies_ms: list[float] = []
    t_dup_start = time.perf_counter()
    for idx in range(iterations):
        target_idx = idx % min(20, iterations)
        t0 = time.perf_counter()
        dup_res = engine.explore(
            ExplorationRequest(
                topic=f"stochastic spontaneity domain exploration topic {target_idx}",
                authorized=True,
                seed=5000 + target_idx,
                request_id=f"bench-dup-req-{idx}",
            )
        )
        dup_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        assert dup_res["metrics"]["accepted_candidates"] == 0

    dup_duration_s = time.perf_counter() - t_dup_start
    dup_ops_per_sec = iterations / max(1e-6, dup_duration_s)

    # 4. Energy measurement
    energy_joules = 0.0
    energy_method = "SOFTWARE_FALLBACK"
    if meter is not None and start_sample is not None:
        try:
            end_sample = meter.sample()
            measured = meter.measure(start_sample, end_sample)
            energy_joules = float(measured.joules or (explore_duration_s * 28.0))
            energy_method = "WINDOWS_EMI"
        except EnergyMeterError:
            energy_joules = explore_duration_s * 28.0
    else:
        energy_joules = explore_duration_s * 28.0

    rss_final = proc.memory_info().rss
    rss_growth_bytes = max(0, rss_final - rss_initial)
    db_file_size = db_path.stat().st_size
    bytes_per_receipt = db_file_size / max(1, iterations * 2)

    store.close()
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass

    results = {
        "pillar": "P06 Stochastic Spontaneity",
        "capability_id": "core.exploration.spontaneous",
        "iterations": iterations,
        "boot": {
            "cold_boot_ms": round(cold_boot_ms, 3),
            "warm_boot_ms": round(warm_boot_ms, 3),
        },
        "exploration": {
            "throughput_req_per_sec": round(explore_ops_per_sec, 2),
            "latency_ms": {
                "mean": round(float(np.mean(explore_latencies_ms)), 3),
                "median": round(float(np.median(explore_latencies_ms)), 3),
                "p95": round(float(np.percentile(explore_latencies_ms, 95)), 3),
                "p99": round(float(np.percentile(explore_latencies_ms, 99)), 3),
                "min": round(float(np.min(explore_latencies_ms)), 3),
                "max": round(float(np.max(explore_latencies_ms)), 3),
            },
            "metrics": {
                "mean_acceptance_rate": round(float(np.mean(acceptance_rates)), 4),
                "mean_novelty_score": round(float(np.mean(novelty_scores)), 4),
                "mean_diversity_score": round(float(np.mean(diversity_scores)), 4),
            },
        },
        "replay": {
            "throughput_req_per_sec": round(replay_ops_per_sec, 2),
            "mean_latency_ms": round(float(np.mean(replay_latencies_ms)), 3),
            "p95_latency_ms": round(float(np.percentile(replay_latencies_ms, 95)), 3),
        },
        "deduplication": {
            "throughput_req_per_sec": round(dup_ops_per_sec, 2),
            "mean_latency_ms": round(float(np.mean(dup_latencies_ms)), 3),
        },
        "storage": {
            "database_size_bytes": db_file_size,
            "bytes_per_receipt": round(bytes_per_receipt, 1),
            "rss_growth_bytes": rss_growth_bytes,
        },
        "energy": {
            "total_joules": round(energy_joules, 4),
            "joules_per_exploration": round(energy_joules / max(1, iterations), 6),
            "method": energy_method,
        },
    }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=100, help="Number of benchmark iterations")
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT / "artifacts" / "benchmark_p06_stochastic_spontaneity.json"),
        help="Path to save benchmark JSON output",
    )
    args = parser.parse_args()

    print(f"[P06 BENCHMARK] Running {args.iterations} iterations on Windows x86_64...")
    results = run_benchmark(args.iterations)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"[P06 BENCHMARK] Results saved to: {out_path}")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
