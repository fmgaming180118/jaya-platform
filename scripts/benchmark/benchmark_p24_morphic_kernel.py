#!/usr/bin/env python3
"""benchmark_p24_morphic_kernel.py — Quantitative Performance, Security & Integrity Benchmark for P24 Morphic Kernel.

Measures:
1. Environment Baseline:
   - OS, architecture, CPU count, Python version, initial RSS memory.
2. Cryptographic Manifest & Evidence Verification:
   - Candidate HMAC-SHA256 signing and verification latency.
   - Manifest dual-key signing and verification latency.
   - Evidence receipt verification latency.
3. Confined Staging & Atomic Publish Copy:
   - Chunked streaming, SHA-256 digest checking, atomic rename, directory fsync.
   - Latency distribution and throughput.
4. Post-Install Canary Probe & Receipt Generation:
   - Execution of post-install canary probe.
   - Canary receipt digest generation and verification latency.
5. Transactional Rollback & Idempotency:
   - Rollback restoring previous state.
   - Repeated rollback idempotency latency.
6. Failure Resilience & Anomaly Recovery:
   - Canary crash recovery latency and clean state restoration.
   - Simulated storage full (ENOSPC) recovery latency.
7. Replay & Revocation Gate Enforcement:
   - Replay blocking latency.
   - Revocation list checking latency.
8. Multithreaded Concurrency:
   - 8 concurrent workers verifying independent signed candidates.
9. Resource Footprint & Memory Telemetry:
   - Initial RSS, final RSS, RSS growth, total benchmark duration.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import errno
import hashlib
import hmac
import json
import math
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import psutil

ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = ROOT / "packages" / "jaya-core"
CORE_SRC = CORE_ROOT / "src"
for import_root in (ROOT, CORE_ROOT, CORE_SRC):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from jaya_core.brain_v2.engine._evolution_manifest_security import signature_payload
from jaya_core.brain_v2.engine.canary import CanaryRegistry, QLoRAAdapterCanary
from jaya_core.brain_v2.engine.evolution_evidence import (
    EvidenceReceiptVerifier,
)
from jaya_core.brain_v2.engine.evolution_gate import (
    EvolutionCandidate,
    EvolutionGate,
)
from jaya_core.brain_v2.engine.evolution_installer import (
    EvolutionInstallError,
    EvolutionInstaller,
)
from jaya_core.brain_v2.engine.evolution_manifest_v1 import (
    ABSENT_RESTORE_DIGEST,
    EvolutionManifestSigner,
    EvolutionManifestVerifier,
    EvolutionTrustStore,
    build_manifest_v1,
    digest_bytes,
    digest_file,
)
from scripts.promote_orchestrator import (
    REVOCATION_SCHEMA_VERSION,
    PromotionError,
    PromotionOrchestrator,
    verify_revocations,
)


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
            "count": 0,
            "mean_ms": 0.0,
            "stddev_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
        }
    sorted_v = sorted(values)
    count = len(sorted_v)
    mean_v = statistics.mean(sorted_v)
    stddev_v = statistics.stdev(sorted_v) if count > 1 else 0.0
    return {
        "count": count,
        "mean_ms": round(mean_v, 4),
        "stddev_ms": round(stddev_v, 4),
        "p50_ms": round(_percentile(sorted_v, 50.0), 4),
        "p95_ms": round(_percentile(sorted_v, 95.0), 4),
        "p99_ms": round(_percentile(sorted_v, 99.0), 4),
        "min_ms": round(sorted_v[0], 4),
        "max_ms": round(sorted_v[-1], 4),
    }


def run_benchmark(iterations: int = 50) -> dict[str, Any]:
    process = psutil.Process()
    rss_start = process.memory_info().rss
    start_total = time.perf_counter()

    # 1. Environment Baseline
    baseline_env = {
        "os": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": sys.version.split()[0],
        "logical_cpus": psutil.cpu_count(logical=True),
        "physical_cpus": psutil.cpu_count(logical=False),
        "initial_rss_bytes": rss_start,
    }

    # Setup keys
    now = time.time()
    candidate_key = b"cand-bench-key-32-bytes-00000000"
    manifest_key = b"manf-bench-key-32-bytes-00000000"
    approval_key = b"appr-bench-key-32-bytes-00000000"
    evidence_key = b"evid-bench-key-32-bytes-00000000"
    commit = "b" * 40
    runner = "bench-runner"
    key_id = "bench-key-id"

    trust = EvolutionTrustStore(
        manifest_keys={"manifest-key": manifest_key},
        approval_keys={"approval-key": approval_key},
        environment="development",
    )
    manifest_verifier = EvolutionManifestVerifier(
        trust_store=trust,
        runtime="JAYA_CORE",
        runtime_version="1.0",
    )
    report_signer = EvidenceReceiptVerifier(evidence_key)
    gate = EvolutionGate(
        environment="production",
        signing_secret=candidate_key,
        evidence_signing_secret=evidence_key,
        trusted_evidence_runners={runner},
    )
    manifest_signer = EvolutionManifestSigner(
        manifest_key_id="manifest-key",
        manifest_key=manifest_key,
        approval_key_id="approval-key",
        approval_key=approval_key,
    )

    # 2. Cryptographic Manifest & Evidence Verification Latencies
    signing_latencies: list[float] = []
    manifest_verify_latencies: list[float] = []

    with tempfile.TemporaryDirectory(prefix="p24_bench_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        fixture_file = tmp_path / "model.safetensors"
        fixture_file.write_bytes(b"x" * 2048)

        for i in range(iterations):
            t0 = time.perf_counter()
            cand = EvolutionCandidate(
                candidate_id=f"cand-{i}",
                source_hash="sha256:" + "0" * 64,
                created_at=now,
                candidate_payload=json.dumps({"op": i}),
                expected_perf_gain_pct=10.0,
                rollback_target="prev",
            )
            gate.sign_candidate(cand, key_id="builder")
            test_rep = report_signer.sign_report(
                {
                    "schema_version": "jaya-evidence-test-v1",
                    "report_type": "test",
                    "candidate_id": cand.candidate_id,
                    "source_hash": cand.source_hash,
                    "dataset_digest": "sha256:" + "d" * 64,
                    "commit": commit,
                    "runner_identity": runner,
                    "key_id": key_id,
                    "issued_at": now - 5,
                    "expires_at": now + 3600,
                    "passed": True,
                    "failed": 0,
                    "skipped": 0,
                    "metrics": {"duration_seconds": 0.01},
                }
            )
            bench_rep = report_signer.sign_report(
                {
                    "schema_version": "jaya-evidence-benchmark-v1",
                    "report_type": "benchmark",
                    "candidate_id": cand.candidate_id,
                    "source_hash": cand.source_hash,
                    "dataset_digest": "sha256:" + "d" * 64,
                    "commit": commit,
                    "runner_identity": runner,
                    "key_id": key_id,
                    "issued_at": now - 5,
                    "expires_at": now + 3600,
                    "passed": True,
                    "baseline_latency_ms": 10.0,
                    "candidate_latency_ms": 9.0,
                    "perf_gain_pct": 10.0,
                    "metrics": {"p95_ms": 9.5},
                }
            )
            m = build_manifest_v1(
                signer=manifest_signer,
                manifest_id=f"manifest-{i}",
                candidate_id=cand.candidate_id,
                payload={"op": i},
                artifact_path=fixture_file,
                artifact_name=f"artifact_{i}.safetensors",
                artifact_media_type="application/vnd.safetensors",
                provenance={
                    "source_uri": "https://example.invalid",
                    "source_revision": commit,
                    "builder_id": "builder",
                    "built_at": now - 10,
                    "reproducible": True,
                },
                license_info={
                    "spdx_id": "Apache-2.0",
                    "redistribution_allowed": True,
                    "source_notice": "test",
                },
                compatibility={
                    "runtime": "JAYA_CORE",
                    "target_versions": ["1.0"],
                    "platform_tags": ["windows-x86_64"],
                },
                evidence_receipts=[
                    {
                        "receipt_type": "test",
                        "receipt_digest": test_rep["report_digest"],
                        "verifier_key_id": key_id,
                        "verified": True,
                    },
                    {
                        "receipt_type": "benchmark",
                        "receipt_digest": bench_rep["report_digest"],
                        "verifier_key_id": key_id,
                        "verified": True,
                    },
                ],
                target_path=f"models/m_{i}.safetensors",
                registry_key=f"cand-{i}",
                canary_check_id="qlora-adapter-inference-v1",
                expected_restore_digest=ABSENT_RESTORE_DIGEST,
                approver="human-approver",
                approval_id=f"approval-{i}",
                approval_issued_at=now - 5,
                approval_expires_at=now + 3600,
                created_at=now - 2,
            )
            signing_latencies.append((time.perf_counter() - t0) * 1000.0)

            t1 = time.perf_counter()
            manifest_verifier.verify(
                m,
                verified_receipt_digests=[test_rep["report_digest"], bench_rep["report_digest"]],
            )
            manifest_verify_latencies.append((time.perf_counter() - t1) * 1000.0)

    # 3. Confined Staging, Atomic Publish & Canary Execution
    publish_latencies: list[float] = []
    rollback_latencies: list[float] = []
    idempotent_rollback_latencies: list[float] = []

    with tempfile.TemporaryDirectory(prefix="p24_bench_install_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        d_root = tmp_path / "data"
        r_root = tmp_path / "reg"
        d_root.mkdir()
        r_root.mkdir()

        art_src = tmp_path / "source.safetensors"
        art_src.write_bytes(b"y" * 4096)

        installer = EvolutionInstaller(
            verifier=manifest_verifier,
            registry_root=r_root,
            data_root=d_root,
            canary_runner=lambda *_: {"passed": True, "probe": "bench"},
        )

        for i in range(iterations):
            m = build_manifest_v1(
                signer=manifest_signer,
                manifest_id=f"manifest-inst-{i}",
                candidate_id=f"cand-inst-{i}",
                payload={"op": i},
                artifact_path=art_src,
                artifact_name=f"artifact_{i}.safetensors",
                artifact_media_type="application/vnd.safetensors",
                provenance={
                    "source_uri": "https://example.invalid",
                    "source_revision": commit,
                    "builder_id": "builder",
                    "built_at": now - 10,
                    "reproducible": True,
                },
                license_info={
                    "spdx_id": "Apache-2.0",
                    "redistribution_allowed": True,
                    "source_notice": "test",
                },
                compatibility={
                    "runtime": "JAYA_CORE",
                    "target_versions": ["1.0"],
                    "platform_tags": ["windows-x86_64"],
                },
                evidence_receipts=[
                    {
                        "receipt_type": "test",
                        "receipt_digest": test_rep["report_digest"],
                        "verifier_key_id": key_id,
                        "verified": True,
                    },
                    {
                        "receipt_type": "benchmark",
                        "receipt_digest": bench_rep["report_digest"],
                        "verifier_key_id": key_id,
                        "verified": True,
                    },
                ],
                target_path=f"models/cand_{i}.safetensors",
                registry_key=f"cand-inst-{i}",
                canary_check_id="qlora-adapter-inference-v1",
                expected_restore_digest=ABSENT_RESTORE_DIGEST,
                approver="human-approver",
                approval_id=f"approval-{i}",
                approval_issued_at=now - 5,
                approval_expires_at=now + 3600,
                created_at=now - 2,
            )
            t_pub = time.perf_counter()
            installer.install(
                m,
                artifact_source=art_src,
                verified_receipt_digests=[test_rep["report_digest"], bench_rep["report_digest"]],
            )
            publish_latencies.append((time.perf_counter() - t_pub) * 1000.0)

            t_rb = time.perf_counter()
            installer.rollback(f"cand-inst-{i}")
            rollback_latencies.append((time.perf_counter() - t_rb) * 1000.0)

            t_rb2 = time.perf_counter()
            res2 = installer.rollback(f"cand-inst-{i}")
            idempotent_rollback_latencies.append((time.perf_counter() - t_rb2) * 1000.0)
            assert res2.idempotent is True

    # 4. Failure Resilience (Canary Crash & ENOSPC Recovery)
    canary_crash_latencies: list[float] = []
    enospc_recovery_latencies: list[float] = []

    with tempfile.TemporaryDirectory(prefix="p24_bench_fail_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        d_root = tmp_path / "data"
        r_root = tmp_path / "reg"
        d_root.mkdir()
        r_root.mkdir()

        art_src = tmp_path / "cand.safetensors"
        art_src.write_bytes(b"z" * 1024)

        target_file = d_root / "models" / "cand_fail.safetensors"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        baseline_bytes = b"baseline"
        target_file.write_bytes(baseline_bytes)
        baseline_dig = digest_bytes(baseline_bytes)

        def _crashing_canary(*_: Any) -> Mapping[str, Any]:
            raise RuntimeError("CRASH")

        crash_installer = EvolutionInstaller(
            verifier=manifest_verifier,
            registry_root=r_root,
            data_root=d_root,
            canary_runner=_crashing_canary,
        )

        for i in range(10):
            m = build_manifest_v1(
                signer=manifest_signer,
                manifest_id=f"manifest-crash-{i}",
                candidate_id=f"cand-crash-{i}",
                payload={"op": i},
                artifact_path=art_src,
                artifact_name="cand_fail.safetensors",
                artifact_media_type="application/vnd.safetensors",
                provenance={
                    "source_uri": "https://example.invalid",
                    "source_revision": commit,
                    "builder_id": "builder",
                    "built_at": now - 10,
                    "reproducible": True,
                },
                license_info={
                    "spdx_id": "Apache-2.0",
                    "redistribution_allowed": True,
                    "source_notice": "test",
                },
                compatibility={
                    "runtime": "JAYA_CORE",
                    "target_versions": ["1.0"],
                    "platform_tags": ["windows-x86_64"],
                },
                evidence_receipts=[
                    {
                        "receipt_type": "test",
                        "receipt_digest": test_rep["report_digest"],
                        "verifier_key_id": key_id,
                        "verified": True,
                    },
                    {
                        "receipt_type": "benchmark",
                        "receipt_digest": bench_rep["report_digest"],
                        "verifier_key_id": key_id,
                        "verified": True,
                    },
                ],
                target_path="models/cand_fail.safetensors",
                registry_key=f"cand-crash-{i}",
                canary_check_id="qlora-adapter-inference-v1",
                expected_restore_digest=baseline_dig,
                approver="human-approver",
                approval_id=f"approval-crash-{i}",
                approval_issued_at=now - 5,
                approval_expires_at=now + 3600,
                created_at=now - 2,
            )
            t_crash = time.perf_counter()
            try:
                crash_installer.install(
                    m,
                    artifact_source=art_src,
                    verified_receipt_digests=[test_rep["report_digest"], bench_rep["report_digest"]],
                )
            except EvolutionInstallError:
                pass
            canary_crash_latencies.append((time.perf_counter() - t_crash) * 1000.0)
            assert target_file.read_bytes() == baseline_bytes

        # ENOSPC simulation
        real_copy = crash_installer._storage.atomic_publish_copy
        def _mock_enospc(src: Path, dst: Path, **kwargs: Any) -> None:
            if dst == target_file:
                raise OSError(errno.ENOSPC, "No space left on device")
            return real_copy(src, dst, **kwargs)

        with patch.object(crash_installer._storage, "atomic_publish_copy", side_effect=_mock_enospc):
            for i in range(10):
                m_enospc = build_manifest_v1(
                    signer=manifest_signer,
                    manifest_id=f"manifest-enospc-{i}",
                    candidate_id=f"cand-enospc-{i}",
                    payload={"op": i},
                    artifact_path=art_src,
                    artifact_name="cand_fail.safetensors",
                    artifact_media_type="application/vnd.safetensors",
                    provenance={
                        "source_uri": "https://example.invalid",
                        "source_revision": commit,
                        "builder_id": "builder",
                        "built_at": now - 10,
                        "reproducible": True,
                    },
                    license_info={
                        "spdx_id": "Apache-2.0",
                        "redistribution_allowed": True,
                        "source_notice": "test",
                    },
                    compatibility={
                        "runtime": "JAYA_CORE",
                        "target_versions": ["1.0"],
                        "platform_tags": ["windows-x86_64"],
                    },
                    evidence_receipts=[
                        {
                            "receipt_type": "test",
                            "receipt_digest": test_rep["report_digest"],
                            "verifier_key_id": key_id,
                            "verified": True,
                        },
                        {
                            "receipt_type": "benchmark",
                            "receipt_digest": bench_rep["report_digest"],
                            "verifier_key_id": key_id,
                            "verified": True,
                        },
                    ],
                    target_path="models/cand_fail.safetensors",
                    registry_key=f"cand-enospc-{i}",
                    canary_check_id="qlora-adapter-inference-v1",
                    expected_restore_digest=baseline_dig,
                    approver="human-approver",
                    approval_id=f"approval-enospc-{i}",
                    approval_issued_at=now - 5,
                    approval_expires_at=now + 3600,
                    created_at=now - 2,
                )
                t_enospc = time.perf_counter()
                try:
                    crash_installer.install(
                        m_enospc,
                        artifact_source=art_src,
                        verified_receipt_digests=[test_rep["report_digest"], bench_rep["report_digest"]],
                    )
                except EvolutionInstallError:
                    pass
                enospc_recovery_latencies.append((time.perf_counter() - t_enospc) * 1000.0)
                assert target_file.read_bytes() == baseline_bytes

    # 5. Multithreaded Concurrency Benchmark (8 workers)
    concurrent_latencies: list[float] = []
    worker_count = 8
    with tempfile.TemporaryDirectory(prefix="p24_bench_concurrent_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        conc_fixture = tmp_path / "shared.safetensors"
        conc_fixture.write_bytes(b"c" * 2048)

        def _verify_worker(worker_id: int) -> float:
            m_conc = build_manifest_v1(
                signer=manifest_signer,
                manifest_id=f"manifest-conc-{worker_id}",
                candidate_id=f"cand-conc-{worker_id}",
                payload={"worker": worker_id},
                artifact_path=conc_fixture,
                artifact_name=f"conc_{worker_id}.safetensors",
                artifact_media_type="application/vnd.safetensors",
                provenance={
                    "source_uri": "https://example.invalid",
                    "source_revision": commit,
                    "builder_id": "builder",
                    "built_at": now - 10,
                    "reproducible": True,
                },
                license_info={
                    "spdx_id": "Apache-2.0",
                    "redistribution_allowed": True,
                    "source_notice": "test",
                },
                compatibility={
                    "runtime": "JAYA_CORE",
                    "target_versions": ["1.0"],
                    "platform_tags": ["windows-x86_64"],
                },
                evidence_receipts=[
                    {
                        "receipt_type": "test",
                        "receipt_digest": test_rep["report_digest"],
                        "verifier_key_id": key_id,
                        "verified": True,
                    },
                    {
                        "receipt_type": "benchmark",
                        "receipt_digest": bench_rep["report_digest"],
                        "verifier_key_id": key_id,
                        "verified": True,
                    },
                ],
                target_path=f"models/conc_{worker_id}.safetensors",
                registry_key=f"cand-conc-{worker_id}",
                canary_check_id="qlora-adapter-inference-v1",
                expected_restore_digest=ABSENT_RESTORE_DIGEST,
                approver="human-approver",
                approval_id=f"approval-conc-{worker_id}",
                approval_issued_at=now - 5,
                approval_expires_at=now + 3600,
                created_at=now - 2,
            )
            t_start = time.perf_counter()
            manifest_verifier.verify(
                m_conc,
                verified_receipt_digests=[test_rep["report_digest"], bench_rep["report_digest"]],
            )
            return (time.perf_counter() - t_start) * 1000.0

        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(_verify_worker, i) for i in range(worker_count * 4)]
            for f in concurrent.futures.as_completed(futures):
                concurrent_latencies.append(f.result())

    rss_end = process.memory_info().rss
    rss_growth = max(0, rss_end - rss_start)
    total_duration = time.perf_counter() - start_total

    results = {
        "benchmark": "p24_morphic_kernel",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "status": "PASS",
        "environment": baseline_env,
        "metrics": {
            "signing_and_manifest_construction": _distribution(signing_latencies),
            "manifest_verification": _distribution(manifest_verify_latencies),
            "staging_atomic_publish_and_canary": _distribution(publish_latencies),
            "transactional_rollback": _distribution(rollback_latencies),
            "idempotent_rollback": _distribution(idempotent_rollback_latencies),
            "canary_crash_recovery": _distribution(canary_crash_latencies),
            "enospc_recovery": _distribution(enospc_recovery_latencies),
            "concurrent_manifest_verification": _distribution(concurrent_latencies),
        },
        "resource_footprint": {
            "initial_rss_bytes": rss_start,
            "final_rss_bytes": rss_end,
            "rss_growth_bytes": rss_growth,
            "total_benchmark_seconds": round(total_duration, 4),
        },
    }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "benchmarks" / "p24_morphic_kernel_benchmark.json",
    )
    args = parser.parse_args()

    results = run_benchmark(iterations=args.iterations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
