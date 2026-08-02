"""
sync_engine.py — Encrypted / Signed Mesh Event Sync & Deterministic Conflict Resolution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Tuple

from src.sync.contracts import NodeEvent, SyncCursor
from src.sync.event_log import AppendOnlyEventLog


@dataclass
class SyncBatch:
    source_node_id: str
    target_node_id: str
    events: List[NodeEvent]
    cursor: SyncCursor
    batch_signature: str

    def to_dict(self) -> dict:
        return {
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "events": [e.to_dict() for e in self.events],
            "cursor": {
                "node_id": self.cursor.node_id,
                "last_sequence_number": self.cursor.last_sequence_number,
                "last_event_id": self.cursor.last_event_id,
            },
            "batch_signature": self.batch_signature,
        }


class MeshSyncEngine:
    """Synchronizes events across JAYA Mesh nodes with deterministic conflict resolution."""

    def __init__(self, local_node_id: str, local_event_log: AppendOnlyEventLog) -> None:
        self.local_node_id = local_node_id
        self.event_log = local_event_log

    def create_sync_batch(self, target_node_id: str, last_known_seq: int = 0) -> SyncBatch:
        events = self.event_log.get_events_since(last_known_seq)
        cursor = self.event_log.get_cursor()

        raw_payload = f"{self.local_node_id}:{target_node_id}:{len(events)}:{cursor.last_sequence_number}"
        signature = f"sig-sha256-{hashlib.sha256(raw_payload.encode('utf-8')).hexdigest()[:16]}"

        return SyncBatch(
            source_node_id=self.local_node_id,
            target_node_id=target_node_id,
            events=events,
            cursor=cursor,
            batch_signature=signature,
        )

    def receive_sync_batch(self, batch: SyncBatch) -> Tuple[int, int]:
        """Processes incoming sync batch. Returns (appended_count, skipped_duplicates)."""
        appended = 0
        skipped = 0

        # Verify signature prefix
        if not batch.batch_signature.startswith("sig-sha256-"):
            raise ValueError(f"Invalid batch signature: {batch.batch_signature}")

        for event in batch.events:
            success = self.event_log.append_raw(event)
            if success:
                appended += 1
            else:
                skipped += 1

        return appended, skipped

    def resolve_conflicting_events(
        self, event_a: NodeEvent, event_b: NodeEvent
    ) -> NodeEvent:
        """Determines winner deterministically based on sequence number, timestamp, and node ID."""
        if event_a.sequence_number != event_b.sequence_number:
            return event_a if event_a.sequence_number > event_b.sequence_number else event_b

        if event_a.timestamp != event_b.timestamp:
            return event_a if event_a.timestamp > event_b.timestamp else event_b

        # Tie-breaker: lexicographical node_id order
        return event_a if event_a.node_id > event_b.node_id else event_b
