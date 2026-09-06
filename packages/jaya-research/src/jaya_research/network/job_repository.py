"""Durable, idempotent background-job state machine for Research."""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .http_security.errors import redact_sensitive

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_SECRET_KEY = re.compile(
    r"(?i)(authorization|password|secret|api[_-]?key|token)"
)


class JobRepositoryError(RuntimeError):
    """Base error for durable job operations."""


class JobValidationError(JobRepositoryError):
    """Raised for unsafe or malformed job input."""


class JobTransitionError(JobRepositoryError):
    """Raised when a requested state transition is not allowed."""


class JobNotFoundError(JobRepositoryError):
    """Raised when a job identifier does not exist."""


class JobState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_REVIEW = "WAITING_REVIEW"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


TERMINAL_STATES = frozenset(
    {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELED}
)


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    job_type: str
    workspace_id: str
    idempotency_key: str
    payload: dict[str, Any]
    payload_sha256: str
    state: JobState
    progress: float
    attempt: int
    max_attempts: int
    cancel_requested: bool
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    created_at: float
    updated_at: float
    lease_owner: str | None
    lease_expires_at: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "workspace_id": self.workspace_id,
            "idempotency_key": self.idempotency_key,
            "payload_sha256": self.payload_sha256,
            "state": self.state.value,
            "progress": self.progress,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "cancel_requested": self.cancel_requested,
            "result": self.result,
            "error": (
                {
                    "code": self.error_code,
                    "message": self.error_message,
                }
                if self.error_code
                else None
            ),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "lease_owner": self.lease_owner,
            "lease_expires_at": self.lease_expires_at,
        }


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise JobValidationError("Job payload must be finite JSON data") from exc


def _validate_no_secrets(value: Any, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEY.search(key_text):
                raise JobValidationError(
                    f"Secret-bearing field is forbidden in persisted {path}"
                )
            _validate_no_secrets(item, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_secrets(item, f"{path}[{index}]")


def _safe_identifier(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_ID.fullmatch(normalized):
        raise JobValidationError(
            f"{field_name} must contain 3-128 safe identifier characters"
        )
    return normalized


class DurableJobRepository:
    """SQLite-backed job queue with leases, retries, cancel, and recovery."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_jobs (
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    progress REAL NOT NULL,
                    attempt INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    cancel_requested INTEGER NOT NULL,
                    result_json TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    lease_owner TEXT,
                    lease_expires_at REAL,
                    UNIQUE(job_type, workspace_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS research_job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT,
                    created_at REAL NOT NULL,
                    details_json TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES research_jobs(job_id)
                );
                """
            )

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            job_type=row["job_type"],
            workspace_id=row["workspace_id"],
            idempotency_key=row["idempotency_key"],
            payload=json.loads(row["payload_json"]),
            payload_sha256=row["payload_sha256"],
            state=JobState(row["state"]),
            progress=float(row["progress"]),
            attempt=int(row["attempt"]),
            max_attempts=int(row["max_attempts"]),
            cancel_requested=bool(row["cancel_requested"]),
            result=(
                json.loads(row["result_json"])
                if row["result_json"] is not None
                else None
            ),
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            lease_owner=row["lease_owner"],
            lease_expires_at=(
                float(row["lease_expires_at"])
                if row["lease_expires_at"] is not None
                else None
            ),
        )

    def _event(
        self,
        connection: sqlite3.Connection,
        *,
        job_id: str,
        event_type: str,
        from_state: JobState | None,
        to_state: JobState | None,
        now: float,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        details_json = _canonical_json(dict(details or {}))
        connection.execute(
            """
            INSERT INTO research_job_events (
                job_id, event_type, from_state, to_state, created_at, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                event_type,
                from_state.value if from_state else None,
                to_state.value if to_state else None,
                now,
                details_json,
            ),
        )

    def create(
        self,
        *,
        job_type: str,
        workspace_id: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
        max_attempts: int = 3,
    ) -> tuple[JobRecord, bool]:
        normalized_type = _safe_identifier(job_type, "job_type")
        normalized_workspace = _safe_identifier(workspace_id, "workspace_id")
        normalized_key = _safe_identifier(idempotency_key, "idempotency_key")
        if isinstance(max_attempts, bool) or not 1 <= max_attempts <= 10:
            raise JobValidationError("max_attempts must be between 1 and 10")
        normalized_payload = dict(payload)
        _validate_no_secrets(normalized_payload)
        payload_json = _canonical_json(normalized_payload)
        payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        now = time.time()

        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM research_jobs
                WHERE job_type = ? AND workspace_id = ? AND idempotency_key = ?
                """,
                (normalized_type, normalized_workspace, normalized_key),
            ).fetchone()
            if existing is not None:
                if existing["payload_sha256"] != payload_sha256:
                    connection.rollback()
                    raise JobValidationError(
                        "Idempotency key was already used for a different payload"
                    )
                connection.commit()
                return self._record_from_row(existing), False

            job_id = f"job-{secrets.token_hex(16)}"
            connection.execute(
                """
                INSERT INTO research_jobs (
                    job_id, job_type, workspace_id, idempotency_key,
                    payload_json, payload_sha256, state, progress, attempt,
                    max_attempts, cancel_requested, result_json, error_code,
                    error_message, created_at, updated_at, lease_owner,
                    lease_expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 0, ?, 0, NULL, NULL,
                          NULL, ?, ?, NULL, NULL)
                """,
                (
                    job_id,
                    normalized_type,
                    normalized_workspace,
                    normalized_key,
                    payload_json,
                    payload_sha256,
                    JobState.QUEUED.value,
                    max_attempts,
                    now,
                    now,
                ),
            )
            self._event(
                connection,
                job_id=job_id,
                event_type="CREATED",
                from_state=None,
                to_state=JobState.QUEUED,
                now=now,
                details={"payload_sha256": payload_sha256},
            )
            row = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            connection.commit()
        assert row is not None
        return self._record_from_row(row), True

    def get(self, job_id: str) -> JobRecord:
        normalized_id = _safe_identifier(job_id, "job_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
        if row is None:
            raise JobNotFoundError(f"Unknown job: {normalized_id}")
        return self._record_from_row(row)

    def start(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_seconds: float = 60.0,
    ) -> JobRecord:
        normalized_id = _safe_identifier(job_id, "job_id")
        normalized_worker = _safe_identifier(worker_id, "worker_id")
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise JobValidationError("lease_seconds must be positive and finite")
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise JobNotFoundError(f"Unknown job: {normalized_id}")
            state = JobState(row["state"])
            if state is not JobState.QUEUED:
                connection.rollback()
                raise JobTransitionError(
                    f"Job cannot start from state {state.value}"
                )
            if bool(row["cancel_requested"]):
                connection.execute(
                    """
                    UPDATE research_jobs
                    SET state = ?, updated_at = ?, lease_owner = NULL,
                        lease_expires_at = NULL
                    WHERE job_id = ?
                    """,
                    (JobState.CANCELED.value, now, normalized_id),
                )
                self._event(
                    connection,
                    job_id=normalized_id,
                    event_type="CANCELED_BEFORE_START",
                    from_state=state,
                    to_state=JobState.CANCELED,
                    now=now,
                )
            else:
                connection.execute(
                    """
                    UPDATE research_jobs
                    SET state = ?, attempt = attempt + 1, updated_at = ?,
                        lease_owner = ?, lease_expires_at = ?
                    WHERE job_id = ?
                    """,
                    (
                        JobState.RUNNING.value,
                        now,
                        normalized_worker,
                        now + lease_seconds,
                        normalized_id,
                    ),
                )
                self._event(
                    connection,
                    job_id=normalized_id,
                    event_type="STARTED",
                    from_state=state,
                    to_state=JobState.RUNNING,
                    now=now,
                    details={"worker_id": normalized_worker},
                )
            updated = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
            connection.commit()
        assert updated is not None
        return self._record_from_row(updated)

    def update_progress(
        self,
        job_id: str,
        *,
        worker_id: str,
        progress: float,
        lease_seconds: float = 60.0,
    ) -> JobRecord:
        normalized_id = _safe_identifier(job_id, "job_id")
        normalized_worker = _safe_identifier(worker_id, "worker_id")
        if not math.isfinite(progress) or not 0.0 <= progress <= 1.0:
            raise JobValidationError("progress must be between 0 and 1")
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise JobValidationError("lease_seconds must be positive and finite")
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise JobNotFoundError(f"Unknown job: {normalized_id}")
            if (
                JobState(row["state"]) is not JobState.RUNNING
                or row["lease_owner"] != normalized_worker
            ):
                connection.rollback()
                raise JobTransitionError("Only the active worker may update progress")
            if progress < float(row["progress"]):
                connection.rollback()
                raise JobTransitionError("Job progress cannot move backwards")
            connection.execute(
                """
                UPDATE research_jobs
                SET progress = ?, updated_at = ?, lease_expires_at = ?
                WHERE job_id = ?
                """,
                (progress, now, now + lease_seconds, normalized_id),
            )
            updated = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
            connection.commit()
        assert updated is not None
        return self._record_from_row(updated)

    def _finish(
        self,
        job_id: str,
        *,
        worker_id: str,
        target_state: JobState,
        result: Mapping[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> JobRecord:
        normalized_id = _safe_identifier(job_id, "job_id")
        normalized_worker = _safe_identifier(worker_id, "worker_id")
        if target_state not in {
            JobState.SUCCEEDED,
            JobState.WAITING_REVIEW,
            JobState.FAILED,
        }:
            raise JobTransitionError("Unsupported worker completion state")
        result_json = None
        if result is not None:
            normalized_result = dict(result)
            _validate_no_secrets(normalized_result, "result")
            result_json = _canonical_json(normalized_result)
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise JobNotFoundError(f"Unknown job: {normalized_id}")
            if (
                JobState(row["state"]) is not JobState.RUNNING
                or row["lease_owner"] != normalized_worker
            ):
                connection.rollback()
                raise JobTransitionError("Only the active worker may finish a job")
            final_state = (
                JobState.CANCELED
                if bool(row["cancel_requested"])
                else target_state
            )
            progress = 1.0 if final_state is JobState.SUCCEEDED else row["progress"]
            connection.execute(
                """
                UPDATE research_jobs
                SET state = ?, progress = ?, result_json = ?, error_code = ?,
                    error_message = ?, updated_at = ?, lease_owner = NULL,
                    lease_expires_at = NULL
                WHERE job_id = ?
                """,
                (
                    final_state.value,
                    progress,
                    result_json,
                    error_code,
                    error_message,
                    now,
                    normalized_id,
                ),
            )
            self._event(
                connection,
                job_id=normalized_id,
                event_type="FINISHED",
                from_state=JobState.RUNNING,
                to_state=final_state,
                now=now,
                details={"error_code": error_code} if error_code else {},
            )
            updated = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
            connection.commit()
        assert updated is not None
        return self._record_from_row(updated)

    def succeed(
        self,
        job_id: str,
        *,
        worker_id: str,
        result: Mapping[str, Any],
    ) -> JobRecord:
        return self._finish(
            job_id,
            worker_id=worker_id,
            target_state=JobState.SUCCEEDED,
            result=result,
        )

    def wait_for_review(
        self,
        job_id: str,
        *,
        worker_id: str,
        result: Mapping[str, Any],
    ) -> JobRecord:
        return self._finish(
            job_id,
            worker_id=worker_id,
            target_state=JobState.WAITING_REVIEW,
            result=result,
        )

    def fail(
        self,
        job_id: str,
        *,
        worker_id: str,
        error_code: str,
        error_message: str,
        retryable: bool = False,
    ) -> JobRecord:
        normalized_code = _safe_identifier(error_code, "error_code")
        safe_message = str(
            redact_sensitive(str(error_message or "Job failed"))
        )[:512]
        current = self.get(job_id)
        if retryable and current.attempt < current.max_attempts:
            failed = self._finish(
                job_id,
                worker_id=worker_id,
                target_state=JobState.FAILED,
                error_code=normalized_code,
                error_message=safe_message,
            )
            return self.retry(failed.job_id)
        return self._finish(
            job_id,
            worker_id=worker_id,
            target_state=JobState.FAILED,
            error_code=normalized_code,
            error_message=safe_message,
        )

    def retry(self, job_id: str) -> JobRecord:
        normalized_id = _safe_identifier(job_id, "job_id")
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise JobNotFoundError(f"Unknown job: {normalized_id}")
            state = JobState(row["state"])
            if state is not JobState.FAILED or row["attempt"] >= row["max_attempts"]:
                connection.rollback()
                raise JobTransitionError("Failed job has no retry remaining")
            connection.execute(
                """
                UPDATE research_jobs
                SET state = ?, updated_at = ?, error_code = NULL,
                    error_message = NULL, cancel_requested = 0
                WHERE job_id = ?
                """,
                (JobState.QUEUED.value, now, normalized_id),
            )
            self._event(
                connection,
                job_id=normalized_id,
                event_type="RETRIED",
                from_state=state,
                to_state=JobState.QUEUED,
                now=now,
            )
            updated = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
            connection.commit()
        assert updated is not None
        return self._record_from_row(updated)

    def request_cancel(self, job_id: str) -> JobRecord:
        normalized_id = _safe_identifier(job_id, "job_id")
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise JobNotFoundError(f"Unknown job: {normalized_id}")
            state = JobState(row["state"])
            if state in TERMINAL_STATES:
                connection.commit()
                return self._record_from_row(row)
            target_state = (
                JobState.RUNNING if state is JobState.RUNNING else JobState.CANCELED
            )
            connection.execute(
                """
                UPDATE research_jobs
                SET state = ?, cancel_requested = 1, updated_at = ?
                WHERE job_id = ?
                """,
                (target_state.value, now, normalized_id),
            )
            self._event(
                connection,
                job_id=normalized_id,
                event_type="CANCEL_REQUESTED",
                from_state=state,
                to_state=target_state,
                now=now,
            )
            updated = connection.execute(
                "SELECT * FROM research_jobs WHERE job_id = ?",
                (normalized_id,),
            ).fetchone()
            connection.commit()
        assert updated is not None
        return self._record_from_row(updated)

    def recover_expired(self, *, now: float | None = None) -> int:
        recovery_time = time.time() if now is None else float(now)
        if not math.isfinite(recovery_time):
            raise JobValidationError("Recovery time must be finite")
        recovered = 0
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT * FROM research_jobs
                WHERE state = ? AND lease_expires_at IS NOT NULL
                      AND lease_expires_at <= ?
                """,
                (JobState.RUNNING.value, recovery_time),
            ).fetchall()
            for row in rows:
                target_state = (
                    JobState.CANCELED
                    if bool(row["cancel_requested"])
                    else (
                        JobState.QUEUED
                        if row["attempt"] < row["max_attempts"]
                        else JobState.FAILED
                    )
                )
                connection.execute(
                    """
                    UPDATE research_jobs
                    SET state = ?, updated_at = ?, lease_owner = NULL,
                        lease_expires_at = NULL,
                        error_code = CASE WHEN ? = ? THEN 'LEASE_EXPIRED' ELSE error_code END,
                        error_message = CASE WHEN ? = ? THEN 'Worker lease expired' ELSE error_message END
                    WHERE job_id = ?
                    """,
                    (
                        target_state.value,
                        recovery_time,
                        target_state.value,
                        JobState.FAILED.value,
                        target_state.value,
                        JobState.FAILED.value,
                        row["job_id"],
                    ),
                )
                self._event(
                    connection,
                    job_id=row["job_id"],
                    event_type="LEASE_RECOVERED",
                    from_state=JobState.RUNNING,
                    to_state=target_state,
                    now=recovery_time,
                )
                recovered += 1
            connection.commit()
        return recovered

    def events(self, job_id: str) -> list[dict[str, Any]]:
        normalized_id = _safe_identifier(job_id, "job_id")
        self.get(normalized_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_type, from_state, to_state, created_at, details_json
                FROM research_job_events
                WHERE job_id = ?
                ORDER BY event_id
                """,
                (normalized_id,),
            ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "from_state": row["from_state"],
                "to_state": row["to_state"],
                "created_at": float(row["created_at"]),
                "details": json.loads(row["details_json"]),
            }
            for row in rows
        ]
