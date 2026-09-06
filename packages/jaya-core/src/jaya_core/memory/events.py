"""
events.py — Memory event models for episodic memory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass
class MemoryEvent:
    event_id: str
    event_type: str
    session_id: str
    goal_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    node_id: str = "local"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sequence_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MemoryEvent:
        payload_raw = data.get("payload")
        if isinstance(payload_raw, str):
            try:
                payload = json.loads(payload_raw)
            except Exception:
                payload = {}
        else:
            payload = dict(payload_raw or {})

        return cls(
            event_id=str(data["event_id"]),
            event_type=str(data["event_type"]),
            session_id=str(data.get("session_id", "default")),
            goal_id=str(data.get("goal_id", "default")),
            payload=payload,
            node_id=str(data.get("node_id", "local")),
            timestamp=str(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            sequence_number=int(data.get("sequence_number", 0)),
        )
