#!/usr/bin/env python3
"""Retired dynamic-code verifier retained as a fail-closed compatibility CLI."""

from __future__ import annotations

import sys


class DynamicExecutionVerificationDisabled(RuntimeError):
    """Raised because importing candidate source is not empirical verification."""


def verify() -> None:
    """Reject the legacy dynamic import before reading or executing source."""
    raise DynamicExecutionVerificationDisabled(
        "dynamic import is disabled; verify signed runner receipts instead"
    )


if __name__ == "__main__":
    try:
        verify()
    except DynamicExecutionVerificationDisabled as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
