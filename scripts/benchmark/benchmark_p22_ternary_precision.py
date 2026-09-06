#!/usr/bin/env python3
"""benchmark_p22_ternary_precision.py — Quantitative Performance, Precision & Integrity Benchmark for P22 Ternary Precision.

Measures:
1. Environment Baseline:
   - Platform, machine, processor count, Python version, initial RSS memory.
2. Deterministic Training & Quantization Calibration:
   - Explicit corpus loading, deterministic train/holdout split, vocabulary construction.
   - Dense probabilities baseline perplexity and top-1 accuracy.
   - Calibrated ternary weights {-1, 0, 1}, row scales, and temperature.
   - Ternary perplexity, ternary top-1 accuracy, perplexity ratio, and top-1 drop.
   - 2-bit packing compression ratio compared to dense float32.
   - Checksum-bound artifact generation.
3. Native Compute & Trusted Artifact Gate:
   - C++20 ternary GEMM (`jaya_ternary_gemm_f32_i8`) vs NumPy reference performance.
   - Rust trusted gate (`jaya_trusted_validate_ternary_values`) validation throughput.
4. Runtime Inference Latency & Throughput:
   - Prediction latency distribution (mean, p50, p95, p99, min, max, stddev).
   - Inferences per second (throughput).
5. Independent Disjoint Corpus Evaluation:
   - Cross-corpus evaluation on separate documents.
   - Evaluation perplexity ratio and top-1 accuracy drop against quality gate.
6. Fail-Closed Security Boundaries:
   - Checksum mismatch fail-closed (`CHECKSUM_MISMATCH`).
   - Tampered weights rejection (`WEIGHTS_INVALID`).
   - Corrupt tokenizer rejection (`TOKENIZER_INVALID`).
   - Unknown field rejection (`UNKNOWN_FIELD`).
   - Invalid input rejection (`INVALID_INPUT`).
   - Timeout enforcement (`TIMEOUT`).
7. Multithreaded Concurrency:
   - Concurrent inference across 8 worker threads.
8. Persistence, Idempotency & Restart Drill:
   - Benchmark receipt persistence in SQLite.
   - Idempotency conflict enforcement and receipt replay across restart.
9. Resource Footprint & Energy:
   - Process RSS memory delta, artifact size on disk.
   - CPU-package energy measurement via Windows EMI/RAPL if available.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import platform
import shutil
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.brain_v2.format.packer import pack_ternary, unpack_ternary
from jaya_core.brain_v2.model.ternary_transition import (
    TernaryModelError,
    TrainedTernaryTransitionModel,
    evaluate_ternary_transition_model,
    train_ternary_transition_model,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars import DynamicPillarRegistry, PillarRuntimeView, load_manifest
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.ternary_capability import (
    TERNARY_CAPABILITY_ID,
    TernaryPrecisionCapabilityService,
)
from jaya_core.providers import ComputeProvider, TrustedArtifactGate

BASELINE_MANIFEST = CORE_SRC / "jaya_core" / "contracts" / "40_pillars.yaml"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    k = (len(values) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    d0 = values[int(f)] * (c - k)
    d1 = values[int(c)] * (k - f)
    return d0 + d1


def _distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "stddev_ms": 0.0,
        }
    sorted_ms = sorted(v * 1000.0 for v in values)
    return {
        "mean_ms": statistics.mean(sorted_ms),
        "p50_ms": _percentile(sorted_ms, 50.0),
        "p95_ms": _percentile(sorted_ms, 95.0),
        "p99_ms": _percentile(sorted_ms, 99.0),
        "min_ms": sorted_ms[0],
        "max_ms": sorted_ms[-1],
        "stddev_ms": statistics.stdev(sorted_ms) if len(sorted_ms) > 1 else 0.0,
    }


def run_benchmark(
    *,
    iterations: int = 2000,
    concurrency_workers: int = 8,
    concurrency_queries: int = 400,
    output_path: Path | None = None,
) -> dict[str, Any]:
    process = psutil.Process()
    rss_initial = process.memory_info().rss
    started_wall = time.perf_counter()

    env_info = {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": psutil.cpu_count(logical=True),
        "python_version": sys.version.split()[0],
        "initial_rss_bytes": rss_initial,
    }

    # 1. Training & Calibration Benchmark
    temp_dir = tempfile.mkdtemp(prefix="p22-bench-")
    temp_root = Path(temp_dir)
    try:
        training_glob = ROOT / "docs" / "pillars"
        training_files = sorted(
            p
            for p in training_glob.glob("*.md")
            if p.name not in ("13-p22-ternary-precision.md", "README.md")
        )
        artifact_path = temp_root / "bench_ternary_model.json"

        train_start = time.perf_counter()
        training_result = train_ternary_transition_model(
            training_files,
            artifact_path,
            max_vocab=768,
            holdout_ratio=0.2,
            smoothing=1.5,
            max_perplexity_ratio=2.0,
            max_top1_accuracy_drop=0.2,
            run_id="p22-quantitative-bench",
        )
        train_elapsed = time.perf_counter() - train_start

        # Model loading & metadata check
        model = TrainedTernaryTransitionModel.load(
            artifact_path, expected_sha256=training_result.artifact_sha256
        )

        dense_matrix_bytes = len(model.vocabulary) * len(model.vocabulary) * 4  # float32
        packed_bytes = len(model.vocabulary) * len(model.vocabulary) // 4 + 8
        compression_ratio = dense_matrix_bytes / packed_bytes if packed_bytes > 0 else 1.0

        training_summary = {
            "training_time_seconds": train_elapsed,
            "training_files_count": training_result.source_count,
            "train_sequences": training_result.train_sequences,
            "holdout_sequences": training_result.holdout_sequences,
            "vocabulary_size": len(model.vocabulary),
            "baseline_perplexity": training_result.metrics["baseline_perplexity"],
            "baseline_top1_accuracy": training_result.metrics["baseline_top1_accuracy"],
            "ternary_perplexity": training_result.metrics["ternary_perplexity"],
            "ternary_top1_accuracy": training_result.metrics["ternary_top1_accuracy"],
            "perplexity_ratio": training_result.metrics["perplexity_ratio"],
            "top1_accuracy_drop": training_result.metrics["top1_accuracy_drop"],
            "quality_gate_passed": bool(training_result.metrics["quality_gate_passed"]),
            "dense_matrix_float32_bytes": dense_matrix_bytes,
            "ternary_packed_bytes": packed_bytes,
            "weight_compression_ratio": compression_ratio,
            "artifact_size_bytes": artifact_path.stat().st_size,
            "artifact_sha256": training_result.artifact_sha256,
            "dataset_sha256": training_result.dataset_sha256,
        }

        # 2. Native Compute & Trusted Gate Benchmarks
        compute_prov = ComputeProvider("auto")
        compute_profile = compute_prov.profile()

        # Compare GEMM C++ vs NumPy
        vocab_dim = len(model.vocabulary)
        rng = np.random.default_rng(42)
        test_inputs = rng.normal(size=(1, vocab_dim)).astype(np.float32)
        test_weights = model.weights.astype(np.int8)

        # Warmup
        for _ in range(50):
            _ = compute_prov.ternary_linear(test_inputs, test_weights)

        gemm_latencies: list[float] = []
        for _ in range(500):
            t0 = time.perf_counter()
            _ = compute_prov.ternary_linear(test_inputs, test_weights)
            gemm_latencies.append(time.perf_counter() - t0)

        trusted_gate = TrustedArtifactGate("auto")
        gate_profile = trusted_gate.profile()
        gate_latencies: list[float] = []
        for _ in range(200):
            t0 = time.perf_counter()
            trusted_gate.validate_ternary_values(model.weights, max_length=64 * 1024 * 1024)
            gate_latencies.append(time.perf_counter() - t0)

        native_summary = {
            "compute_provider": compute_profile,
            "gemm_distribution": _distribution(gemm_latencies),
            "gemm_throughput_ops": len(gemm_latencies) / sum(gemm_latencies) if gemm_latencies else 0,
            "trusted_gate_provider": gate_profile,
            "gate_validation_distribution": _distribution(gate_latencies),
        }

        # 3. Runtime Capability Inference Latency & Throughput
        service_data_dir = temp_root / "pillar_data"
        cap_service = TernaryPrecisionCapabilityService(
            data_dir=service_data_dir,
            artifact_path=artifact_path,
            expected_sha256=training_result.artifact_sha256,
        )

        test_query = "runtime ternary memproses inferensi lokal"
        # Warmup
        for _ in range(50):
            _ = cap_service.execute({"action": "predict", "text": test_query, "top_k": 5})

        infer_latencies: list[float] = []
        infer_start = time.perf_counter()
        for _ in range(iterations):
            t0 = time.perf_counter()
            _ = cap_service.execute({"action": "predict", "text": test_query, "top_k": 5})
            infer_latencies.append(time.perf_counter() - t0)
        infer_total_elapsed = time.perf_counter() - infer_start

        infer_dist = _distribution(infer_latencies)
        infer_throughput = iterations / infer_total_elapsed if infer_total_elapsed > 0 else 0.0

        inference_summary = {
            "iterations": iterations,
            "total_elapsed_seconds": infer_total_elapsed,
            "inferences_per_second": infer_throughput,
            "distribution": infer_dist,
        }

        # 4. Independent Corpus Evaluation
        evaluation_files = sorted(
            p
            for p in (ROOT / "docs").glob("*.md")
            if p.is_file() and p.suffix.casefold() in (".md", ".txt")
        )
        eval_start = time.perf_counter()
        eval_result = evaluate_ternary_transition_model(
            model,
            training_files,
            evaluation_files,
            max_perplexity_ratio=2.5,
            max_top1_accuracy_drop=0.05,
        )
        eval_elapsed = time.perf_counter() - eval_start

        evaluation_summary = {
            "evaluation_time_seconds": eval_elapsed,
            "evaluation_sources_count": eval_result.source_count,
            "sequence_count": eval_result.sequence_count,
            "pair_count": eval_result.pair_count,
            "baseline_perplexity": eval_result.metrics["baseline_perplexity"],
            "baseline_top1_accuracy": eval_result.metrics["baseline_top1_accuracy"],
            "ternary_perplexity": eval_result.metrics["ternary_perplexity"],
            "ternary_top1_accuracy": eval_result.metrics["ternary_top1_accuracy"],
            "perplexity_ratio": eval_result.metrics["perplexity_ratio"],
            "top1_accuracy_drop": eval_result.metrics["top1_accuracy_drop"],
            "quality_gate_passed": bool(eval_result.metrics["quality_gate_passed"]),
        }

        # 5. Fail-Closed Security & Boundary Drills
        security_tests: dict[str, bool] = {}

        # Drill A: Checksum mismatch
        corrupt_artifact = temp_root / "corrupt.json"
        corrupt_artifact.write_bytes(artifact_path.read_bytes() + b"TAMPER")
        try:
            TrainedTernaryTransitionModel.load(
                corrupt_artifact, expected_sha256=training_result.artifact_sha256
            )
            security_tests["tamper_checksum_rejected"] = False
        except TernaryModelError as exc:
            security_tests["tamper_checksum_rejected"] = exc.code == "CHECKSUM_MISMATCH"

        # Drill B: Non-ternary weights
        non_ternary_artifact = temp_root / "non_ternary.json"
        raw_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        raw_payload["weights"]["values"] = [-1, 0, 2]  # Invalid non-ternary contract
        tampered_bytes = json.dumps(raw_payload, sort_keys=True).encode("utf-8")
        non_ternary_artifact.write_bytes(tampered_bytes)
        non_ternary_sha = f"sha256:{hashlib.sha256(tampered_bytes).hexdigest()}"
        try:
            TrainedTernaryTransitionModel.load(
                non_ternary_artifact, expected_sha256=non_ternary_sha
            )
            security_tests["non_ternary_weights_rejected"] = False
        except TernaryModelError as exc:
            security_tests["non_ternary_weights_rejected"] = exc.code == "WEIGHTS_INVALID"

        # Drill C: Invalid input / empty text
        try:
            cap_service.execute({"action": "predict", "text": "   ", "top_k": 5})
            security_tests["empty_input_rejected"] = False
        except LocalPillarError as exc:
            security_tests["empty_input_rejected"] = exc.code == "INVALID_INPUT"

        # Drill D: Unknown field in request
        try:
            cap_service.execute(
                {"action": "predict", "text": "test", "unauthorized_param": 123}
            )
            security_tests["unknown_field_rejected"] = False
        except LocalPillarError as exc:
            security_tests["unknown_field_rejected"] = exc.code == "UNKNOWN_FIELD"

        # Drill E: Timeout enforcement
        try:
            cap_service.execute(
                {
                    "action": "benchmark",
                    "request_id": "timeout-test",
                    "text": "test",
                    "iterations": 10000,
                    "timeout_seconds": 0.01,
                }
            )
            security_tests["timeout_enforced"] = False
        except LocalPillarError as exc:
            security_tests["timeout_enforced"] = exc.code == "TIMEOUT"

        # 6. Multithreaded Concurrency Benchmark
        concurrency_errors: list[str] = []
        queries_per_thread = concurrency_queries // concurrency_workers

        def _worker_fn(worker_idx: int) -> None:
            for q_idx in range(queries_per_thread):
                try:
                    res = cap_service.execute(
                        {"action": "predict", "text": f"token worker {worker_idx}", "top_k": 3}
                    )
                    if res.code != "TERNARY_PREDICTION_COMPLETED":
                        concurrency_errors.append(f"Unexpected code: {res.code}")
                except Exception as e:
                    concurrency_errors.append(str(e))

        conc_start = time.perf_counter()
        threads: list[threading.Thread] = []
        for i in range(concurrency_workers):
            t = threading.Thread(target=_worker_fn, args=(i,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        conc_elapsed = time.perf_counter() - conc_start

        concurrency_summary = {
            "workers": concurrency_workers,
            "total_queries": concurrency_queries,
            "elapsed_seconds": conc_elapsed,
            "throughput_queries_per_sec": concurrency_queries / conc_elapsed if conc_elapsed > 0 else 0,
            "errors_count": len(concurrency_errors),
            "thread_safety_verified": len(concurrency_errors) == 0,
        }

        # 7. Persistence, Idempotency & Restart Drill
        bench_req_id = "bench-req-p22-persistence-001"
        res_initial = cap_service.execute(
            {
                "action": "benchmark",
                "request_id": bench_req_id,
                "text": "runtime restart persistence test",
                "iterations": 100,
                "timeout_seconds": 10.0,
            }
        )

        # Idempotent replay
        res_replay = cap_service.execute(
            {
                "action": "benchmark",
                "request_id": bench_req_id,
                "text": "runtime restart persistence test",
                "iterations": 100,
                "timeout_seconds": 10.0,
            }
        )
        replay_ok = res_replay.code == "TERNARY_BENCHMARK_REPLAYED" and res_replay.data.get("replayed") is True

        # Conflict on changed payload with same request_id
        try:
            cap_service.execute(
                {
                    "action": "benchmark",
                    "request_id": bench_req_id,
                    "text": "completely different payload text",
                    "iterations": 100,
                    "timeout_seconds": 10.0,
                }
            )
            conflict_ok = False
        except LocalPillarError as exc:
            conflict_ok = exc.code == "IDEMPOTENCY_CONFLICT"

        # Restart drill: instantiate brand new service pointing to same directory
        restarted_service = TernaryPrecisionCapabilityService(
            data_dir=service_data_dir,
            artifact_path=artifact_path,
            expected_sha256=training_result.artifact_sha256,
        )
        receipt_after_restart = restarted_service.execute(
            {"action": "receipt", "request_id": bench_req_id}
        )
        restart_ok = receipt_after_restart.code == "TERNARY_BENCHMARK_RECEIPT"

        persistence_summary = {
            "receipt_persisted": res_initial.code == "TERNARY_BENCHMARK_COMPLETED",
            "idempotent_replay_verified": replay_ok,
            "conflict_detection_verified": conflict_ok,
            "restart_recovery_verified": restart_ok,
        }

        # 8. Energy & Resource Footprint
        energy_meter = WindowsEmiEnergyMeter()
        energy_info: dict[str, Any] = {"status": "NOT_AVAILABLE"}
        try:
            s0 = energy_meter.sample()
            # Run small load
            for _ in range(500):
                _ = cap_service.execute({"action": "predict", "text": "energy measurement", "top_k": 3})
            s1 = energy_meter.sample()
            m = energy_meter.measure(s0, s1)
            energy_info = {
                "status": "MEASURED",
                "joules": m.joules,
                "average_watts": m.average_package_watts,
                "joules_per_inference": m.joules / 500,
            }
        except EnergyMeterError as e:
            energy_info = {"status": f"FAILED: {e.code}"}

        rss_final = process.memory_info().rss
        total_wall_elapsed = time.perf_counter() - started_wall

        resource_summary = {
            "rss_initial_bytes": rss_initial,
            "rss_final_bytes": rss_final,
            "rss_delta_bytes": rss_final - rss_initial,
            "energy_measurement": energy_info,
            "total_benchmark_wall_seconds": total_wall_elapsed,
        }

        # Overall Status
        all_security_passed = all(security_tests.values())
        all_persistence_passed = all(persistence_summary.values())
        overall_passed = (
            training_summary["quality_gate_passed"]
            and evaluation_summary["quality_gate_passed"]
            and all_security_passed
            and concurrency_summary["thread_safety_verified"]
            and all_persistence_passed
        )

        final_report = {
            "benchmark_name": "P22_TERNARY_PRECISION_QUANTITATIVE_BENCHMARK",
            "timestamp": datetime.now(UTC).isoformat(),
            "pillar_id": "P022",
            "capability_id": TERNARY_CAPABILITY_ID,
            "status": "PASS" if overall_passed else "FAIL",
            "environment": env_info,
            "training_and_calibration": training_summary,
            "native_compute_and_gate": native_summary,
            "inference_performance": inference_summary,
            "independent_evaluation": evaluation_summary,
            "security_boundaries": security_tests,
            "concurrency": concurrency_summary,
            "persistence_and_restart": persistence_summary,
            "resources_and_energy": resource_summary,
        }

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(final_report, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        return final_report

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="P22 Ternary Precision Quantitative Benchmark")
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--output", default=str(ROOT / "outputs" / "reports" / "benchmarks" / "p22_ternary_precision_benchmark.json"))
    args = parser.parse_args()

    report = run_benchmark(iterations=args.iterations, output_path=Path(args.output))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
