"""
offline_sync.py — Standard Node Offline Sync & Reconnection Manager.

Manages offline event queues for Standard / Edge nodes and flushes synced batches
to Central upon reconnection via MeshSyncEngine.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.mesh.sync_engine import MeshSyncEngine, SyncBatch
from src.sync.contracts import NodeEvent, SyncCursor
from src.sync.event_log import AppendOnlyEventLog

logger = logging.getLogger(__name__)


@dataclass
class SyncFlushResult:
    source_node_id: str
    target_node_id: str
    events_flushed: int
    duplicates_skipped: int
    flushed_at: float
    is_success: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StandardNodeOfflineSyncManager:
    """Manages offline event buffering and reconnection syncing for Standard/Edge nodes."""

    def __init__(
        self,
        local_node_id: str,
        event_log: AppendOnlyEventLog,
        sync_engine: MeshSyncEngine,
    ) -> None:
        self.local_node_id = local_node_id
        self.event_log = event_log
        self.sync_engine = sync_engine
        self._offline_queue: List[NodeEvent] = []
        self._is_online = False
        self._central_node_id: Optional[str] = None

    def record_offline_event(
        self, event_type: str, payload: Dict[str, Any]
    ) -> NodeEvent:
        """Record an event locally while offline."""
        cursor = self.event_log.get_cursor()
        next_seq = cursor.last_sequence_number + 1

        event = NodeEvent(
            event_id=f"evt-{self.local_node_id}-{next_seq}",
            event_type=event_type,
            node_id=self.local_node_id,
            sequence_number=next_seq,
            payload=payload,
            signature=f"sig-node-{self.local_node_id}",
        )

        self.event_log.append_raw(event)
        self._offline_queue.append(event)
        return event

    def set_connectivity(
        self, is_online: bool, central_node_id: Optional[str] = None
    ) -> None:
        self._is_online = is_online
        if central_node_id:
            self._central_node_id = central_node_id

    def flush_offline_events(
        self,
        target_central_node_id: Optional[str] = None,
        target_sync_engine: Optional[MeshSyncEngine] = None,
    ) -> SyncFlushResult:
        target_id = target_central_node_id or self._central_node_id
        if not target_id:
            raise ValueError("[ConfigError] Central node ID must be provided to flush events")

        if not self._is_online:
            logger.warning("Node %s is offline; flush aborted", self.local_node_id)
            return SyncFlushResult(
                source_node_id=self.local_node_id,
                target_node_id=target_id,
                events_flushed=0,
                duplicates_skipped=0,
                flushed_at=time.time(),
                is_success=False,
            )

        # Create sync batch from event log
        batch = self.sync_engine.create_sync_batch(target_id, last_known_seq=0)
        receiver = target_sync_engine or self.sync_engine
        appended, skipped = receiver.receive_sync_batch(batch)

        flushed_count = len(self._offline_queue)
        self._offline_queue.clear()

        return SyncFlushResult(
            source_node_id=self.local_node_id,
            target_node_id=target_id,
            events_flushed=appended,
            duplicates_skipped=skipped,
            flushed_at=time.time(),
            is_success=True,
        )

    @property
    def pending_offline_count(self) -> int:
        return len(self._offline_queue)
