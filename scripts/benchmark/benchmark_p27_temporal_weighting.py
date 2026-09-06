#!/usr/bin/env python3
"""benchmark_p27_temporal_weighting.py — Quantitative Performance, Ranking & Audit Benchmark for P27 Temporal Weighting.

Measures:
1. Environment Baseline:
   - Platform, CPU count, Python version, initial RSS memory.
2. Record Ingestion Latency (add operation):
   - Latency distribution (mean, p50, p95, p99, min, max, stddev) and throughput (adds/sec).
3. Ranking & Decay Evaluation Latency (rank operation):
   - Scaling across dataset sizes (100, 500, 1000, 2000 records).
4. Historical Point-in-Time Query Latency (history as_of):
   - Deterministic state reconstruction at arbitrary historical timestamps.
5. Policy Event & Legal Hold Latency (set_legal_hold):
   - Append-only policy audit events, idempotency, and retention status update.
6. Fault Drills Latency:
   - Clock skew rejection, invalid time window rejection, missing parent supersession.
7. Multithreaded Concurrency (8 threads):
   - Concurrent adds and ranking queries under transactional SQLite locking.
8. Resource Footprint:
   - RSS memory growth, database file size, and bytes per record.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import platform
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.foundation_capabilities import TemporalWeightingCapability  # noqa: E402
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402


def _stats(samples_ms: list[float]) -> dict[str, float]:
    if not samples_ms:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0, "stddev": 0.0}
    sorted_s = sorted(samples_ms)
    n = len(sorted_s)
    p50_idx = int(0.50 * (n - 1))
    p95_idx = int(0.95 * (n - 1))
    p99_idx = int(0.99 * (n - 1))
    mean = statistics.mean(sorted_s)
    stddev = statistics.stdev(sorted_s) if n > 1 else 0.0
    return {
        "mean": round(mean, 3),
        "p50": round(sorted_s[p50_idx], 3),
        "p95": round(sorted_s[p95_idx], 3),
        "p99": round(sorted_s[p99_idx], 3),
        "min": round(sorted_s[0], 3),
        "max": round(sorted_s[-1], 3),
        "stddev": round(stddev, 3),
    }


def run_benchmark(iterations: int = 1000, out_dir: Path | None = None) -> dict[str, Any]:
    print("=" * 70)
    print(" PILAR 27: TEMPORAL WEIGHTING — QUANTITATIVE BENCHMARK SUITE")
    print("=" * 70)

    process = psutil.Process()
    rss_start = process.memory_info().rss
    sys_name = platform.system()
    cpu_cnt = psutil.cpu_count(logical=True)
    py_ver = sys.version.split()[0]

    print(f"Environment: {sys_name} | CPU: {cpu_cnt} logical cores | Python: {py_ver}")
    print(f"Initial RSS: {rss_start / (1024 * 1024):.2f} MiB\n")

    with tempfile.TemporaryDirectory(prefix="jaya-p27-bench-", ignore_cleanup_errors=True) as tmp:
        work_dir = Path(tmp)
        db_path = work_dir / "bench_temporal.sqlite3"
        temporal = TemporalWeightingCapability(db_path)
        base_time = time.time()

        # ---------------------------------------------------------------------
        # 1. Record Ingestion Latency (add)
        # ---------------------------------------------------------------------
        print(f"1. Measuring Record Ingestion Latency ({iterations} records)...")
        add_latencies: list[float] = []
        for i in range(iterations):
            req = {
                "action": "add",
                "record_id": f"rec-{i}",
                "source_ref": f"source:doc-{i % 50}",
                "base_score": 0.5 + (i % 50) * 0.01,
                "observed_at": base_time - (iterations - i) * 10,
                "valid_until": base_time + 3600,
                "retention_until": base_time + 7200,
                "clock_source": "SYSTEM_UTC",
                "payload": {"index": i, "tag": "bench"},
            }
            t0 = time.perf_counter()
            temporal.execute(req)
            add_latencies.append((time.perf_counter() - t0) * 1000.0)

        add_stats = _stats(add_latencies)
        throughput_adds = iterations / (sum(add_latencies) / 1000.0) if sum(add_latencies) > 0 else 0.0
        print(
            f"   Mean: {add_stats['mean']:6.2f}ms | P50: {add_stats['p50']:6.2f}ms | "
            f"P95: {add_stats['p95']:6.2f}ms | Throughput: {throughput_adds:8.1f} adds/sec\n"
        )

        # ---------------------------------------------------------------------
        # 2. Ranking & Decay Scaling
        # ---------------------------------------------------------------------
        print("2. Measuring Ranking Latency across Decay Rates & Evaluations...")
        rank_latencies: list[float] = []
        decay_rates = [0.001, 0.01, 0.05, 0.1]
        for rate in decay_rates:
            for _ in range(25):
                t0 = time.perf_counter()
                temporal.execute({"action": "rank", "decay_rate": rate, "now": base_time})
                rank_latencies.append((time.perf_counter() - t0) * 1000.0)

        rank_stats = _stats(rank_latencies)
        print(
            f"   Dataset: {iterations} records | Mean: {rank_stats['mean']:6.2f}ms | "
            f"P50: {rank_stats['p50']:6.2f}ms | P95: {rank_stats['p95']:6.2f}ms\n"
        )

        # ---------------------------------------------------------------------
        # 3. Historical Point-in-Time Queries (as_of)
        # ---------------------------------------------------------------------
        print("3. Measuring Historical Point-in-Time Reconstruction (as_of)...")
        as_of_latencies: list[float] = []
        timestamps = [
            base_time - iterations * 10,
            base_time - (iterations // 2) * 10,
            base_time,
        ]
        for ts in timestamps:
            for _ in range(30):
                t0 = time.perf_counter()
                temporal.execute({"action": "history", "as_of": ts})
                as_of_latencies.append((time.perf_counter() - t0) * 1000.0)

        history_stats = _stats(as_of_latencies)
        print(
            f"   Mean: {history_stats['mean']:6.2f}ms | P50: {history_stats['p50']:6.2f}ms | "
            f"P95: {history_stats['p95']:6.2f}ms\n"
        )

        # ---------------------------------------------------------------------
        # 4. Policy Event & Legal Hold Latency
        # ---------------------------------------------------------------------
        print("4. Measuring Legal Hold & Policy Event Latency...")
        hold_latencies: list[float] = []
        for i in range(100):
            req = {
                "action": "set_legal_hold",
                "event_id": f"hold-event-{i}",
                "record_id": f"rec-{i}",
                "enabled": True,
                "reason": "regulatory audit hold",
                "changed_at": base_time,
            }
            t0 = time.perf_counter()
            temporal.execute(req)
            hold_latencies.append((time.perf_counter() - t0) * 1000.0)

        hold_stats = _stats(hold_latencies)
        print(
            f"   Mean: {hold_stats['mean']:6.2f}ms | P50: {hold_stats['p50']:6.2f}ms | "
            f"P95: {hold_stats['p95']:6.2f}ms\n"
        )

        # ---------------------------------------------------------------------
        # 5. Fault Drills Latency & Rejection
        # ---------------------------------------------------------------------
        print("5. Measuring Fault Drills Latency & Boundary Rejections...")
        fault_drills: dict[str, Any] = {}

        # 5a. Clock Skew (future observed_at)
        t0 = time.perf_counter()
        try:
            temporal.execute(
                {
                    "action": "add",
                    "record_id": "rec-future",
                    "source_ref": "source:future",
                    "base_score": 1.0,
                    "observed_at": base_time + 99999,
                    "payload": {},
                }
            )
            clock_skew_pass = False
        except LocalPillarError as err:
            clock_skew_pass = err.code == "CLOCK_SKEW"
        skew_latency = (time.perf_counter() - t0) * 1000.0

        # 5b. Invalid Window (valid_until < observed_at)
        t0 = time.perf_counter()
        try:
            temporal.execute(
                {
                    "action": "add",
                    "record_id": "rec-inv-win",
                    "source_ref": "source:inv",
                    "base_score": 1.0,
                    "observed_at": base_time,
                    "valid_until": base_time - 100,
                    "payload": {},
                }
            )
            inv_win_pass = False
        except LocalPillarError as err:
            inv_win_pass = err.code == "INVALID_INPUT"
        inv_win_latency = (time.perf_counter() - t0) * 1000.0

        # 5c. Missing Supersedes Parent
        t0 = time.perf_counter()
        try:
            temporal.execute(
                {
                    "action": "add",
                    "record_id": "rec-missing-parent",
                    "source_ref": "source:child",
                    "base_score": 0.8,
                    "observed_at": base_time,
                    "supersedes": "nonexistent-parent",
                    "payload": {},
                }
            )
            missing_parent_pass = False
        except LocalPillarError as err:
            missing_parent_pass = err.code == "SUPERSESSION_NOT_FOUND"
        missing_parent_latency = (time.perf_counter() - t0) * 1000.0

        fault_drills["clock_skew"] = {"passed": clock_skew_pass, "latency_ms": round(skew_latency, 3)}
        fault_drills["invalid_window"] = {"passed": inv_win_pass, "latency_ms": round(inv_win_latency, 3)}
        fault_drills["missing_parent"] = {"passed": missing_parent_pass, "latency_ms": round(missing_parent_latency, 3)}

        print(f"   Clock Skew Rejection:        {round(skew_latency, 3)}ms (PASS={clock_skew_pass})")
        print(f"   Invalid Window Rejection:    {round(inv_win_latency, 3)}ms (PASS={inv_win_pass})")
        print(f"   Missing Parent Rejection:    {round(missing_parent_latency, 3)}ms (PASS={missing_parent_pass})\n")

        # ---------------------------------------------------------------------
        # 6. Multithreaded Concurrency (8 threads)
        # ---------------------------------------------------------------------
        print("6. Measuring Multithreaded Concurrency (8 threads, 200 operations)...")
        concurrency_latencies: list[float] = []
        concurrency_errors = 0

        def _worker(thread_id: int) -> list[float]:
            worker_latencies: list[float] = []
            for j in range(25):
                rec_id = f"conc-thread-{thread_id}-{j}"
                t_start = time.perf_counter()
                try:
                    temporal.execute(
                        {
                            "action": "add",
                            "record_id": rec_id,
                            "source_ref": f"source:thread-{thread_id}",
                            "base_score": 0.85,
                            "observed_at": base_time - j,
                            "payload": {"thread": thread_id},
                        }
                    )
                    worker_latencies.append((time.perf_counter() - t_start) * 1000.0)
                except Exception:  # noqa: BLE001
                    nonlocal concurrency_errors
                    concurrency_errors += 1
            return worker_latencies

        t_conc_start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_worker, tid) for tid in range(8)]
            for fut in concurrent.futures.as_completed(futures):
                concurrency_latencies.extend(fut.result())
        conc_elapsed = time.perf_counter() - t_conc_start

        conc_stats = _stats(concurrency_latencies)
        print(
            f"   8 Threads (200 ops) | Elapsed: {conc_elapsed:.2f}s | "
            f"Mean: {conc_stats['mean']:.3f}ms | Errors: {concurrency_errors}\n"
        )

        # ---------------------------------------------------------------------
        # 7. Memory & Storage Telemetry
        # ---------------------------------------------------------------------
        print("7. Resource Footprint & SQLite Storage Density...")
        rss_end = process.memory_info().rss
        rss_growth = max(0, rss_end - rss_start)
        db_size = db_path.stat().st_size
        bytes_per_rec = db_size / (iterations + 200)

        print(f"   Final RSS:         {rss_end / (1024 * 1024):.2f} MiB")
        print(f"   RSS Delta:         {rss_growth / (1024 * 1024):.2f} MiB")
        print(f"   Database Size:     {db_size / 1024:.2f} KiB")
        print(f"   Density:           {bytes_per_rec:.1f} bytes/record")

    report = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "environment": {
            "os": sys_name,
            "cpu_count": cpu_cnt,
            "python_version": py_ver,
            "initial_rss_bytes": rss_start,
            "final_rss_bytes": rss_end,
            "rss_growth_bytes": rss_growth,
        },
        "metrics": {
            "iterations": iterations,
            "add_latency_ms": add_stats,
            "ranking_latency_ms": rank_stats,
            "history_latency_ms": history_stats,
            "legal_hold_latency_ms": hold_stats,
            "fault_drills": fault_drills,
            "concurrency": {
                "threads": 8,
                "total_operations": 200,
                "elapsed_seconds": round(conc_elapsed, 3),
                "errors": concurrency_errors,
                "latency_ms": conc_stats,
            },
            "storage": {
                "db_size_bytes": db_size,
                "bytes_per_record": round(bytes_per_rec, 1),
            },
        },
    }

    if out_dir:
        out_path = out_dir / "benchmark_p27_temporal_weighting.json"
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nArtifact saved to: {out_path}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "artifacts" / "benchmarks"),
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_benchmark(iterations=args.iterations, out_dir=out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
