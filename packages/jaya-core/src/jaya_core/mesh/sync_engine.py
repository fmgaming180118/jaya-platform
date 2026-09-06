"""
sync_engine.py — Mesh Event Sync & Deterministic Conflict Resolution.

STATUS: PROTOTYPE / LOCAL ONLY

This module is a PROTOTYPE/SCAFFOLD only. It does NOT provide:
- Real cryptographic signatures (no private/public keys, HMAC, certificates)
- Real encryption (no encryption at all)
- Network transport (local in-memory only)
- Secure distributed mesh

Current implementation:
- Creates deterministic hash-based "signatures" (NOT cryptographic)
- Only verifies signature prefix format (trivial check)
- No actual signature verification or sender authentication
- Local event log only, no network sync

MUST NOT be claimed as "encrypted/signed mesh" or secure distributed system.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Tuple

from jaya_core.security.capsule import CapsuleKind, JayaCapsuleCodec
from jaya_core.sync.contracts import NodeEvent, SyncCursor
from jaya_core.sync.event_log import AppendOnlyEventLog


@dataclass
class SyncBatch:
    source_node_id: str
    target_node_id: str
    events: List[NodeEvent]
    cursor: SyncCursor
    batch_signature: str  # PROTOTYPE: hash-based prefix only, NOT cryptographic

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
    """
    Mesh event synchronization - CURRENTLY A PROTOTYPE/SCAFFOLD.

    Does NOT provide:
    - Cryptographic signatures (no keys, no verification)
    - Encryption (none)
    - Network transport (local only)
    - Secure distributed consensus

    Only provides:
    - Local event log management
    - Deterministic conflict resolution (sequence/timestamp/node_id)
    - Placeholder signature format for contract testing
    """

    def __init__(
        self,
        local_node_id: str,
        local_event_log: AppendOnlyEventLog,
        *,
        capsule_codec: JayaCapsuleCodec | None = None,
    ) -> None:
        self.local_node_id = local_node_id
        self.event_log = local_event_log
        self.capsule_codec = capsule_codec
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            "Legacy MeshSyncEngine mode is a prototype without crypto or network"
        )

    def create_sync_batch(
        self, target_node_id: str, last_known_seq: int = 0
    ) -> SyncBatch:
        events = self.event_log.get_events_since(last_known_seq)
        cursor = self.event_log.get_cursor()

        # PROTOTYPE: Deterministic hash prefix - NOT a cryptographic signature
        raw_payload = (
            f"{self.local_node_id}:{target_node_id}:"
            f"{len(events)}:{cursor.last_sequence_number}"
        )
        signature = (
            f"sig-sha256-{hashlib.sha256(raw_payload.encode('utf-8')).hexdigest()[:16]}"
        )

        return SyncBatch(
            source_node_id=self.local_node_id,
            target_node_id=target_node_id,
            events=events,
            cursor=cursor,
            batch_signature=signature,
        )

    def receive_sync_batch(self, batch: SyncBatch) -> Tuple[int, int]:
        """Process a legacy batch and return appended and duplicate counts."""
        appended = 0
        skipped = 0

        # PROTOTYPE: Only checks signature prefix format - NO actual verification
        if not batch.batch_signature.startswith("sig-sha256-"):
            raise ValueError(f"Invalid batch signature format: {batch.batch_signature}")

        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            "Legacy mesh mode verifies only a signature prefix. "
            "NO cryptographic verification, NO sender authentication."
        )

        for event in batch.events:
            success = self.event_log.append_raw(event)
            if success:
                appended += 1
            else:
                skipped += 1

        return appended, skipped

    def create_secure_sync_capsule(
        self, target_node_id: str, last_known_seq: int = 0
    ) -> bytes:
        if self.capsule_codec is None:
            raise RuntimeError("secure mesh capsule service is unavailable")
        batch = self.create_sync_batch(target_node_id, last_known_seq)
        payload = json.dumps(
            batch.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return self.capsule_codec.seal(
            payload,
            kind=CapsuleKind.MESH,
            subject=f"mesh:{self.local_node_id}:{target_node_id}",
            ttl_seconds=300,
        )

    def receive_secure_sync_capsule(
        self, source_node_id: str, capsule: bytes
    ) -> Tuple[int, int]:
        if self.capsule_codec is None:
            raise RuntimeError("secure mesh capsule service is unavailable")
        payload = self.capsule_codec.open(
            capsule,
            expected_kind=CapsuleKind.MESH,
            expected_subject=f"mesh:{source_node_id}:{self.local_node_id}",
        )
        try:
            raw = json.loads(payload)
            if set(raw) != {
                "source_node_id",
                "target_node_id",
                "events",
                "cursor",
                "batch_signature",
            }:
                raise ValueError
            if (
                raw["source_node_id"] != source_node_id
                or raw["target_node_id"] != self.local_node_id
                or not isinstance(raw["events"], list)
            ):
                raise ValueError
            events = [NodeEvent.from_dict(item) for item in raw["events"]]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("secure mesh capsule payload is invalid") from exc
        appended = 0
        skipped = 0
        for event in events:
            if event.node_id != source_node_id:
                raise ValueError("secure mesh event source does not match capsule")
            if self.event_log.append_raw(event):
                appended += 1
            else:
                skipped += 1
        return appended, skipped

    def resolve_conflicting_events(
        self, event_a: NodeEvent, event_b: NodeEvent
    ) -> NodeEvent:
        """Resolve conflicts by sequence number, timestamp, then node ID."""
        if event_a.sequence_number != event_b.sequence_number:
            return (
                event_a
                if event_a.sequence_number > event_b.sequence_number
                else event_b
            )

        if event_a.timestamp != event_b.timestamp:
            return event_a if event_a.timestamp > event_b.timestamp else event_b

        # Tie-breaker: lexicographical node_id order
        return event_a if event_a.node_id > event_b.node_id else event_b
