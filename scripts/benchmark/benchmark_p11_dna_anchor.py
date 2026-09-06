#!/usr/bin/env python3
"""benchmark_p11_dna_anchor.py — Performance & Security Benchmark for P11 DNA Anchor.

Measures:
- Enrollment latency (Scrypt KDF derivation, Ed25519 generation, AES-GCM keystore, genesis audit).
- Challenge-Response roundtrip latency across 500 iterations (issue -> sign -> verify with one-time consumption).
- Attestation creation and verification throughput.
- Key rotation latency (lineage proof, atomic keystore replacement, audit chain).
- Replay attack rejection latency (fail-closed check on consumed challenge).
- Full audit chain verification latency.
- Health check readiness probe latency.
- Memory RSS and database file size growth.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

import psutil  # noqa: E402
from jaya_core.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    DNAAnchorError,
    DNAFailureCode,
    EncryptedFileKeyStore,
)


def _measure_environment() -> dict[str, object]:
    process = psutil.Process(os.getpid())
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or "Unknown",
        "cpu_count_logical": os.cpu_count(),
        "python_version": platform.python_version(),
        "initial_rss_mb": round(process.memory_info().rss / (1024 * 1024), 2),
    }


def run_benchmark(iterations: int = 500) -> dict[str, object]:
    env = _measure_environment()
    process = psutil.Process(os.getpid())

    scratch_dir = ROOT / "outputs" / "scratch" / "p11_bench"
    if scratch_dir.exists():
        import shutil
        shutil.rmtree(scratch_dir, ignore_errors=True)
    scratch_dir.mkdir(parents=True, exist_ok=True)

    keystore_dir = scratch_dir / "keystore"
    keystore_dir.mkdir(parents=True, exist_ok=True)
    unlock_secret = "benchmark-super-secret-unlock-key-32bytes!!"

    keystore = EncryptedFileKeyStore(keystore_dir, unlock_secret)
    anchor = DNAAnchor(scratch_dir, keystore)

    # 1. Enrollment Latency (Scrypt KDF + Ed25519 keypair + AESGCM keystore + Genesis audit)
    enroll_start = time.perf_counter()
    brain_record, enroll_receipt = anchor.enroll()
    enroll_latency_ms = (time.perf_counter() - enroll_start) * 1000

    # 2. Challenge-Response Roundtrip Latency (Issue -> Sign -> Verify)
    roundtrip_latencies_us: list[float] = []
    sign_latencies_us: list[float] = []
    verify_latencies_us: list[float] = []

    last_challenge = None
    last_sig = ""
    for i in range(iterations):
        rt_start = time.perf_counter()
        challenge = anchor.issue_challenge(f"bench.auth.{i}", ttl_seconds=60)

        s_start = time.perf_counter()
        signature = anchor.sign_challenge(challenge)
        sign_latencies_us.append((time.perf_counter() - s_start) * 1_000_000)

        v_start = time.perf_counter()
        verified_receipt = anchor.verify_challenge(challenge, signature)
        verify_latencies_us.append((time.perf_counter() - v_start) * 1_000_000)

        roundtrip_latencies_us.append((time.perf_counter() - rt_start) * 1_000_000)
        assert verified_receipt.event == "CHALLENGE_VERIFIED"
        last_challenge = challenge
        last_sig = signature

    # 3. Replay Attack Rejection Latency (Attempting to re-verify consumed challenge)
    replay_start = time.perf_counter()
    try:
        anchor.verify_challenge(last_challenge, last_sig)
        replay_rejected = False
    except DNAAnchorError as e:
        replay_rejected = (e.code is DNAFailureCode.REPLAY_DETECTED)
    replay_rejection_us = (time.perf_counter() - replay_start) * 1_000_000
    assert replay_rejected is True

    # 4. Attestation Creation & Verification Throughput (100 samples)
    attest_create_us: list[float] = []
    attest_verify_us: list[float] = []
    for j in range(100):
        dummy_hash = f"{j:064x}"
        a_start = time.perf_counter()
        attestation = anchor.sign_attestation("model_receipt", dummy_hash)
        attest_create_us.append((time.perf_counter() - a_start) * 1_000_000)

        av_start = time.perf_counter()
        is_valid = anchor.verify_attestation(attestation)
        attest_verify_us.append((time.perf_counter() - av_start) * 1_000_000)
        assert is_valid is True

    # 5. Key Rotation Latency (Atomic re-encryption + Lineage proof + SQLite record)
    rot_start = time.perf_counter()
    rotated_record, rotated_receipt = anchor.rotate_key()
    rotation_latency_ms = (time.perf_counter() - rot_start) * 1000
    assert rotated_record.key_version == 2
    assert rotated_record.rotation_proof is not None

    # Verify that new challenge uses key_version 2
    new_c = anchor.issue_challenge("post.rotation", ttl_seconds=60)
    new_sig = anchor.sign_challenge(new_c)
    assert anchor.verify_challenge(new_c, new_sig).event == "CHALLENGE_VERIFIED"

    # 6. Full Audit Chain Verification Latency
    audit_start = time.perf_counter()
    audit_chain_verified = anchor.audit_chain_valid()
    audit_latency_ms = (time.perf_counter() - audit_start) * 1000
    assert audit_chain_verified is True
    audit_event_count = anchor._connection.execute("SELECT COUNT(*) FROM identity_audit").fetchone()[0]

    # 7. Health Check Readiness Probe Latency
    health_latencies_us: list[float] = []
    for _ in range(50):
        h_start = time.perf_counter()
        is_ready = anchor.health_check()
        health_latencies_us.append((time.perf_counter() - h_start) * 1_000_000)
        assert is_ready is True

    db_size_bytes = os.path.getsize(anchor.database_path)
    keystore_size_bytes = os.path.getsize(keystore.path)
    final_rss_mb = round(process.memory_info().rss / (1024 * 1024), 2)
    anchor.close()

    def quantiles(vals: list[float]) -> dict[str, float]:
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        return {
            "min": round(sorted_vals[0], 2),
            "p50": round(sorted_vals[int(n * 0.50)], 2),
            "p90": round(sorted_vals[int(n * 0.90)], 2),
            "p99": round(sorted_vals[int(n * 0.99)], 2),
            "max": round(sorted_vals[-1], 2),
            "mean": round(statistics.mean(sorted_vals), 2),
        }

    return {
        "environment": env,
        "iterations": iterations,
        "memory": {
            "initial_rss_mb": env["initial_rss_mb"],
            "final_rss_mb": final_rss_mb,
            "delta_rss_mb": round(final_rss_mb - env["initial_rss_mb"], 2),
        },
        "storage": {
            "database_size_bytes": db_size_bytes,
            "keystore_size_bytes": keystore_size_bytes,
            "audit_trail_events": audit_event_count,
        },
        "enrollment_and_rotation_ms": {
            "enrollment_scrypt_aesgcm_ms": round(enroll_latency_ms, 2),
            "key_rotation_with_lineage_ms": round(rotation_latency_ms, 2),
        },
        "challenge_response_latencies_us": {
            "roundtrip_us": quantiles(roundtrip_latencies_us),
            "sign_phase_us": quantiles(sign_latencies_us),
            "verify_phase_us": quantiles(verify_latencies_us),
        },
        "replay_attack_rejection_us": round(replay_rejection_us, 2),
        "attestation_throughput_us": {
            "creation_us": quantiles(attest_create_us),
            "verification_us": quantiles(attest_verify_us),
        },
        "readiness_and_audit": {
            "health_check_probe_us": quantiles(health_latencies_us),
            "full_audit_chain_verification_ms": round(audit_latency_ms, 2),
        },
        "identity_provenance": {
            "brain_id": brain_record.brain_id,
            "owner_id": brain_record.owner_id,
            "initial_key_fingerprint": brain_record.public_key_fingerprint,
            "rotated_key_fingerprint": rotated_record.public_key_fingerprint,
            "status": rotated_record.status.value,
        },
    }


def main() -> int:
    print("=" * 65)
    print("       JAYA BENCHMARK: PILAR P11 DNA ANCHOR")
    print("=" * 65)

    result = run_benchmark(iterations=500)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
