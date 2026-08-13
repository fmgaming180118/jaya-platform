"""
job_worker.py — Background Job Worker Queue for long-running task isolation.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class PersistentJob:
    job_id: str
    job_type: str
    payload: Dict[str, Any]
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    retry_count: int = 0
    max_retries: int = 3
    correlation_id: str = field(default_factory=lambda: f"corr-{uuid.uuid4().hex[:8]}")
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["status"] = self.status.value
        return res


class BackgroundJobWorker:
    """Manages background task queue execution independently from API event loop."""

    def __init__(self, max_retries_default: int = 3) -> None:
        self.max_retries_default = max_retries_default
        self._jobs: Dict[str, PersistentJob] = {}
        self._handlers: Dict[str, Callable[[PersistentJob], bool]] = {}

    def register_handler(
        self, job_type: str, handler: Callable[[PersistentJob], bool]
    ) -> None:
        self._handlers[job_type] = handler

    def submit_job(
        self,
        job_type: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
        max_retries: Optional[int] = None,
    ) -> PersistentJob:
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        corr_id = correlation_id or f"corr-{uuid.uuid4().hex[:8]}"
        retries = max_retries if max_retries is not None else self.max_retries_default

        job = PersistentJob(
            job_id=job_id,
            job_type=job_type,
            payload=payload,
            status=JobStatus.QUEUED,
            correlation_id=corr_id,
            max_retries=retries,
        )
        self._jobs[job_id] = job
        logger.info("Submitted job %s (type=%s, corr_id=%s)", job_id, job_type, corr_id)
        return job

    def get_job(self, job_id: str) -> Optional[PersistentJob]:
        return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        job = self._jobs[job_id]
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return False
        job.status = JobStatus.CANCELLED
        job.completed_at = time.time()
        logger.info("Cancelled job %s", job_id)
        return True

    def process_next_job(self) -> Optional[PersistentJob]:
        # Find oldest QUEUED job
        queued = [j for j in self._jobs.values() if j.status == JobStatus.QUEUED]
        if not queued:
            return None

        job = sorted(queued, key=lambda j: j.created_at)[0]
        job.status = JobStatus.RUNNING
        logger.info("Processing job %s (type=%s)", job.job_id, job.job_type)

        handler = self._handlers.get(job.job_type)
        if not handler:
            job.status = JobStatus.FAILED
            job.error_message = f"No handler registered for job_type '{job.job_type}'"
            job.completed_at = time.time()
            return job

        try:
            success = handler(job)
            if success:
                job.status = JobStatus.COMPLETED
                job.progress = 1.0
                job.completed_at = time.time()
            else:
                self._handle_job_failure(job, "Handler returned failure status")
        except Exception as exc:
            self._handle_job_failure(job, str(exc))

        return job

    def _handle_job_failure(self, job: PersistentJob, error_msg: str) -> None:
        job.retry_count += 1
        if job.retry_count <= job.max_retries:
            job.status = JobStatus.QUEUED
            job.error_message = f"Retry {job.retry_count}/{job.max_retries}: {error_msg}"
            logger.warning(
                "Job %s failed, re-queued (retry %d/%d): %s",
                job.job_id,
                job.retry_count,
                job.max_retries,
                error_msg,
            )
        else:
            job.status = JobStatus.FAILED
            job.error_message = f"Max retries exceeded: {error_msg}"
            job.completed_at = time.time()
            logger.error("Job %s permanently FAILED: %s", job.job_id, error_msg)
