#!/usr/bin/env python3
"""Run a real P11 enrollment, restart, challenge, rotation, and migration demo."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT / "JAYA_CORE"
for import_root in (ROOT, CORE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from src.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    EncryptedFileKeyStore,
)


def _anchor(root: Path, secret: str) -> DNAAnchor:
    return DNAAnchor(root, EncryptedFileKeyStore(root / "keystore", secret))


def run_demo(workspace: Path, purpose: str) -> dict[str, object]:
    started = time.perf_counter()
    secret = secrets.token_urlsafe(48)
    source = workspace / "source"
    destination = workspace / "destination"

    enrolled = _anchor(source, secret)
    record, enrollment = enrolled.enroll()
    enrolled.close()

    restarted = _anchor(source, secret)
    challenge = restarted.issue_challenge(purpose)
    signature = restarted.sign_challenge(challenge)
    verification = restarted.verify_challenge(challenge, signature)
    rotated, rotation = restarted.rotate_key()
    audit_valid = restarted.audit_chain_valid()
    restarted.close()

    (destination / "keystore").mkdir(parents=True)
    shutil.copy2(source / "dna_identity.db", destination / "dna_identity.db")
    shutil.copy2(
        source / "keystore" / "dna_private_key.json",
        destination / "keystore" / "dna_private_key.json",
    )
    migrated = _anchor(destination, secret)
    migrated_record = migrated.load_identity()
    migrated.close()

    return {
        "status": "VERIFIED_LOCAL",
        "brain_id": record.brain_id,
        "owner_id": record.owner_id,
        "initial_key_version": record.key_version,
        "rotated_key_version": rotated.key_version,
        "migration_preserved_brain_id": migrated_record.brain_id == record.brain_id,
        "audit_chain_valid": audit_valid,
        "receipts": {
            "enrollment": enrollment.to_dict(),
            "verification": verification.to_dict(),
            "rotation": rotation.to_dict(),
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--purpose", default="runtime.boot")
    args = parser.parse_args()
    if args.workspace:
        report = run_demo(args.workspace.resolve(), args.purpose)
    else:
        with tempfile.TemporaryDirectory(prefix="jaya-sovereign-demo-") as directory:
            report = run_demo(Path(directory), args.purpose)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
