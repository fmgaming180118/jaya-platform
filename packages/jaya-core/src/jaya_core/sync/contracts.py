"""
contracts.py — Sync contracts, NodeEvent schema, and SyncCursor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class NodeEvent:
    event_id: str
    event_type: str
    node_id: str
    sequence_number: int
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signature: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NodeEvent:
        return cls(
            event_id=str(data["event_id"]),
            event_type=str(data["event_type"]),
            node_id=str(data.get("node_id", "local")),
            sequence_number=int(data.get("sequence_number", 0)),
            payload=dict(data.get("payload") or {}),
            timestamp=str(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            signature=data.get("signature"),
        )


@dataclass
class SyncCursor:
    node_id: str
    last_sequence_number: int = 0
    last_event_id: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
