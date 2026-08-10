#!/usr/bin/env python3
"""Explicit owner operations for the JAYA Core DNA Anchor."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT / "JAYA_CORE"
for import_root in (ROOT, CORE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from src.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    DNAAnchorError,
    DNAFailureCode,
    EncryptedFileKeyStore,
)


def _identity_dir(argument: Path | None) -> Path:
    raw = argument or (
        Path(os.environ["JAYA_IDENTITY_DIR"])
        if os.environ.get("JAYA_IDENTITY_DIR")
        else None
    )
    if raw is None:
        raise DNAAnchorError(
            DNAFailureCode.INVALID_INPUT,
            "--identity-dir or JAYA_IDENTITY_DIR is required",
        )
    return raw.expanduser().resolve()


def _anchor(identity_dir: Path) -> DNAAnchor:
    secret = os.environ.get("JAYA_IDENTITY_KEY_SECRET", "")
    if not secret:
        raise DNAAnchorError(
            DNAFailureCode.KEYSTORE_UNAVAILABLE,
            "JAYA_IDENTITY_KEY_SECRET is required",
        )
    return DNAAnchor(
        identity_dir,
        EncryptedFileKeyStore(identity_dir / "keystore", secret),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-dir", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("enroll")
    commands.add_parser("status")
    verify = commands.add_parser("verify")
    verify.add_argument("--purpose", required=True)
    commands.add_parser("rotate")
    revoke = commands.add_parser("revoke")
    revoke.add_argument("--reason", required=True)
    args = parser.parse_args()

    anchor: DNAAnchor | None = None
    started = time.perf_counter()
    try:
        anchor = _anchor(_identity_dir(args.identity_dir))
        if args.command == "enroll":
            record, receipt = anchor.enroll()
            result = {
                "status": "ENROLLED",
                "identity": record.to_dict(),
                "receipt": receipt.to_dict(),
            }
        elif args.command == "status":
            record = anchor.load_identity()
            result = {
                "status": record.status.value,
                "identity": record.to_dict(),
                "audit_chain_valid": anchor.audit_chain_valid(),
            }
        elif args.command == "verify":
            challenge = anchor.issue_challenge(args.purpose)
            signature = anchor.sign_challenge(challenge)
            receipt = anchor.verify_challenge(challenge, signature)
            result = {
                "status": "VERIFIED",
                "purpose": challenge.purpose,
                "receipt": receipt.to_dict(),
            }
        elif args.command == "rotate":
            record, receipt = anchor.rotate_key()
            result = {
                "status": "ROTATED",
                "identity": record.to_dict(),
                "receipt": receipt.to_dict(),
            }
        else:
            receipt = anchor.revoke(args.reason)
            result = {
                "status": "REVOKED",
                "receipt": receipt.to_dict(),
            }
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1_000, 3)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except DNAAnchorError as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error": exc.code.value,
                    "message": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    finally:
        if anchor is not None:
            anchor.close()


if __name__ == "__main__":
    raise SystemExit(main())
