#!/usr/bin/env python3
"""Dedicated benchmark suite for Pillar 25 Digital Epigenetics."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars.local_capabilities import DigitalEpigeneticsService

SIGNING_KEY = bytes(range(32))


def run_benchmark(iterations: int = 5000) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_epigenetics_"))
    db_path = temp_dir / "lineage_bench.sqlite3"
    service = DigitalEpigeneticsService(db_path, SIGNING_KEY)

    proc = psutil.Process()
    rss_start = proc.memory_info().rss

    energy_meter = WindowsEmiEnergyMeter()
    energy_start = None
    try:
        energy_start = energy_meter.sample()
    except EnergyMeterError:
        energy_start = None

    # 1. Append Benchmark
    append_latencies = []
    t_append_start = time.perf_counter()
    for i in range(iterations):
        t0 = time.perf_counter()
        service.append(
            generation_id=f"bench-gen-{i:06d}",
            payload={"batch_size": (i % 32) + 1, "metric": 0.85 + (i % 100) / 1000.0},
            evidence_refs=[f"artifact:bench-{i}"],
            approval_ref="approval:benchmarker",
            signer_id="bench:operator",
        )
        append_latencies.append((time.perf_counter() - t0) * 1000.0)
    t_append_elapsed = time.perf_counter() - t_append_start

    # 2. Get / Read Benchmark
    get_latencies = []
    t_get_start = time.perf_counter()
    for i in range(min(iterations, 2000)):
        gen_id = f"bench-gen-{i:06d}"
        t0 = time.perf_counter()
        service.get(gen_id)
        get_latencies.append((time.perf_counter() - t0) * 1000.0)
    t_get_elapsed = time.perf_counter() - t_get_start

    # 3. List Benchmark
    list_latencies = []
    t_list_start = time.perf_counter()
    for i in range(min(iterations // 5, 500)):
        offset = (i * 10) % (iterations - 50)
        t0 = time.perf_counter()
        service.list_entries(limit=50, offset=offset)
        list_latencies.append((time.perf_counter() - t0) * 1000.0)
    t_list_elapsed = time.perf_counter() - t_list_start

    # 4. Rollback Benchmark
    rollback_latencies = []
    t_rb_start = time.perf_counter()
    for i in range(min(iterations // 10, 200)):
        target = f"bench-gen-{(i * 13) % iterations:06d}"
        t0 = time.perf_counter()
        service.rollback(
            target_generation_id=target,
            approval_ref="approval:rollback-bench",
            generation_id=f"bench-rb-{i:04d}",
        )
        rollback_latencies.append((time.perf_counter() - t0) * 1000.0)
    t_rb_elapsed = time.perf_counter() - t_rb_start

    # 5. Full Chain Verification Benchmark
    t_ver_start = time.perf_counter()
    ver_result = service.verify().data
    t_ver_elapsed = time.perf_counter() - t_ver_start

    # Metrics
    rss_end = proc.memory_info().rss
    rss_growth = max(0, rss_end - rss_start)
    db_size = db_path.stat().st_size
    total_records = ver_result["entries"]
    bytes_per_record = db_size / total_records if total_records > 0 else 0.0

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
        "pillar": "P025",
        "name": "Digital Epigenetics",
        "iterations": iterations,
        "total_records_in_chain": total_records,
        "append": {
            "elapsed_seconds": round(t_append_elapsed, 4),
            "throughput_ops_sec": round(iterations / t_append_elapsed, 2),
            "mean_ms": round(float(np.mean(append_latencies)), 4),
            "p50_ms": round(float(np.percentile(append_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(append_latencies, 95)), 4),
            "p99_ms": round(float(np.percentile(append_latencies, 99)), 4),
        },
        "get": {
            "elapsed_seconds": round(t_get_elapsed, 4),
            "throughput_ops_sec": round(len(get_latencies) / t_get_elapsed, 2),
            "mean_ms": round(float(np.mean(get_latencies)), 4),
            "p50_ms": round(float(np.percentile(get_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(get_latencies, 95)), 4),
            "p99_ms": round(float(np.percentile(get_latencies, 99)), 4),
        },
        "list": {
            "elapsed_seconds": round(t_list_elapsed, 4),
            "throughput_ops_sec": round(len(list_latencies) / t_list_elapsed, 2),
            "mean_ms": round(float(np.mean(list_latencies)), 4),
            "p50_ms": round(float(np.percentile(list_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(list_latencies, 95)), 4),
            "p99_ms": round(float(np.percentile(list_latencies, 99)), 4),
        },
        "rollback": {
            "elapsed_seconds": round(t_rb_elapsed, 4),
            "throughput_ops_sec": round(len(rollback_latencies) / t_rb_elapsed, 2),
            "mean_ms": round(float(np.mean(rollback_latencies)), 4),
            "p50_ms": round(float(np.percentile(rollback_latencies, 50)), 4),
            "p95_ms": round(float(np.percentile(rollback_latencies, 95)), 4),
            "p99_ms": round(float(np.percentile(rollback_latencies, 99)), 4),
        },
        "verification": {
            "total_entries": total_records,
            "elapsed_seconds": round(t_ver_elapsed, 4),
            "entries_per_sec": round(total_records / t_ver_elapsed, 2),
        },
        "resource": {
            "rss_growth_bytes": rss_growth,
            "database_size_bytes": db_size,
            "bytes_per_record": round(bytes_per_record, 2),
            "total_package_joules": round(package_joules, 4),
            "joules_per_operation": round(package_joules / (iterations + len(rollback_latencies)), 6) if package_joules > 0 else 0.0,
        },
    }

    out_dir = ROOT / "artifacts" / "verified-digital-epigenetics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "benchmark_p25_digital_epigenetics.json"
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Benchmark artifact saved: {out_file}")
    return results


def main() -> int:
    print("=" * 70)
    print(" JAYA COGNITIVE ARCHITECTURE — PILAR 25 BENCHMARK")
    print("=" * 70)
    results = run_benchmark(iterations=1000)
    print(f"\nTotal Entries: {results['total_records_in_chain']}")
    print(f"Append Throughput:  {results['append']['throughput_ops_sec']} ops/sec (mean: {results['append']['mean_ms']} ms, p95: {results['append']['p95_ms']} ms)")
    print(f"Get Throughput:     {results['get']['throughput_ops_sec']} ops/sec (mean: {results['get']['mean_ms']} ms, p95: {results['get']['p95_ms']} ms)")
    print(f"List Throughput:    {results['list']['throughput_ops_sec']} ops/sec (mean: {results['list']['mean_ms']} ms, p95: {results['list']['p95_ms']} ms)")
    print(f"Rollback Throughput:{results['rollback']['throughput_ops_sec']} ops/sec (mean: {results['rollback']['mean_ms']} ms, p95: {results['rollback']['p95_ms']} ms)")
    print(f"Full Verification:  {results['verification']['entries_per_sec']} entries/sec ({results['verification']['elapsed_seconds']}s for {results['verification']['total_entries']} entries)")
    print(f"Database Record Size: {results['resource']['bytes_per_record']} bytes/rec")
    print(f"RSS Memory Growth:    {results['resource']['rss_growth_bytes']} bytes")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
