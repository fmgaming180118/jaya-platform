"""Transactional SQLite storage for dynamic pillar definitions and state."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .models import (
    PillarDefinition,
    PillarRecord,
    PillarStatus,
    PillarStorageError,
    PillarValidationError,
    definition_from_storage,
    validate_reference,
)

SCHEMA_VERSION = 1
_CANDIDATE_STATUSES = frozenset(
    {
        PillarStatus.NOT_IMPLEMENTED,
        PillarStatus.IDEA,
        PillarStatus.PLANNED,
        PillarStatus.PROTOTYPE,
        PillarStatus.BLOCKED_EXTERNAL,
        PillarStatus.FAILED,
    }
)
_EVIDENCE_REQUIRED = frozenset(
    {
        PillarStatus.IMPLEMENTED_LOCAL,
        PillarStatus.INTEGRATED,
        PillarStatus.VERIFIED,
        PillarStatus.PRODUCTION,
    }
)
_APPROVAL_REQUIRED = frozenset(
    {PillarStatus.INTEGRATED, PillarStatus.VERIFIED, PillarStatus.PRODUCTION}
)
_TRANSITIONS: dict[PillarStatus, frozenset[PillarStatus]] = {
    PillarStatus.NOT_IMPLEMENTED: frozenset(
        {PillarStatus.IDEA, PillarStatus.PLANNED, PillarStatus.BLOCKED_EXTERNAL, PillarStatus.FAILED}
    ),
    PillarStatus.IDEA: frozenset(
        {PillarStatus.PLANNED, PillarStatus.BLOCKED_EXTERNAL, PillarStatus.FAILED}
    ),
    PillarStatus.PLANNED: frozenset(
        {PillarStatus.PROTOTYPE, PillarStatus.BLOCKED_EXTERNAL, PillarStatus.FAILED}
    ),
    PillarStatus.PROTOTYPE: frozenset(
        {PillarStatus.IMPLEMENTED_LOCAL, PillarStatus.BLOCKED_EXTERNAL, PillarStatus.FAILED}
    ),
    PillarStatus.IMPLEMENTED_LOCAL: frozenset(
        {PillarStatus.INTEGRATED, PillarStatus.BLOCKED_EXTERNAL, PillarStatus.FAILED}
    ),
    PillarStatus.INTEGRATED: frozenset(
        {PillarStatus.VERIFIED, PillarStatus.BLOCKED_EXTERNAL, PillarStatus.FAILED}
    ),
    PillarStatus.VERIFIED: frozenset(
        {PillarStatus.PRODUCTION, PillarStatus.BLOCKED_EXTERNAL, PillarStatus.FAILED}
    ),
    PillarStatus.PRODUCTION: frozenset({PillarStatus.FAILED}),
    PillarStatus.BLOCKED_EXTERNAL: frozenset(
        {
            PillarStatus.PLANNED,
            PillarStatus.PROTOTYPE,
            PillarStatus.IMPLEMENTED_LOCAL,
            PillarStatus.FAILED,
        }
    ),
    PillarStatus.FAILED: frozenset({PillarStatus.PLANNED, PillarStatus.BLOCKED_EXTERNAL}),
}


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PillarValidationError("INVALID_JSON", "pillar data must be finite JSON") from exc


class PillarRepository:
    """Persistent append-audited repository with optimistic revisions."""

    def __init__(self, database_path: str | Path) -> None:
        raw_path = str(database_path)
        if raw_path == ":memory:":
            raise PillarStorageError(
                "PERSISTENCE_REQUIRED",
                "dynamic pillar registry requires a persistent database path",
            )
        self.database_path = Path(database_path).expanduser().resolve()
        self._lock = threading.RLock()
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        except PillarStorageError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise PillarStorageError("STORAGE_UNAVAILABLE", "pillar database could not be initialized") from exc

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                str(self.database_path),
                timeout=10.0,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            return connection
        except sqlite3.Error as exc:
            raise PillarStorageError("STORAGE_UNAVAILABLE", "pillar database connection failed") from exc

    def _initialize(self) -> None:
        with self._connect() as connection:
            try:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version > SCHEMA_VERSION:
                    raise PillarStorageError(
                        "SCHEMA_TOO_NEW",
                        "pillar database schema is newer than this runtime",
                    )
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = FULL")
                if version == 0:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.executescript(
                        """
                        CREATE TABLE pillar_definitions (
                            pillar_id TEXT PRIMARY KEY,
                            definition_json TEXT NOT NULL,
                            definition_digest TEXT NOT NULL,
                            origin TEXT NOT NULL,
                            idempotency_key TEXT UNIQUE,
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL
                        );
                        CREATE TABLE pillar_states (
                            pillar_id TEXT PRIMARY KEY,
                            status TEXT NOT NULL,
                            revision INTEGER NOT NULL,
                            evidence_json TEXT NOT NULL,
                            updated_at REAL NOT NULL,
                            FOREIGN KEY(pillar_id) REFERENCES pillar_definitions(pillar_id)
                        );
                        CREATE TABLE pillar_events (
                            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            pillar_id TEXT NOT NULL,
                            event_type TEXT NOT NULL,
                            actor TEXT NOT NULL,
                            details_json TEXT NOT NULL,
                            created_at REAL NOT NULL,
                            FOREIGN KEY(pillar_id) REFERENCES pillar_definitions(pillar_id)
                        );
                        CREATE INDEX idx_pillar_states_status
                            ON pillar_states(status, updated_at DESC);
                        CREATE INDEX idx_pillar_events_pillar
                            ON pillar_events(pillar_id, event_id DESC);
                        PRAGMA user_version = 1;
                        """
                    )
                    connection.commit()
            except PillarStorageError:
                raise
            except sqlite3.Error as exc:
                raise PillarStorageError("STORAGE_CORRUPT", "pillar database schema is invalid") from exc

    @staticmethod
    def _record(row: sqlite3.Row) -> PillarRecord:
        try:
            definition = definition_from_storage(json.loads(row["definition_json"]))
            evidence = json.loads(row["evidence_json"])
            if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
                raise ValueError
            return PillarRecord(
                definition=definition,
                status=PillarStatus(row["status"]),
                revision=int(row["revision"]),
                origin=str(row["origin"]),
                evidence_refs=tuple(evidence),
                created_at=float(row["created_at"]),
                updated_at=float(row["state_updated_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PillarStorageError("STORAGE_CORRUPT", "stored pillar record is invalid") from exc

    @staticmethod
    def _select_sql() -> str:
        return """
            SELECT d.definition_json, d.definition_digest, d.origin,
                   d.created_at, s.status, s.revision, s.evidence_json,
                   s.updated_at AS state_updated_at
            FROM pillar_definitions AS d
            JOIN pillar_states AS s ON s.pillar_id = d.pillar_id
        """

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        *,
        pillar_id: str,
        event_type: str,
        actor: str,
        details: Mapping[str, Any],
        now: float,
    ) -> None:
        connection.execute(
            """
            INSERT INTO pillar_events (
                pillar_id, event_type, actor, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (pillar_id, event_type, actor, _json(dict(details)), now),
        )

    def seed(self, definitions: Iterable[tuple[PillarDefinition, str]]) -> int:
        """Insert immutable baseline definitions; conflicting drift fails closed."""

        inserted = 0
        with self._lock, self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                for definition, raw_origin in definitions:
                    origin = validate_reference(raw_origin, "origin")
                    existing = connection.execute(
                        "SELECT definition_digest FROM pillar_definitions WHERE pillar_id = ?",
                        (definition.pillar_id,),
                    ).fetchone()
                    if existing is not None:
                        if str(existing[0]) != definition.digest():
                            raise PillarValidationError(
                                "BASELINE_CONFLICT",
                                f"persisted definition conflicts with {definition.pillar_id}",
                            )
                        continue
                    now = time.time()
                    connection.execute(
                        """
                        INSERT INTO pillar_definitions (
                            pillar_id, definition_json, definition_digest, origin,
                            idempotency_key, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                        """,
                        (
                            definition.pillar_id,
                            _json(definition.to_dict()),
                            definition.digest(),
                            origin,
                            now,
                            now,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO pillar_states (
                            pillar_id, status, revision, evidence_json, updated_at
                        ) VALUES (?, ?, 1, '[]', ?)
                        """,
                        (definition.pillar_id, definition.initial_status.value, now),
                    )
                    self._event(
                        connection,
                        pillar_id=definition.pillar_id,
                        event_type="BASELINE_SEEDED",
                        actor="system:bootstrap",
                        details={"digest": definition.digest(), "origin": origin},
                        now=now,
                    )
                    inserted += 1
                connection.commit()
            except (PillarValidationError, PillarStorageError):
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                raise PillarStorageError("STORAGE_WRITE_FAILED", "pillar baseline could not be persisted") from exc
        return inserted

    def register_candidate(
        self,
        definition: PillarDefinition,
        *,
        origin: str,
        idempotency_key: str,
        actor: str,
    ) -> tuple[PillarRecord, bool]:
        if definition.initial_status not in _CANDIDATE_STATUSES:
            raise PillarValidationError(
                "CANDIDATE_STATUS_FORBIDDEN",
                "new pillars must enter as non-promoted candidates",
            )
        safe_origin = validate_reference(origin, "origin")
        safe_key = validate_reference(idempotency_key, "idempotency_key")
        safe_actor = validate_reference(actor, "actor")
        digest = definition.digest()
        with self._lock, self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                duplicate_key = connection.execute(
                    "SELECT pillar_id, definition_digest FROM pillar_definitions WHERE idempotency_key = ?",
                    (safe_key,),
                ).fetchone()
                if duplicate_key is not None:
                    if str(duplicate_key["definition_digest"]) != digest:
                        raise PillarValidationError(
                            "IDEMPOTENCY_CONFLICT",
                            "idempotency key was already used for different pillar data",
                        )
                    connection.commit()
                    return self.get(str(duplicate_key["pillar_id"])), False
                existing = connection.execute(
                    "SELECT definition_digest FROM pillar_definitions WHERE pillar_id = ?",
                    (definition.pillar_id,),
                ).fetchone()
                if existing is not None:
                    if str(existing[0]) != digest:
                        raise PillarValidationError("PILLAR_CONFLICT", "pillar ID already has a different definition")
                    connection.commit()
                    return self.get(definition.pillar_id), False
                now = time.time()
                connection.execute(
                    """
                    INSERT INTO pillar_definitions (
                        pillar_id, definition_json, definition_digest, origin,
                        idempotency_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        definition.pillar_id,
                        _json(definition.to_dict()),
                        digest,
                        safe_origin,
                        safe_key,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO pillar_states (
                        pillar_id, status, revision, evidence_json, updated_at
                    ) VALUES (?, ?, 1, '[]', ?)
                    """,
                    (definition.pillar_id, definition.initial_status.value, now),
                )
                self._event(
                    connection,
                    pillar_id=definition.pillar_id,
                    event_type="CANDIDATE_REGISTERED",
                    actor=safe_actor,
                    details={"digest": digest, "origin": safe_origin},
                    now=now,
                )
                connection.commit()
            except PillarValidationError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                raise PillarStorageError("STORAGE_WRITE_FAILED", "pillar candidate could not be persisted") from exc
        return self.get(definition.pillar_id), True

    def get(self, pillar_id: str) -> PillarRecord:
        with self._connect() as connection:
            try:
                row = connection.execute(
                    self._select_sql() + " WHERE d.pillar_id = ?",
                    (pillar_id,),
                ).fetchone()
            except sqlite3.Error as exc:
                raise PillarStorageError("STORAGE_READ_FAILED", "pillar record could not be read") from exc
        if row is None:
            raise PillarValidationError("PILLAR_NOT_FOUND", "pillar ID is not registered")
        return self._record(row)

    def list(self) -> tuple[PillarRecord, ...]:
        with self._connect() as connection:
            try:
                rows = connection.execute(
                    self._select_sql() + " ORDER BY d.pillar_id"
                ).fetchall()
            except sqlite3.Error as exc:
                raise PillarStorageError("STORAGE_READ_FAILED", "pillar catalog could not be read") from exc
        return tuple(self._record(row) for row in rows)

    def transition_status(
        self,
        pillar_id: str,
        target: PillarStatus,
        *,
        expected_revision: int,
        evidence_refs: Sequence[str],
        actor: str,
        approval_reference: str | None = None,
    ) -> PillarRecord:
        if isinstance(expected_revision, bool) or expected_revision < 1:
            raise PillarValidationError("INVALID_REVISION", "expected revision must be positive")
        safe_actor = validate_reference(actor, "actor")
        evidence = tuple(dict.fromkeys(validate_reference(item, "evidence") for item in evidence_refs))
        approval = (
            validate_reference(approval_reference, "approval_reference")
            if approval_reference is not None
            else None
        )
        if target in _EVIDENCE_REQUIRED and not evidence:
            raise PillarValidationError("EVIDENCE_REQUIRED", "this status requires evidence references")
        if target in _APPROVAL_REQUIRED and approval is None:
            raise PillarValidationError("APPROVAL_REQUIRED", "this status requires an approval reference")
        with self._lock, self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT status, revision FROM pillar_states WHERE pillar_id = ?",
                    (pillar_id,),
                ).fetchone()
                if row is None:
                    raise PillarValidationError("PILLAR_NOT_FOUND", "pillar ID is not registered")
                current = PillarStatus(row["status"])
                revision = int(row["revision"])
                if revision != expected_revision:
                    raise PillarValidationError("REVISION_CONFLICT", "pillar state changed since it was read")
                if target not in _TRANSITIONS[current]:
                    raise PillarValidationError(
                        "INVALID_TRANSITION",
                        f"pillar cannot transition from {current.value} to {target.value}",
                    )
                now = time.time()
                updated = connection.execute(
                    """
                    UPDATE pillar_states
                    SET status = ?, revision = revision + 1,
                        evidence_json = ?, updated_at = ?
                    WHERE pillar_id = ? AND revision = ?
                    """,
                    (target.value, _json(list(evidence)), now, pillar_id, expected_revision),
                )
                if updated.rowcount != 1:
                    raise PillarValidationError("REVISION_CONFLICT", "pillar state changed during update")
                details: dict[str, Any] = {
                    "from": current.value,
                    "to": target.value,
                    "evidence_refs": list(evidence),
                }
                if approval is not None:
                    details["approval_reference"] = approval
                self._event(
                    connection,
                    pillar_id=pillar_id,
                    event_type="STATUS_TRANSITIONED",
                    actor=safe_actor,
                    details=details,
                    now=now,
                )
                connection.commit()
            except PillarValidationError:
                connection.rollback()
                raise
            except (ValueError, sqlite3.Error) as exc:
                connection.rollback()
                raise PillarStorageError("STORAGE_WRITE_FAILED", "pillar state could not be updated") from exc
        return self.get(pillar_id)

    def events(self, pillar_id: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            try:
                rows = connection.execute(
                    """
                    SELECT event_id, event_type, actor, details_json, created_at
                    FROM pillar_events WHERE pillar_id = ? ORDER BY event_id
                    """,
                    (pillar_id,),
                ).fetchall()
            except sqlite3.Error as exc:
                raise PillarStorageError("STORAGE_READ_FAILED", "pillar audit events could not be read") from exc
        return tuple(
            {
                "event_id": int(row["event_id"]),
                "event_type": str(row["event_type"]),
                "actor": str(row["actor"]),
                "details": json.loads(row["details_json"]),
                "created_at": float(row["created_at"]),
            }
            for row in rows
        )

    def health_check(self) -> bool:
        try:
            with self._connect() as connection:
                integrity = connection.execute("PRAGMA quick_check").fetchone()
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            return bool(integrity and integrity[0] == "ok" and version == SCHEMA_VERSION)
        except (PillarStorageError, sqlite3.Error, TypeError, ValueError):
            return False
