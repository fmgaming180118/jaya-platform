#!/usr/bin/env python3
"""Retired legacy workflow; retained only as a fail-closed compatibility CLI."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from _legacy_promotion import disabled_main


def main(argv: Sequence[str] | None = None) -> int:
    """Reject the legacy workflow before reading or changing any artifact."""
    return disabled_main("promote_adapter", argv)


if __name__ == "__main__":
    sys.exit(main())
