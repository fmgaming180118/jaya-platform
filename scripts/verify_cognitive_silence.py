#!/usr/bin/env python3
"""Execute the representative P07 Cognitive Silence verification profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.verification.cognitive_silence import (  # noqa: E402
    SilenceVerificationError,
    verify_cognitive_silence,
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
            / "p07_windows_cognitive_silence_v1.json"
        ),
    )
    parser.add_argument(
        "--output-dir", default=str(ROOT / "artifacts" / "verified-cognitive-silence")
    )
    parser.add_argument("--approver", required=True)
    args = parser.parse_args()

    try:
        report_path, report = verify_cognitive_silence(
            profile_path=Path(args.profile),
            output_directory=Path(args.output_dir),
            repository_root=ROOT,
            approver=args.approver,
        )
    except SilenceVerificationError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code, "message": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "status": report["status"],
                "pillar": report["pillar"],
                "name": report["name"],
                "profile_id": report["profile_id"],
                "report_path": str(report_path),
                "gates": [
                    {
                        "gate_id": g["gate_id"],
                        "passed": g["passed"],
                        "actual": g["actual"],
                    }
                    for g in report["gates"]
                ],
                "metrics": report["metrics"],
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "VERIFIED_REPRESENTATIVE" else 1


if __name__ == "__main__":
    sys.exit(main())
