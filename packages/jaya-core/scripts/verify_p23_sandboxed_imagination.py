"""Executable verification script for Pilar 23 Sandboxed Imagination."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add core src to path
current_dir = Path(__file__).resolve().parent
repo_root = current_dir.parent.parent.parent
core_src = repo_root / "packages" / "jaya-core" / "src"
if str(core_src) not in sys.path:
    sys.path.insert(0, str(core_src))

from jaya_core.verification.sandboxed_imagination import (
    run_sandboxed_imagination_verification,
)


def main() -> int:
    profile_path = (
        repo_root
        / "packages"
        / "jaya-core"
        / "verification"
        / "p23_windows_sandboxed_imagination_v1.json"
    )
    print(f"[*] Running P23 Sandboxed Imagination Verification against: {profile_path}")
    try:
        receipt = run_sandboxed_imagination_verification(
            profile_path, base_dir=repo_root
        )
        print("\n[+] Verification PASSED!")
        print(json.dumps(receipt, indent=2))
        return 0
    except Exception as exc:
        print(f"\n[-] Verification FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
