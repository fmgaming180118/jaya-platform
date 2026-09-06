"""
episodic.py — Lightweight SQLite episodic memory engine.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from .events import MemoryEvent

logger = logging.getLogger(__name__)


class EpisodicPayloadCodec(Protocol):
    def encode_event(self, event: MemoryEvent) -> str:
        ...

    def decode_payload(self, stored: str, owner_id: str) -> dict[str, Any]:
        ...


class EpisodicMemoryStore:
    """Persistent, lightweight SQLite episodic memory with event idempotency."""

    def __init__(
        self,
        db_path: Path | str = ":memory:",
        payload_codec: EpisodicPayloadCodec | None = None,
    ) -> None:
        if str(db_path) == ":memory:":
            self.db_path = ":memory:"
        else:
            database_path = Path(db_path).expanduser().resolve()
            database_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(database_path)
        self._payload_codec = payload_codec
        self._conn: sqlite3.Connection | None = None
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS holographic_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO holographic_meta (key, value) VALUES ('schema_version', '1');
                CREATE TABLE IF NOT EXISTS holographic_metadata (
                    event_id TEXT PRIMARY KEY,
                    source_digest TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    owner_id TEXT NOT NULL,
                    policy TEXT NOT NULL,
                    observed_at REAL NOT NULL,
                    revoked_at REAL,
                    revoke_reason TEXT,
                    raw_indexes_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(event_id) REFERENCES episodic_events(event_id)
                );
                CREATE TABLE IF NOT EXISTS holographic_indexes (
                    event_id TEXT NOT NULL,
                    index_type TEXT NOT NULL,
                    index_value TEXT NOT NULL,
                    PRIMARY KEY(event_id, index_type, index_value),
                    FOREIGN KEY(event_id) REFERENCES episodic_events(event_id)
                );
                CREATE INDEX IF NOT EXISTS idx_holographic_lookup
                ON holographic_indexes(index_type, index_value, event_id);
                """
            )
            meta_cols = [
                row[1]
                for row in conn.execute("PRAGMA table_info(holographic_metadata);").fetchall()
            ]
            if "raw_indexes_json" not in meta_cols:
                conn.execute(
                    "ALTER TABLE holographic_metadata ADD COLUMN raw_indexes_json TEXT NOT NULL DEFAULT '{}';"
                )

    def append_event(self, event: MemoryEvent) -> bool:
        """Appends event idempotently. Returns True if inserted, False if duplicate."""
        payload_str = (
            self._payload_codec.encode_event(event)
            if self._payload_codec is not None
            else json.dumps(event.payload, sort_keys=True)
        )
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

    def append_holographic(
        self,
        event: MemoryEvent,
        metadata: Mapping[str, Any],
        indexes: Mapping[str, Sequence[str]],
    ) -> bool:
        """Atomically append an episodic event, provenance, and multi-index entries."""
        payload_str = (
            self._payload_codec.encode_event(event)
            if self._payload_codec is not None
            else json.dumps(event.payload, sort_keys=True)
        )
        try:
            with self._lock, self._get_connection() as conn:
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute(
                    """
                    INSERT INTO episodic_events (
                        event_id, event_type, session_id, goal_id,
                        payload_json, node_id, timestamp, sequence_number
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                conn.execute(
                    """INSERT INTO holographic_metadata(
                    event_id,source_digest,confidence,owner_id,policy,observed_at,raw_indexes_json
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (
                        event.event_id,
                        metadata["source_digest"],
                        metadata["confidence"],
                        metadata["owner_id"],
                        metadata["policy"],
                        metadata["observed_at"],
                        json.dumps(dict(indexes), sort_keys=True),
                    ),
                )
                conn.executemany(
                    "INSERT INTO holographic_indexes VALUES(?,?,?)",
                    (
                        (event.event_id, index_type, index_value)
                        for index_type, values in indexes.items()
                        for index_value in values
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            logger.debug("Duplicate holographic event_id '%s' ignored", event.event_id)
            return False

    def holographic_metadata(self, event_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._get_connection().execute(
                "SELECT * FROM holographic_metadata WHERE event_id=?", (event_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def holographic_record(self, event_id: str) -> dict[str, Any] | None:
        """Read one complete event, provenance record, and its durable indexes."""
        with self._lock:
            connection = self._get_connection()
            row = connection.execute(
                """
                SELECT e.event_id, e.event_type, e.session_id, e.goal_id,
                       e.payload_json AS payload, e.node_id, e.timestamp,
                       e.sequence_number, m.source_digest, m.confidence,
                       m.owner_id, m.policy, m.observed_at, m.revoked_at,
                       m.revoke_reason
                FROM episodic_events e JOIN holographic_metadata m
                ON m.event_id=e.event_id WHERE e.event_id=?
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            index_rows = connection.execute(
                """SELECT index_type,index_value FROM holographic_indexes
                WHERE event_id=? ORDER BY index_type,index_value""",
                (event_id,),
            ).fetchall()
        raw = dict(row)
        indexes: dict[str, list[str]] = {}
        for item in index_rows:
            indexes.setdefault(str(item["index_type"]), []).append(
                str(item["index_value"])
            )
        return {
            "event": self._row_to_event(row).to_dict(),
            "provenance": {
                key: raw[key]
                for key in (
                    "source_digest",
                    "confidence",
                    "owner_id",
                    "policy",
                    "observed_at",
                    "revoked_at",
                    "revoke_reason",
                )
            },
            "indexes": indexes,
        }

    def query_holographic(
        self,
        index_type: str,
        index_value: str,
        limit: int = 50,
        *,
        include_revoked: bool = False,
    ) -> list[dict[str, Any]]:
        revoked_clause = "" if include_revoked else "AND m.revoked_at IS NULL"
        with self._lock:
            rows = self._get_connection().execute(
                f"""
                SELECT e.event_id, e.event_type, e.session_id, e.goal_id,
                       e.payload_json AS payload, e.node_id, e.timestamp,
                       e.sequence_number, m.source_digest, m.confidence,
                       m.owner_id, m.policy, m.observed_at, m.revoked_at,
                       m.revoke_reason
                FROM holographic_indexes i
                JOIN episodic_events e ON e.event_id=i.event_id
                JOIN holographic_metadata m ON m.event_id=e.event_id
                WHERE i.index_type=? AND i.index_value=? {revoked_clause}
                ORDER BY m.observed_at DESC, e.sequence_number DESC
                LIMIT ?
                """,
                (index_type, index_value, limit),
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            raw = dict(row)
            event = self._row_to_event(row).to_dict()
            event["provenance"] = {
                key: raw[key]
                for key in (
                    "source_digest",
                    "confidence",
                    "owner_id",
                    "policy",
                    "observed_at",
                    "revoked_at",
                    "revoke_reason",
                )
            }
            output.append(event)
        return output

    def revoke_holographic(self, event_id: str, reason: str, revoked_at: float) -> bool:
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """UPDATE holographic_metadata SET revoked_at=?, revoke_reason=?
                WHERE event_id=? AND revoked_at IS NULL""",
                (revoked_at, reason, event_id),
            )
        return cursor.rowcount == 1

    def rebuild_indexes(self) -> int:
        """Reconstruct the entire holographic_indexes table deterministically from holographic_metadata."""
        with self._lock, self._get_connection() as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("DELETE FROM holographic_indexes;")
            cursor = conn.execute(
                "SELECT event_id, raw_indexes_json FROM holographic_metadata WHERE raw_indexes_json IS NOT NULL;"
            )
            rows = cursor.fetchall()
            count = 0
            to_insert: list[tuple[str, str, str]] = []
            for row in rows:
                event_id = str(row["event_id"])
                raw_json = row["raw_indexes_json"]
                if not raw_json:
                    continue
                try:
                    raw_indexes = json.loads(raw_json)
                except Exception:
                    continue
                if isinstance(raw_indexes, dict):
                    count += 1
                    for index_type, index_values in raw_indexes.items():
                        if isinstance(index_values, list):
                            for val in index_values:
                                to_insert.append((event_id, str(index_type), str(val)))
            if to_insert:
                conn.executemany(
                    "INSERT OR IGNORE INTO holographic_indexes VALUES(?,?,?)",
                    to_insert,
                )
            return count

    def compact(self, retention_seconds: float = 86400.0) -> dict[str, Any]:
        """Prune revoked holographic events whose revocation timestamp is older than retention_seconds."""
        cutoff = time.time() - max(0.0, float(retention_seconds))
        with self._lock, self._get_connection() as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cursor = conn.execute(
                "SELECT event_id FROM holographic_metadata WHERE revoked_at IS NOT NULL AND revoked_at <= ?",
                (cutoff,),
            )
            expired_ids = [str(r["event_id"]) for r in cursor.fetchall()]
            if expired_ids:
                placeholders = ",".join("?" for _ in expired_ids)
                conn.execute(
                    f"DELETE FROM holographic_indexes WHERE event_id IN ({placeholders});",
                    expired_ids,
                )
                conn.execute(
                    f"DELETE FROM holographic_metadata WHERE event_id IN ({placeholders});",
                    expired_ids,
                )
                conn.execute(
                    f"DELETE FROM episodic_events WHERE event_id IN ({placeholders});",
                    expired_ids,
                )
                try:
                    conn.execute("PRAGMA incremental_vacuum;")
                except Exception:
                    pass
            return {
                "pruned_events_count": len(expired_ids),
                "cutoff_timestamp": cutoff,
                "pruned_event_ids": expired_ids,
            }

    def export_holographic(
        self,
        session_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Export durable holographic records (with event, provenance, indexes) for data portability."""
        with self._lock:
            query = """
                SELECT e.event_id
                FROM episodic_events e JOIN holographic_metadata m
                ON m.event_id=e.event_id
                WHERE 1=1
            """
            params: list[Any] = []
            if session_id:
                query += " AND e.session_id=?"
                params.append(session_id)
            if owner_id:
                query += " AND m.owner_id=?"
                params.append(owner_id)
            query += " ORDER BY m.observed_at ASC, e.sequence_number ASC"
            rows = self._get_connection().execute(query, params).fetchall()
            output: list[dict[str, Any]] = []
            for row in rows:
                rec = self.holographic_record(str(row["event_id"]))
                if rec is not None:
                    output.append(rec)
            return output

    def delete_holographic(self, event_id: str, owner_id: str) -> bool:
        """Permanently remove an episodic event, provenance, and indexes if owner_id matches."""
        with self._lock, self._get_connection() as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            row = conn.execute(
                "SELECT owner_id FROM holographic_metadata WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if row is None or str(row["owner_id"]) != owner_id:
                return False
            conn.execute("DELETE FROM holographic_indexes WHERE event_id=?", (event_id,))
            conn.execute("DELETE FROM holographic_metadata WHERE event_id=?", (event_id,))
            conn.execute("DELETE FROM episodic_events WHERE event_id=?", (event_id,))
            return True

    def query_by_session(self, session_id: str, limit: int = 50) -> list[MemoryEvent]:
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
        return [self._row_to_event(r) for r in rows]

    def query_by_goal(self, goal_id: str, limit: int = 50) -> list[MemoryEvent]:
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
        return [self._row_to_event(r) for r in rows]

    def get_recent_events(self, limit: int = 20) -> list[MemoryEvent]:
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
        events = [self._row_to_event(r) for r in rows]
        events.reverse()
        return events

    def _row_to_event(self, row: sqlite3.Row) -> MemoryEvent:
        value = dict(row)
        if self._payload_codec is not None:
            value["payload"] = self._payload_codec.decode_payload(
                str(value["payload"]),
                str(value["session_id"]),
            )
        return MemoryEvent.from_dict(value)

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
