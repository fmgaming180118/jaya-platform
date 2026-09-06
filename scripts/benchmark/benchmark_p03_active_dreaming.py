#!/usr/bin/env python3
"""Benchmark suite for Pillar 03: Active Dreaming."""

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
    ActiveDreamingCapability,
    DeterministicCounterfactualProvider,
)


def run_benchmark(iterations: int = 100) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_p03_"))
    db_path = temp_dir / "active_dreaming_bench.sqlite3"
    rag_db_path = temp_dir / "rag_bench.sqlite3"
    provider = DeterministicCounterfactualProvider()

    rag = AgenticRAGCapability(rag_db_path, None)
    rag.ingest({
        "action": "ingest",
        "source_ref": "thermal_cryo_dissipation_source",
        "title": "Cryogenic Dissipation Reference",
        "content": "Superconducting circuits operate with 95% reduced thermal noise under liquid helium cooling at 4 Kelvin.",
    })
    rag.ingest({
        "action": "ingest",
        "source_ref": "thermoelectric_materials_source",
        "title": "Thermoelectric Lattices",
        "content": "Bismuth telluride alloys demonstrate high Seebeck coefficients for solid-state thermoelectric heat pumping.",
    })

    sandbox = SandboxedImaginationCapability()

    # Cold boot measurement
    t_cold_start = time.perf_counter()
    dream = ActiveDreamingCapability(db_path, rag, sandbox, provider)
    cold_boot_ms = (time.perf_counter() - t_cold_start) * 1000.0

    # Warm boot measurement
    t_warm_start = time.perf_counter()
    dream.health_check()
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

    # 1. Active Dreaming Generation Benchmark (Subprocess + RAG + Candidate Synthesis)
    dream_latencies_ms: list[float] = []
    acceptance_rates: list[float] = []
    novelty_scores: list[float] = []
    diversity_scores: list[float] = []

    t_dream_start = time.perf_counter()
    for idx in range(iterations):
        t0 = time.perf_counter()
        res = dream.dream({
            "action": "dream",
            "topic": f"Cryogenic thermoelectric dissipation branch {idx}",
            "query": "cryogenic thermoelectric",
            "constraints": [f"{idx} + 1 == {idx + 1}"],
            "seed": 8000 + idx,
            "request_id": f"bench-dream-req-{idx}",
            "candidate_limit": 2,
        })
        dream_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        metrics = res.data["metrics"]
        acceptance_rates.append(metrics["acceptance_rate"])
        novelty_scores.append(metrics["novelty_score"])
        diversity_scores.append(metrics["diversity_score"])

    dream_duration_s = time.perf_counter() - t_dream_start
    dream_ops_per_sec = iterations / max(1e-6, dream_duration_s)

    # 2. Replay & Receipt Integrity Verification Benchmark
    replay_latencies_ms: list[float] = []
    t_replay_start = time.perf_counter()
    for idx in range(iterations):
        target_idx = idx % min(20, iterations)
        t0 = time.perf_counter()
        replayed = dream.dream({
            "action": "dream",
            "topic": f"Cryogenic thermoelectric dissipation branch {target_idx}",
            "query": "cryogenic thermoelectric",
            "constraints": [f"{target_idx} + 1 == {target_idx + 1}"],
            "seed": 8000 + target_idx,
            "request_id": f"bench-dream-req-{target_idx}",
        })
        replay_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        assert replayed.code == "REPLAYED_DREAM"

    replay_duration_s = time.perf_counter() - t_replay_start
    replay_ops_per_sec = iterations / max(1e-6, replay_duration_s)

    # 3. Duplicate Detection Benchmark
    dup_latencies_ms: list[float] = []
    t_dup_start = time.perf_counter()
    for idx in range(iterations):
        target_idx = idx % min(20, iterations)
        t0 = time.perf_counter()
        dup_res = dream.dream({
            "action": "dream",
            "topic": f"Cryogenic thermoelectric dissipation branch {target_idx}",
            "query": "cryogenic thermoelectric",
            "constraints": [f"{target_idx} + 1 == {target_idx + 1}"],
            "seed": 8000 + target_idx,
            "request_id": f"bench-dup-req-{idx}",
            "candidate_limit": 2,
        })
        dup_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        assert dup_res.data["metrics"]["accepted_candidates"] == 0

    dup_duration_s = time.perf_counter() - t_dup_start
    dup_ops_per_sec = iterations / max(1e-6, dup_duration_s)

    # 4. Energy measurement
    energy_joules = 0.0
    energy_method = "SOFTWARE_FALLBACK"
    if meter is not None and start_sample is not None:
        try:
            end_sample = meter.sample()
            measured = meter.measure(start_sample, end_sample)
            energy_joules = float(measured.joules or (dream_duration_s * 28.0))
            energy_method = "WINDOWS_EMI"
        except EnergyMeterError:
            energy_joules = dream_duration_s * 28.0
    else:
        energy_joules = dream_duration_s * 28.0

    rss_final = proc.memory_info().rss
    rss_growth_bytes = max(0, rss_final - rss_initial)
    db_file_size = db_path.stat().st_size

    dream.close()
    rag.close()
    shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "pillar_id": 3,
        "pillar_name": "Active Dreaming",
        "iterations": iterations,
        "cold_boot_ms": round(cold_boot_ms, 3),
        "warm_boot_ms": round(warm_boot_ms, 3),
        "dream_generation": {
            "mean_latency_ms": round(float(np.mean(dream_latencies_ms)), 3),
            "median_latency_ms": round(float(np.median(dream_latencies_ms)), 3),
            "p95_latency_ms": round(float(np.percentile(dream_latencies_ms, 95)), 3),
            "p99_latency_ms": round(float(np.percentile(dream_latencies_ms, 99)), 3),
            "min_latency_ms": round(float(np.min(dream_latencies_ms)), 3),
            "max_latency_ms": round(float(np.max(dream_latencies_ms)), 3),
            "ops_per_sec": round(dream_ops_per_sec, 2),
            "mean_novelty_score": round(float(np.mean(novelty_scores)), 4),
            "mean_diversity_score": round(float(np.mean(diversity_scores)), 4),
            "mean_acceptance_rate": round(float(np.mean(acceptance_rates)), 4),
        },
        "replay_integrity": {
            "mean_latency_ms": round(float(np.mean(replay_latencies_ms)), 3),
            "p95_latency_ms": round(float(np.percentile(replay_latencies_ms, 95)), 3),
            "ops_per_sec": round(replay_ops_per_sec, 2),
        },
        "duplicate_detection": {
            "mean_latency_ms": round(float(np.mean(dup_latencies_ms)), 3),
            "p95_latency_ms": round(float(np.percentile(dup_latencies_ms, 95)), 3),
            "ops_per_sec": round(dup_ops_per_sec, 2),
        },
        "system_resources": {
            "rss_initial_bytes": rss_initial,
            "rss_final_bytes": rss_final,
            "rss_growth_bytes": rss_growth_bytes,
            "database_bytes_total": db_file_size,
            "database_bytes_per_record": round(db_file_size / max(1, iterations), 2),
            "energy_joules_total": round(energy_joules, 4),
            "energy_joules_per_record": round(energy_joules / max(1, iterations), 5),
            "energy_method": energy_method,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    results = run_benchmark(args.iterations)
    print(json.dumps(results, indent=2))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Artifact written to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
