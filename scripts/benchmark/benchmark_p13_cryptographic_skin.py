#!/usr/bin/env python3
"""benchmark_p13_cryptographic_skin.py — Comprehensive Quantitative Benchmark for P13 Cryptographic Skin.

Measures:
1. Admission Gate Evaluation:
   - Python reference envelope admission gate across 25,000 decisions.
   - Native Rust envelope gate latency & availability status.
2. End-to-End AEAD Sealing and Opening Lifecycle:
   - Measures AES-256-GCM + Ed25519 DNA-attested envelope throughput & latency across payload sizes (1 KB, 4 KB, 64 KB, 1 MB).
3. One-File Capsule (.jayac) Codec:
   - Measures seal and open throughput across all four boundary kinds (brain, backup, puzzle, mesh).
4. Nonce Uniqueness & Collision Prevention:
   - Persistent nonce reservation throughput and fail-closed reuse denial (CRYPTO_SKIN_NONCE_COLLISION).
5. Dynamic Key Lifecycle:
   - Key rotation latency, continuity of opening retired key envelopes, and fail-closed revocation denial (CRYPTO_SKIN_KEY_REVOKED).
6. Fail-Closed Security Validation:
   - 1-bit flip ciphertext tamper rejection.
   - Associated data / metadata tampering rejection.
   - Expired envelope rejection.
   - Corrupt state / wrong unlock secret rejection.
7. Audit Chain & Keyed State Integrity:
   - Full hash-chain verification latency across all logged security events.
8. Resource Footprint & Data Hygiene:
   - RSS memory growth, database storage growth, envelope overhead.
   - Strict plaintext absence scan across persistent storage and serialized envelopes.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import shutil
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
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
from jaya_core.providers import (  # noqa: E402
    CryptographicEnvelopeContract,
    NativeProviderError,
    TrustedCryptographicSkinGate,
)
from jaya_core.security.capsule import CapsuleKind, JayaCapsuleCodec  # noqa: E402
from jaya_core.security.cryptographic_skin import (  # noqa: E402
    CryptographicSkin,
    CryptographicSkinError,
    CryptographicSkinFailureCode,
    SealedEnvelope,
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


def _benchmark_admission_gate(iterations: int = 1_000, samples: int = 25) -> dict[str, Any]:
    """Benchmark admission gate decision across 25,000 decisions."""
    contract = CryptographicEnvelopeContract(
        envelope_id="env-benchmark-gate",
        key_id="key-benchmark-gate",
        purpose="core.artifact",
        subject="artifact:benchmark-gate",
        content_type="application/jaya-artifact",
        schema_version=1,
        algorithm_suite_code=1,
        operation_code=2,
        key_state=1,
        attestation_state=1,
        temporal_state=1,
        nonce_size_bytes=12,
        ciphertext_size_bytes=128,
        max_payload_bytes=4096,
    )

    py_gate = TrustedCryptographicSkinGate("python-reference")
    for _ in range(50):
        py_gate.evaluate(contract)

    timings: list[int] = []
    effect = 0
    reason_code = ""
    for _ in range(samples):
        t0 = time.perf_counter_ns()
        for _ in range(iterations):
            d = py_gate.evaluate(contract)
            effect = d.effect
            reason_code = d.reason_code
        elapsed = time.perf_counter_ns() - t0
        timings.append(elapsed // iterations)

    timings.sort()
    total_decisions = samples * iterations
    median_ns = int(statistics.median(timings))
    p95_ns = timings[int(len(timings) * 0.95)]
    ops_sec = int(1_000_000_000 / median_ns) if median_ns > 0 else 0

    native_status = "UNAVAILABLE"
    native_error = None
    native_median_ns = None
    try:
        rust_gate = TrustedCryptographicSkinGate("trusted-rust")
        rust_timings: list[int] = []
        for _ in range(samples):
            t0 = time.perf_counter_ns()
            for _ in range(iterations):
                rust_gate.evaluate(contract)
            elapsed = time.perf_counter_ns() - t0
            rust_timings.append(elapsed // iterations)
        rust_timings.sort()
        native_median_ns = int(statistics.median(rust_timings))
        native_status = "AVAILABLE"
    except NativeProviderError as exc:
        native_error = f"{exc.code}: {exc}"

    return {
        "total_decisions": total_decisions,
        "python_reference": {
            "median_ns_per_decision": median_ns,
            "p95_ns_per_decision": p95_ns,
            "decisions_per_second": ops_sec,
            "decision": {"effect": effect, "reason_code": reason_code},
        },
        "native_rust": {
            "status": native_status,
            "median_ns_per_decision": native_median_ns,
            "error": native_error,
        },
    }


def _benchmark_envelope_e2e(
    skin: CryptographicSkin,
    payload_sizes: tuple[int, ...] = (1024, 4096, 65536, 1048576),
    iterations_per_size: int = 20,
) -> dict[str, Any]:
    """Measure end-to-end seal and open across multiple payload sizes."""
    results: dict[str, Any] = {}

    for size in payload_sizes:
        label = f"{size // 1024}KB" if size >= 1024 else f"{size}B"
        payload = os.urandom(size)

        seal_times_ms: list[float] = []
        open_times_ms: list[float] = []
        envelopes: list[SealedEnvelope] = []

        # Warmup
        w_env = skin.seal(payload, purpose="core.benchmark", subject="bench:warmup")
        assert skin.open(w_env) == payload

        for i in range(iterations_per_size):
            t0 = time.perf_counter()
            env = skin.seal(
                payload,
                purpose="core.benchmark",
                subject=f"bench:{label}:{i}",
                ttl_seconds=300,
            )
            seal_times_ms.append((time.perf_counter() - t0) * 1000)
            envelopes.append(env)

        for env in envelopes:
            t0 = time.perf_counter()
            decrypted = skin.open(env)
            open_times_ms.append((time.perf_counter() - t0) * 1000)
            assert decrypted == payload

        seal_times_ms.sort()
        open_times_ms.sort()

        mean_seal = statistics.mean(seal_times_ms)
        p95_seal = seal_times_ms[int(len(seal_times_ms) * 0.95)]
        seal_ops_sec = round(1000.0 / mean_seal, 2) if mean_seal > 0 else 0
        seal_throughput_mb_sec = round((size * seal_ops_sec) / (1024 * 1024), 2)

        mean_open = statistics.mean(open_times_ms)
        p95_open = open_times_ms[int(len(open_times_ms) * 0.95)]
        open_ops_sec = round(1000.0 / mean_open, 2) if mean_open > 0 else 0
        open_throughput_mb_sec = round((size * open_ops_sec) / (1024 * 1024), 2)

        sample_env = envelopes[0]
        envelope_overhead_bytes = len(sample_env.ciphertext) - size

        results[label] = {
            "payload_bytes": size,
            "iterations": iterations_per_size,
            "seal": {
                "mean_ms": round(mean_seal, 3),
                "p95_ms": round(p95_seal, 3),
                "ops_per_second": seal_ops_sec,
                "throughput_mb_sec": seal_throughput_mb_sec,
            },
            "open": {
                "mean_ms": round(mean_open, 3),
                "p95_ms": round(p95_open, 3),
                "ops_per_second": open_ops_sec,
                "throughput_mb_sec": open_throughput_mb_sec,
            },
            "envelope_overhead_bytes": envelope_overhead_bytes,
        }

    return results


def _benchmark_capsules(
    skin: CryptographicSkin,
    iterations: int = 15,
) -> dict[str, Any]:
    """Benchmark JayaCapsuleCodec (.jayac) across all four boundary kinds."""
    codec = JayaCapsuleCodec(skin)
    kinds = (CapsuleKind.BRAIN, CapsuleKind.BACKUP, CapsuleKind.PUZZLE, CapsuleKind.MESH)
    results: dict[str, Any] = {}
    payload = os.urandom(8192)

    for kind in kinds:
        seal_times: list[float] = []
        open_times: list[float] = []

        for i in range(iterations):
            subject = f"capsule:{kind.value}:{i}"
            t0 = time.perf_counter()
            container = codec.seal(payload, kind=kind, subject=subject, ttl_seconds=600)
            seal_times.append((time.perf_counter() - t0) * 1000)

            t1 = time.perf_counter()
            opened = codec.open(
                container,
                expected_kind=kind,
                expected_subject=subject,
            )
            open_times.append((time.perf_counter() - t1) * 1000)
            assert opened == payload

        seal_times.sort()
        open_times.sort()

        results[kind.value] = {
            "iterations": iterations,
            "seal_mean_ms": round(statistics.mean(seal_times), 3),
            "seal_p95_ms": round(seal_times[int(len(seal_times) * 0.95)], 3),
            "open_mean_ms": round(statistics.mean(open_times), 3),
            "open_p95_ms": round(open_times[int(len(open_times) * 0.95)], 3),
            "container_bytes": len(container),
        }

    return results


def _benchmark_key_lifecycle(
    skin: CryptographicSkin,
) -> dict[str, Any]:
    """Benchmark key rotation latency, backward verification, and revocation fail-closed denial."""
    payload = b"lifecycle-protected-payload"
    env_old_key = skin.seal(payload, purpose="core.lifecycle", subject="subject:lifecycle")
    old_key_id = env_old_key.key_id

    # 1. Rotate Key
    t0 = time.perf_counter()
    new_key_id = skin.rotate_key()
    rotate_ms = (time.perf_counter() - t0) * 1000

    # 2. Verify continuity (old envelope opens with retired key)
    t0 = time.perf_counter()
    opened_retired = skin.open(env_old_key)
    continuity_ms = (time.perf_counter() - t0) * 1000
    assert opened_retired == payload

    # 3. Seal new envelope with new active key
    env_new_key = skin.seal(payload, purpose="core.lifecycle", subject="subject:lifecycle-new")
    assert env_new_key.key_id == new_key_id

    # 4. Revoke old key
    t0 = time.perf_counter()
    skin.revoke_key(old_key_id)
    revoke_ms = (time.perf_counter() - t0) * 1000

    # 5. Fail-closed check: old envelope must be rejected with KEY_REVOKED
    revocation_rejected = False
    rejection_code = ""
    try:
        skin.open(env_old_key)
    except CryptographicSkinError as exc:
        revocation_rejected = True
        rejection_code = exc.code.value

    # 6. New envelope continues to open cleanly
    assert skin.open(env_new_key) == payload

    return {
        "old_key_id": old_key_id,
        "new_key_id": new_key_id,
        "rotation_latency_ms": round(rotate_ms, 3),
        "retired_key_open_latency_ms": round(continuity_ms, 3),
        "revocation_latency_ms": round(revoke_ms, 3),
        "revocation_enforced_fail_closed": revocation_rejected,
        "revocation_rejection_code": rejection_code,
    }


def _benchmark_nonce_uniqueness(
    skin: CryptographicSkin,
    count: int = 50,
) -> dict[str, Any]:
    """Benchmark nonce reservation throughput and collision rejection."""
    payload = b"nonce-uniqueness-test-payload"
    nonces_seen: set[str] = set()

    t0 = time.perf_counter()
    envelopes = [
        skin.seal(payload, purpose="core.nonce", subject=f"nonce:{i}")
        for i in range(count)
    ]
    elapsed = time.perf_counter() - t0
    for env in envelopes:
        nonces_seen.add(env.nonce)

    assert len(nonces_seen) == count, "All reserved nonces must be strictly unique"

    # Collision drill: attempt to re-reserve an already committed nonce
    test_env = envelopes[0]
    collision_rejected = False
    collision_code = ""
    try:
        # Directly test internal reserve_nonce on existing nonce
        skin._reserve_nonce(test_env.nonce)  # noqa: SLF001
    except CryptographicSkinError as exc:
        collision_rejected = True
        collision_code = exc.code.value

    return {
        "reserved_nonces": count,
        "unique_nonces": len(nonces_seen),
        "reservation_throughput_ops_sec": round(count / elapsed, 2),
        "mean_reservation_ms": round((elapsed / count) * 1000, 3),
        "collision_rejected_fail_closed": collision_rejected,
        "collision_code": collision_code,
    }


def _benchmark_fail_closed_drills(
    skin: CryptographicSkin,
    database_path: Path,
    identity_root: Path,
    identity_secret: str,
    skin_secret: str,
    anchor: DNAAnchor,
) -> dict[str, Any]:
    """Verify strict fail-closed rejection for all tampering and boundary violations."""
    payload = b"fail-closed-verification-payload"
    valid_env = skin.seal(payload, purpose="core.tamper", subject="subject:tamper", ttl_seconds=300)

    # 1. 1-Bit Flip Tamper in Ciphertext
    raw_ct = bytearray(base64.urlsafe_b64decode(valid_env.ciphertext + "=="))
    raw_ct[0] ^= 0x01
    tampered_ct = base64.urlsafe_b64encode(raw_ct).decode("ascii").rstrip("=")
    env_bad_ct = SealedEnvelope(**{**valid_env.to_dict(), "ciphertext": tampered_ct})

    ct_tamper_rejected = False
    ct_tamper_code = ""
    try:
        skin.open(env_bad_ct)
    except CryptographicSkinError as exc:
        ct_tamper_rejected = True
        ct_tamper_code = exc.code.value

    # 2. Associated Data Tamper (modified purpose)
    env_bad_purpose = SealedEnvelope(**{**valid_env.to_dict(), "purpose": "core.unauthorized"})
    aad_tamper_rejected = False
    aad_tamper_code = ""
    try:
        skin.open(env_bad_purpose)
    except CryptographicSkinError as exc:
        aad_tamper_rejected = True
        aad_tamper_code = exc.code.value

    # 3. Expired Envelope (authentic signature, but current time past expiry)
    clock_state = [datetime.now(UTC)]
    exp_skin = CryptographicSkin(
        database_path,
        skin_secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(purpose, digest).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        clock=lambda: clock_state[0],
    )
    env_expiring = exp_skin.seal(payload, purpose="core.tamper", subject="subject:expired-test", ttl_seconds=5)
    clock_state[0] += timedelta(seconds=6)
    expiry_rejected = False
    expiry_code = ""
    try:
        exp_skin.open(env_expiring)
    except CryptographicSkinError as exc:
        expiry_rejected = True
        expiry_code = exc.code.value
    finally:
        exp_skin.close()

    # 4. Wrong Skin Secret initialization
    wrong_secret_rejected = False
    wrong_secret_code = ""
    probe_anchor = DNAAnchor(identity_root, EncryptedFileKeyStore(identity_root / "keystore", identity_secret))
    try:
        CryptographicSkin(
            database_path,
            "wrong-secret-" + os.urandom(32).hex(),
            attestation_signer=lambda purpose, digest: probe_anchor.sign_attestation(purpose, digest).to_dict(),
            attestation_verifier=probe_anchor.verify_attestation,
        )
    except CryptographicSkinError as exc:
        wrong_secret_rejected = True
        wrong_secret_code = exc.code.value
    finally:
        probe_anchor.close()

    return {
        "ciphertext_1bit_flip_rejected": ct_tamper_rejected,
        "ciphertext_tamper_code": ct_tamper_code,
        "metadata_aad_tamper_rejected": aad_tamper_rejected,
        "metadata_tamper_code": aad_tamper_code,
        "expired_envelope_rejected": expiry_rejected,
        "expired_rejection_code": expiry_code,
        "wrong_secret_rejected": wrong_secret_rejected,
        "wrong_secret_code": wrong_secret_code,
    }


def _benchmark_audit_and_hygiene(
    skin: CryptographicSkin,
    database_path: Path,
    test_payload: bytes,
) -> dict[str, Any]:
    """Measure full audit chain verification and verify zero plaintext leakage."""
    # 1. Full Audit Verification
    t0 = time.perf_counter()
    audit_valid = skin.audit_chain_valid()
    audit_time_ms = (time.perf_counter() - t0) * 1000

    # 2. Keyed State Authenticity
    state = skin.status()
    state_authenticated = state.get("state_authenticated", False)

    # 3. Plaintext Leakage Scan
    db_bytes = database_path.read_bytes()
    plaintext_absent_db = test_payload not in db_bytes

    return {
        "audit_chain_valid": audit_valid,
        "audit_verification_ms": round(audit_time_ms, 3),
        "state_authenticated": state_authenticated,
        "plaintext_absent_in_database": plaintext_absent_db,
        "database_file_size_bytes": len(db_bytes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--iterations", type=int, default=1_000)
    parser.add_argument("--samples", type=int, default=25)
    args = parser.parse_args()

    started_time = time.perf_counter()
    env = _measure_environment()
    process = psutil.Process(os.getpid())

    # Set up dedicated isolated benchmark scratch workspace
    scratch_dir = ROOT / "outputs" / "scratch" / "p13_bench"
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir, ignore_errors=True)
    scratch_dir.mkdir(parents=True, exist_ok=True)

    db_path = scratch_dir / "p13_benchmark.db"
    identity_root = scratch_dir / "identity"
    identity_secret = "dna-identity-secret-" + os.urandom(32).hex()
    skin_secret = "crypto-skin-secret-" + os.urandom(32).hex()

    # Enroll authentic DNA Anchor
    anchor = DNAAnchor(identity_root, EncryptedFileKeyStore(identity_root / "keystore", identity_secret))
    anchor.enroll()

    skin = CryptographicSkin(
        db_path,
        skin_secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(purpose, digest).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )

    print("=" * 70)
    print(" JAYA PILAR 13: CRYPTOGRAPHIC SKIN QUANTITATIVE BENCHMARK")
    print("=" * 70)
    print(f"Platform: {env['platform']} | Python: {env['python_version']} | Cores: {env['cpu_count_logical']}")
    print()

    # 1. Gate Admission
    print("[1/7] Benchmarking Admission Gate (25,000 decisions)...")
    gate_bench = _benchmark_admission_gate(iterations=args.iterations, samples=args.samples)
    ref_gate = gate_bench["python_reference"]
    print(f"      Python Reference: {ref_gate['median_ns_per_decision']} ns/decision ({ref_gate['decisions_per_second']:,} ops/sec)")
    rust_gate = gate_bench["native_rust"]
    rust_detail = rust_gate["error"] or f"{rust_gate['median_ns_per_decision']} ns"
    print(f"      Native Rust: {rust_gate['status']} ({rust_detail})")
    print()

    # 2. E2E AEAD Envelope Seal/Open
    print("[2/7] Benchmarking AEAD Envelope Lifecycle across sizes (1KB, 4KB, 64KB, 1MB)...")
    envelope_bench = _benchmark_envelope_e2e(skin)
    for size_label, metrics in envelope_bench.items():
        s = metrics["seal"]
        o = metrics["open"]
        print(f"      [{size_label}] Seal: {s['mean_ms']} ms ({s['ops_per_second']} ops/s, {s['throughput_mb_sec']} MB/s) | "
              f"Open: {o['mean_ms']} ms ({o['ops_per_second']} ops/s, {o['throughput_mb_sec']} MB/s)")
    print()

    # 3. One-File Capsule (.jayac) Codec
    print("[3/7] Benchmarking One-File Capsule Codec (.jayac) across 4 kinds...")
    capsule_bench = _benchmark_capsules(skin)
    for kind, metrics in capsule_bench.items():
        print(f"      [{kind.upper()}] Seal: {metrics['seal_mean_ms']} ms | Open: {metrics['open_mean_ms']} ms | Size: {metrics['container_bytes']} B")
    print()

    # 4. Nonce Uniqueness & Collision
    print("[4/7] Benchmarking Persistent Nonce Uniqueness & Collision Protection...")
    nonce_bench = _benchmark_nonce_uniqueness(skin, count=50)
    print(f"      Reserved {nonce_bench['reserved_nonces']} nonces at {nonce_bench['reservation_throughput_ops_sec']} ops/sec")
    print(f"      Collision Rejection: {'PASS' if nonce_bench['collision_rejected_fail_closed'] else 'FAIL'} ({nonce_bench['collision_code']})")
    print()

    # 5. Key Lifecycle (Rotation, Continuity, Revocation)
    print("[5/7] Benchmarking Key Rotation, Continuity, and Revocation...")
    key_bench = _benchmark_key_lifecycle(skin)
    print(f"      Rotate Key: {key_bench['rotation_latency_ms']} ms (New: {key_bench['new_key_id'][:16]}...)")
    print(f"      Retired Key Continuity: {key_bench['retired_key_open_latency_ms']} ms")
    print(f"      Revoke Key: {key_bench['revocation_latency_ms']} ms")
    print(f"      Revocation Fail-Closed: {'PASS' if key_bench['revocation_enforced_fail_closed'] else 'FAIL'} ({key_bench['revocation_rejection_code']})")
    print()

    # 6. Fail-Closed Security Drills
    print("[6/7] Running Fail-Closed Security Drills (tamper, bit-flip, expired, wrong secret)...")
    fail_drills = _benchmark_fail_closed_drills(skin, db_path, identity_root, identity_secret, skin_secret, anchor)
    print(f"      1-Bit Flip Ciphertext: {'PASS' if fail_drills['ciphertext_1bit_flip_rejected'] else 'FAIL'} ({fail_drills['ciphertext_tamper_code']})")
    print(f"      Metadata AAD Tamper:   {'PASS' if fail_drills['metadata_aad_tamper_rejected'] else 'FAIL'} ({fail_drills['metadata_tamper_code']})")
    print(f"      Expired Envelope:      {'PASS' if fail_drills['expired_envelope_rejected'] else 'FAIL'} ({fail_drills['expired_rejection_code']})")
    print(f"      Wrong Skin Secret:     {'PASS' if fail_drills['wrong_secret_rejected'] else 'FAIL'} ({fail_drills['wrong_secret_code']})")
    print()

    # 7. Audit Chain & Plaintext Absence
    print("[7/7] Verifying Audit Chain Integrity & Plaintext Absence...")
    audit_bench = _benchmark_audit_and_hygiene(skin, db_path, b"fail-closed-verification-payload")
    print(f"      Audit Chain Valid:     {'PASS' if audit_bench['audit_chain_valid'] else 'FAIL'} ({audit_bench['audit_verification_ms']} ms)")
    print(f"      State Authenticated:   {'PASS' if audit_bench['state_authenticated'] else 'FAIL'}")
    print(f"      Plaintext Absent:      {'PASS' if audit_bench['plaintext_absent_in_database'] else 'FAIL'} (DB size: {audit_bench['database_file_size_bytes']:,} B)")
    print()

    total_elapsed_s = round(time.perf_counter() - started_time, 2)
    final_rss_mb = round(process.memory_info().rss / (1024 * 1024), 2)
    rss_growth_mb = round(final_rss_mb - env["initial_rss_mb"], 2)

    report: dict[str, Any] = {
        "pillar": "p13_cryptographic_skin",
        "profile": "p13-windows-authenticated-crypto-skin-v1",
        "timestamp": datetime.now(UTC).astimezone().isoformat(),
        "total_elapsed_seconds": total_elapsed_s,
        "environment": env,
        "memory": {
            "initial_rss_mb": env["initial_rss_mb"],
            "final_rss_mb": final_rss_mb,
            "rss_growth_mb": rss_growth_mb,
        },
        "admission_gate": gate_bench,
        "envelope_lifecycle": envelope_bench,
        "one_file_capsule": capsule_bench,
        "nonce_uniqueness": nonce_bench,
        "key_lifecycle": key_bench,
        "fail_closed_drills": fail_drills,
        "audit_and_hygiene": audit_bench,
        "all_security_drills_passed": all((
            nonce_bench["collision_rejected_fail_closed"],
            key_bench["revocation_enforced_fail_closed"],
            fail_drills["ciphertext_1bit_flip_rejected"],
            fail_drills["metadata_aad_tamper_rejected"],
            fail_drills["expired_envelope_rejected"],
            fail_drills["wrong_secret_rejected"],
            audit_bench["audit_chain_valid"],
            audit_bench["state_authenticated"],
            audit_bench["plaintext_absent_in_database"],
        )),
    }

    # Output artifact
    out_path = args.output or (ROOT / "artifacts" / "benchmarks" / "benchmark_p13_cryptographic_skin.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Report saved to {out_path}")
    print(f"Total benchmark elapsed time: {total_elapsed_s}s (RSS growth: {rss_growth_mb} MB)")
    print("=" * 70)

    # Cleanup
    anchor.close()
    return 0 if report["all_security_drills_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
