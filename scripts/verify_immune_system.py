#!/usr/bin/env python3
"""Execute the representative P12 Immune System verification profile."""

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

from jaya_core.verification.immune_system import (  # noqa: E402
    ImmuneSystemVerificationError,
    verify_immune_system,
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
            / "p12_windows_authenticated_immune_system_v1.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "artifacts" / "verified-immune-system"),
    )
    parser.add_argument("--approver", required=True)
    args = parser.parse_args()
    try:
        report_path, report = verify_immune_system(
            repository_root=ROOT,
            profile_path=Path(args.profile),
            output_directory=Path(args.output_dir),
            approver=args.approver,
        )
    except ImmuneSystemVerificationError as exc:
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
