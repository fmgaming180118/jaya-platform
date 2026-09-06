#!/usr/bin/env python3
"""Run the real local P12 integrity quarantine and recovery lifecycle."""

from __future__ import annotations

import argparse
import hashlib
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

from jaya_core.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    EncryptedFileKeyStore,
)
from jaya_core.security.cryptographic_skin import CryptographicSkin  # noqa: E402
from jaya_core.security.immune_system import (  # noqa: E402
    ImmuneFailureCode,
    ImmuneSystem,
    ImmuneSystemError,
)

_WORKSPACE_NOT_EMPTY = "demo workspace must be empty"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:  # noqa: PLR0914, PLR0915
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if any(workspace.iterdir()):
        raise RuntimeError(_WORKSPACE_NOT_EMPTY)
    started = time.perf_counter()
    approved = b"P12-APPROVED-CORE-ARTIFACT"
    unsafe = b"P12-UNSAFE-MODIFIED-ARTIFACT"
    target = workspace / "runtime-component.bin"
    target.write_bytes(approved)
    identity_secret = os.environ.get("JAYA_IDENTITY_KEY_SECRET") or os.urandom(48).hex()
    skin_secret = os.environ.get("JAYA_CRYPTOGRAPHIC_SKIN_SECRET") or os.urandom(48).hex()
    identity_root = workspace / "identity"
    database = workspace / "core.db"

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
    immune = ImmuneSystem(
        database,
        workspace,
        skin,
        attestation_signer=signer,
        attestation_verifier=anchor.verify_attestation,
    )
    immune.register_target(
        "runtime-component",
        target,
        _digest(target),
        critical=True,
    )
    healthy_scan = immune.scan("runtime-component") is None
    target.write_bytes(unsafe)
    incident = immune.scan("runtime-component")
    quarantine = workspace / str(incident.quarantine_path)
    quarantined = not target.exists() and quarantine.is_file()
    plaintext_absent = unsafe not in quarantine.read_bytes()
    quarantine_roundtrip = immune.open_quarantine(incident.incident_id) == unsafe
    for failure_code in ("TIMEOUT", "TIMEOUT", "INVALID_RESPONSE"):
        immune.record_dependency_failure("demo-dependency", failure_code)
    circuit_open = not immune.can_execute("demo-dependency")
    try:
        immune.recover_dependency("demo-dependency", lambda: False)
    except ImmuneSystemError as exc:
        rejected_probe = exc.code is ImmuneFailureCode.RECOVERY_REJECTED
    else:
        rejected_probe = False
    safe_stop = immune.safe_stop()
    immune.close()
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
    immune = ImmuneSystem(
        database,
        workspace,
        skin,
        attestation_signer=signer,
        attestation_verifier=anchor.verify_attestation,
    )
    restart_safe_stop = immune.safe_stop()
    target.write_bytes(approved)
    resolved = immune.recover_target("runtime-component")
    dependency_resolved = immune.recover_dependency("demo-dependency", lambda: True)
    recovered = (
        resolved.state.value == "RESOLVED"
        and dependency_resolved.state.value == "RESOLVED"
        and not immune.safe_stop()
    )
    audit_chain_valid = immune.audit_chain_valid()
    status = immune.status()
    report = {
        "status": "VERIFIED_REPRESENTATIVE_DEMO",
        "healthy_scan": healthy_scan,
        "quarantined": quarantined,
        "quarantine_roundtrip": quarantine_roundtrip,
        "plaintext_absent": plaintext_absent,
        "circuit_open": circuit_open,
        "unhealthy_probe_rejected": rejected_probe,
        "safe_stop": safe_stop,
        "restart_safe_stop": restart_safe_stop,
        "verified_recovery": recovered,
        "audit_chain_valid": audit_chain_valid,
        "state_authenticated": status["state_authenticated"],
        "storage_schema_version": status["storage_schema_version"],
        "metrics": status["metrics"],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "database_bytes": database.stat().st_size,
        "quarantine_bytes": quarantine.stat().st_size,
    }
    immune.close()
    skin.close()
    anchor.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return (
        0
        if all(
            (
                healthy_scan,
                quarantined,
                quarantine_roundtrip,
                plaintext_absent,
                circuit_open,
                rejected_probe,
                safe_stop,
                restart_safe_stop,
                recovered,
                audit_chain_valid,
                status["state_authenticated"],
            )
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
