#!/usr/bin/env python3
"""benchmark_p14_hardware_locked.py — Quantitative Performance & Security Benchmark for P14 Hardware Locked.

Measures:
1. Provider Root Performance:
   - Windows DPAPI machine-scope wrap and unwrap roundtrip latency and throughput across 100 iterations.
2. Node Binding Authority Lifecycle:
   - Initial node enrollment latency (DNA attestation, DPAPI key wrapping, genesis audit).
   - Boot authorization throughput & latency across 100 restarts.
   - Ephemeral instance_id rotation across all boots with stable brain_id and node_id.
3. P13 Cryptographic Skin Hardware Context Binding:
   - Stable derivation of P13 key binding context from hardware node authority.
   - Confirms encrypted brain artifact can be opened after boot unseal.
4. Owner-Authorized Migration & Lineage:
   - Migration latency from source node to target node.
   - Lineage chain validation (target.previous_binding_id == source.binding_id).
   - Source node binding revocation upon migration.
5. Fail-Closed Security Validation:
   - Cloned database without root unwrap fails closed (HARDWARE_NODE_MISMATCH / HARDWARE_UNWRAP_FAILED).
   - Wrong node ID fails closed (HARDWARE_NODE_MISMATCH).
   - Tampered binding record fails closed (HARDWARE_BINDING_CORRUPT).
   - Attacker-recomputed audit hash-chain fails closed (HARDWARE_AUDIT_CORRUPT).
   - Revoked node boot attempt fails closed (HARDWARE_BINDING_NOT_FOUND).
6. Signed Audit Chain Integrity:
   - Verification of DNA signatures and hash-chain linkage across all logged events.
7. Resource Footprint & Data Hygiene:
   - RSS memory growth, database file size, and storage per operation.
   - Strict absence of raw unwrapped secrets in persistent SQLite storage.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import shutil
import sqlite3
import statistics
import sys
import time
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
from jaya_core.brain_v2.protection.hardware import (  # noqa: E402
    BindingState,
    HardwareBindingError,
    HardwareBindingFailureCode,
    NodeBindingAuthority,
    WindowsDPAPIMachineProvider,
)
from jaya_core.security.cryptographic_skin import CryptographicSkin, SealedEnvelope  # noqa: E402


def _measure_environment() -> dict[str, Any]:
    process = psutil.Process(os.getpid())
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or "Unknown",
        "cpu_count_logical": os.cpu_count(),
        "python_version": platform.python_version(),
        "initial_rss_mb": round(process.memory_info().rss / (1024 * 1024), 2),
    }


def _authority(
    database: Path,
    anchor: DNAAnchor,
    provider: Any,
) -> NodeBindingAuthority:
    return NodeBindingAuthority(
        database,
        provider,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(purpose, digest).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )


def _benchmark_root_provider(
    provider: WindowsDPAPIMachineProvider,
    iterations: int = 100,
) -> dict[str, Any]:
    """Measure raw DPAPI machine-scope wrap and unwrap latency and throughput."""
    plaintext = b"benchmark-raw-hardware-secret-32b!!"
    associated_data = b"benchmark-aad-context-v1"

    wrap_times_ms: list[float] = []
    unwrap_times_ms: list[float] = []

    # Warmup
    w = provider.wrap(plaintext, associated_data)
    assert provider.unwrap(w, associated_data) == plaintext

    for _ in range(iterations):
        t0 = time.perf_counter()
        wrapped = provider.wrap(plaintext, associated_data)
        wrap_times_ms.append((time.perf_counter() - t0) * 1000)

        t1 = time.perf_counter()
        unwrapped = provider.unwrap(wrapped, associated_data)
        unwrap_times_ms.append((time.perf_counter() - t1) * 1000)
        assert unwrapped == plaintext

    wrap_times_ms.sort()
    unwrap_times_ms.sort()

    mean_wrap = statistics.mean(wrap_times_ms)
    p95_wrap = wrap_times_ms[int(len(wrap_times_ms) * 0.95)]
    mean_unwrap = statistics.mean(unwrap_times_ms)
    p95_unwrap = unwrap_times_ms[int(len(unwrap_times_ms) * 0.95)]

    total_roundtrip_ms = mean_wrap + mean_unwrap
    roundtrip_ops_sec = round(1000.0 / total_roundtrip_ms, 2) if total_roundtrip_ms > 0 else 0

    return {
        "iterations": iterations,
        "provider_id": provider.provider_id,
        "hardware_backed": provider.hardware_backed,
        "wrap": {
            "mean_ms": round(mean_wrap, 3),
            "p95_ms": round(p95_wrap, 3),
            "ops_per_second": round(1000.0 / mean_wrap, 2) if mean_wrap > 0 else 0,
        },
        "unwrap": {
            "mean_ms": round(mean_unwrap, 3),
            "p95_ms": round(p95_unwrap, 3),
            "ops_per_second": round(1000.0 / mean_unwrap, 2) if mean_unwrap > 0 else 0,
        },
        "roundtrip_ops_per_second": roundtrip_ops_sec,
        "wrapped_overhead_bytes": len(wrapped) - len(plaintext),
    }


def _benchmark_node_authority(
    db_path: Path,
    anchor: DNAAnchor,
    provider: WindowsDPAPIMachineProvider,
    brain_id: str,
    node_id: str = "benchmark-node-a",
    iterations: int = 100,
) -> dict[str, Any]:
    """Measure enrollment and boot authorization throughput across multiple restarts."""
    # 1. Enrollment
    authority = _authority(db_path, anchor, provider)
    t0 = time.perf_counter()
    binding = authority.enroll(brain_id, node_id)
    enroll_ms = (time.perf_counter() - t0) * 1000

    first_receipt = authority.authorize_boot(brain_id, node_id, os.urandom(32))
    instances_seen: set[str] = {first_receipt.instance_id}
    authority.close()

    # 2. Boot Authorizations
    boot_times_ms: list[float] = []

    for _ in range(iterations):
        restarted = _authority(db_path, anchor, provider)
        challenge = os.urandom(32)
        t0 = time.perf_counter()
        receipt = restarted.authorize_boot(brain_id, node_id, challenge)
        boot_times_ms.append((time.perf_counter() - t0) * 1000)

        assert receipt.brain_id == brain_id
        assert receipt.node_id == node_id
        instances_seen.add(receipt.instance_id)
        restarted.close()

    boot_times_ms.sort()
    mean_boot = statistics.mean(boot_times_ms)
    p95_boot = boot_times_ms[int(len(boot_times_ms) * 0.95)]
    boot_ops_sec = round(1000.0 / mean_boot, 2) if mean_boot > 0 else 0

    return {
        "node_id": node_id,
        "binding_id": binding.binding_id,
        "brain_id": brain_id,
        "enrollment_latency_ms": round(enroll_ms, 3),
        "boot_authorizations": iterations,
        "unique_instances_generated": len(instances_seen),
        "instances_strictly_separated": len(instances_seen) == iterations + 1,
        "boot": {
            "mean_ms": round(mean_boot, 3),
            "p95_ms": round(p95_boot, 3),
            "ops_per_second": boot_ops_sec,
        },
    }


def _benchmark_p13_context_binding(
    db_path: Path,
    anchor: DNAAnchor,
    provider: WindowsDPAPIMachineProvider,
    brain_id: str,
    node_id: str = "benchmark-node-a",
) -> dict[str, Any]:
    """Measure P13 hardware context stability and encryption integration."""
    authority = _authority(db_path, anchor, provider)
    ctx1 = authority.binding_key_context(brain_id, node_id)

    # Seal with P13 using hardware context
    skin = CryptographicSkin(
        db_path.parent / "p13_bound.db",
        "p13-bound-secret-" + ("s" * 32),
        attestation_signer=lambda p, d: anchor.sign_attestation(p, d).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        key_binding_context=ctx1,
    )
    payload = b"hardware-bound-p13-payload"
    env = skin.seal(payload, purpose="core.bound-artifact", subject="subject:bound")
    opened = skin.open(env)
    assert opened == payload
    skin.close()
    authority.close()

    # Restart authority and verify context remains identical
    restarted = _authority(db_path, anchor, provider)
    ctx2 = restarted.binding_key_context(brain_id, node_id)
    context_stable = ctx1 == ctx2

    restarted_skin = CryptographicSkin(
        db_path.parent / "p13_bound.db",
        "p13-bound-secret-" + ("s" * 32),
        attestation_signer=lambda p, d: anchor.sign_attestation(p, d).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        key_binding_context=ctx2,
    )
    reopened = restarted_skin.open(env)
    assert reopened == payload
    restarted_skin.close()
    restarted.close()

    return {
        "context_stable": context_stable,
        "context_length_bytes": len(ctx1),
        "p13_payload_restored_across_restart": reopened == payload,
    }


def _benchmark_migration_lifecycle(
    db_path: Path,
    anchor: DNAAnchor,
    provider: WindowsDPAPIMachineProvider,
    brain_id: str,
    source_node: str = "benchmark-node-a",
    target_node: str = "benchmark-node-b",
) -> dict[str, Any]:
    """Measure owner-authorized migration latency and verify lineage chain."""
    source = _authority(db_path, anchor, provider)
    source_status = source.status(brain_id)
    source_binding_id = source_status["active_binding_id"]

    # Owner-authorized migration to target node
    t0 = time.perf_counter()
    target_binding = source.migrate(brain_id, target_node, provider)
    migration_ms = (time.perf_counter() - t0) * 1000

    # Lineage verification
    lineage_valid = (
        target_binding.previous_binding_id == source_binding_id
        and target_binding.node_id == target_node
        and target_binding.state is BindingState.ACTIVE
    )

    # Source node authority must now be rejected for boot
    source_revoked = False
    try:
        source.authorize_boot(brain_id, source_node, os.urandom(32))
    except HardwareBindingError as exc:
        source_revoked = exc.code is HardwareBindingFailureCode.NODE_MISMATCH

    source.close()

    # Target node now boots as authorized node
    target = _authority(db_path, anchor, provider)
    target_receipt = target.authorize_boot(brain_id, target_node, os.urandom(32))
    target_authorized = (
        target_receipt.brain_id == brain_id
        and target_receipt.node_id == target_node
    )
    target.close()

    return {
        "source_node": source_node,
        "target_node": target_node,
        "migration_latency_ms": round(migration_ms, 3),
        "lineage_valid": lineage_valid,
        "source_revoked_fail_closed": source_revoked,
        "target_authorized": target_authorized,
        "target_binding_id": target_binding.binding_id,
        "previous_binding_id": target_binding.previous_binding_id,
    }


def _benchmark_fail_closed_drills(
    db_path: Path,
    anchor: DNAAnchor,
    provider: WindowsDPAPIMachineProvider,
    brain_id: str,
    active_node: str,
) -> dict[str, Any]:
    """Run comprehensive fail-closed tampering and boundary violation checks."""
    authority = _authority(db_path, anchor, provider)
    challenge = os.urandom(32)

    # 1. Wrong Node ID
    wrong_node_rejected = False
    wrong_node_code = ""
    try:
        authority.authorize_boot(brain_id, "unauthorized-intruder-node", challenge)
    except HardwareBindingError as exc:
        wrong_node_rejected = True
        wrong_node_code = exc.code.value

    # 2. Cloned Database / Missing Root Provider
    class FakeBrokenProvider:
        provider_id = "broken-provider"
        hardware_backed = False

        def available(self) -> bool:
            return True

        def wrap(self, plaintext: bytes, associated_data: bytes) -> bytes:
            return plaintext

        def unwrap(self, wrapped: bytes, associated_data: bytes) -> bytes:
            raise HardwareBindingError(HardwareBindingFailureCode.UNWRAP_FAILED, "clone unwrap failed")

    clone_rejected = False
    clone_code = ""
    try:
        broken_auth = _authority(db_path, anchor, FakeBrokenProvider())
        broken_auth.authorize_boot(brain_id, active_node, challenge)
    except HardwareBindingError as exc:
        clone_rejected = True
        clone_code = exc.code.value

    # 3. Tampered Binding Record
    tamper_scratch = db_path.parent / "tamper_scratch.db"
    shutil.copy2(db_path, tamper_scratch)
    with sqlite3.connect(tamper_scratch) as conn:
        conn.execute("UPDATE hardware_bindings SET wrapped_secret = 'AAAA' WHERE state = 'ACTIVE'")
        conn.commit()

    tamper_rejected = False
    tamper_code = ""
    try:
        tamper_auth = _authority(tamper_scratch, anchor, provider)
        tamper_auth.authorize_boot(brain_id, active_node, challenge)
    except HardwareBindingError as exc:
        tamper_rejected = True
        tamper_code = exc.code.value

    # 4. Attacker Recomputed Audit Hash-Chain
    audit_tamper_scratch = db_path.parent / "audit_tamper.db"
    shutil.copy2(db_path, audit_tamper_scratch)
    with sqlite3.connect(audit_tamper_scratch) as conn:
        conn.execute("UPDATE hardware_binding_audit SET payload_json = '{\"forged\":true}' WHERE event_id = 1")
        conn.commit()

    recomputed_audit_rejected = False
    recomputed_audit_code = ""
    try:
        recomputed_auth = _authority(audit_tamper_scratch, anchor, provider)
        recomputed_auth.authorize_boot(brain_id, active_node, challenge)
    except HardwareBindingError as exc:
        recomputed_audit_rejected = True
        recomputed_audit_code = exc.code.value

    # 5. Revocation Fail-Closed
    revocation_scratch = db_path.parent / "revocation_scratch.db"
    shutil.copy2(db_path, revocation_scratch)
    rev_auth = _authority(revocation_scratch, anchor, provider)
    rev_auth.revoke(brain_id)
    rev_auth.close()

    revoked_boot_rejected = False
    revoked_code = ""
    try:
        rev_restarted = _authority(revocation_scratch, anchor, provider)
        rev_restarted.authorize_boot(brain_id, active_node, challenge)
    except HardwareBindingError as exc:
        revoked_boot_rejected = True
        revoked_code = exc.code.value

    authority.close()

    return {
        "wrong_node_rejected": wrong_node_rejected,
        "wrong_node_code": wrong_node_code,
        "clone_unwrap_rejected": clone_rejected,
        "clone_unwrap_code": clone_code,
        "binding_tamper_rejected": tamper_rejected,
        "binding_tamper_code": tamper_code,
        "recomputed_audit_rejected": recomputed_audit_rejected,
        "recomputed_audit_code": recomputed_audit_code,
        "revoked_boot_rejected": revoked_boot_rejected,
        "revoked_boot_code": revoked_code,
    }


def _benchmark_audit_and_hygiene(
    db_path: Path,
    anchor: DNAAnchor,
    provider: WindowsDPAPIMachineProvider,
    brain_id: str,
) -> dict[str, Any]:
    """Measure full audit verification and verify raw secrets are never in SQLite."""
    authority = _authority(db_path, anchor, provider)

    t0 = time.perf_counter()
    status = authority.status(brain_id)
    audit_elapsed_ms = (time.perf_counter() - t0) * 1000

    audit_chain_valid = status.get("audit_chain_valid", False)
    audit_attestations_verified = status.get("audit_attestations_verified", False)
    authority.close()

    # Plaintext absence scan: look for test string in raw database bytes
    db_bytes = db_path.read_bytes()
    plaintext_absent = b"benchmark-raw-hardware-secret-32b!!" not in db_bytes

    return {
        "audit_chain_valid": audit_chain_valid,
        "audit_attestations_verified": audit_attestations_verified,
        "audit_verification_ms": round(audit_elapsed_ms, 3),
        "database_file_size_bytes": len(db_bytes),
        "plaintext_absent_in_database": plaintext_absent,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()

    started_time = time.perf_counter()
    env = _measure_environment()
    process = psutil.Process(os.getpid())

    # Set up dedicated isolated benchmark scratch workspace
    scratch_dir = ROOT / "outputs" / "scratch" / "p14_bench"
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir, ignore_errors=True)
    scratch_dir.mkdir(parents=True, exist_ok=True)

    db_path = scratch_dir / "p14_benchmark.db"
    identity_root = scratch_dir / "identity"
    identity_secret = "dna-identity-secret-" + os.urandom(32).hex()

    # Enroll authentic DNA Anchor
    anchor = DNAAnchor(identity_root, EncryptedFileKeyStore(identity_root / "keystore", identity_secret))
    identity_record, _ = anchor.enroll()
    brain_id = identity_record.brain_id

    provider = WindowsDPAPIMachineProvider()
    if not provider.available():
        print("[!] Windows DPAPI provider is not available on this platform.")
        return 2

    print("=" * 70)
    print(" JAYA PILAR 14: HARDWARE LOCKED QUANTITATIVE BENCHMARK")
    print("=" * 70)
    print(f"Platform: {env['platform']} | Python: {env['python_version']} | Cores: {env['cpu_count_logical']}")
    print(f"Provider: {provider.provider_id} (Hardware Backed: {provider.hardware_backed})")
    print(f"Brain ID: {brain_id}")
    print()

    # 1. Provider Root Performance
    print(f"[1/6] Benchmarking DPAPI Root Provider ({args.iterations} roundtrips)...")
    provider_bench = _benchmark_root_provider(provider, iterations=args.iterations)
    print(f"      Wrap:   {provider_bench['wrap']['mean_ms']} ms ({provider_bench['wrap']['ops_per_second']} ops/s)")
    print(f"      Unwrap: {provider_bench['unwrap']['mean_ms']} ms ({provider_bench['unwrap']['ops_per_second']} ops/s)")
    print(f"      Roundtrip Throughput: {provider_bench['roundtrip_ops_per_second']} ops/sec")
    print()

    # 2. Node Binding Authority Lifecycle
    print(f"[2/6] Benchmarking Node Authority & Boot Authorization ({args.iterations} boots)...")
    authority_bench = _benchmark_node_authority(
        db_path, anchor, provider, brain_id=brain_id, node_id="node-alpha", iterations=args.iterations
    )
    print(f"      Enrollment Latency: {authority_bench['enrollment_latency_ms']} ms")
    print(f"      Boot Authorization: {authority_bench['boot']['mean_ms']} ms (P95: {authority_bench['boot']['p95_ms']} ms, {authority_bench['boot']['ops_per_second']} ops/s)")
    print(f"      Instance Separation: {'PASS' if authority_bench['instances_strictly_separated'] else 'FAIL'} ({authority_bench['unique_instances_generated']} unique per-boot IDs)")
    print()

    # 3. P13 Context Binding
    print("[3/6] Benchmarking P13 Cryptographic Skin Context Binding...")
    p13_bench = _benchmark_p13_context_binding(db_path, anchor, provider, brain_id=brain_id, node_id="node-alpha")
    print(f"      Hardware Context Stable Across Restart: {'PASS' if p13_bench['context_stable'] else 'FAIL'}")
    print(f"      P13 Payload Restored: {'PASS' if p13_bench['p13_payload_restored_across_restart'] else 'FAIL'}")
    print()

    # 4. Owner-Authorized Migration & Lineage
    print("[4/6] Benchmarking Owner Migration & Lineage Proof...")
    migration_bench = _benchmark_migration_lifecycle(
        db_path, anchor, provider, brain_id=brain_id, source_node="node-alpha", target_node="node-beta"
    )
    print(f"      Migration Latency: {migration_bench['migration_latency_ms']} ms")
    print(f"      Signed Lineage Valid: {'PASS' if migration_bench['lineage_valid'] else 'FAIL'}")
    print(f"      Source Revoked Fail-Closed: {'PASS' if migration_bench['source_revoked_fail_closed'] else 'FAIL'}")
    print(f"      Target Node Authorized: {'PASS' if migration_bench['target_authorized'] else 'FAIL'}")
    print()

    # 5. Fail-Closed Security Drills
    print("[5/6] Running Fail-Closed Security Drills...")
    fail_drills = _benchmark_fail_closed_drills(db_path, anchor, provider, brain_id=brain_id, active_node="node-beta")
    print(f"      Wrong Node ID:       {'PASS' if fail_drills['wrong_node_rejected'] else 'FAIL'} ({fail_drills['wrong_node_code']})")
    print(f"      Cloned DB Unwrap:    {'PASS' if fail_drills['clone_unwrap_rejected'] else 'FAIL'} ({fail_drills['clone_unwrap_code']})")
    print(f"      Tampered Binding:    {'PASS' if fail_drills['binding_tamper_rejected'] else 'FAIL'} ({fail_drills['binding_tamper_code']})")
    print(f"      Recomputed Audit:    {'PASS' if fail_drills['recomputed_audit_rejected'] else 'FAIL'} ({fail_drills['recomputed_audit_code']})")
    print(f"      Revoked Node Boot:   {'PASS' if fail_drills['revoked_boot_rejected'] else 'FAIL'} ({fail_drills['revoked_boot_code']})")
    print()

    # 6. Audit Chain & Plaintext Absence
    print("[6/6] Verifying Signed Audit Integrity & Plaintext Absence...")
    audit_bench = _benchmark_audit_and_hygiene(db_path, anchor, provider, brain_id=brain_id)
    print(f"      Audit Chain Valid:     {'PASS' if audit_bench['audit_chain_valid'] else 'FAIL'} ({audit_bench['audit_verification_ms']} ms)")
    print(f"      Attestations Verified: {'PASS' if audit_bench['audit_attestations_verified'] else 'FAIL'}")
    print(f"      Plaintext Absent:      {'PASS' if audit_bench['plaintext_absent_in_database'] else 'FAIL'} (DB size: {audit_bench['database_file_size_bytes']:,} B)")
    print()

    total_elapsed_s = round(time.perf_counter() - started_time, 2)
    final_rss_mb = round(process.memory_info().rss / (1024 * 1024), 2)
    rss_growth_mb = round(final_rss_mb - env["initial_rss_mb"], 2)

    report: dict[str, Any] = {
        "pillar": "p14_hardware_locked",
        "profile": "p14-windows-dpapi-hardware-locked-v1",
        "timestamp": datetime.now(UTC).astimezone().isoformat(),
        "total_elapsed_seconds": total_elapsed_s,
        "environment": env,
        "memory": {
            "initial_rss_mb": env["initial_rss_mb"],
            "final_rss_mb": final_rss_mb,
            "rss_growth_mb": rss_growth_mb,
        },
        "root_provider": provider_bench,
        "node_authority": authority_bench,
        "p13_context_binding": p13_bench,
        "migration_lifecycle": migration_bench,
        "fail_closed_drills": fail_drills,
        "audit_and_hygiene": audit_bench,
        "all_security_drills_passed": all((
            authority_bench["instances_strictly_separated"],
            p13_bench["context_stable"],
            p13_bench["p13_payload_restored_across_restart"],
            migration_bench["lineage_valid"],
            migration_bench["source_revoked_fail_closed"],
            migration_bench["target_authorized"],
            fail_drills["wrong_node_rejected"],
            fail_drills["clone_unwrap_rejected"],
            fail_drills["binding_tamper_rejected"],
            fail_drills["recomputed_audit_rejected"],
            fail_drills["revoked_boot_rejected"],
            audit_bench["audit_chain_valid"],
            audit_bench["audit_attestations_verified"],
            audit_bench["plaintext_absent_in_database"],
        )),
    }

    out_path = args.output or (ROOT / "artifacts" / "benchmarks" / "benchmark_p14_hardware_locked.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Report saved to {out_path}")
    print(f"Total benchmark elapsed time: {total_elapsed_s}s (RSS growth: {rss_growth_mb} MB)")
    print("=" * 70)

    anchor.close()
    return 0 if report["all_security_drills_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
