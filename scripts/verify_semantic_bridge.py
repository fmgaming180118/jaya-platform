#!/usr/bin/env python3
"""Execute the representative P26 semantic-bridge verification profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.verification.semantic_bridge import (  # noqa: E402
    SemanticVerificationError,
    run_semantic_bridge_verification,
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
            / "p26_windows_semantic_bridge_v1.json"
        ),
    )
    parser.add_argument(
        "--output-dir", default=str(ROOT / "artifacts" / "verified-semantic-bridge")
    )
    parser.add_argument("--approver", required=True)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        receipt = run_semantic_bridge_verification(
            profile_path=Path(args.profile),
            base_dir=ROOT,
            approver=args.approver,
        )
    except SemanticVerificationError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code, "message": str(exc)}, indent=2))
        return 1

    report_path = out_dir / "verified-semantic-bridge-receipt.json"
    report_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": receipt["status"],
                "capability_id": receipt["capability_id"],
                "profile_id": receipt["profile_id"],
                "receipt_path": str(report_path),
                "metrics": receipt["metrics"],
                "gates": receipt["gates"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
