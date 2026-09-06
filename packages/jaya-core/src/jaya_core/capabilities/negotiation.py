"""
negotiation.py — Structured capability negotiation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from jaya_core.cognitive.contracts import ResourceBudget
from jaya_core.resources.modes import ExecutionMode
from .manifest import CapabilityManifest
from .registry import CapabilityRegistry


class NegotiationResultStatus(str, Enum):
    EXECUTE_LOCAL = "EXECUTE_LOCAL"
    OFFLOAD_TO_NODE = "OFFLOAD_TO_NODE"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"


@dataclass
class NegotiationResult:
    status: NegotiationResultStatus
    capability_id: str
    target_node: str = "local"
    reason: str = ""
    manifest: Optional[CapabilityManifest] = None


class CapabilityNegotiator:
    """Negotiates capability execution target based on local registry, modes, and budget."""

    def __init__(self, local_registry: CapabilityRegistry) -> None:
        self.local_registry = local_registry

    def negotiate(
        self,
        capability_id: str,
        execution_mode: ExecutionMode,
        budget: ResourceBudget,
        known_remote_capabilities: Optional[dict[str, list[str]]] = None,
    ) -> NegotiationResult:
        manifest = self.local_registry.lookup(capability_id)
        is_online = execution_mode in (ExecutionMode.ONLINE_FULL, ExecutionMode.ONLINE_DEGRADED)

        # 1. Check local availability
        if manifest is not None:
            if manifest.health_status != "HEALTHY":
                return NegotiationResult(
                    status=NegotiationResultStatus.CAPABILITY_UNAVAILABLE,
                    capability_id=capability_id,
                    reason=f"Local capability '{capability_id}' is unhealthy ({manifest.health_status})",
                )
            if manifest.min_memory_mb > budget.max_memory_mb:
                return NegotiationResult(
                    status=NegotiationResultStatus.CAPABILITY_UNAVAILABLE,
                    capability_id=capability_id,
                    reason=f"Required memory {manifest.min_memory_mb}MB exceeds budget {budget.max_memory_mb}MB",
                )
            if not is_online and not manifest.offline_available:
                return NegotiationResult(
                    status=NegotiationResultStatus.CAPABILITY_UNAVAILABLE,
                    capability_id=capability_id,
                    reason=f"Capability '{capability_id}' is not available offline",
                )
            return NegotiationResult(
                status=NegotiationResultStatus.EXECUTE_LOCAL,
                capability_id=capability_id,
                target_node="local",
                manifest=manifest,
            )

        # 2. Local missing -> Check remote offload
        if is_online and budget.allow_remote_offload and known_remote_capabilities:
            for remote_node, caps in known_remote_capabilities.items():
                if capability_id in caps:
                    return NegotiationResult(
                        status=NegotiationResultStatus.OFFLOAD_TO_NODE,
                        capability_id=capability_id,
                        target_node=remote_node,
                        reason=f"Offloading to remote node '{remote_node}'",
                    )

        # 3. Not available anywhere
        return NegotiationResult(
            status=NegotiationResultStatus.CAPABILITY_UNAVAILABLE,
            capability_id=capability_id,
            reason=f"Capability '{capability_id}' is not registered locally or remotely",
        )
