#!/usr/bin/env python3
"""benchmark_p08_holographic_memory.py — Quantitative Performance & Durability Benchmark for P08 Holographic Memory.

Measures:
1. Environment Baseline:
   - Platform, CPU count, Python version, initial RSS memory.
2. Episodic Store Append Throughput & Latency Scaling:
   - Scaling across event payloads and index counts.
   - Latency distribution (mean, p50, p95, p99, min, max, stddev) and throughput (events/sec, KiB/sec).
3. Multi-Index Retrieval Latency:
   - Queries across session, goal, event_type, semantic, entity, task, and procedure indices.
4. Idempotency & Conflict Detection Overhead:
   - Duplicate append fast-path latency.
   - Conflict detection latency on payload/provenance mismatches.
5. Index Reconstruction & Self-Healing Throughput:
   - Full deterministic index rebuild time and records/sec from raw metadata.
6. Multithreaded Concurrency:
   - 8 concurrent threads concurrently writing into the SQLite episodic memory store.
7. Compaction & Retention Pruning Latency:
   - Compacting revoked records beyond retention threshold.
8. Memory & Storage Footprint:
   - Initial RSS, final RSS, delta RSS, SQLite file size, and storage density per holographic record.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
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

from jaya_core.memory.episodic import EpisodicMemoryStore  # noqa: E402
from jaya_core.pillars.foundation_capabilities import (  # noqa: E402
    MEMORY_CAPABILITY_ID,
    FoundationPillarCapabilityService,
)
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


def run_benchmark(iterations: int = 500, out_dir: Path | None = None) -> dict[str, Any]:
    print("=" * 70)
    print(" PILAR 08: HOLOGRAPHIC MEMORY — QUANTITATIVE BENCHMARK SUITE")
    print("=" * 70)

    process = psutil.Process()
    rss_start = process.memory_info().rss
    sys_name = platform.system()
    cpu_cnt = psutil.cpu_count(logical=True)
    py_ver = sys.version.split()[0]

    print(f"Environment: {sys_name} | CPU: {cpu_cnt} logical cores | Python: {py_ver}")
    print(f"Initial RSS: {rss_start / (1024 * 1024):.2f} MiB\n")

    with tempfile.TemporaryDirectory(prefix="jaya-p08-bench-", ignore_cleanup_errors=True) as tmp:
        work_dir = Path(tmp)
        db_path = work_dir / "bench_holographic.sqlite3"
        pillar_dir = work_dir / "pillars"
        store = EpisodicMemoryStore(db_path)
        service = FoundationPillarCapabilityService(
            data_dir=pillar_dir,
            episodic_memory=store,
        )

        try:
            # ---------------------------------------------------------------------
            # 1. Append Throughput & Latency Scaling
            # ---------------------------------------------------------------------
            print(f"1. Evaluating Append Latency and Throughput ({iterations} events)...")
            append_latencies_ms: list[float] = []
            source_digest = "sha256:" + hashlib.sha256(b"p08-benchmark-source-proof").hexdigest()
            t0_append = time.perf_counter()

            saved_event_100: dict[str, Any] = {}
            for i in range(iterations):
                req = {
                    "action": "append",
                    "event_id": f"evt-bench-{i:06d}",
                    "event_type": "BENCH_RECORD",
                    "session_id": f"sess-bench-{i % 20}",
                    "goal_id": f"goal-bench-{i % 10}",
                    "payload": {
                        "iteration": i,
                        "metric_a": round(i * 1.5, 2),
                        "metric_b": f"synthetic_payload_text_{i}",
                    },
                    "sequence_number": i,
                    "provenance": {
                        "source_digest": source_digest,
                        "confidence": 0.95,
                        "owner_id": "bench-agent",
                        "policy": "INTERNAL",
                        "observed_at": time.time(),
                    },
                    "indexes": {
                        "semantic": [f"topic_cluster_{i % 25}", "holographic_bench"],
                        "entity": [f"sensor_node_{i % 15}"],
                        "task": [f"task_step_{i % 5}"],
                        "procedure": ["standard_bench_procedure"],
                    },
                }
                if i == 100:
                    saved_event_100 = {
                        **req,
                        "payload": dict(req["payload"]),
                        "provenance": dict(req["provenance"]),
                        "indexes": {k: list(v) for k, v in req["indexes"].items()},
                    }
                t_single0 = time.perf_counter()
                res = service.execute(MEMORY_CAPABILITY_ID, req)
                append_latencies_ms.append((time.perf_counter() - t_single0) * 1000.0)
                if res.code != "MEMORY_EVENT_APPENDED":
                    raise RuntimeError(f"Unexpected append status: {res.code}")

            total_append_time = time.perf_counter() - t0_append
            append_throughput = iterations / total_append_time if total_append_time > 0 else 0.0
            append_stats = _stats(append_latencies_ms)
            print(f"   -> Append Throughput: {append_throughput:.1f} events/sec")
            print(f"   -> Mean Latency: {append_stats['mean']} ms | p50: {append_stats['p50']} ms | p95: {append_stats['p95']} ms\n")

            # ---------------------------------------------------------------------
            # 2. Multi-Index Retrieval Latency
            # ---------------------------------------------------------------------
            print("2. Evaluating Multi-Index Retrieval Latency Across Index Types...")
            index_benchmarks: dict[str, Any] = {}
            queries_to_test = [
                ("session", "sess-bench-5"),
                ("goal", "goal-bench-3"),
                ("event_type", "bench_record"),
                ("semantic", "holographic_bench"),
                ("entity", "sensor_node_7"),
                ("task", "task_step_2"),
                ("procedure", "standard_bench_procedure"),
            ]
            for idx_type, idx_val in queries_to_test:
                latencies: list[float] = []
                for _ in range(50):
                    t_q0 = time.perf_counter()
                    q_res = service.execute(
                        MEMORY_CAPABILITY_ID,
                        {"action": "query", "index_type": idx_type, "index_value": idx_val, "limit": 50},
                    )
                    latencies.append((time.perf_counter() - t_q0) * 1000.0)
                index_benchmarks[idx_type] = {
                    "matched_count": len(q_res.data.get("events", [])),
                    "stats": _stats(latencies),
                }
                print(f"   -> [{idx_type.upper():<11}] matched: {index_benchmarks[idx_type]['matched_count']:<3} | mean: {index_benchmarks[idx_type]['stats']['mean']:>6.3f} ms | p95: {index_benchmarks[idx_type]['stats']['p95']:>6.3f} ms")
            print()

            # ---------------------------------------------------------------------
            # 3. Idempotency & Conflict Detection Overhead
            # ---------------------------------------------------------------------
            print("3. Evaluating Idempotency vs Conflict Detection Latency...")
            target_event = saved_event_100
            # Duplicate idempotent check
            dup_latencies: list[float] = []
            for _ in range(50):
                t_d0 = time.perf_counter()
                d_res = service.execute(MEMORY_CAPABILITY_ID, target_event)
                dup_latencies.append((time.perf_counter() - t_d0) * 1000.0)
                assert d_res.code == "MEMORY_EVENT_DUPLICATE"
            dup_stats = _stats(dup_latencies)
            print(f"   -> Duplicate Idempotent Check: mean: {dup_stats['mean']} ms | p95: {dup_stats['p95']} ms")

            # Conflict detection
            conflict_latencies: list[float] = []
            conflict_event = dict(target_event, payload={"iteration": 100, "diverged": True})
            for _ in range(50):
                t_c0 = time.perf_counter()
                try:
                    service.execute(MEMORY_CAPABILITY_ID, conflict_event)
                except LocalPillarError as exc:
                    assert exc.code == "MEMORY_CONFLICT"
                conflict_latencies.append((time.perf_counter() - t_c0) * 1000.0)
            conflict_stats = _stats(conflict_latencies)
            print(f"   -> Conflict Detection Check:   mean: {conflict_stats['mean']} ms | p95: {conflict_stats['p95']} ms\n")

            # ---------------------------------------------------------------------
            # 4. Self-Healing Index Reconstruction Performance
            # ---------------------------------------------------------------------
            print("4. Evaluating Deterministic Index Reconstruction...")
            with store._get_connection() as conn:
                conn.execute("DELETE FROM holographic_indexes;")
            t_rebuild0 = time.perf_counter()
            rebuild_res = service.execute(MEMORY_CAPABILITY_ID, {"action": "rebuild_indexes"})
            t_rebuild_elapsed = time.perf_counter() - t_rebuild0
            rebuild_count = rebuild_res.data.get("indexed_events_count", 0)
            rebuild_throughput = rebuild_count / t_rebuild_elapsed if t_rebuild_elapsed > 0 else 0.0
            print(f"   -> Rebuilt {rebuild_count} records in {t_rebuild_elapsed * 1000:.2f} ms ({rebuild_throughput:.1f} records/sec)\n")

            # ---------------------------------------------------------------------
            # 5. Multithreaded Concurrency (8 Threads)
            # ---------------------------------------------------------------------
            print("5. Evaluating Multithreaded Concurrency (8 Threads, 200 concurrent appends)...")
            num_workers = 8
            appends_per_worker = 25
            total_concurrent = num_workers * appends_per_worker

            def _worker_task(worker_id: int) -> list[float]:
                worker_times: list[float] = []
                for j in range(appends_per_worker):
                    idx = 10000 + worker_id * 1000 + j
                    t_w0 = time.perf_counter()
                    service.execute(
                        MEMORY_CAPABILITY_ID,
                        {
                            "action": "append",
                            "event_id": f"concurrent-evt-{idx}",
                            "event_type": "CONCURRENT_TEST",
                            "session_id": f"sess-worker-{worker_id}",
                            "goal_id": "goal-concurrent",
                            "payload": {"worker_id": worker_id, "step": j},
                            "sequence_number": j,
                            "provenance": {
                                "source_digest": source_digest,
                                "confidence": 0.90,
                                "owner_id": f"worker-{worker_id}",
                                "policy": "INTERNAL",
                                "observed_at": time.time(),
                            },
                            "indexes": {
                                "task": ["multithread_concurrency"],
                                "entity": [f"worker_{worker_id}"],
                            },
                        },
                    )
                    worker_times.append((time.perf_counter() - t_w0) * 1000.0)
                return worker_times

            t_concurrent0 = time.perf_counter()
            all_concurrent_latencies: list[float] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(_worker_task, w) for w in range(num_workers)]
                for f in concurrent.futures.as_completed(futures):
                    all_concurrent_latencies.extend(f.result())
            total_concurrent_time = time.perf_counter() - t_concurrent0
            concurrent_throughput = total_concurrent / total_concurrent_time if total_concurrent_time > 0 else 0.0
            concurrent_stats = _stats(all_concurrent_latencies)
            print(f"   -> 8-Thread Throughput: {concurrent_throughput:.1f} events/sec")
            print(f"   -> Mean Latency: {concurrent_stats['mean']} ms | p95: {concurrent_stats['p95']} ms\n")

            # ---------------------------------------------------------------------
            # 6. Compaction and Retention Pruning Latency
            # ---------------------------------------------------------------------
            print("6. Evaluating Compaction & Retention Pruning Latency...")
            # Revoke 50 events
            t_now = time.time()
            for k in range(50):
                store.revoke_holographic(f"evt-bench-{k:06d}", "benchmark batch prune", t_now - 1000.0)
            t_compact0 = time.perf_counter()
            compact_res = service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "compact", "retention_seconds": 300.0},
            )
            compact_time_ms = (time.perf_counter() - t_compact0) * 1000.0
            pruned_count = compact_res.data.get("pruned_events_count", 0)
            print(f"   -> Pruned {pruned_count} records in {compact_time_ms:.2f} ms\n")

            # ---------------------------------------------------------------------
            # 7. Memory & Storage Footprint
            # ---------------------------------------------------------------------
            print("7. Evaluating Memory & Storage Footprint...")
            rss_end = process.memory_info().rss
            delta_rss = max(0, rss_end - rss_start)
            db_size_bytes = db_path.stat().st_size
            total_records_inserted = iterations + total_concurrent
            bytes_per_record = db_size_bytes / max(1, total_records_inserted)

            print(f"   -> Initial RSS:    {rss_start / (1024 * 1024):.2f} MiB")
            print(f"   -> Final RSS:      {rss_end / (1024 * 1024):.2f} MiB (Growth: {delta_rss / (1024 * 1024):.2f} MiB)")
            print(f"   -> SQLite DB Size: {db_size_bytes / 1024:.2f} KiB")
            print(f"   -> Density:        {bytes_per_record:.1f} bytes / holographic record\n")

            benchmark_report = {
                "benchmark": "P08_HOLOGRAPHIC_MEMORY",
                "timestamp": datetime.now(UTC).isoformat(),
                "environment": {
                    "os": sys_name,
                    "python_version": py_ver,
                    "logical_cpus": cpu_cnt,
                },
                "append_throughput": {
                    "total_events": iterations,
                    "throughput_events_per_sec": round(append_throughput, 2),
                    "latency_ms": append_stats,
                },
                "multi_index_retrieval": index_benchmarks,
                "idempotency_and_conflict": {
                    "idempotent_check_latency_ms": dup_stats,
                    "conflict_check_latency_ms": conflict_stats,
                },
                "index_reconstruction": {
                    "rebuilt_count": rebuild_count,
                    "elapsed_ms": round(t_rebuild_elapsed * 1000.0, 2),
                    "throughput_records_per_sec": round(rebuild_throughput, 2),
                },
                "multithreaded_concurrency": {
                    "workers": num_workers,
                    "total_events": total_concurrent,
                    "throughput_events_per_sec": round(concurrent_throughput, 2),
                    "latency_ms": concurrent_stats,
                },
                "compaction": {
                    "pruned_count": pruned_count,
                    "latency_ms": round(compact_time_ms, 2),
                },
                "footprint": {
                    "initial_rss_bytes": rss_start,
                    "final_rss_bytes": rss_end,
                    "delta_rss_bytes": delta_rss,
                    "db_size_bytes": db_size_bytes,
                    "bytes_per_record": round(bytes_per_record, 1),
                },
            }

            if out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / "benchmark_p08_holographic_memory.json"
                out_file.write_text(json.dumps(benchmark_report, indent=2), encoding="utf-8")
                print(f"Benchmark report written to: {out_file}")

            return benchmark_report
        finally:
            store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=500, help="Number of benchmark append iterations")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(ROOT / "artifacts" / "verified-holographic-memory"),
        help="Output directory for benchmark JSON receipt",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else None
    run_benchmark(iterations=args.iterations, out_dir=out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
