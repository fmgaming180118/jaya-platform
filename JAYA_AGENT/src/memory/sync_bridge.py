"""Disabled legacy Research-to-Agent copy bridge.

The former implementation copied databases and model adapters directly into a
runtime directory. A capability grant cannot establish artifact provenance,
signature validity, compatibility, or rollback safety, so that path remains
closed. Promotion must use the reviewed manifest installer owned by Core/OS.
"""

from __future__ import annotations


class LegacySyncDisabled(PermissionError):
    """Raised whenever the unsafe direct-copy bridge is invoked."""


class EcosystemSyncBridge:
    """Compatibility facade that fails closed without touching the filesystem."""

    def sync_latest_evolution(self) -> dict[str, object]:
        raise LegacySyncDisabled(
            "Direct Research artifact copying is disabled; use a signed, "
            "verified manifest installer with approval and rollback"
        )
