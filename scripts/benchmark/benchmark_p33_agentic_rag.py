#!/usr/bin/env python3
"""Benchmark suite for Pillar 33 Agentic RAG."""

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
from jaya_core.pillars.agentic_rag_capability import (  # noqa: E402
    AgenticRAGCapability,
    ExtractiveGroundedAnswerProvider,
)


def run_benchmark(iterations: int = 100) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_p33_"))
    db_path = temp_dir / "rag_bench.sqlite3"

    # Cold boot measurement
    t_cold_start = time.perf_counter()
    rag = AgenticRAGCapability(db_path, None)
    rag.health_check()
    cold_boot_ms = (time.perf_counter() - t_cold_start) * 1000.0

    # Warm boot measurement
    t_warm_start = time.perf_counter()
    rag.health_check()
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

    # 1. Ingestion Benchmark
    ingest_latencies_ms: list[float] = []
    total_bytes_ingested = 0
    t_ingest_start = time.perf_counter()
    for idx in range(iterations):
        content = (
            f"Knowledge domain entity {idx}. "
            f"Autonomous node {idx} executes task routing using semantic bridge protocol. "
            f"Parameter alpha is set to {1000 + idx} units. "
            f"Verification hash for round {idx} confirms integrity."
        )
        data_bytes = len(content.encode("utf-8"))
        total_bytes_ingested += data_bytes

        t0 = time.perf_counter()
        rag.execute({
            "action": "ingest",
            "source_ref": f"artifact:doc-node-{idx}",
            "title": f"Node Specification {idx}",
            "content": content,
        })
        ingest_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
    ingest_duration_s = time.perf_counter() - t_ingest_start
    ingest_ops_per_sec = iterations / max(1e-6, ingest_duration_s)
    ingest_mb_per_sec = (total_bytes_ingested / (1024 * 1024)) / max(1e-6, ingest_duration_s)

    # 2. Retrieval Benchmark
    retrieval_latencies_ms: list[float] = []
    t_ret_start = time.perf_counter()
    for idx in range(iterations):
        target_idx = idx % 20
        query = f"semantic bridge node {target_idx}"
        t0 = time.perf_counter()
        rag.retrieve(query, top_k=5)
        retrieval_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
    retrieval_duration_s = time.perf_counter() - t_ret_start
    retrieval_ops_per_sec = iterations / max(1e-6, retrieval_duration_s)

    # 3. Sufficiency Evaluation Benchmark
    sample_evidence = rag.retrieve("semantic bridge", top_k=5)
    suff_latencies_ms: list[float] = []
    t_suff_start = time.perf_counter()
    for idx in range(iterations):
        t0 = time.perf_counter()
        rag.evaluate_sufficiency("What does the semantic bridge do?", sample_evidence)
        suff_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
    suff_duration_s = time.perf_counter() - t_suff_start
    suff_ops_per_sec = iterations / max(1e-6, suff_duration_s)

    # 4. Extractive Grounded Answering Benchmark
    ask_latencies_ms: list[float] = []
    precisions: list[float] = []
    groundedness_scores: list[float] = []
    t_ask_start = time.perf_counter()
    for idx in range(min(50, iterations)):
        target_idx = idx % 10
        t0 = time.perf_counter()
        res = rag.execute({
            "action": "ask",
            "question": f"What is set to {1000 + target_idx} units?",
            "allow_extractive_fallback": True,
            "strict_conflict": False,
        })
        ask_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        precisions.append(res.data.get("precision", 1.0))
        groundedness_scores.append(res.data.get("groundedness", 1.0))
    ask_duration_s = time.perf_counter() - t_ask_start
    ask_ops_per_sec = len(ask_latencies_ms) / max(1e-6, ask_duration_s)

    # Storage & Memory Metrics
    rss_final = proc.memory_info().rss
    rss_growth = max(0, rss_final - rss_initial)
    db_size = db_path.stat().st_size
    status = rag.status()
    bytes_per_chunk = db_size / max(1, status["chunks_count"])

    # Energy Measurement
    energy_joules = 0.0
    energy_method = "SOFTWARE_FALLBACK"
    if meter is not None and start_sample is not None:
        try:
            end_sample = meter.sample()
            measured = meter.measure(start_sample, end_sample)
            energy_joules = float(measured.joules)
            energy_method = "WINDOWS_EMI"
        except EnergyMeterError:
            energy_joules = (time.perf_counter() - t_ingest_start) * 28.0
    else:
        energy_joules = (time.perf_counter() - t_ingest_start) * 28.0

    rag.close()
    shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "pillar": "P33 Agentic RAG",
        "iterations": iterations,
        "boot": {
            "cold_boot_ms": round(cold_boot_ms, 3),
            "warm_boot_ms": round(warm_boot_ms, 3),
        },
        "ingestion": {
            "mean_latency_ms": round(float(np.mean(ingest_latencies_ms)), 3),
            "p50_latency_ms": round(float(np.percentile(ingest_latencies_ms, 50)), 3),
            "p95_latency_ms": round(float(np.percentile(ingest_latencies_ms, 95)), 3),
            "p99_latency_ms": round(float(np.percentile(ingest_latencies_ms, 99)), 3),
            "throughput_ops_sec": round(ingest_ops_per_sec, 1),
            "throughput_mb_sec": round(ingest_mb_per_sec, 3),
            "total_bytes": total_bytes_ingested,
        },
        "retrieval": {
            "mean_latency_ms": round(float(np.mean(retrieval_latencies_ms)), 3),
            "p50_latency_ms": round(float(np.percentile(retrieval_latencies_ms, 50)), 3),
            "p95_latency_ms": round(float(np.percentile(retrieval_latencies_ms, 95)), 3),
            "p99_latency_ms": round(float(np.percentile(retrieval_latencies_ms, 99)), 3),
            "throughput_queries_sec": round(retrieval_ops_per_sec, 1),
        },
        "sufficiency_evaluation": {
            "mean_latency_ms": round(float(np.mean(suff_latencies_ms)), 3),
            "throughput_eval_sec": round(suff_ops_per_sec, 1),
        },
        "grounded_answering": {
            "mean_latency_ms": round(float(np.mean(ask_latencies_ms)), 3),
            "p50_latency_ms": round(float(np.percentile(ask_latencies_ms, 50)), 3),
            "p95_latency_ms": round(float(np.percentile(ask_latencies_ms, 95)), 3),
            "throughput_answers_sec": round(ask_ops_per_sec, 1),
            "mean_citation_precision": round(float(np.mean(precisions)), 4),
            "mean_groundedness": round(float(np.mean(groundedness_scores)), 4),
        },
        "storage": {
            "total_database_bytes": db_size,
            "total_chunks": status["chunks_count"],
            "bytes_per_chunk": round(bytes_per_chunk, 1),
        },
        "resources": {
            "rss_initial_mb": round(rss_initial / (1024 * 1024), 2),
            "rss_final_mb": round(rss_final / (1024 * 1024), 2),
            "rss_growth_mb": round(rss_growth / (1024 * 1024), 2),
            "energy_joules": round(energy_joules, 4),
            "energy_method": energy_method,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument(
        "--output",
        default=str(
            Path.home()
            / ".gemini"
            / "antigravity-ide"
            / "brain"
            / "ed6cfd53-0771-44cb-b479-c0270dfa3a89"
            / "scratch"
            / "benchmark_p33_agentic_rag.json"
        ),
    )
    args = parser.parse_args()

    results = run_benchmark(args.iterations)
    print(json.dumps(results, indent=2))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nBenchmark results saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
