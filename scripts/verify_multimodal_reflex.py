#!/usr/bin/env python3
"""Execute the representative P04 Multimodal Reflex verification profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.verification.multimodal_reflex import (  # noqa: E402
    MultimodalReflexVerificationError,
    verify_multimodal_reflex,
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
            / "p04_windows_multimodal_reflex_v1.json"
        ),
    )
    parser.add_argument(
        "--output-dir", default=str(ROOT / "artifacts" / "verified-multimodal-reflex")
    )
    parser.add_argument("--approver", required=True)
    args = parser.parse_args()
    try:
        report_path, report = verify_multimodal_reflex(
            repository_root=ROOT,
            profile_path=Path(args.profile),
            output_directory=Path(args.output_dir),
            approver=args.approver,
        )
    except MultimodalReflexVerificationError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code, "message": str(exc)}))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "pillar": report["pillar"],
                "profile_id": report["profile_id"],
                "report_path": str(report_path),
                "total_gates": report["total_gates"],
                "passed_gates": report["passed_gates"],
                "gates": report["gates"],
                "soak_metrics": report["soak_metrics"],
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "VERIFIED_REPRESENTATIVE" else 1


if __name__ == "__main__":
    sys.exit(main())
