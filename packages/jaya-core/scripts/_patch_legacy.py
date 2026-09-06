"""Retired one-shot patch for `src/brain_v2/engine/legacy_protocol.py`."""

from __future__ import annotations

from collections.abc import Sequence

try:
    from scripts._retired_source_patch import retired_main
except ModuleNotFoundError:  # Direct execution from this directory.
    from _retired_source_patch import retired_main


def main(argv: Sequence[str] | None = None) -> int:
    return retired_main(
        utility="_patch_legacy.py",
        target="src/brain_v2/engine/legacy_protocol.py",
        replacement="the migration and cryptography tests",
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
