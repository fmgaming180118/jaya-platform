#!/usr/bin/env python3
"""Retired unsigned artifact copier; retained as a fail-closed compatibility CLI."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from _legacy_promotion import disabled_main


def main(argv: Sequence[str] | None = None) -> int:
    """Reject unsigned copy-and-manifest promotion before touching artifacts."""
    return disabled_main("promote_research_artifact", argv)


if __name__ == "__main__":
    sys.exit(main())
