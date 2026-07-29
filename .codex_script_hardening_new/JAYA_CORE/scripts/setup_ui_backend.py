"""Retired cross-module scaffold that previously wrote into the workspace root."""

from __future__ import annotations

from collections.abc import Sequence

try:
    from scripts._retired_source_patch import retired_main
except ModuleNotFoundError:  # Direct execution from this directory.
    from _retired_source_patch import retired_main


def main(argv: Sequence[str] | None = None) -> int:
    return retired_main(
        utility="setup_ui_backend.py",
        target="the repository source layout",
        replacement="the canonical JAYA_CORE and JAYA_RESEARCH component tests",
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
