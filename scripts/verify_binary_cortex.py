#!/usr/bin/env python3
"""Run the P29 Binary Cortex representative verification profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "packages" / "jaya-core" / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from jaya_core.verification.binary_cortex import (  # noqa: E402
    BinaryCortexVerificationError,
    verify_binary_cortex,
)

DEFAULT_PROFILE = (
    ROOT
    / "packages"
    / "jaya-core"
    / "verification"
    / "p29_windows_authenticated_binary_cortex_v1.json"
)
DEFAULT_OUTPUT = ROOT / "artifacts" / "verified-binary-cortex"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--approver", required=True)
    args = parser.parse_args()
    try:
        report_path, report = verify_binary_cortex(
            repository_root=ROOT,
            profile_path=args.profile,
            output_directory=args.output_directory,
            approver=args.approver,
        )
    except BinaryCortexVerificationError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code, "message": str(exc)}))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "pillar": report["pillar"],
                "profile_id": report["profile_id"],
                "report_path": str(report_path),
                "gates": report["gates"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
