"""
node_manager.py — Node Registry, Heartbeat, & Capability Discovery for JAYA Mesh.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.identity.models import NodeClass, NodeIdentity, NodeRole


@dataclass
class NodeState:
    identity: NodeIdentity
    last_heartbeat_timestamp: float
    is_online: bool = True
    available_memory_mb: int = 1024
    capabilities: List[str] = field(default_factory=list)


class NodeRegistry:
    """Manages active nodes in the JAYA Mesh network."""

    def __init__(self, heartbeat_timeout_seconds: float = 30.0) -> None:
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._nodes: Dict[str, NodeState] = {}

    def register_node(
        self,
        identity: NodeIdentity,
        available_memory_mb: int = 1024,
        capabilities: Optional[List[str]] = None,
    ) -> NodeState:
        now = time.time()
        caps = capabilities or ["text.reasoning.basic"]
        state = NodeState(
            identity=identity,
            last_heartbeat_timestamp=now,
            is_online=True,
            available_memory_mb=available_memory_mb,
            capabilities=caps,
        )
        self._nodes[identity.node_id] = state
        return state

    def update_heartbeat(
        self, node_id: str, available_memory_mb: Optional[int] = None
    ) -> bool:
        if node_id not in self._nodes:
            return False
        state = self._nodes[node_id]
        state.last_heartbeat_timestamp = time.time()
        state.is_online = True
        if available_memory_mb is not None:
            state.available_memory_mb = available_memory_mb
        return True

    def get_node(self, node_id: str) -> Optional[NodeState]:
        self._sweep_timeouts()
        return self._nodes.get(node_id)

    def list_active_nodes(
        self,
        node_class: Optional[NodeClass] = None,
        required_capability: Optional[str] = None,
        min_memory_mb: int = 0,
    ) -> List[NodeState]:
        self._sweep_timeouts()
        active: List[NodeState] = []
        for state in self._nodes.values():
            if not state.is_online:
                continue
            if node_class and state.identity.node_class != node_class:
                continue
            if state.available_memory_mb < min_memory_mb:
                continue
            if required_capability and required_capability not in state.capabilities:
                continue
            active.append(state)
        return active

    def _sweep_timeouts(self) -> None:
        now = time.time()
        for state in self._nodes.values():
            if now - state.last_heartbeat_timestamp > self.heartbeat_timeout_seconds:
                state.is_online = False
