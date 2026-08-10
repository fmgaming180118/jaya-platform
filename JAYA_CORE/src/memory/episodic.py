"""
episodic.py — Lightweight SQLite episodic memory engine.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional

from .events import MemoryEvent

logger = logging.getLogger(__name__)


class EpisodicMemoryStore:
    """Persistent, lightweight SQLite episodic memory with event idempotency."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path, timeout=5.0, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            if self.db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL;")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodic_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    goal_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session ON episodic_events(session_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_goal ON episodic_events(goal_id);"
            )

    def append_event(self, event: MemoryEvent) -> bool:
        """Appends event idempotently. Returns True if inserted, False if duplicate."""
        payload_str = json.dumps(event.payload, sort_keys=True)
        try:
            with self._lock, self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO episodic_events (
                        event_id, event_type, session_id, goal_id,
                        payload_json, node_id, timestamp, sequence_number
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        event.event_id,
                        event.event_type,
                        event.session_id,
                        event.goal_id,
                        payload_str,
                        event.node_id,
                        event.timestamp,
                        event.sequence_number,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            logger.debug("Duplicate event_id '%s' ignored", event.event_id)
            return False

    def query_by_session(self, session_id: str, limit: int = 50) -> List[MemoryEvent]:
        with self._lock:
            rows = (
                self._get_connection()
                .execute(
                    """
                SELECT event_id, event_type, session_id, goal_id,
                       payload_json AS payload, node_id, timestamp, sequence_number
                FROM episodic_events
                WHERE session_id = ?
                ORDER BY sequence_number ASC, timestamp ASC
                LIMIT ?;
                """,
                    (session_id, limit),
                )
                .fetchall()
            )
        return [MemoryEvent.from_dict(dict(r)) for r in rows]

    def query_by_goal(self, goal_id: str, limit: int = 50) -> List[MemoryEvent]:
        with self._lock:
            rows = (
                self._get_connection()
                .execute(
                    """
                SELECT event_id, event_type, session_id, goal_id,
                       payload_json AS payload, node_id, timestamp, sequence_number
                FROM episodic_events
                WHERE goal_id = ?
                ORDER BY sequence_number ASC, timestamp ASC
                LIMIT ?;
                """,
                    (goal_id, limit),
                )
                .fetchall()
            )
        return [MemoryEvent.from_dict(dict(r)) for r in rows]

    def get_recent_events(self, limit: int = 20) -> List[MemoryEvent]:
        with self._lock:
            rows = (
                self._get_connection()
                .execute(
                    """
                SELECT event_id, event_type, session_id, goal_id,
                       payload_json AS payload, node_id, timestamp, sequence_number
                FROM episodic_events
                ORDER BY sequence_number DESC, timestamp DESC
                LIMIT ?;
                """,
                    (limit,),
                )
                .fetchall()
            )
        events = [MemoryEvent.from_dict(dict(r)) for r in rows]
        events.reverse()
        return events

    def health_check(self) -> bool:
        """Return storage readiness without mutating episodic state."""
        try:
            with self._lock:
                self._get_connection().execute("SELECT 1").fetchone()
        except sqlite3.Error:
            return False
        return True

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
