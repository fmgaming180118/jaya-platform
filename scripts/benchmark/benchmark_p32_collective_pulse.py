#!/usr/bin/env python3
"""Benchmark suite for Pilar 32: Collective Pulse (core.collective.pulse)."""

from __future__ import annotations

import argparse
import json
import os
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

from jaya_core.observability.energy_meter import WindowsEmiEnergyMeter  # noqa: E402
from jaya_core.pillars.distributed_capabilities import CollectiveEvidenceCapability  # noqa: E402
from jaya_core.pillars.reasoning_capabilities import AgenticRAGCapability  # noqa: E402

DEFAULT_SHARED_SECRET = "jaya-collective-pulse-bench-key-32b-secret!"


def _setup_node(temp_dir: Path, node_id: str, allowed_peers: tuple[str, ...]) -> tuple[CollectiveEvidenceCapability, str]:
    node_dir = temp_dir / node_id
    node_dir.mkdir(parents=True, exist_ok=True)
    rag = AgenticRAGCapability(node_dir / "rag.sqlite3", None)
    rag.execute({
        "action": "ingest",
        "source_ref": "collective-bench-v1",
        "title": "Benchmark Evidence Policy",
        "content": "Benchmark evidence payload for measuring collective pulse throughput and latency.",
    })
    evidence_id = rag.retrieve("benchmark evidence payload", 1)[0]["evidence_id"]
    cap = CollectiveEvidenceCapability(
        node_id=node_id,
        database_path=node_dir / "collective.sqlite3",
        shared_secret=DEFAULT_SHARED_SECRET,
        allowed_peers=allowed_peers,
        rag=rag,
    )
    return cap, evidence_id


def run_benchmark(iterations: int = 25, output_file: Path | None = None) -> dict:
    print(f"Starting Pillar 32 Collective Pulse benchmark ({iterations} iterations)...")

    with tempfile.TemporaryDirectory(prefix="jaya_bench_p32_") as tmp:
        temp_dir = Path(tmp)
        node_a, evidence_a = _setup_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, evidence_b = _setup_node(temp_dir, "node-b", ("node-a", "node-c"))
        node_c, evidence_c = _setup_node(temp_dir, "node-c", ("node-a", "node-b"))

        latencies_ms: list[float] = []
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

        for i in range(iterations):
            t0 = time.perf_counter()
            try:
                consent_a = node_a.execute({
                    "action": "issue_consent",
                    "evidence_id": evidence_a,
                    "max_privacy_budget": 0.2,
                    "expires_at": time.time() + 3600,
                }).data["receipt"]

                packet_a = node_a.execute({
                    "action": "create",
                    "evidence_id": evidence_a,
                    "value": 0.70 + (i % 10) * 0.01,
                    "trust": 0.9,
                    "quality": 0.9,
                    "privacy_budget": 0.05,
                    "consent_receipt": consent_a,
                }).data["packet"]

                consent_c = node_c.execute({
                    "action": "issue_consent",
                    "evidence_id": evidence_c,
                    "max_privacy_budget": 0.2,
                    "expires_at": time.time() + 3600,
                }).data["receipt"]

                packet_c = node_c.execute({
                    "action": "create",
                    "evidence_id": evidence_c,
                    "value": 0.80 + (i % 10) * 0.01,
                    "trust": 0.9,
                    "quality": 0.9,
                    "privacy_budget": 0.05,
                    "consent_receipt": consent_c,
                }).data["packet"]

                node_b.execute({"action": "ingest", "packet": packet_a})
                node_b.execute({"action": "ingest", "packet": packet_c})

                agg = node_b.execute({
                    "action": "aggregate",
                    "local_evidence_id": evidence_b,
                    "local_value": 0.75,
                }).data

                dur = (time.perf_counter() - t0) * 1000.0
                if agg["peer_count"] == 2:
                    successful += 1
                latencies_ms.append(dur)
            except Exception:
                dur = (time.perf_counter() - t0) * 1000.0
                latencies_ms.append(dur)

        total_bench_duration_s = time.perf_counter() - start_wall
        rss_final = process.memory_info().rss
        rss_growth_bytes = max(0, rss_final - rss_initial)

        total_energy_joules = total_bench_duration_s * 28.0  # fallback estimated
        if meter is not None and start_sample is not None:
            try:
                end_sample = meter.sample()
                reading = meter.measure(start_sample, end_sample)
                total_energy_joules = reading.joules
            except Exception:
                pass

        completion_rate = successful / iterations
        throughput_cycles_sec = iterations / total_bench_duration_s if total_bench_duration_s > 0 else 0

        mean_lat = float(np.mean(latencies_ms)) if latencies_ms else 0.0
        p50_lat = float(np.percentile(latencies_ms, 50)) if latencies_ms else 0.0
        p95_lat = float(np.percentile(latencies_ms, 95)) if latencies_ms else 0.0

        results = {
            "pillar_id": 32,
            "pillar_name": "Collective Pulse",
            "capability_id": "core.collective.pulse",
            "iterations": iterations,
            "successful_cycles": successful,
            "completion_rate": completion_rate,
            "latency_ms": {
                "mean": round(mean_lat, 3),
                "p50": round(p50_lat, 3),
                "p95": round(p95_lat, 3),
            },
            "throughput_cycles_per_sec": round(throughput_cycles_sec, 2),
            "total_duration_s": round(total_bench_duration_s, 4),
            "memory": {
                "initial_rss_bytes": rss_initial,
                "final_rss_bytes": rss_final,
                "growth_rss_bytes": rss_growth_bytes,
                "growth_rss_mb": round(rss_growth_bytes / (1024 * 1024), 2),
            },
            "energy": {
                "method": energy_method,
                "total_joules": round(total_energy_joules, 4),
                "joules_per_cycle": round(total_energy_joules / iterations, 6) if iterations else 0.0,
            },
        }

        print("\n" + "=" * 65)
        print("  PILAR 32: COLLECTIVE PULSE BENCHMARK RESULTS")
        print("=" * 65)
        print(f"  Iterations:          {iterations}")
        print(f"  Completion Rate:     {completion_rate * 100:.1f}%")
        print(f"  Cycle Latency Mean:  {results['latency_ms']['mean']} ms")
        print(f"  Cycle Latency p50:   {results['latency_ms']['p50']} ms")
        print(f"  Cycle Latency p95:   {results['latency_ms']['p95']} ms")
        print(f"  Throughput:          {results['throughput_cycles_per_sec']} cycles/sec")
        print(f"  RSS Growth:          {results['memory']['growth_rss_mb']} MB")
        print(f"  Energy Consumption:  {results['energy']['total_joules']} J ({results['energy']['joules_per_cycle']} J/cycle, {energy_method})")
        print("=" * 65)

        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(f"Results saved to: {output_file}")

        return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=25, help="Number of benchmark cycles")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "benchmark_p32_collective_pulse.json",
        help="Path to save benchmark JSON",
    )
    args = parser.parse_args()
    results = run_benchmark(iterations=args.iterations, output_file=args.output)
    return 0 if results["completion_rate"] >= 0.95 else 1


if __name__ == "__main__":
    sys.exit(main())
