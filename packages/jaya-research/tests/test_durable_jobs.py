"""Durable Research job state-machine tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from jaya_research.network.job_repository import (
    DurableJobRepository,
    JobState,
    JobTransitionError,
    JobValidationError,
)


def _repository(tmp_path: Path) -> DurableJobRepository:
    return DurableJobRepository(tmp_path / "jobs.db")


def test_idempotent_create_survives_repository_restart(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    first, created = repository.create(
        job_type="research-study",
        workspace_id="default",
        idempotency_key="request-0001",
        payload={"topic": "grounded retrieval"},
    )
    reconstructed = _repository(tmp_path)
    second, created_again = reconstructed.create(
        job_type="research-study",
        workspace_id="default",
        idempotency_key="request-0001",
        payload={"topic": "grounded retrieval"},
    )

    assert created is True
    assert created_again is False
    assert first.job_id == second.job_id
    assert second.state is JobState.QUEUED


def test_idempotency_key_cannot_hide_changed_payload(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.create(
        job_type="research-study",
        workspace_id="default",
        idempotency_key="request-0002",
        payload={"topic": "first"},
    )

    with pytest.raises(JobValidationError, match="different payload"):
        repository.create(
            job_type="research-study",
            workspace_id="default",
            idempotency_key="request-0002",
            payload={"topic": "second"},
        )


def test_job_runs_progresses_and_completes_with_persistent_events(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    job, _ = repository.create(
        job_type="research-study",
        workspace_id="default",
        idempotency_key="request-0003",
        payload={"topic": "evidence"},
    )
    running = repository.start(
        job.job_id,
        worker_id="worker-001",
        lease_seconds=60,
    )
    progressed = repository.update_progress(
        job.job_id,
        worker_id="worker-001",
        progress=0.5,
    )
    completed = repository.succeed(
        job.job_id,
        worker_id="worker-001",
        result={"artifact_id": "candidate-001"},
    )

    assert running.state is JobState.RUNNING
    assert progressed.progress == 0.5
    assert completed.state is JobState.SUCCEEDED
    assert completed.progress == 1.0
    assert completed.result == {"artifact_id": "candidate-001"}
    assert [event["event_type"] for event in repository.events(job.job_id)] == [
        "CREATED",
        "STARTED",
        "FINISHED",
    ]


def test_retry_is_bounded_and_expired_lease_is_resumed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    job, _ = repository.create(
        job_type="research-study",
        workspace_id="default",
        idempotency_key="request-0004",
        payload={"topic": "retry"},
        max_attempts=2,
    )
    running = repository.start(
        job.job_id,
        worker_id="worker-001",
        lease_seconds=0.001,
    )

    recovered = repository.recover_expired(
        now=float(running.lease_expires_at) + 1.0
    )
    queued = repository.get(job.job_id)
    second_run = repository.start(
        job.job_id,
        worker_id="worker-002",
        lease_seconds=60,
    )
    failed = repository.fail(
        job.job_id,
        worker_id="worker-002",
        error_code="PROVIDER_TIMEOUT",
        error_message="Provider request timed out",
        retryable=True,
    )

    assert recovered == 1
    assert queued.state is JobState.QUEUED
    assert second_run.attempt == 2
    assert failed.state is JobState.FAILED
    with pytest.raises(JobTransitionError, match="retry"):
        repository.retry(job.job_id)


def test_cancel_is_idempotent_and_running_worker_cannot_claim_success(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    queued, _ = repository.create(
        job_type="research-study",
        workspace_id="default",
        idempotency_key="request-0005",
        payload={"topic": "cancel queued"},
    )
    canceled = repository.request_cancel(queued.job_id)
    canceled_again = repository.request_cancel(queued.job_id)
    assert canceled.state is JobState.CANCELED
    assert canceled_again.state is JobState.CANCELED

    running_job, _ = repository.create(
        job_type="research-study",
        workspace_id="default",
        idempotency_key="request-0006",
        payload={"topic": "cancel running"},
    )
    repository.start(running_job.job_id, worker_id="worker-001")
    pending_cancel = repository.request_cancel(running_job.job_id)
    final = repository.succeed(
        running_job.job_id,
        worker_id="worker-001",
        result={"claim": "must not become successful"},
    )

    assert pending_cancel.state is JobState.RUNNING
    assert pending_cancel.cancel_requested is True
    assert final.state is JobState.CANCELED


def test_persisted_payload_rejects_secret_fields(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with pytest.raises(JobValidationError, match="Secret-bearing"):
        repository.create(
            job_type="research-study",
            workspace_id="default",
            idempotency_key="request-0007",
            payload={"provider": {"api_key": "must-not-persist"}},
        )


def test_failure_message_is_redacted_before_persistence(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    job, _ = repository.create(
        job_type="research-study",
        workspace_id="default",
        idempotency_key="request-0008",
        payload={"topic": "redaction"},
        max_attempts=1,
    )
    repository.start(job.job_id, worker_id="worker-001")
    secret = "provider-secret-" + ("x" * 32)

    failed = repository.fail(
        job.job_id,
        worker_id="worker-001",
        error_code="PROVIDER_FAILURE",
        error_message=f"authorization=Bearer {secret}",
    )

    assert failed.state is JobState.FAILED
    assert secret not in str(failed.error_message)
    assert "[REDACTED]" in str(failed.error_message)
