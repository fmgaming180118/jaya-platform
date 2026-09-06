#!/usr/bin/env python3
"""Benchmark suite for Pillar 30: Twin Protocol."""

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
from jaya_core.pillars.distributed_capabilities import (  # noqa: E402
    TWIN_TRANSFER_CAPABILITY_ID,
    TwinMigrationCapability,
)

BENCH_SECRET = "benchmark-twin-shared-secret-must-have-thirty-two-chars!"


def run_benchmark(iterations: int = 25) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_bench_p30_"))
    node_a_root = temp_dir / "node-a"
    node_b_root = temp_dir / "node-b"
    node_a_root.mkdir(parents=True, exist_ok=True)
    node_b_root.mkdir(parents=True, exist_ok=True)

    sender = TwinMigrationCapability(
        node_id="node-a",
        root=node_a_root,
        database_path=node_a_root / "twin.sqlite3",
        shared_secret=BENCH_SECRET,
        allowed_peers=("node-b",),
    )
    receiver = TwinMigrationCapability(
        node_id="node-b",
        root=node_b_root,
        database_path=node_b_root / "twin.sqlite3",
        shared_secret=BENCH_SECRET,
        allowed_peers=("node-a",),
    )

    probe = sender.probe_transport()
    rec_res = receiver.execute({"action": "start_receiver", "port": 0}).data
    port = rec_res["port"]

    latencies_ms: list[float] = []
    total_bytes_transferred = 0

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
    successful = 0

    try:
        for i in range(iterations):
            chunk_bytes = 64 * 1024  # 64 KB per test file
            content = os.urandom(chunk_bytes)
            source_file = f"bench_{i}.bin"
            (node_a_root / source_file).write_bytes(content)

            t0 = time.perf_counter()
            try:
                res = sender.execute({
                    "action": "send_batch",
                    "host": "127.0.0.1",
                    "port": port,
                    "transfer_id": f"tx-bench-{i}",
                    "source_path": source_file,
                    "target_node_id": "node-b",
                    "brain_id": f"brain-bench-{i}",
                    "destination_name": f"dest_{i}.bin",
                })
                dur = (time.perf_counter() - t0) * 1000.0
                if res.data["complete"]:
                    successful += 1
                    total_bytes_transferred += chunk_bytes
                latencies_ms.append(dur)
            except Exception:
                dur = (time.perf_counter() - t0) * 1000.0
                latencies_ms.append(dur)
    finally:
        sender.close()
        receiver.close()

    total_bench_duration_s = time.perf_counter() - start_wall

    energy_joules = total_bench_duration_s * 28.0
    if meter is not None and start_sample is not None:
        try:
            end_sample = meter.sample()
            measured = meter.measure(start_sample, end_sample)
            energy_joules = measured.joules or (total_bench_duration_s * 28.0)
        except EnergyMeterError:
            pass

    rss_final = process.memory_info().rss
    rss_growth = max(0, rss_final - rss_initial)
    db_a_size = (node_a_root / "twin.sqlite3").stat().st_size if (node_a_root / "twin.sqlite3").exists() else 0
    db_b_size = (node_b_root / "twin.sqlite3").stat().st_size if (node_b_root / "twin.sqlite3").exists() else 0
    total_db_bytes = db_a_size + db_b_size

    results = {
        "pillar_id": 30,
        "capability_id": TWIN_TRANSFER_CAPABILITY_ID,
        "iterations": iterations,
        "successful": successful,
        "completion_rate": round(successful / iterations, 4),
        "transport_probe": probe,
        "total_transferred_kb": round(total_bytes_transferred / 1024, 2),
        "transfer_throughput_kb_per_sec": round((total_bytes_transferred / 1024) / max(0.001, total_bench_duration_s), 2),
        "latency_cycle_ms": {
            "mean": round(float(np.mean(latencies_ms)), 3),
            "median": round(float(np.median(latencies_ms)), 3),
            "p95": round(float(np.percentile(latencies_ms, 95)), 3),
            "p99": round(float(np.percentile(latencies_ms, 99)), 3),
            "min": round(float(np.min(latencies_ms)), 3),
            "max": round(float(np.max(latencies_ms)), 3),
        },
        "throughput": {
            "cycles_per_sec": round(iterations / total_bench_duration_s, 2),
            "total_duration_seconds": round(total_bench_duration_s, 3),
        },
        "resource": {
            "initial_rss_bytes": rss_initial,
            "final_rss_bytes": rss_final,
            "rss_growth_bytes": rss_growth,
            "database_size_bytes": total_db_bytes,
            "database_bytes_per_cycle": round(total_db_bytes / max(1, iterations), 2),
        },
        "energy": {
            "total_joules": round(energy_joules, 4),
            "joules_per_cycle": round(energy_joules / max(1, iterations), 6),
            "method": energy_method,
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    del sender
    del receiver
    gc.collect()
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Pillar 30 Twin Protocol Benchmark Suite")
    parser.add_argument("--iterations", type=int, default=25, help="Number of benchmark iterations (default: 25)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path for benchmark results")
    args = parser.parse_args()

    print(f"Starting Pillar 30 Twin Protocol benchmark ({args.iterations} iterations)...")
    results = run_benchmark(iterations=args.iterations)

    print("\n" + "=" * 65)
    print("  PILAR 30: TWIN PROTOCOL BENCHMARK RESULTS")
    print("=" * 65)
    print(f"  Iterations:          {results['iterations']}")
    print(f"  Completion Rate:     {results['completion_rate'] * 100:.1f}%")
    print(f"  Cycle Latency Mean:  {results['latency_cycle_ms']['mean']:.3f} ms")
    print(f"  Cycle Latency p50:   {results['latency_cycle_ms']['median']:.3f} ms")
    print(f"  Cycle Latency p95:   {results['latency_cycle_ms']['p95']:.3f} ms")
    print(f"  Throughput:          {results['throughput']['cycles_per_sec']} cycles/sec")
    print(f"  Network Throughput:  {results['transfer_throughput_kb_per_sec']} KB/sec")
    print(f"  Total Transferred:   {results['total_transferred_kb']} KB")
    print(f"  RSS Growth:          {results['resource']['rss_growth_bytes'] / (1024 * 1024):.2f} MB")
    print(f"  Energy Consumption:  {results['energy']['total_joules']} J ({results['energy']['joules_per_cycle']} J/cycle, {results['energy']['method']})")
    print("=" * 65)

    out_file = Path(args.output) if args.output else ROOT / "artifacts" / "benchmark_p30_twin_protocol.json"
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
