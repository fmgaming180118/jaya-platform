"""
registry.py — Capability Registry for local and remote capabilities.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
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

    def probe_and_update_health(self, capability_id: str) -> bool:
        """
        Probe a capability's provider and update its health status.
        
        Returns True if capability is HEALTHY, False otherwise.
        """
        manifest = self.lookup(capability_id)
        if manifest is None:
            logger.warning("Cannot probe unknown capability: %s", capability_id)
            return False
        
        # Built-in capabilities: probe their actual providers
        if manifest.provider == "built_in":
            healthy = self._probe_builtin_capability(manifest)
            manifest.health_status = "HEALTHY" if healthy else "UNHEALTHY"
            logger.info("Capability %s health probe: %s", capability_id, manifest.health_status)
            return healthy
        
        # For remote/MCP capabilities, could add provider-specific probes
        logger.warning("No probe implementation for provider: %s", manifest.provider)
        manifest.health_status = "UNHEALTHY"
        return False

    def _probe_builtin_capability(self, manifest: CapabilityManifest) -> bool:
        """Probe built-in capability providers."""
        cap_id = manifest.capability_id
        
        try:
            if cap_id == "text.reasoning.basic":
                # Probe: check if cognitive model adapter is available
                from JAYA_CORE.src.ai_connectors.cognitive_model_adapter import create_cognitive_adapter_from_env
                adapter = create_cognitive_adapter_from_env()
                return adapter.is_local_available() or adapter.is_cloud_available()
            
            elif cap_id == "system.file.read":
                # Probe: check if we can read from workspace
                workspace = Path.cwd()
                test_file = workspace / ".gitignore"
                return test_file.exists() or workspace.exists()
            
            elif cap_id == "system.file.write":
                # Probe: check if we can write to workspace (temp file)
                import tempfile
                with tempfile.NamedTemporaryFile(dir=Path.cwd(), delete=True) as f:
                    f.write(b"probe")
                return True
            
            elif cap_id == "code.execution":
                # Probe: check if python is available
                result = subprocess.run([sys.executable, "--version"], capture_output=True, timeout=5)
                return result.returncode == 0
            
            elif cap_id == "memory.read" or cap_id == "memory.write":
                # Probe: check if memory system is available
                try:
                    from JAYA_CORE.src.memory import MemorySystem
                    return True
                except ImportError:
                    return False
            
            elif cap_id == "cad.parametric_modeling":
                # Probe: check if CAD backend is available
                try:
                    import OCC.Core
                    return True
                except ImportError:
                    return False
            
            elif cap_id == "device.control":
                # Probe: no actual device control provider is implemented yet
                # Returning False prevents executor false positives
                return False
            
            elif cap_id == "web.search" or cap_id == "web.fetch":
                # Probe: verify search provider adapter is actually available
                # Network check is insufficient; we need the actual implementation
                try:
                    from JAYA_CORE.src.ai_connectors.search_adapter import SearchAdapter
                    return True
                except ImportError:
                    return False
            
            else:
                logger.warning("No probe for built-in capability: %s", cap_id)
                return False
                
        except Exception as e:
            logger.warning("Probe failed for %s: %s", cap_id, e)
            return False

    def probe_all_capabilities(self) -> Dict[str, bool]:
        """Probe all registered capabilities and update their health status."""
        results = {}
        for cap_id in self._capabilities:
            results[cap_id] = self.probe_and_update_health(cap_id)
        return results
