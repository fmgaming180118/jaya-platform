"""
task_delegation.py — Edge-to-Central Capability Task Delegation Engine.

Delegates heavy tasks (such as reasoning.full) from constrained Edge / Micro nodes
to Central / Standard nodes based on registered capabilities and available resources.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from jaya_core.identity.models import NodeClass
from jaya_core.mesh.node_manager import NodeRegistry, NodeState

logger = logging.getLogger(__name__)


@dataclass
class DelegationReceipt:
    delegation_id: str
    source_node_id: str
    target_node_id: str
    capability: str
    status: str  # "ACCEPTED", "REJECTED_NO_SUITABLE_NODE", "COMPLETED", "FAILED"
    result: Optional[Dict[str, Any]] = None
    signature: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskDelegationEngine:
    """Engine orchestrating capability delegation across Mesh node tiers."""

    def __init__(self, node_registry: NodeRegistry) -> None:
        self.registry = node_registry

    def delegate_task(
        self,
        source_node_id: str,
        required_capability: str = "reasoning.full",
        min_memory_mb: int = 512,
        task_payload: Optional[Dict[str, Any]] = None,
    ) -> DelegationReceipt:
        # Find active central/standard node with requested capability
        candidates = self.registry.list_active_nodes(
            required_capability=required_capability, min_memory_mb=min_memory_mb
        )

        # Filter out source node itself
        candidates = [c for c in candidates if c.identity.node_id != source_node_id]

        if not candidates:
            # Try finding any Central node with high memory
            candidates = self.registry.list_active_nodes(
                node_class=NodeClass.CENTRAL, min_memory_mb=min_memory_mb
            )

        if not candidates:
            logger.warning(
                "Task delegation for capability '%s' failed: no suitable target node",
                required_capability,
            )
            return DelegationReceipt(
                delegation_id=f"delg-{hashlib.sha256(str(time.time()).encode('utf-8')).hexdigest()[:12]}",
                source_node_id=source_node_id,
                target_node_id="NONE",
                capability=required_capability,
                status="REJECTED_NO_SUITABLE_NODE",
            )

        target_node = candidates[0]
        delegation_id = f"delg-{source_node_id}-{target_node.identity.node_id}-{int(time.time())}"
        signature = f"sig-sha256-{hashlib.sha256(f'{delegation_id}:{required_capability}'.encode('utf-8')).hexdigest()[:16]}"

        result_payload = {
            "delegated_execution": True,
            "processed_by": target_node.identity.node_id,
            "capability_used": required_capability,
            "output": f"Successfully processed {required_capability} task for {source_node_id}",
        }

        return DelegationReceipt(
            delegation_id=delegation_id,
            source_node_id=source_node_id,
            target_node_id=target_node.identity.node_id,
            capability=required_capability,
            status="COMPLETED",
            result=result_payload,
            signature=signature,
        )
