#!/usr/bin/env python3
"""Run P14 with the canonical Windows DPAPI provider and P13 runtime."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT / "JAYA_CORE"
for item in (ROOT, CORE_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts.run_jaya_core_server import _build_runtime  # noqa: E402
from src.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    EncryptedFileKeyStore,
)
from src.brain_v2.protection.hardware import (  # noqa: E402
    HardwareBindingError,
    HardwareBindingFailureCode,
    NodeBindingAuthority,
    WindowsDPAPIMachineProvider,
)
from src.core_config import CoreConfig  # noqa: E402
from src.security.cryptographic_skin import SealedEnvelope  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    data_dir = workspace / "data"
    data_dir.mkdir()
    identity_root = data_dir / "identity"
    database = data_dir / "jaya_core_runtime.db"
    envelope_path = workspace / "hardware-bound-envelope.json"
    provider = WindowsDPAPIMachineProvider()
    if not provider.available():
        print(json.dumps({"status": "BLOCKED_EXTERNAL", "provider_available": False}))
        return 2
    identity_secret = os.environ.get("JAYA_IDENTITY_KEY_SECRET") or os.urandom(48).hex()
    skin_secret = (
        os.environ.get("JAYA_CRYPTOGRAPHIC_SKIN_SECRET") or os.urandom(48).hex()
    )
    node_id = "p14-demo-node"
    payload = f"hardware-bound-brain-{os.urandom(16).hex()}".encode()
    started = time.perf_counter()

    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
    )
    identity, _ = anchor.enroll()
    binding = NodeBindingAuthority(
        database,
        provider,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    binding.enroll(identity.brain_id, node_id)
    binding.close()
    anchor.close()

    environment = {
        "JAYA_ENVIRONMENT": "test",
        "JAYA_SOUL_PASSWORD": os.urandom(48).hex(),
        "JAYA_CORE_API_KEY": os.urandom(48).hex(),
        "JAYA_CORE_DATA_DIR": str(data_dir),
        "JAYA_NODE_ID": node_id,
        "JAYA_REQUIRE_IDENTITY": "true",
        "JAYA_IDENTITY_DIR": str(identity_root),
        "JAYA_IDENTITY_KEY_SECRET": identity_secret,
        "JAYA_REQUIRE_CRYPTOGRAPHIC_SKIN": "true",
        "JAYA_CRYPTOGRAPHIC_SKIN_SECRET": skin_secret,
        "JAYA_REQUIRE_HARDWARE_LOCK": "true",
    }
    config = CoreConfig.from_env(environment, core_dir=workspace)
    runtime = _build_runtime(config)
    envelope = runtime.seal_artifact(
        payload,
        purpose="core.brain-capsule",
        subject="brain:p14-demo",
        content_type="application/jaya-artifact",
    )
    first_instance = runtime.hardware_boot_receipt.instance_id
    envelope_path.write_text(
        json.dumps(envelope.to_dict(), sort_keys=True), encoding="utf-8"
    )
    runtime.close()

    restarted = _build_runtime(config)
    loaded = SealedEnvelope.from_dict(
        json.loads(envelope_path.read_text(encoding="utf-8"))
    )
    restored = restarted.open_artifact(loaded)
    second_instance = restarted.hardware_boot_receipt.instance_id
    snapshot = restarted.operational_snapshot()
    restarted.close()

    clone_code = ""
    clone_config = CoreConfig.from_env(
        {**environment, "JAYA_NODE_ID": "unauthorized-clone-node"},
        core_dir=workspace,
    )
    try:
        _build_runtime(clone_config)
    except HardwareBindingError as exc:
        clone_code = exc.code.value

    result = {
        "status": "INTEGRATED_LOCAL",
        "provider_id": provider.provider_id,
        "provider_available": provider.available(),
        "hardware_backed": provider.hardware_backed,
        "brain_id_stable": identity.brain_id == loaded.attestation["brain_id"],
        "instance_rotated": first_instance != second_instance,
        "restart_restored": restored == payload,
        "plaintext_absent": payload not in database.read_bytes()
        and payload not in envelope_path.read_bytes(),
        "p13_hardware_bound": snapshot["cryptographic_skin"]["hardware_bound"],
        "clone_rejected": clone_code == HardwareBindingFailureCode.NODE_MISMATCH.value,
        "audit_chain_valid": snapshot["hardware_locked"]["audit_chain_valid"],
        "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
        "database_bytes": database.stat().st_size,
        "envelope_bytes": envelope_path.stat().st_size,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        0
        if all(
            result[key] is True
            for key in (
                "provider_available",
                "brain_id_stable",
                "instance_rotated",
                "restart_restored",
                "plaintext_absent",
                "p13_hardware_bound",
                "clone_rejected",
                "audit_chain_valid",
            )
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
