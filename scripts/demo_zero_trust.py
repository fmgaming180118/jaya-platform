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
CORE_ROOT = ROOT / "packages" / "jaya-core" / "src"
for item in (ROOT, CORE_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from jaya_core.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    DNAAnchorError,
    DNAFailureCode,
    EncryptedFileKeyStore,
)
from jaya_core.brain_v2.protection.zero_trust import (  # noqa: E402
    ZeroTrustAuthority,
    create_trust_envelope,
)


def _principal_state(anchor: DNAAnchor):
    def resolve(principal_id: str) -> dict[str, object] | None:
        try:
            record = anchor.load_identity()
        except DNAAnchorError as exc:
            if exc.code is DNAFailureCode.IDENTITY_REVOKED:
                return {"active": False, "key_version": 0}
            raise
        if record.brain_id != principal_id:
            return None
        return {"active": True, "key_version": record.key_version}

    return resolve


def _envelope(
    anchor: DNAAnchor,
    principal_id: str,
    payload: dict[str, object],
):
    return create_trust_envelope(
        principal_id=principal_id,
        node_id="node-demo",
        capability_id="core.logic.evaluate",
        payload=payload,
        policy_receipt_sha256="a" * 64,
        privacy_receipt_sha256="b" * 64,
        signer=lambda purpose, digest: anchor.sign_attestation(purpose, digest).to_dict(),
    )


def run_demo(workspace: Path) -> dict[str, object]:  # noqa: PLR0914
    workspace.mkdir(parents=True, exist_ok=True)
    secret = os.environ.get("JAYA_IDENTITY_KEY_SECRET") or os.urandom(48).hex()
    identity_dir = workspace / "identity"
    database = workspace / "trust-demo.db"
    started = time.perf_counter()
    anchor = DNAAnchor(
        identity_dir,
        EncryptedFileKeyStore(identity_dir / "keystore", secret),
    )
    record, _ = anchor.enroll()
    authority = ZeroTrustAuthority(
        database,
        attestation_verifier=anchor.verify_attestation,
        principal_state_resolver=_principal_state(anchor),
    )
    authority.ensure_principal(record.brain_id, "node-demo", ("core.logic.evaluate",))
    payload = {"facts": ["trust.required"], "query": "trust.required"}
    envelope = _envelope(anchor, record.brain_id, payload)
    stale_candidate = _envelope(anchor, record.brain_id, payload)
    allowed = authority.authorize(envelope, payload)
    replay = authority.authorize(envelope, payload)
    changed = authority.authorize(envelope, {"query": "changed"})
    rotated, _ = anchor.rotate_key()
    stale_after_rotation = authority.authorize(stale_candidate, payload)
    current_envelope = _envelope(anchor, record.brain_id, payload)
    current = authority.authorize(current_envelope, payload)
    revocation_candidate = _envelope(anchor, record.brain_id, payload)
    audit_valid = authority.audit_chain_valid()
    authority.close()
    anchor.close()

    anchor = DNAAnchor(
        identity_dir,
        EncryptedFileKeyStore(identity_dir / "keystore", secret),
    )
    authority = ZeroTrustAuthority(
        database,
        attestation_verifier=anchor.verify_attestation,
        principal_state_resolver=_principal_state(anchor),
    )
    restart_replay = authority.authorize(current_envelope, payload)
    authority.revoke_principal(record.brain_id)
    revoked_after_restart = authority.authorize(revocation_candidate, payload)
    restart_valid = authority.audit_chain_valid()
    status = authority.status()
    authority.close()
    anchor.close()
    return {
        "status": "VERIFIED_LOCAL",
        "allow": allowed.effect.value,
        "replay": replay.reason_code,
        "payload_tamper": changed.reason_code,
        "rotation_version": rotated.key_version,
        "stale_key": stale_after_rotation.reason_code,
        "current_key_allow": current.effect.value,
        "restart_replay": restart_replay.reason_code,
        "revoked_after_restart": revoked_after_restart.reason_code,
        "principal_state_source": status["principal_state_source"],
        "authorization_provider": status["authorization_provider"],
        "audit_chain_valid": audit_valid and restart_valid,
        "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
        "storage_bytes": database.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    result = run_demo(args.workspace)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        0
        if (
            result["allow"] == "ALLOW"
            and result["replay"] == "ZERO_TRUST_REPLAY_DETECTED"
            and result["payload_tamper"] == "ZERO_TRUST_PAYLOAD_MISMATCH"
            and result["restart_replay"] == "ZERO_TRUST_REPLAY_DETECTED"
            and result["stale_key"] == "ZERO_TRUST_PRINCIPAL_KEY_STALE"
            and result["current_key_allow"] == "ALLOW"
            and result["revoked_after_restart"] == "ZERO_TRUST_PRINCIPAL_REVOKED"
            and result["principal_state_source"] == "dynamic_resolver"
            and result["audit_chain_valid"]
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
