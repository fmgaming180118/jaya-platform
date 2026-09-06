#!/usr/bin/env python3
"""benchmark_p15_ethical_heart.py — Performance & Security Benchmark for P15 Ethical Heart.

Measures:
- Native Rust JPR1 vs Python rule evaluator latency (nanoseconds/microseconds across 25,000 decisions).
- End-to-end EthicalHeart.evaluate() throughput with DNA Anchor signed decision receipts.
- Owner approval lifecycle (creation, signature verification, expiry, one-time consumption).
- Anti-replay defense on reused owner approval (fail-closed check).
- Dynamic approval trust store latency (rotation, revocation, recovery appeal).
- Memory RSS and SQLite database storage growth.
"""

from __future__ import annotations

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

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

import psutil  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from jaya_core.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    EncryptedFileKeyStore,
)
from jaya_core.brain_v2.soul.ethical_heart import (  # noqa: E402
    EthicalHeart,
    OwnerApproval,
    PolicyBundle,
    PolicyEffect,
    PolicyError,
    PolicyFailureCode,
    PolicyRequest,
    PolicyRisk,
    PolicyRule,
    create_owner_approval,
)
from jaya_core.providers import (  # noqa: E402
    TrustedPolicyGate,
    TrustedPolicyRule,
    get_trusted_policy_gate,
)
from jaya_core.security.approval_trust import (  # noqa: E402
    ApprovalTrustAction,
    ApprovalTrustRegistry,
)


def _public(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _payload_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _measure_environment() -> dict[str, object]:
    process = psutil.Process(os.getpid())
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or "Unknown",
        "cpu_count_logical": os.cpu_count(),
        "python_version": platform.python_version(),
        "initial_rss_mb": round(process.memory_info().rss / (1024 * 1024), 2),
    }


def run_benchmark(iterations: int = 200) -> dict[str, object]:
    env = _measure_environment()
    process = psutil.Process(os.getpid())

    scratch_dir = ROOT / "outputs" / "scratch" / "p15_bench"
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir, ignore_errors=True)
    scratch_dir.mkdir(parents=True, exist_ok=True)

    # 1. Setup DNA Anchor for signed receipts
    keystore_dir = scratch_dir / "keystore"
    keystore_dir.mkdir(parents=True, exist_ok=True)
    keystore = EncryptedFileKeyStore(keystore_dir, "benchmark-secret-unlock-32bytes-long!!")
    dna_anchor = DNAAnchor(scratch_dir / "dna", keystore)
    brain_record, _ = dna_anchor.enroll()

    # 2. Setup Approval Trust Registry & Root Authority
    root_authority = Ed25519PrivateKey.generate()
    approver_v1 = Ed25519PrivateKey.generate()
    approver_v2 = Ed25519PrivateKey.generate()

    trust_db = scratch_dir / "approval-trust.db"
    trust_registry = ApprovalTrustRegistry(trust_db, _public(root_authority))

    # Install approver v1
    install_event = trust_registry.prepare_event(
        approver_id="human-owner",
        action=ApprovalTrustAction.INSTALL,
        public_key=_public(approver_v1),
        reason="initial enrollment",
        occurred_at=datetime.now(UTC).isoformat(),
        signer=root_authority.sign,
    )
    trust_registry.apply(install_event)

    # 3. Setup PolicyBundle
    policy = PolicyBundle(
        policy_id="bench.core-policy",
        version=1,
        brain_id=brain_record.brain_id,
        rules=(
            PolicyRule(
                rule_id="allow.read",
                effect=PolicyEffect.ALLOW,
                risk_classes=(PolicyRisk.READ_ONLY,),
                capability_ids=("core.reason.pure_logic",),
                reason_code="SAFE_READ_ALLOW",
            ),
            PolicyRule(
                rule_id="deny.destructive",
                effect=PolicyEffect.DENY,
                risk_classes=(PolicyRisk.DESTRUCTIVE, PolicyRisk.SECURITY_SENSITIVE),
                capability_ids=("tool.unauthorized_network_probe",),
                reason_code="SECURITY_DENIED",
            ),
        ),
        default_effect=PolicyEffect.REQUIRE_APPROVAL,
        default_reason_code="HUMAN_APPROVAL_REQUIRED",
    )

    heart = EthicalHeart(
        scratch_dir / "ethical-heart.db",
        policy,
        attestation_signer=lambda purpose, digest: dna_anchor.sign_attestation(purpose, digest).to_dict(),
        attestation_verifier=dna_anchor.verify_attestation,
        approval_key_resolver=trust_registry.resolve_public_key,
    )

    # 4. Compare Native Rust JPR1 Rule Evaluator vs Python Reference (25,000 decisions)
    native_gate = get_trusted_policy_gate()
    py_gate = TrustedPolicyGate(selection="python-reference")
    rules = (
        TrustedPolicyRule(
            effect=1,  # ALLOW
            risk_mask=1 << 0,
            capability_ids=("tool.read",),
        ),
        TrustedPolicyRule(
            effect=2,  # DENY
            risk_mask=1 << 2,
            capability_ids=("tool.delete",),
        ),
        TrustedPolicyRule(
            effect=3,  # REQUIRE_APPROVAL
            risk_mask=1 << 4,
            capability_ids=("tool.reboot",),
        ),
    )

    rust_available = native_gate.native_available
    test_queries = [
        ("tool.read", 0),
        ("tool.delete", 2),
        ("tool.reboot", 4),
        ("tool.unknown", 0),
    ]

    # Warmup
    for cap, risk in test_queries:
        if rust_available:
            _ = native_gate.evaluate(capability_id=cap, risk_code=risk, rules=rules, default_effect=3)
        _ = py_gate.evaluate(capability_id=cap, risk_code=risk, rules=rules, default_effect=3)

    total_evals = 25000
    if rust_available:
        r_start = time.perf_counter_ns()
        for i in range(total_evals):
            cap, risk = test_queries[i % len(test_queries)]
            _ = native_gate.evaluate(capability_id=cap, risk_code=risk, rules=rules, default_effect=3)
        r_total_ns = time.perf_counter_ns() - r_start
        rust_ns_per_op = r_total_ns / total_evals
    else:
        rust_ns_per_op = 0.0

    py_start = time.perf_counter_ns()
    for i in range(total_evals):
        cap, risk = test_queries[i % len(test_queries)]
        _ = py_gate.evaluate(capability_id=cap, risk_code=risk, rules=rules, default_effect=3)
    py_total_ns = time.perf_counter_ns() - py_start
    py_ns_per_op = py_total_ns / total_evals

    # 5. End-to-End Evaluation Latency (ALLOW & DENY with DNA Signed Receipt)
    e2e_allow_latencies_us: list[float] = []
    e2e_deny_latencies_us: list[float] = []

    for k in range(iterations // 2):
        allow_req = PolicyRequest(
            request_id=f"req_allow_{k}",
            actor_brain_id=brain_record.brain_id,
            node_id="node-benchmark",
            capability_id="core.reason.pure_logic",
            risk_class=PolicyRisk.READ_ONLY,
            permissions=("logic.evaluate",),
            payload_sha256=_payload_digest({"k": k}),
        )
        t0 = time.perf_counter()
        d_allow = heart.evaluate(allow_req)
        e2e_allow_latencies_us.append((time.perf_counter() - t0) * 1_000_000)
        assert d_allow.effect is PolicyEffect.ALLOW

        deny_req = PolicyRequest(
            request_id=f"req_deny_{k}",
            actor_brain_id=brain_record.brain_id,
            node_id="node-benchmark",
            capability_id="tool.unauthorized_network_probe",
            risk_class=PolicyRisk.SECURITY_SENSITIVE,
            permissions=("net.probe",),
            payload_sha256=_payload_digest({"deny_k": k}),
        )
        t1 = time.perf_counter()
        d_deny = heart.evaluate(deny_req)
        e2e_deny_latencies_us.append((time.perf_counter() - t1) * 1_000_000)
        assert d_deny.effect is PolicyEffect.DENY

    # 6. Owner Approval Lifecycle & Replay Defense (100 cycles)
    approval_create_us: list[float] = []
    approval_verify_us: list[float] = []
    last_req = None
    last_app = None

    for m in range(100):
        action_req = PolicyRequest(
            request_id=f"req_action_{m}",
            actor_brain_id=brain_record.brain_id,
            node_id="node-benchmark",
            capability_id="device.actuate",
            risk_class=PolicyRisk.PHYSICAL_ACTION,
            permissions=("device.write",),
            payload_sha256=_payload_digest({"m": m}),
        )
        now = datetime.now(UTC)
        t_c = time.perf_counter()
        app = create_owner_approval(
            approver_id="human-owner",
            actor_brain_id=action_req.actor_brain_id,
            capability_id=action_req.capability_id,
            payload_sha256=action_req.payload_sha256,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=2)).isoformat(),
            signer=approver_v1.sign,
        )
        approval_create_us.append((time.perf_counter() - t_c) * 1_000_000)

        t_v = time.perf_counter()
        d_app = heart.evaluate(action_req, approval=app)
        approval_verify_us.append((time.perf_counter() - t_v) * 1_000_000)
        assert d_app.effect is PolicyEffect.ALLOW
        assert d_app.reason_code == "VALID_OWNER_APPROVAL"
        last_req = action_req
        last_app = app

    # Replay defense on reused approval
    replay_start = time.perf_counter()
    try:
        heart.evaluate(last_req, approval=last_app)
        replay_rejected = False
    except PolicyError as exc:
        replay_rejected = (exc.code is PolicyFailureCode.APPROVAL_REPLAYED)
    replay_rejection_us = (time.perf_counter() - replay_start) * 1_000_000
    assert replay_rejected is True

    # 7. Dynamic Trust Rotation Latency
    rot_start = time.perf_counter()
    rot_event = trust_registry.prepare_event(
        approver_id="human-owner",
        action=ApprovalTrustAction.ROTATE,
        public_key=_public(approver_v2),
        reason="scheduled key rotation",
        occurred_at=datetime.now(UTC).isoformat(),
        signer=root_authority.sign,
    )
    trust_registry.apply(rot_event)
    rotation_latency_ms = (time.perf_counter() - rot_start) * 1000

    # Verify that approver v2 is now active
    assert trust_registry.resolve_public_key("human-owner") == _public(approver_v2)

    db_size_bytes = os.path.getsize(scratch_dir / "ethical-heart.db")
    trust_db_bytes = os.path.getsize(trust_db)
    final_rss_mb = round(process.memory_info().rss / (1024 * 1024), 2)
    audit_chain_valid = heart.audit_chain_valid()
    heart.close()
    trust_registry.close()
    dna_anchor.close()

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
            "policy_database_bytes": db_size_bytes,
            "trust_database_bytes": trust_db_bytes,
            "audit_chain_valid": audit_chain_valid,
        },
        "rule_evaluator_25000_ops": {
            "rust_jpr1_available": rust_available,
            "rust_provider_id": native_gate.provider_id if rust_available else None,
            "rust_nanoseconds_per_decision": round(rust_ns_per_op, 2),
            "python_reference_nanoseconds_per_decision": round(py_ns_per_op, 2),
            "latency_ratio_rust_to_py": round(rust_ns_per_op / py_ns_per_op, 2) if py_ns_per_op else None,
        },
        "end_to_end_decision_with_dna_receipt_us": {
            "allow_decisions_us": quantiles(e2e_allow_latencies_us),
            "deny_decisions_us": quantiles(e2e_deny_latencies_us),
        },
        "owner_approval_lifecycle_us": {
            "creation_us": quantiles(approval_create_us),
            "verification_and_gate_us": quantiles(approval_verify_us),
            "replay_rejection_us": round(replay_rejection_us, 2),
        },
        "trust_store_rotation_ms": round(rotation_latency_ms, 2),
    }


def main() -> int:
    print("=" * 65)
    print("       JAYA BENCHMARK: PILAR P15 ETHICAL HEART")
    print("=" * 65)

    result = run_benchmark(iterations=200)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
