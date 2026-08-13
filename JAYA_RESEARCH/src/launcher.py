"""Compatibility entry point for the canonical Research tray launcher.

Process management belongs to :mod:`tray_launcher`; this module intentionally
contains no shell command construction or duplicate service lifecycle state.
"""

from __future__ import annotations

from tray_launcher import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
