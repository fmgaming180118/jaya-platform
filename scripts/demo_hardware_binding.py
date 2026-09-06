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
CORE_ROOT = ROOT / "packages" / "jaya-core" / "src"
for item in (ROOT, CORE_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts.run_jaya_core_server import _build_runtime  # noqa: E402, PLC2701

from jaya_core.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    EncryptedFileKeyStore,
)
from jaya_core.brain_v2.protection.hardware import (  # noqa: E402
    HardwareBindingError,
    HardwareBindingFailureCode,
    NodeBindingAuthority,
    WindowsDPAPIMachineProvider,
)
from jaya_core.core_config import CoreConfig  # noqa: E402
from jaya_core.security.cryptographic_skin import SealedEnvelope  # noqa: E402


def main() -> int:  # noqa: PLR0914, PLR0915
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
    migration_receipt_path = workspace / "migration-receipt.json"
    provider = WindowsDPAPIMachineProvider()
    if not provider.available():
        print(json.dumps({"status": "BLOCKED_EXTERNAL", "provider_available": False}))
        return 2
    identity_secret = os.environ.get("JAYA_IDENTITY_KEY_SECRET") or os.urandom(48).hex()
    skin_secret = os.environ.get("JAYA_CRYPTOGRAPHIC_SKIN_SECRET") or os.urandom(48).hex()
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
    envelope_path.write_text(json.dumps(envelope.to_dict(), sort_keys=True), encoding="utf-8")
    runtime.close()

    restarted = _build_runtime(config)
    loaded = SealedEnvelope.from_dict(json.loads(envelope_path.read_text(encoding="utf-8")))
    restored = restarted.open_artifact(loaded)
    second_instance = restarted.hardware_boot_receipt.instance_id
    restart_snapshot = restarted.operational_snapshot()
    restarted.close()

    migration_anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
    )
    migration_binding = NodeBindingAuthority(
        database,
        provider,
        attestation_signer=lambda purpose, digest: migration_anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=migration_anchor.verify_attestation,
    )
    source_context = migration_binding.binding_key_context(identity.brain_id, node_id)
    migration_started = time.perf_counter()
    migrated_record = migration_binding.migrate(
        identity.brain_id,
        "p14-demo-node-migrated",
        provider,
    )
    migrated_receipt = migration_binding.authorize_boot(
        identity.brain_id,
        "p14-demo-node-migrated",
        os.urandom(32),
    )
    target_context = migration_binding.binding_key_context(
        identity.brain_id,
        "p14-demo-node-migrated",
    )
    migration_elapsed_ms = (time.perf_counter() - migration_started) * 1_000
    migration_binding.close()
    migration_anchor.close()

    migrated_environment = {
        **environment,
        "JAYA_NODE_ID": "p14-demo-node-migrated",
    }
    migrated_config = CoreConfig.from_env(migrated_environment, core_dir=workspace)
    migrated_runtime = _build_runtime(migrated_config)
    migration_restored = migrated_runtime.open_artifact(loaded)
    snapshot = migrated_runtime.operational_snapshot()
    migrated_runtime.close()
    migration_receipt_path.write_text(
        json.dumps(
            {
                "brain_id": identity.brain_id,
                "source_node_id": node_id,
                "target_node_id": migrated_record.node_id,
                "target_binding_id": migrated_record.binding_id,
                "previous_binding_id": migrated_record.previous_binding_id,
                "target_instance_id": migrated_receipt.instance_id,
                "binding_context_stable": source_context == target_context,
                "migration_elapsed_ms": round(migration_elapsed_ms, 3),
                "scope": "SINGLE_HOST_REPRESENTATIVE_REWRAP",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    clone_code = ""
    clone_config = CoreConfig.from_env(
        {**migrated_environment, "JAYA_NODE_ID": "unauthorized-clone-node"},
        core_dir=workspace,
    )
    try:
        _build_runtime(clone_config)
    except HardwareBindingError as exc:
        clone_code = exc.code.value

    result = {
        "status": "VERIFIED_REPRESENTATIVE_DEMO",
        "provider_id": provider.provider_id,
        "provider_available": provider.available(),
        "hardware_backed": provider.hardware_backed,
        "provider_health": provider.health(),
        "brain_id_stable": identity.brain_id == loaded.attestation["brain_id"],
        "instance_rotated": first_instance != second_instance,
        "restart_restored": restored == payload,
        "restart_ready": restart_snapshot["hardware_locked"]["ready"],
        "migration_restored": migration_restored == payload,
        "migration_lineage": migrated_record.previous_binding_id is not None,
        "binding_context_stable": source_context == target_context,
        "migration_scope": "SINGLE_HOST_REPRESENTATIVE_REWRAP",
        "cross_machine_attestation": "BLOCKED_EXTERNAL",
        "plaintext_absent": payload not in database.read_bytes()
        and payload not in envelope_path.read_bytes()
        and payload not in migration_receipt_path.read_bytes(),
        "p13_hardware_bound": snapshot["cryptographic_skin"]["hardware_bound"],
        "clone_rejected": clone_code == HardwareBindingFailureCode.NODE_MISMATCH.value,
        "audit_chain_valid": snapshot["hardware_locked"]["audit_chain_valid"],
        "audit_attestations_verified": snapshot["hardware_locked"]["audit_attestations_verified"],
        "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
        "migration_elapsed_ms": round(migration_elapsed_ms, 3),
        "database_bytes": database.stat().st_size,
        "envelope_bytes": envelope_path.stat().st_size,
        "migration_receipt_bytes": migration_receipt_path.stat().st_size,
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
                "restart_ready",
                "migration_restored",
                "migration_lineage",
                "binding_context_stable",
                "plaintext_absent",
                "p13_hardware_bound",
                "clone_rejected",
                "audit_chain_valid",
                "audit_attestations_verified",
            )
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
