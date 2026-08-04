"""
registry.py — Capability Registry for local and remote capabilities.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .manifest import CapabilityManifest

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """Registry managing capability manifests and health filters."""

    def __init__(self) -> None:
        self._capabilities: Dict[str, CapabilityManifest] = {}

    def register(self, manifest: CapabilityManifest) -> None:
        self._capabilities[manifest.capability_id] = manifest
        logger.info("Registered capability '%s' v%s", manifest.capability_id, manifest.version)

    def unregister(self, capability_id: str) -> None:
        if capability_id in self._capabilities:
            del self._capabilities[capability_id]
            logger.info("Unregistered capability '%s'", capability_id)

    def lookup(self, capability_id: str) -> Optional[CapabilityManifest]:
        return self._capabilities.get(capability_id)

    def has_capability(self, capability_id: str) -> bool:
        """Check if a capability is registered."""
        return capability_id in self._capabilities

    def list_capabilities(self) -> List[CapabilityManifest]:
        return list(self._capabilities.values())

    def filter_available(
        self,
        memory_available_mb: int,
        is_online: bool = True,
        required_permissions: Optional[List[str]] = None,
    ) -> List[CapabilityManifest]:
        res = []
        perms = set(required_permissions or [])
        for cap in self._capabilities.values():
            if cap.health_status != "HEALTHY":
                continue
            if cap.min_memory_mb > memory_available_mb:
                continue
            if not is_online and not cap.offline_available:
                continue
            if perms and not perms.issubset(set(cap.permissions_required)):
                continue
            res.append(cap)
        return res
