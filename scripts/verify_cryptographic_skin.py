#!/usr/bin/env python3
"""Execute the representative P13 Cryptographic Skin verification profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
for import_root in (ROOT, CORE_SRC):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from jaya_core.verification.cryptographic_skin import (  # noqa: E402
    CryptographicSkinVerificationError,
    verify_cryptographic_skin,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default=str(
            ROOT
            / "packages"
            / "jaya-core"
            / "verification"
            / "p13_windows_authenticated_crypto_skin_v1.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "artifacts" / "verified-cryptographic-skin"),
    )
    parser.add_argument("--approver", required=True)
    args = parser.parse_args()
    try:
        report_path, report = verify_cryptographic_skin(
            repository_root=ROOT,
            profile_path=Path(args.profile),
            output_directory=Path(args.output_dir),
            approver=args.approver,
        )
    except CryptographicSkinVerificationError as exc:
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
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
