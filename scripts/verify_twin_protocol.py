#!/usr/bin/env python3
"""Execute the representative P30 Twin Protocol verification profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.verification.twin_protocol import (  # noqa: E402
    TwinProtocolVerificationError,
    verify_twin_protocol,
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
            / "p30_windows_twin_protocol_v1.json"
        ),
    )
    parser.add_argument(
        "--output-dir", default=str(ROOT / "artifacts" / "verified-twin-protocol")
    )
    parser.add_argument("--approver", default="System-Veritas")
    args = parser.parse_args()
    try:
        report_path, report = verify_twin_protocol(
            repository_root=ROOT,
            profile_path=Path(args.profile),
            output_directory=Path(args.output_dir),
            approver=args.approver,
        )
    except TwinProtocolVerificationError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code, "message": str(exc)}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "pillar_id": report["pillar_id"],
                "profile_id": report["profile_id"],
                "report_path": str(report_path),
                "summary": report["gates_summary"],
                "gates": {k: {"status": v["status"], "duration_ms": v["duration_ms"]} for k, v in report["gates"].items()},
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
