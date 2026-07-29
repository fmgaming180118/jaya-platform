"""Retired one-shot patch for `src/brain_v2/genesis.py`."""

from __future__ import annotations

from collections.abc import Sequence

try:
    from scripts._retired_source_patch import retired_main
except ModuleNotFoundError:  # Direct execution from this directory.
    from _retired_source_patch import retired_main


def main(argv: Sequence[str] | None = None) -> int:
    return retired_main(
        utility="_patch_genesis.py",
        target="src/brain_v2/genesis.py",
        replacement="the genesis and artifact tests",
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
