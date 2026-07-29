"""Fail-closed compatibility shim for the quarantined discovery engine.

The historical promoted copy rewrote Core source files and marked unbenchmarked
mutations as successful. Research can now export only immutable, non-executable
candidates; installation remains behind Core's signed manifest verifier.
"""

from __future__ import annotations

from typing import NoReturn


class LegacyDiscoveryDisabled(PermissionError):
    """Raised whenever the quarantined discovery workflow is requested."""


_DISABLED_MESSAGE = (
    "Legacy discovery is disabled: submit an immutable Research candidate and "
    "install it only through Core's signed manifest verification boundary"
)


class ScientificDiscovery:
    """Compatibility name that fails before reading, writing, or executing code."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise LegacyDiscoveryDisabled(_DISABLED_MESSAGE)


def main() -> NoReturn:
    """Reject direct execution of the retired discovery workflow."""
    raise LegacyDiscoveryDisabled(_DISABLED_MESSAGE)


if __name__ == "__main__":
    main()
