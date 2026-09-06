"""
context.py — Context Manager with snapshot bounding.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from jaya_core.identity.models import NodeClass, NodeIdentity
from jaya_core.memory.events import MemoryEvent
from jaya_core.resources.modes import ExecutionMode
from jaya_core.resources.profiler import ResourceProfile


@dataclass
class ContextSnapshot:
    session_id: str
    user_prompt: str
    node_identity: NodeIdentity
    resource_profile: ResourceProfile
    execution_mode: ExecutionMode
    recent_events: List[MemoryEvent] = field(default_factory=list)
    active_goal_id: str = "default_goal"
    extra_context: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_prompt": self.user_prompt,
            "node_identity": self.node_identity.to_dict(),
            "resource_profile": self.resource_profile.to_dict(),
            "execution_mode": self.execution_mode.value,
            "recent_events": [e.to_dict() for e in self.recent_events],
            "active_goal_id": self.active_goal_id,
            "extra_context": self.extra_context,
            "schema_version": self.schema_version,
        }


class ContextManager:
    """Manages and bounds context snapshots for JAYA Core."""

    def build_snapshot(
        self,
        session_id: str,
        user_prompt: str,
        node_identity: NodeIdentity,
        resource_profile: ResourceProfile,
        execution_mode: ExecutionMode,
        recent_events: List[MemoryEvent],
        active_goal_id: str = "default_goal",
        extra_context: Dict[str, Any] | None = None,
    ) -> ContextSnapshot:
        # Bound recent_events based on node_class
        max_events = 20
        if resource_profile.node_class in (NodeClass.EDGE, NodeClass.CONSTRAINED):
            max_events = 5
        elif resource_profile.node_class == NodeClass.STANDARD:
            max_events = 10

        bounded_events = recent_events[-max_events:] if recent_events else []

        return ContextSnapshot(
            session_id=session_id,
            user_prompt=user_prompt,
            node_identity=node_identity,
            resource_profile=resource_profile,
            execution_mode=execution_mode,
            recent_events=bounded_events,
            active_goal_id=active_goal_id,
            extra_context=dict(extra_context or {}),
        )
