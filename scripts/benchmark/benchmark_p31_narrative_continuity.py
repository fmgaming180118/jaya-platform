#!/usr/bin/env python3
"""benchmark_p31_narrative_continuity.py — Quantitative Performance & Cryptographic Integrity Benchmark for P31 Narrative Continuity.

Measures:
1. Environment Baseline:
   - Platform, CPU count, Python version, initial RSS memory.
2. Signed Append Throughput & Latency Scaling:
   - Evaluates append operations with DNA Anchor Ed25519 signatures across distinct narrative event types
     (CONVERSATION_TURN, FACT_ASSERTED, COMMITMENT_CREATED, INFERENCE_RECORDED, CORRECTION_RECORDED).
   - Latency distribution (mean, p50, p95, p99, min, max, stddev) and throughput (events/sec).
3. Cryptographic Chain Integrity Verification:
   - Full-chain SHA-256 hash-chain and Ed25519 signature audit throughput across hundreds of signed records.
4. Conflict Detection & Correction Latency:
   - Latency to detect conflicting facts on identical subjects.
   - Latency to resolve conflicts via evidence-bound correction links.
5. Snapshot & Boot Context Generation:
   - Latency to construct deterministic bounded narrative snapshots and boot contexts across restarts.
6. Multithreaded Concurrency (8 Threads):
   - 8 concurrent threads appending signed narrative events into SQLite.
7. Memory & Storage Footprint:
   - Initial RSS, final RSS, delta RSS, SQLite file size, and storage density per signed event.
   - CPU package energy per event via EnergyMeter if available.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
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

from jaya_core.brain_v2.engine.narrative_continuity import (  # noqa: E402
    DNAAnchorNarrativeSigner,
    NarrativeContinuity,
    NarrativeEventType,
    NarrativeTruthClass,
)
from jaya_core.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    EncryptedFileKeyStore,
)
from jaya_core.observability.energy_meter import (  # noqa: E402
    EnergyMeterError,
    WindowsEmiEnergyMeter,
)


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
    print("=" * 75)
    print(" PILAR 31: NARRATIVE CONTINUITY — QUANTITATIVE BENCHMARK SUITE")
    print("=" * 75)

    process = psutil.Process()
    rss_start = process.memory_info().rss
    sys_name = platform.system()
    cpu_cnt = psutil.cpu_count(logical=True)
    py_ver = sys.version.split()[0]

    print(f"Environment: {sys_name} | CPU: {cpu_cnt} logical cores | Python: {py_ver}")
    print(f"Initial RSS: {rss_start / (1024 * 1024):.2f} MiB\n")

    with tempfile.TemporaryDirectory(prefix="jaya-p31-bench-", ignore_cleanup_errors=True) as tmp:
        work_dir = Path(tmp)
        identity_dir = work_dir / "identity"
        keystore_dir = identity_dir / "keystore"
        ledger_path = work_dir / "bench_narrative.sqlite3"

        secret = "benchmark-p31-secret-material-32-bytes-long!!"
        anchor = DNAAnchor(identity_dir, EncryptedFileKeyStore(keystore_dir, secret))
        anchor.enroll()
        signer = DNAAnchorNarrativeSigner(anchor)
        ledger = NarrativeContinuity(ledger_path, signer)

        energy_meter = WindowsEmiEnergyMeter() if platform.system() == "Windows" else None
        energy_sample_start = None
        if energy_meter is not None:
            try:
                energy_sample_start = energy_meter.sample()
            except Exception:
                energy_sample_start = None

        try:
            # ---------------------------------------------------------------------
            # 1. Signed Append Latency & Throughput Scaling
            # ---------------------------------------------------------------------
            print(f"1. Evaluating Signed Append Latency and Throughput ({iterations} events)...")
            # Register common evidence
            ev_ref = ledger.register_evidence(
                content=b"bench evidence material for signed facts",
                source_uri="memory://bench-evidence-source",
                media_type="text/plain",
            )

            append_latencies_ms: list[float] = []
            t0_append = time.perf_counter()

            for i in range(iterations):
                t_single0 = time.perf_counter()
                mod = i % 5
                if mod == 0:
                    ledger.remember_turn(
                        f"User request turn #{i}",
                        request_id=f"bench-turn-{i:06d}",
                    )
                elif mod == 1:
                    ledger.record_verified_fact(
                        request_id=f"bench-fact-{i:06d}",
                        subject=f"system.metric_{i % 20}",
                        value=f"value_{i}",
                        evidence_refs=(ev_ref,),
                    )
                elif mod == 2:
                    ledger.record_commitment(
                        request_id=f"bench-commit-{i:06d}",
                        commitment_id=f"commitment:task_{i % 15}",
                        subject=f"system.task_{i % 15}",
                        details={"iteration": i, "state": "active"},
                        evidence_refs=(ev_ref,),
                    )
                elif mod == 3:
                    ledger.record_inference(
                        request_id=f"bench-infer-{i:06d}",
                        subject=f"system.metric_{i % 20}",
                        inference={"hypothesis": f"inferred property {i}", "confidence": 0.85},
                        evidence_refs=(ev_ref,),
                    )
                else:
                    ledger.remember_feedback(
                        task=f"task_{i % 10}",
                        score=0.98,
                        request_id=f"bench-feedback-{i:06d}",
                    )
                append_latencies_ms.append((time.perf_counter() - t_single0) * 1000.0)

            total_append_time = time.perf_counter() - t0_append
            append_throughput = iterations / total_append_time if total_append_time > 0 else 0.0
            append_stats = _stats(append_latencies_ms)

            energy_delta_j = 0.0
            energy_per_event = 0.0
            if energy_meter is not None and energy_sample_start is not None:
                try:
                    energy_sample_end = energy_meter.sample()
                    measurement = WindowsEmiEnergyMeter.measure(energy_sample_start, energy_sample_end)
                    energy_delta_j = measurement.joules
                    energy_per_event = energy_delta_j / iterations
                except Exception:
                    pass

            print(f"   -> Append Throughput: {append_throughput:.1f} signed events/sec")
            print(f"   -> Mean Latency:      {append_stats['mean']} ms | p50: {append_stats['p50']} ms | p95: {append_stats['p95']} ms")
            if energy_delta_j > 0:
                print(f"   -> Energy Footprint:  {energy_per_event:.5f} J / signed event (total: {energy_delta_j:.2f} J)\n")
            else:
                print()

            # ---------------------------------------------------------------------
            # 2. Cryptographic Chain Integrity Verification
            # ---------------------------------------------------------------------
            print("2. Evaluating Full-Chain Cryptographic Integrity Audit Latency...")
            audit_latencies: list[float] = []
            for _ in range(5):
                t_aud0 = time.perf_counter()
                valid = ledger.verify_integrity()
                audit_latencies.append((time.perf_counter() - t_aud0) * 1000.0)
                assert valid is True
            audit_stats = _stats(audit_latencies)
            audit_records_sec = (iterations / (audit_stats["mean"] / 1000.0)) if audit_stats["mean"] > 0 else 0.0
            print(f"   -> Full-Chain Audit: {audit_stats['mean']} ms for {iterations} events ({audit_records_sec:.1f} events/sec)\n")

            # ---------------------------------------------------------------------
            # 3. Conflict Detection & Correction Latency
            # ---------------------------------------------------------------------
            print("3. Evaluating Conflict Detection & Correction Resolution Overhead...")
            conflict_subject = "bench.conflict.release"
            fact_1 = ledger.record_verified_fact(
                request_id="conflict-bench-fact-1",
                subject=conflict_subject,
                value="release_v1",
                evidence_refs=(ev_ref,),
            )
            fact_2 = ledger.record_verified_fact(
                request_id="conflict-bench-fact-2",
                subject=conflict_subject,
                value="release_v2",
                evidence_refs=(ev_ref,),
            )

            t_detect0 = time.perf_counter()
            snap_c = ledger.snapshot(limit=20, max_chars=20_000)
            t_detect_ms = (time.perf_counter() - t_detect0) * 1000.0
            assert len(snap_c["summary"].get("conflicts", [])) > 0

            t_correct0 = time.perf_counter()
            corr = ledger.record_correction(
                request_id="conflict-bench-correction",
                correction_of=fact_1.event_id,
                subject=conflict_subject,
                corrected_value="release_v2",
                evidence_refs=(ev_ref,),
                truth_class=NarrativeTruthClass.VERIFIED_FACT,
            )
            t_correct_ms = (time.perf_counter() - t_correct0) * 1000.0

            snap_resolved = ledger.snapshot(limit=20, max_chars=20_000)
            conflicts_remaining = [
                c for c in snap_resolved["summary"].get("conflicts", [])
                if c["subject"] == conflict_subject
            ]
            assert len(conflicts_remaining) == 0

            print(f"   -> Conflict Detection (Snapshot): {t_detect_ms:.3f} ms")
            print(f"   -> Correction Recording:          {t_correct_ms:.3f} ms\n")

            # ---------------------------------------------------------------------
            # 4. Snapshot & Boot Context Generation
            # ---------------------------------------------------------------------
            print("4. Evaluating Snapshot & Boot Context Generation Latency...")
            snap_latencies: list[float] = []
            for _ in range(20):
                t_s0 = time.perf_counter()
                s = ledger.snapshot(limit=10, max_chars=20_000)
                snap_latencies.append((time.perf_counter() - t_s0) * 1000.0)
            snap_stats = _stats(snap_latencies)

            boot_latencies: list[float] = []
            for _ in range(20):
                t_b0 = time.perf_counter()
                b = ledger.boot_context()
                boot_latencies.append((time.perf_counter() - t_b0) * 1000.0)
            boot_stats = _stats(boot_latencies)

            print(f"   -> Snapshot Generation: mean: {snap_stats['mean']} ms | p95: {snap_stats['p95']} ms")
            print(f"   -> Boot Context Extraction: mean: {boot_stats['mean']} ms | p95: {boot_stats['p95']} ms\n")

            # ---------------------------------------------------------------------
            # 5. Multithreaded Concurrency (8 Threads)
            # ---------------------------------------------------------------------
            print("5. Evaluating Multithreaded Concurrency (8 Threads, 200 concurrent appends)...")
            num_workers = 8
            events_per_worker = 25
            total_concurrent = num_workers * events_per_worker

            def _worker_task(worker_id: int) -> list[float]:
                worker_times: list[float] = []
                for j in range(events_per_worker):
                    idx = 50000 + worker_id * 1000 + j
                    t_w0 = time.perf_counter()
                    ledger.remember_turn(
                        f"Concurrent turn worker {worker_id} step {j}",
                        request_id=f"concurrent-turn-{idx}",
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
            print(f"   -> Mean Latency:        {concurrent_stats['mean']} ms | p95: {concurrent_stats['p95']} ms\n")

            # ---------------------------------------------------------------------
            # 6. Memory & Storage Footprint
            # ---------------------------------------------------------------------
            print("6. Evaluating Memory & Storage Footprint...")
            rss_end = process.memory_info().rss
            delta_rss = max(0, rss_end - rss_start)
            db_size_bytes = ledger_path.stat().st_size
            total_records = iterations + total_concurrent + 3
            bytes_per_event = db_size_bytes / max(1, total_records)

            print(f"   -> Initial RSS:    {rss_start / (1024 * 1024):.2f} MiB")
            print(f"   -> Final RSS:      {rss_end / (1024 * 1024):.2f} MiB (Growth: {delta_rss / (1024 * 1024):.2f} MiB)")
            print(f"   -> SQLite DB Size: {db_size_bytes / 1024:.2f} KiB")
            print(f"   -> Density:        {bytes_per_event:.1f} bytes / signed event\n")

            benchmark_report = {
                "benchmark": "P31_NARRATIVE_CONTINUITY",
                "timestamp": datetime.now(UTC).isoformat(),
                "environment": {
                    "os": sys_name,
                    "python_version": py_ver,
                    "logical_cpus": cpu_cnt,
                    "signer_actor_id": signer.actor_id,
                },
                "signed_append_throughput": {
                    "total_events": iterations,
                    "throughput_events_per_sec": round(append_throughput, 2),
                    "latency_ms": append_stats,
                    "package_energy_joules_per_event": round(energy_per_event, 5) if energy_delta_j > 0 else None,
                },
                "cryptographic_integrity_audit": {
                    "total_audited_events": iterations,
                    "audit_time_ms": audit_stats,
                    "throughput_events_per_sec": round(audit_records_sec, 2),
                },
                "conflict_and_correction": {
                    "detection_latency_ms": round(t_detect_ms, 3),
                    "correction_latency_ms": round(t_correct_ms, 3),
                },
                "snapshot_and_boot": {
                    "snapshot_latency_ms": snap_stats,
                    "boot_context_latency_ms": boot_stats,
                },
                "multithreaded_concurrency": {
                    "workers": num_workers,
                    "total_events": total_concurrent,
                    "throughput_events_per_sec": round(concurrent_throughput, 2),
                    "latency_ms": concurrent_stats,
                },
                "footprint": {
                    "initial_rss_bytes": rss_start,
                    "final_rss_bytes": rss_end,
                    "delta_rss_bytes": delta_rss,
                    "db_size_bytes": db_size_bytes,
                    "bytes_per_event": round(bytes_per_event, 1),
                },
            }

            if out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / "benchmark_p31_narrative_continuity.json"
                out_file.write_text(json.dumps(benchmark_report, indent=2), encoding="utf-8")
                print(f"Benchmark report written to: {out_file}")

            return benchmark_report

        finally:
            ledger.close()
            anchor.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=500, help="Number of benchmark append iterations")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(ROOT / "artifacts" / "verified-narrative"),
        help="Output directory for benchmark JSON receipt",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else None
    run_benchmark(iterations=args.iterations, out_dir=out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
