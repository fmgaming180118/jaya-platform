"""Fail-closed entrypoint shared by retired promotion scripts."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


class LegacyPromotionDisabledError(RuntimeError):
    """Raised when an unsafe legacy promotion workflow is requested."""


def disabled_main(workflow: str, argv: Sequence[str] | None = None) -> int:
    """Explain the safe replacement without reading or changing artifacts."""
    parser = argparse.ArgumentParser(
        description=f"Retired JAYA Core workflow: {workflow}"
    )
    parser.parse_args(argv)
    error = LegacyPromotionDisabledError(
        f"{workflow} is disabled: use the signed v1 manifest verifier and "
        "installer with an artifact already present in the Core-owned inbox"
    )
    print(f"ERROR: {error}", file=sys.stderr)
    return 2
