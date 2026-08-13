#!/usr/bin/env python3
"""Run a real ML-DSA-65, rotation, restart, and JAYA capsule lifecycle."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT / "JAYA_CORE"
for item in (ROOT, CORE_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from src.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    EncryptedFileKeyStore,
)
from src.brain_v2.protection.pqc import (  # noqa: E402
    QuantumPolicy,
    QuantumSecurityError,
    QuantumSuite,
)
from src.security.capsule import (  # noqa: E402
    CapsuleKind,
    JayaCapsuleCodec,
)
from src.security.cryptographic_skin import CryptographicSkin  # noqa: E402
from src.security.quantum_lifecycle import (  # noqa: E402
    PersistentQuantumAuthority,
)


def _policy() -> QuantumPolicy:
    return QuantumPolicy(
        policy_version=1,
        minimum_suite=QuantumSuite.HYBRID_ED25519_ML_DSA_65,
        asset_lifetime_days=3650,
        threat_horizon_year=2035,
        allow_classical_until_year=2028,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if any(workspace.iterdir()):
        raise RuntimeError("demo workspace must be empty")
    identity_root = workspace / "identity"
    database = workspace / "core.db"
    identity_secret = "p16-demo-identity-" + ("i" * 40)
    skin_secret = "p16-demo-skin-" + ("s" * 40)
    payload = b"JAYA-PORTABLE-QUANTUM-BRAIN"

    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
    )
    anchor.enroll()
    signer = lambda purpose, digest: anchor.sign_attestation(  # noqa: E731
        purpose, digest
    ).to_dict()
    skin = CryptographicSkin(
        database,
        skin_secret,
        attestation_signer=signer,
        attestation_verifier=anchor.verify_attestation,
    )
    started = time.perf_counter()
    quantum = PersistentQuantumAuthority(
        database, skin, _policy(), current_year=2026
    )
    initialized_ms = (time.perf_counter() - started) * 1000
    first_key = quantum.active_key_id
    sign_started = time.perf_counter()
    signature = quantum.sign(payload)
    sign_ms = (time.perf_counter() - sign_started) * 1000
    verify_started = time.perf_counter()
    verified = quantum.verify(payload, signature)
    verify_ms = (time.perf_counter() - verify_started) * 1000
    codec = JayaCapsuleCodec(
        skin, quantum_authority=quantum, quantum_required=True
    )
    capsule = codec.seal(
        payload, kind=CapsuleKind.BRAIN, subject="brain:portable"
    )
    capsule_restored = codec.open(
        capsule,
        expected_kind=CapsuleKind.BRAIN,
        expected_subject="brain:portable",
    ) == payload
    second_key = quantum.rotate()
    rotation_continuity = quantum.verify(payload, signature)
    quantum.close()
    skin.close()
    anchor.close()

    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
    )
    signer = lambda purpose, digest: anchor.sign_attestation(  # noqa: E731
        purpose, digest
    ).to_dict()
    skin = CryptographicSkin(
        database,
        skin_secret,
        attestation_signer=signer,
        attestation_verifier=anchor.verify_attestation,
    )
    quantum = PersistentQuantumAuthority(
        database, skin, _policy(), current_year=2026
    )
    restart_restored = quantum.active_key_id == second_key
    quantum.revoke(first_key)
    try:
        quantum.verify(payload, signature)
    except QuantumSecurityError:
        revoked_rejected = True
    else:
        revoked_rejected = False
    status = quantum.status()
    report = {
        "status": "INTEGRATED_LOCAL",
        "provider": status["provider"],
        "versions": status["versions"],
        "ml_dsa_ready": status["ready"],
        "hybrid_verified": verified,
        "capsule_restored": capsule_restored,
        "plaintext_absent": payload not in capsule,
        "rotation_continuity": rotation_continuity,
        "restart_restored": restart_restored,
        "revoked_rejected": revoked_rejected,
        "public_key_bytes": len(signature.pq_public_key or "") * 3 // 4,
        "signature_bytes": len(signature.pq_signature or "") * 3 // 4,
        "capsule_bytes": len(capsule),
        "initialized_ms": round(initialized_ms, 3),
        "sign_ms": round(sign_ms, 3),
        "verify_ms": round(verify_ms, 3),
    }
    quantum.close()
    skin.close()
    anchor.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    required = (
        report["ml_dsa_ready"],
        report["hybrid_verified"],
        report["capsule_restored"],
        report["plaintext_absent"],
        report["rotation_continuity"],
        report["restart_restored"],
        report["revoked_rejected"],
    )
    return 0 if all(required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
