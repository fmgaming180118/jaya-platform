#!/usr/bin/env python3
"""Run a real local P13 seal, restart, rotation, and revocation lifecycle."""

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
    EncryptedFileKeyStore,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime  # noqa: E402
from jaya_core.security.cryptographic_skin import (  # noqa: E402
    CryptographicSkin,
    CryptographicSkinError,
    CryptographicSkinFailureCode,
    SealedEnvelope,
)


def _anchor(root: Path, secret: str) -> DNAAnchor:
    return DNAAnchor(root, EncryptedFileKeyStore(root / "keystore", secret))


def _skin(database: Path, anchor: DNAAnchor, secret: str) -> CryptographicSkin:
    return CryptographicSkin(
        database,
        secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )


def main() -> int:  # noqa: PLR0914
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    database = workspace / "cryptographic-skin-demo.db"
    identity_root = workspace / "identity"
    envelope_path = workspace / "brain-artifact.jaya-envelope.json"
    identity_secret = os.environ.get("JAYA_IDENTITY_KEY_SECRET") or os.urandom(48).hex()
    skin_secret = os.environ.get("JAYA_CRYPTOGRAPHIC_SKIN_SECRET") or os.urandom(48).hex()
    payload = f"portable-brain-artifact-{os.urandom(16).hex()}".encode()

    started = time.perf_counter()
    anchor = _anchor(identity_root, identity_secret)
    anchor.enroll()
    runtime = JayaCoreRuntime(
        db_path=database,
        identity_anchor=anchor,
        identity_required=True,
        cryptographic_skin=_skin(database, anchor, skin_secret),
        cryptographic_skin_required=True,
    )
    envelope = runtime.seal_artifact(
        payload,
        purpose="core.brain-capsule",
        subject="brain:demo-artifact",
        content_type="application/jaya-artifact",
        ttl_seconds=600,
    )
    envelope_path.write_text(
        json.dumps(envelope.to_dict(), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    old_key = envelope.key_id
    runtime.close()

    restarted_anchor = _anchor(identity_root, identity_secret)
    restarted_skin = _skin(database, restarted_anchor, skin_secret)
    restarted = JayaCoreRuntime(
        db_path=database,
        identity_anchor=restarted_anchor,
        identity_required=True,
        cryptographic_skin=restarted_skin,
        cryptographic_skin_required=True,
    )
    loaded = SealedEnvelope.from_dict(json.loads(envelope_path.read_text(encoding="utf-8")))
    restored = restarted.open_artifact(loaded)
    new_key = restarted_skin.rotate_key()
    rotation_continuity = restarted.open_artifact(loaded) == payload
    restarted_skin.revoke_key(old_key)
    revoked_code = ""
    try:
        restarted.open_artifact(loaded)
    except CryptographicSkinError as exc:
        revoked_code = exc.code.value
    status = restarted_skin.status()
    restarted.close()

    probe_anchor = _anchor(identity_root, identity_secret)
    wrong_secret_code = ""
    try:
        _skin(database, probe_anchor, "wrong-" + os.urandom(48).hex())
    except CryptographicSkinError as exc:
        wrong_secret_code = exc.code.value
    finally:
        probe_anchor.close()

    plaintext_absent = (
        payload not in database.read_bytes() and payload not in envelope_path.read_bytes()
    )
    elapsed_ms = round((time.perf_counter() - started) * 1_000, 3)
    result = {
        "status": "VERIFIED_LOCAL_PROFILE_INPUT",
        "algorithm_suite": loaded.algorithm_suite,
        "restart_restored": restored == payload,
        "plaintext_absent": plaintext_absent,
        "rotation_continuity": rotation_continuity,
        "old_key_revoked": revoked_code == CryptographicSkinFailureCode.KEY_REVOKED.value,
        "old_key_id": old_key,
        "new_key_id": new_key,
        "audit_chain_valid": status["audit_chain_valid"],
        "state_authenticated": status["state_authenticated"],
        "storage_schema_version": status["storage_schema_version"],
        "wrong_secret_rejected": wrong_secret_code
        == CryptographicSkinFailureCode.AUDIT_CORRUPT.value,
        "envelope_path": str(envelope_path),
        "envelope_bytes": envelope_path.stat().st_size,
        "database_bytes": database.stat().st_size,
        "elapsed_ms": elapsed_ms,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        0
        if all(
            (
                result["restart_restored"],
                result["plaintext_absent"],
                result["rotation_continuity"],
                result["old_key_revoked"],
                result["audit_chain_valid"],
                result["state_authenticated"],
                result["wrong_secret_rejected"],
            )
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
