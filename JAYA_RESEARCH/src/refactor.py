"""Retired source-tree rewrite utility.

The historical script embedded a developer workstation path and rewrote Python
modules in place. Runtime source mutation is outside the Research boundary.
Configuration migrations must be reviewed as ordinary repository changes.
"""

from __future__ import annotations


class LegacyRefactorDisabled(PermissionError):
    """Raised when the unsafe source mutation entry point is invoked."""


def main() -> int:
    raise LegacyRefactorDisabled(
        "Bulk source rewriting is disabled; submit a reviewed repository patch"
    )


if __name__ == "__main__":
    raise SystemExit(main())
