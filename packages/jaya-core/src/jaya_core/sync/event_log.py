"""
event_log.py — Append-only Node Event Log for node synchronization.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .contracts import NodeEvent, SyncCursor

logger = logging.getLogger(__name__)


class AppendOnlyEventLog:
    """In-memory append-only event log with sequence tracking and deduplication."""

    def __init__(self, node_id: str = "local") -> None:
        self.node_id = node_id
        self._events: List[NodeEvent] = []
        self._event_ids: Dict[str, int] = {}  # event_id -> index
        self._sequence_counter = 0

    def append(self, event_type: str, payload: dict) -> NodeEvent:
        self._sequence_counter += 1
        event_id = f"ne-{self.node_id}-{self._sequence_counter}"
        event = NodeEvent(
            event_id=event_id,
            event_type=event_type,
            node_id=self.node_id,
            sequence_number=self._sequence_counter,
            payload=payload,
        )
        self._events.append(event)
        self._event_ids[event_id] = len(self._events) - 1
        return event

    def append_raw(self, event: NodeEvent) -> bool:
        if event.event_id in self._event_ids:
            logger.debug("Duplicate event_id '%s' ignored", event.event_id)
            return False
        if event.sequence_number > self._sequence_counter:
            self._sequence_counter = event.sequence_number
        self._events.append(event)
        self._event_ids[event.event_id] = len(self._events) - 1
        return True

    def get_events_since(self, last_sequence_number: int = 0) -> List[NodeEvent]:
        return [e for e in self._events if e.sequence_number > last_sequence_number]

    def get_cursor(self) -> SyncCursor:
        last_seq = self._sequence_counter
        last_id = self._events[-1].event_id if self._events else None
        return SyncCursor(
            node_id=self.node_id,
            last_sequence_number=last_seq,
            last_event_id=last_id,
        )
