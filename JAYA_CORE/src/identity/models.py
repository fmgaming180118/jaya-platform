"""
models.py — Data models for JAYA Identity and Node Identity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class NodeClass(str, Enum):
    CENTRAL = "CENTRAL"
    STANDARD = "STANDARD"
    EDGE = "EDGE"
    MISSION = "MISSION"
    MICRO = "MICRO"
    CONSTRAINED = "CONSTRAINED"


class NodeRole(str, Enum):
    PRIMARY_COGNITIVE_NODE = "PRIMARY_COGNITIVE_NODE"
    PERSONAL_WORKSTATION_NODE = "PERSONAL_WORKSTATION_NODE"
    PERSONAL_MOBILE_NODE = "PERSONAL_MOBILE_NODE"
    MISSION_CRITICAL_AUTONOMOUS_NODE = "MISSION_CRITICAL_AUTONOMOUS_NODE"
    PERCEPTION_MICRO_NODE = "PERCEPTION_MICRO_NODE"


class AuthorityLevel(int, Enum):
    MICRO_SENSOR = 1
    EDGE_OBSERVER = 2
    STANDARD_WORKER = 3
    MISSION_OPERATOR = 4
    CENTRAL_AUTHORITY = 5


@dataclass
class JayaIdentity:
    identity_id: str
    owner_id: str
    version: str = "1.0"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NodeIdentity:
    node_id: str
    jaya_identity_id: str
    node_class: NodeClass
    role: NodeRole
    authority: AuthorityLevel
    public_key_fingerprint: Optional[str] = None
    registered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["node_class"] = self.node_class.value
        res["role"] = self.role.value
        res["authority"] = self.authority.value
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NodeIdentity:
        return cls(
            node_id=str(data["node_id"]),
            jaya_identity_id=str(data["jaya_identity_id"]),
            node_class=NodeClass(data["node_class"]),
            role=NodeRole(data["role"]),
            authority=AuthorityLevel(int(data["authority"])),
            public_key_fingerprint=data.get("public_key_fingerprint"),
            registered_at=str(
                data.get("registered_at", datetime.now(timezone.utc).isoformat())
            ),
        )
