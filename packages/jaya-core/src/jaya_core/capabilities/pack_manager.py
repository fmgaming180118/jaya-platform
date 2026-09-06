"""
pack_manager.py — Dynamic Capability Pack Manager & Hot-Plug Interface.

Enables domain-specific Capability Packs (such as cad.basic) to be installed,
uninstalled, and executed dynamically on top of a domain-neutral Cognitive Kernel
without restarting the Core runtime.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .manifest import CapabilityManifest
from .registry import CapabilityRegistry

logger = logging.getLogger(__name__)


class CapabilityPack(ABC):
    """Abstract Base Class for modular, hot-pluggable Capability Packs."""

    def __init__(self, pack_id: str, version: str, description: str) -> None:
        self.pack_id = pack_id
        self.version = version
        self.description = description
        self.is_installed = False

    @abstractmethod
    def get_manifests(self) -> List[CapabilityManifest]:
        """Return all capability manifests declared by this pack."""

    @abstractmethod
    def install(self, registry: CapabilityRegistry) -> bool:
        """Register manifests into the CapabilityRegistry upon installation."""

    @abstractmethod
    def uninstall(self, registry: CapabilityRegistry) -> bool:
        """Unregister manifests from the CapabilityRegistry upon uninstallation."""

    @abstractmethod
    def execute_capability(self, capability_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an installed capability provided by this pack."""


class DynamicCapabilityPackManager:
    """Manager for live installation, uninstallation, and execution of CapabilityPacks."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry
        self._installed_packs: Dict[str, CapabilityPack] = {}

    def install_pack(self, pack: CapabilityPack) -> bool:
        if pack.pack_id in self._installed_packs:
            logger.warning("CapabilityPack '%s' is already installed", pack.pack_id)
            return False

        success = pack.install(self.registry)
        if success:
            pack.is_installed = True
            self._installed_packs[pack.pack_id] = pack
            logger.info("Successfully installed CapabilityPack '%s' v%s", pack.pack_id, pack.version)
            return True
        return False

    def uninstall_pack(self, pack_id: str) -> bool:
        if pack_id not in self._installed_packs:
            logger.warning("CapabilityPack '%s' is not installed", pack_id)
            return False

        pack = self._installed_packs[pack_id]
        success = pack.uninstall(self.registry)
        if success:
            pack.is_installed = False
            del self._installed_packs[pack_id]
            logger.info("Successfully uninstalled CapabilityPack '%s'", pack_id)
            return True
        return False

    def get_pack(self, pack_id: str) -> Optional[CapabilityPack]:
        return self._installed_packs.get(pack_id)

    def list_installed_packs(self) -> List[CapabilityPack]:
        return list(self._installed_packs.values())

    def execute_pack_capability(
        self, pack_id: str, capability_id: str, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        pack = self.get_pack(pack_id)
        if not pack:
            raise KeyError(f"[PackError] CapabilityPack '{pack_id}' is not installed")
        if not pack.is_installed:
            raise RuntimeError(f"[PackError] CapabilityPack '{pack_id}' is not active")

        return pack.execute_capability(capability_id, inputs)
