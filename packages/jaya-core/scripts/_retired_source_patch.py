"""Fail-closed entry point for retired one-shot source patch utilities."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def retired_main(
    *,
    utility: str,
    target: str,
    replacement: str,
    argv: Sequence[str] | None = None,
) -> int:
    """Explain retirement and refuse to mutate tracked source files."""
    parser = argparse.ArgumentParser(
        prog=utility,
        description="Explain why this legacy source patch utility is retired.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="print the retirement guidance (also printed by default)",
    )
    parser.parse_args(argv)

    print(
        f"{utility} is retired and will not modify {target}. "
        f"Apply reviewed source changes directly and verify them with {replacement}.",
        file=sys.stderr,
    )
    return 2
