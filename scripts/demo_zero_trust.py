#!/usr/bin/env python3
"""Execute real P18 signed allow, deny, replay, restart, and measurement."""

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

from src.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    EncryptedFileKeyStore,
)
from src.brain_v2.protection.zero_trust import (  # noqa: E402
    ZeroTrustAuthority,
    create_trust_envelope,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    args.workspace.mkdir(parents=True, exist_ok=True)
    secret = os.environ.get("JAYA_IDENTITY_KEY_SECRET") or os.urandom(48).hex()
    identity_dir = args.workspace / "identity"
    database = args.workspace / "trust-demo.db"
    started = time.perf_counter()
    anchor = DNAAnchor(
        identity_dir,
        EncryptedFileKeyStore(identity_dir / "keystore", secret),
    )
    record, _ = anchor.enroll()
    authority = ZeroTrustAuthority(
        database, attestation_verifier=anchor.verify_attestation
    )
    authority.ensure_principal(record.brain_id, "node-demo", ("core.logic.evaluate",))
    payload = {"facts": ["trust.required"], "query": "trust.required"}
    envelope = create_trust_envelope(
        principal_id=record.brain_id,
        node_id="node-demo",
        capability_id="core.logic.evaluate",
        payload=payload,
        policy_receipt_sha256="a" * 64,
        privacy_receipt_sha256="b" * 64,
        signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
    )
    allowed = authority.authorize(envelope, payload)
    replay = authority.authorize(envelope, payload)
    changed = authority.authorize(envelope, {"query": "changed"})
    audit_valid = authority.audit_chain_valid()
    authority.close()
    anchor.close()

    anchor = DNAAnchor(
        identity_dir,
        EncryptedFileKeyStore(identity_dir / "keystore", secret),
    )
    authority = ZeroTrustAuthority(
        database, attestation_verifier=anchor.verify_attestation
    )
    restart_replay = authority.authorize(envelope, payload)
    restart_valid = authority.audit_chain_valid()
    authority.close()
    anchor.close()
    result = {
        "status": "VERIFIED_LOCAL",
        "allow": allowed.effect.value,
        "replay": replay.reason_code,
        "payload_tamper": changed.reason_code,
        "restart_replay": restart_replay.reason_code,
        "audit_chain_valid": audit_valid and restart_valid,
        "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
        "storage_bytes": database.stat().st_size,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        0
        if (
            result["allow"] == "ALLOW"
            and result["replay"] == "ZERO_TRUST_REPLAY_DETECTED"
            and result["payload_tamper"] == "ZERO_TRUST_PAYLOAD_MISMATCH"
            and result["restart_replay"] == "ZERO_TRUST_REPLAY_DETECTED"
            and result["audit_chain_valid"]
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
