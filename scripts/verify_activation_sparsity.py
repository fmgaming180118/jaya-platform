#!/usr/bin/env python3
"""Execute the representative P35 Activation Sparsity verification profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.verification.activation_sparsity import (  # noqa: E402
    ActivationSparsityVerificationError,
    verify_activation_sparsity,
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
            / "p35_windows_activation_sparsity_v1.json"
        ),
    )
    parser.add_argument(
        "--output-dir", default=str(ROOT / "artifacts" / "verified-activation-sparsity")
    )
    parser.add_argument("--approver", default="System-Veritas")
    args = parser.parse_args()
    try:
        report_path, report = verify_activation_sparsity(
            repository_root=ROOT,
            profile_path=Path(args.profile),
            output_directory=Path(args.output_dir),
            approver=args.approver,
        )
    except ActivationSparsityVerificationError as exc:
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
