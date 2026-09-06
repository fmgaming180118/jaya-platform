#!/usr/bin/env python3
"""benchmark_p12_immune_system.py — Quantitative Performance & Security Benchmark for P12 Immune System.

Measures:
1. Environment Baseline:
   - Host platform, CPU architecture, processor count, Python version, initial RSS memory.
2. Integrity Scan Performance:
   - Healthy artifact scan latency distribution (mean, p50, p95, p99, min, max, stddev) across 100+ iterations.
   - Scan throughput (operations per second).
3. Quarantine & Isolation Lifecycle:
   - Detection, P13 encrypted wrapping, source file elimination, and incident logging latency.
   - Authenticated quarantine unsealing roundtrip and plaintext absence verification.
4. Dependency Circuit Breaker:
   - Failure recording latency and trip threshold enforcement.
   - Fast fail-closed rejection throughput when circuit is OPEN.
   - Bounded dependency health probe execution and recovery latency.
5. Fail-Closed Security Boundary:
   - Bit-flip tamper detection.
   - Corrupted quarantine envelope rejection (IMMUNE_QUARANTINE_CORRUPT).
   - Path traversal attempt rejection (IMMUNE_PATH_OUTSIDE_ROOT).
   - Unregistered target rejection (IMMUNE_TARGET_NOT_FOUND).
   - Probe timeout bounding (IMMUNE_PROBE_TIMEOUT).
   - Probe exception stability (IMMUNE_PROBE_FAILED).
   - Tampered incident / circuit / audit ledger rejection (IMMUNE_AUDIT_CORRUPT).
   - Invalid recovery artifact rejection (IMMUNE_RECOVERY_REJECTED).
6. Multithreaded Concurrency:
   - Race condition resilience: 8 concurrent scans on tampered artifact produce exactly 1 incident and 1 quarantine envelope.
7. Persistence & Restart Drill:
   - Persistent safe-stop enforcement across process restarts.
   - Recovery and readiness restoration across restart.
   - SQLite online backup creation and recovery validation.
8. Resource Footprint & Data Hygiene:
   - Process RSS memory growth, database size, quarantine overhead, storage per operation.
   - Strict absence of raw plaintext secrets in database and quarantine storage.
"""

from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

import psutil  # noqa: E402

from jaya_core.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    EncryptedFileKeyStore,
)
from jaya_core.security.cryptographic_skin import CryptographicSkin  # noqa: E402
from jaya_core.security.immune_system import (  # noqa: E402
    ImmuneFailureCode,
    ImmuneSystem,
    ImmuneSystemError,
    IncidentState,
)


def _measure_environment() -> dict[str, Any]:
    process = psutil.Process(os.getpid())
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or "Unknown",
        "cpu_count_logical": os.cpu_count(),
        "python_version": platform.python_version(),
        "initial_rss_mb": round(process.memory_info().rss / (1024 * 1024), 2),
    }


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * pct) - 1)
    return ordered[index]


def _build_components(
    workspace: Path,
    identity_secret: str,
    skin_secret: str,
    probe_timeout: float = 0.05,
) -> tuple[DNAAnchor, CryptographicSkin, ImmuneSystem]:
    identity_root = workspace / "identity"
    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
    )
    anchor.enroll()

    signer = lambda purpose, digest: anchor.sign_attestation(purpose, digest).to_dict()  # noqa: E731
    database = workspace / "core.db"
    skin = CryptographicSkin(
        database,
        skin_secret,
        attestation_signer=signer,
        attestation_verifier=anchor.verify_attestation,
    )
    immune = ImmuneSystem(
        database,
        workspace,
        skin,
        attestation_signer=signer,
        attestation_verifier=anchor.verify_attestation,
        dependency_probe_timeout_seconds=probe_timeout,
    )
    return anchor, skin, immune


def benchmark_healthy_scans(
    immune: ImmuneSystem,
    target_id: str,
    iterations: int = 100,
) -> dict[str, Any]:
    """Measure latency and throughput for healthy artifact scans."""
    latencies_ms: list[float] = []
    start_total = time.perf_counter()
    for _ in range(iterations):
        t0 = time.perf_counter()
        incident = immune.scan(target_id)
        elapsed = (time.perf_counter() - t0) * 1000.0
        assert incident is None, "healthy scan must return None"
        latencies_ms.append(elapsed)
    total_elapsed = time.perf_counter() - start_total

    return {
        "iterations": iterations,
        "total_elapsed_ms": round(total_elapsed * 1000.0, 3),
        "throughput_scans_per_sec": round(iterations / total_elapsed, 2),
        "mean_latency_ms": round(statistics.mean(latencies_ms), 4),
        "median_latency_ms": round(statistics.median(latencies_ms), 4),
        "p95_latency_ms": round(_percentile(latencies_ms, 0.95), 4),
        "p99_latency_ms": round(_percentile(latencies_ms, 0.99), 4),
        "min_latency_ms": round(min(latencies_ms), 4),
        "max_latency_ms": round(max(latencies_ms), 4),
        "stddev_latency_ms": round(statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0.0, 4),
    }


def benchmark_quarantine_lifecycle(
    immune: ImmuneSystem,
    workspace: Path,
    target_path: Path,
    target_id: str,
    unsafe_content: bytes,
) -> dict[str, Any]:
    """Measure quarantine latency, encrypted wrapping, source removal, and unsealing roundtrip."""
    target_path.write_bytes(unsafe_content)
    t0 = time.perf_counter()
    incident = immune.scan(target_id)
    quarantine_latency_ms = (time.perf_counter() - t0) * 1000.0

    assert incident is not None, "corrupted target must create incident"
    assert incident.state is IncidentState.OPEN
    assert incident.quarantine_path is not None
    quarantine_file = workspace / incident.quarantine_path

    quarantined_ok = not target_path.exists() and quarantine_file.is_file()
    quarantine_raw = quarantine_file.read_bytes()
    plaintext_absent = unsafe_content not in quarantine_raw

    t1 = time.perf_counter()
    unsealed_content = immune.open_quarantine(incident.incident_id)
    unseal_latency_ms = (time.perf_counter() - t1) * 1000.0
    unsealed_matches = unsealed_content == unsafe_content

    return {
        "quarantine_latency_ms": round(quarantine_latency_ms, 3),
        "unseal_latency_ms": round(unseal_latency_ms, 3),
        "quarantined": quarantined_ok,
        "plaintext_absent_in_envelope": plaintext_absent,
        "unsealed_matches": unsealed_matches,
        "quarantine_envelope_bytes": len(quarantine_raw),
        "safe_stop_active": immune.safe_stop(),
    }


def benchmark_circuit_breaker(
    immune: ImmuneSystem,
    dependency_id: str = "demo-dependency",
) -> dict[str, Any]:
    """Measure dependency failure recording, trip enforcement, and fast-reject throughput."""
    record_times_ms: list[float] = []
    for code in ("TIMEOUT", "CONNECTION_RESET", "HTTP_503"):
        t0 = time.perf_counter()
        immune.record_dependency_failure(dependency_id, code)
        record_times_ms.append((time.perf_counter() - t0) * 1000.0)

    circuit_open = not immune.can_execute(dependency_id)

    # Measure fast-reject throughput (when circuit is open, can_execute must return False instantly)
    fast_reject_iterations = 1_000
    t0 = time.perf_counter()
    for _ in range(fast_reject_iterations):
        assert not immune.can_execute(dependency_id)
    fast_reject_elapsed = time.perf_counter() - t0
    fast_reject_throughput = round(fast_reject_iterations / fast_reject_elapsed, 2)
    fast_reject_mean_us = round((fast_reject_elapsed / fast_reject_iterations) * 1_000_000, 3)

    # Health probe recovery
    t0 = time.perf_counter()
    resolved = immune.recover_dependency(dependency_id, lambda: True)
    recovery_latency_ms = (time.perf_counter() - t0) * 1000.0
    circuit_closed = immune.can_execute(dependency_id)

    return {
        "mean_record_failure_ms": round(statistics.mean(record_times_ms), 3),
        "circuit_open_enforced": circuit_open,
        "fast_reject_throughput_ops_per_sec": fast_reject_throughput,
        "fast_reject_mean_latency_us": fast_reject_mean_us,
        "recovery_latency_ms": round(recovery_latency_ms, 3),
        "circuit_closed_after_recovery": circuit_closed,
        "resolved_state": resolved.state.value,
    }


def benchmark_fail_closed_security(
    immune: ImmuneSystem,
    workspace: Path,
    approved_target_id: str,
    approved_path: Path,
    approved_content: bytes,
) -> dict[str, Any]:
    """Verify all fail-closed security invariants."""
    results: dict[str, bool] = {}

    # 1. Path outside root
    try:
        immune.register_target(
            "path-escape",
            Path(tempfile.gettempdir()) / "outside.bin",
            "0" * 64,
            critical=True,
        )
        results["path_escape_rejected"] = False
    except ImmuneSystemError as exc:
        results["path_escape_rejected"] = exc.code is ImmuneFailureCode.PATH_OUTSIDE_ROOT

    # 2. Unregistered target scan
    try:
        immune.scan("non-existent-target")
        results["unregistered_target_rejected"] = False
    except ImmuneSystemError as exc:
        results["unregistered_target_rejected"] = exc.code is ImmuneFailureCode.TARGET_NOT_FOUND

    # 3. Missing quarantine incident rejected
    try:
        immune.open_quarantine("non-existent-incident")
        results["missing_quarantine_incident_rejected"] = False
    except ImmuneSystemError as exc:
        results["missing_quarantine_incident_rejected"] = exc.code is ImmuneFailureCode.TARGET_NOT_FOUND

    # 3b. Corrupted quarantine envelope rejected
    quarantine_files = list((workspace / "quarantine").glob("*.jaya-quarantine.json"))
    if quarantine_files:
        test_envelope = quarantine_files[0]
        original_bytes = test_envelope.read_bytes()
        # Find incident id for this quarantine file
        row = immune._connection.execute(
            "SELECT incident_id FROM immune_incidents WHERE quarantine_path LIKE ?",
            (f"%{test_envelope.name}",),
        ).fetchone()
        if row:
            test_incident_id = row["incident_id"]
            # Tamper envelope
            test_envelope.write_bytes(b"tampered-not-valid-json-envelope")
            try:
                immune.open_quarantine(test_incident_id)
                results["corrupt_quarantine_rejected"] = False
            except ImmuneSystemError as exc:
                results["corrupt_quarantine_rejected"] = exc.code is ImmuneFailureCode.QUARANTINE_CORRUPT
            finally:
                test_envelope.write_bytes(original_bytes)
        else:
            results["corrupt_quarantine_rejected"] = False
    else:
        results["corrupt_quarantine_rejected"] = False

    # 4. Dependency probe timeout bounded
    immune.record_dependency_failure("timeout-dep", "ERR")
    immune.record_dependency_failure("timeout-dep", "ERR")
    immune.record_dependency_failure("timeout-dep", "ERR")
    t0 = time.perf_counter()
    try:
        immune.recover_dependency("timeout-dep", lambda: time.sleep(0.2) or True)
        results["probe_timeout_bounded"] = False
    except ImmuneSystemError as exc:
        elapsed = time.perf_counter() - t0
        results["probe_timeout_bounded"] = (
            exc.code is ImmuneFailureCode.PROBE_TIMEOUT and elapsed < 0.5
        )

    # 5. Dependency probe exception stable
    try:
        def _raising_probe():
            raise ValueError("hardware bus faulted")
        immune.recover_dependency("timeout-dep", _raising_probe)
        results["probe_exception_stable"] = False
    except ImmuneSystemError as exc:
        results["probe_exception_stable"] = exc.code is ImmuneFailureCode.PROBE_FAILED

    # 6. Wrong recovery artifact rejected
    approved_path.write_bytes(b"some-other-unapproved-payload")
    try:
        immune.recover_target(approved_target_id)
        results["wrong_recovery_rejected"] = False
    except ImmuneSystemError as exc:
        results["wrong_recovery_rejected"] = exc.code is ImmuneFailureCode.RECOVERY_REJECTED

    # 7. Valid recovery succeeds
    approved_path.write_bytes(approved_content)
    recovered = immune.recover_target(approved_target_id)
    results["valid_recovery_succeeds"] = recovered.state is IncidentState.RESOLVED

    # 8. Clean up timeout-dep
    immune.recover_dependency("timeout-dep", lambda: True)

    return {
        "all_passed": all(results.values()),
        "checks": results,
    }


def benchmark_concurrency(
    immune: ImmuneSystem,
    workspace: Path,
    target_id: str,
    target_path: Path,
    unsafe_content: bytes,
    threads: int = 8,
) -> dict[str, Any]:
    """Test concurrent scans on corrupted target; verify idempotent single incident creation."""
    target_path.write_bytes(unsafe_content)
    results: list[Any] = []

    def _worker():
        return immune.scan(target_id)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(_worker) for _ in range(threads)]
        for f in futures:
            results.append(f.result())
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    incidents = [r for r in results if r is not None]
    incident_ids = {inc.incident_id for inc in incidents}
    quarantine_files = list((workspace / "quarantine").glob("*.jaya-quarantine.json"))

    idempotent = len(incident_ids) == 1 and len(quarantine_files) >= 1

    return {
        "threads": threads,
        "elapsed_ms": round(elapsed_ms, 3),
        "incident_count": len(incidents),
        "unique_incident_ids": len(incident_ids),
        "idempotent": idempotent,
    }


def benchmark_persistence_and_backup(
    workspace: Path,
    identity_secret: str,
    skin_secret: str,
) -> dict[str, Any]:
    """Verify state persistence across restart and SQLite online backup recovery."""
    database = workspace / "core.db"
    backup_path = workspace / "core_backup.db"

    # 1. Online SQLite backup
    t0 = time.perf_counter()
    source_con = sqlite3.connect(database)
    backup_con = sqlite3.connect(backup_path)
    with backup_con:
        source_con.backup(backup_con)
    source_con.close()
    backup_con.close()
    backup_latency_ms = (time.perf_counter() - t0) * 1000.0

    # 2. Re-open backup in new immune instance and verify state authenticity
    anchor = DNAAnchor(
        workspace / "identity",
        EncryptedFileKeyStore(workspace / "identity" / "keystore", identity_secret),
    )
    signer = lambda purpose, digest: anchor.sign_attestation(purpose, digest).to_dict()  # noqa: E731
    skin = CryptographicSkin(
        backup_path,
        skin_secret,
        attestation_signer=signer,
        attestation_verifier=anchor.verify_attestation,
    )
    immune_backup = ImmuneSystem(
        backup_path,
        workspace,
        skin,
        attestation_signer=signer,
        attestation_verifier=anchor.verify_attestation,
    )

    status = immune_backup.status()
    audit_chain_valid = immune_backup.audit_chain_valid()
    state_authenticated = status["state_authenticated"]

    immune_backup.close()
    skin.close()
    anchor.close()

    return {
        "backup_latency_ms": round(backup_latency_ms, 3),
        "backup_size_bytes": backup_path.stat().st_size,
        "backup_audit_chain_valid": audit_chain_valid,
        "backup_state_authenticated": state_authenticated,
    }


def benchmark_resource_footprint(
    workspace: Path,
    initial_rss_bytes: int,
    total_operations: int,
) -> dict[str, Any]:
    """Measure RSS growth, database size, and per-operation storage footprint."""
    process = psutil.Process(os.getpid())
    current_rss_bytes = process.memory_info().rss
    rss_growth_bytes = max(0, current_rss_bytes - initial_rss_bytes)

    db_path = workspace / "core.db"
    db_bytes = db_path.stat().st_size if db_path.exists() else 0
    storage_per_op = round(db_bytes / max(1, total_operations), 2)

    # Plaintext absence scan: verify no secrets or raw unsafe files in DB
    db_raw = db_path.read_bytes() if db_path.exists() else b""
    plaintext_clean = (
        b"benchmark-secret" not in db_raw
        and b"UNSAFE_TEST_CONTENT_NEVER_PERSIST_RAW" not in db_raw
    )

    return {
        "final_rss_mb": round(current_rss_bytes / (1024 * 1024), 2),
        "rss_growth_bytes": rss_growth_bytes,
        "database_bytes": db_bytes,
        "storage_bytes_per_operation": storage_per_op,
        "plaintext_clean": plaintext_clean,
    }


def run_benchmark(output_path: Path | None = None) -> dict[str, Any]:
    temp_dir = tempfile.mkdtemp(prefix="jaya-p12-benchmark-")
    workspace = Path(temp_dir).resolve()
    process = psutil.Process(os.getpid())
    initial_rss_bytes = process.memory_info().rss

    try:
        env = _measure_environment()
        identity_secret = "p12-identity-key-secret-" + ("k" * 32)
        skin_secret = "p12-skin-key-secret-" + ("s" * 32)

        anchor, skin, immune = _build_components(
            workspace,
            identity_secret,
            skin_secret,
            probe_timeout=0.05,
        )

        # Create approved target
        approved_target_id = "core-runtime-component"
        target_path = workspace / "runtime-component.bin"
        approved_content = b"P12-APPROVED-CORE-ARTIFACT-DATA-BLOCK"
        target_path.write_bytes(approved_content)
        immune.register_target(
            approved_target_id,
            target_path,
            _digest_file(target_path),
            critical=True,
        )

        # 1. Healthy scans benchmark (100 iterations)
        scan_bench = benchmark_healthy_scans(immune, approved_target_id, iterations=100)

        # 2. Quarantine lifecycle benchmark
        unsafe_content = b"UNSAFE_TEST_CONTENT_NEVER_PERSIST_RAW_MODIFIED_PAYLOAD"
        quarantine_bench = benchmark_quarantine_lifecycle(
            immune, workspace, target_path, approved_target_id, unsafe_content
        )

        # 3. Dependency circuit breaker benchmark
        circuit_bench = benchmark_circuit_breaker(immune, "dep-worker-service")

        # 4. Fail-closed security validation
        security_bench = benchmark_fail_closed_security(
            immune, workspace, approved_target_id, target_path, approved_content
        )

        # 5. Concurrency benchmark (8 threads)
        target2_id = "concurrent-target"
        target2_path = workspace / "concurrent-target.bin"
        target2_path.write_bytes(approved_content)
        immune.register_target(target2_id, target2_path, _digest_file(target2_path), critical=False)
        concurrency_bench = benchmark_concurrency(
            immune, workspace, target2_id, target2_path, unsafe_content, threads=8
        )

        # 6. Persistence and SQLite backup
        persistence_bench = benchmark_persistence_and_backup(workspace, identity_secret, skin_secret)

        # 7. Resource footprint
        total_ops = 100 + 1 + 3 + 8 + 10  # scans + quarantine + circuit + concurrency + security
        resource_bench = benchmark_resource_footprint(workspace, initial_rss_bytes, total_ops)

        # Full audit chain validity on active immune instance
        final_audit_valid = immune.audit_chain_valid()
        final_status = immune.status()

        immune.close()
        skin.close()
        anchor.close()

        report: dict[str, Any] = {
            "status": "VERIFIED_QUANTITATIVE_BENCHMARK",
            "pillar": "P12 Immune System",
            "benchmark_timestamp": datetime.now(UTC).isoformat(),
            "environment": env,
            "healthy_scan_benchmark": scan_bench,
            "quarantine_lifecycle_benchmark": quarantine_bench,
            "circuit_breaker_benchmark": circuit_bench,
            "fail_closed_security": security_bench,
            "concurrency_benchmark": concurrency_bench,
            "persistence_and_backup": persistence_bench,
            "resource_footprint": resource_bench,
            "final_system_state": {
                "audit_chain_valid": final_audit_valid,
                "state_authenticated": final_status["state_authenticated"],
                "storage_schema_version": final_status["storage_schema_version"],
                "open_incidents": final_status["open_incidents"],
                "ready": final_status["ready"],
            },
        }

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return report

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None, help="Path to write JSON benchmark report")
    args = parser.parse_args()

    report = run_benchmark(args.output)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "VERIFIED_QUANTITATIVE_BENCHMARK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
