"""Durable SQLite repository for thesis-analysis sessions."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any


class ThesisSessionError(RuntimeError):
    """Raised when durable thesis session state cannot be read or written."""


class ThesisSessionRepository:
    """Transactionally persist complete session payloads with revision numbers."""

    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.database_path),
            timeout=10,
            isolation_level=None,
        )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS thesis_sessions (
                    session_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_thesis_sessions_workspace_updated
                ON thesis_sessions(workspace_id, updated_at DESC)
                """
            )

    @staticmethod
    def _serialize(payload: dict[str, Any]) -> str:
        try:
            return json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ThesisSessionError(
                f"Session payload is not JSON serializable: {exc}"
            ) from exc

    @staticmethod
    def _deserialize(session_id: str, raw_payload: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise ThesisSessionError(
                f"Session {session_id} contains invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ThesisSessionError(f"Session {session_id} payload is not an object")
        return payload

    def exists(self, session_id: str) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM thesis_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row is not None

    def get(self, session_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM thesis_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return self._deserialize(session_id, row[0])

    def save(self, session_id: str, payload: dict[str, Any]) -> int:
        if not session_id or len(session_id) > 128:
            raise ThesisSessionError("Invalid session_id")
        workspace_id = str(payload.get("workspace_id") or "").strip()
        if not workspace_id:
            raise ThesisSessionError("Session workspace_id is required")
        serialized = self._serialize(payload)
        now = time.time()

        with self._lock, self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT revision, created_at FROM thesis_sessions "
                    "WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                revision = (int(existing[0]) + 1) if existing else 1
                created_at = float(existing[1]) if existing else now
                connection.execute(
                    """
                    INSERT INTO thesis_sessions (
                        session_id,
                        workspace_id,
                        payload_json,
                        revision,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        workspace_id = excluded.workspace_id,
                        payload_json = excluded.payload_json,
                        revision = excluded.revision,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session_id,
                        workspace_id,
                        serialized,
                        revision,
                        created_at,
                        now,
                    ),
                )
                connection.commit()
            except sqlite3.Error as exc:
                connection.rollback()
                raise ThesisSessionError(
                    f"Could not save thesis session {session_id}: {exc}"
                ) from exc
        return revision

    def list_ids(self) -> list[str]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT session_id FROM thesis_sessions ORDER BY updated_at DESC"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def delete(self, session_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM thesis_sessions WHERE session_id = ?",
                (session_id,),
            )

    def recover_interrupted(self) -> int:
        """Mark process-local running work as interrupted after a restart."""
        recovered = 0
        for session_id in self.list_ids():
            payload = self.get(session_id)
            if payload.get("status") not in {"analyzing", "running"}:
                continue
            payload["status"] = "interrupted"
            payload["error"] = (
                "Analysis was interrupted by a process restart; explicitly start "
                "the analysis again to resume from durable source text."
            )
            self.save(session_id, payload)
            recovered += 1
        return recovered


class PersistentThesisSessions(MutableMapping[str, dict[str, Any]]):
    """Minimal mapping compatibility layer backed by the repository."""

    def __init__(self, repository: ThesisSessionRepository):
        self.repository = repository

    def __getitem__(self, key: str) -> dict[str, Any]:
        return self.repository.get(key)

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        self.repository.save(key, value)

    def __delitem__(self, key: str) -> None:
        if not self.repository.exists(key):
            raise KeyError(key)
        self.repository.delete(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.repository.list_ids())

    def __len__(self) -> int:
        return len(self.repository.list_ids())

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.repository.exists(key)

    def persist(self, session_id: str, payload: dict[str, Any]) -> int:
        return self.repository.save(session_id, payload)
