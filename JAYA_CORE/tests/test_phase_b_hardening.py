"""
test_phase_b_hardening.py — Unit tests for Phase B Production Hardening (Worker Queue, Tracing, & Backup Recovery Drill).
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

from src.memory.backup import SQLiteBackupEngine
from src.observability.tracing import TraceContext
from src.worker.job_worker import BackgroundJobWorker, JobStatus


class TestBackgroundJobWorker:
    def test_job_submission_and_successful_processing(self):
        worker = BackgroundJobWorker()
        executed_jobs = []

        def sample_handler(job):
            executed_jobs.append(job.job_id)
            return True

        worker.register_handler("INDEX_DOCUMENT", sample_handler)
        job = worker.submit_job("INDEX_DOCUMENT", {"doc_id": "doc-123"})

        assert job.status == JobStatus.QUEUED
        assert job.correlation_id.startswith("corr-")

        processed = worker.process_next_job()
        assert processed is not None
        assert processed.status == JobStatus.COMPLETED
        assert processed.job_id in executed_jobs

    def test_job_retry_backoff_and_cancellation(self):
        worker = BackgroundJobWorker()

        def failing_handler(job):
            return False

        worker.register_handler("FAILING_JOB", failing_handler)
        job = worker.submit_job("FAILING_JOB", {}, max_retries=1)

        # First run -> retry 1 -> status QUEUED
        proc1 = worker.process_next_job()
        assert proc1.status == JobStatus.QUEUED
        assert proc1.retry_count == 1

        # Second run -> retry 2 > max 1 -> status FAILED
        proc2 = worker.process_next_job()
        assert proc2.status == JobStatus.FAILED

        # Job Cancellation test
        job_to_cancel = worker.submit_job("FAILING_JOB", {})
        cancelled = worker.cancel_job(job_to_cancel.job_id)
        assert cancelled is True
        assert worker.get_job(job_to_cancel.job_id).status == JobStatus.CANCELLED


class TestTraceContext:
    def test_correlation_id_generation_and_override(self):
        TraceContext.clear()
        cid1 = TraceContext.get_correlation_id()
        assert cid1.startswith("corr-")

        TraceContext.set_correlation_id("corr-custom-999")
        assert TraceContext.get_correlation_id() == "corr-custom-999"

        TraceContext.clear()
        cid2 = TraceContext.get_correlation_id()
        assert cid2 != "corr-custom-999"


class TestSQLiteBackupAndCrashRecovery:
    def test_sqlite_backup_and_crash_recovery_drill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            active_db = os.path.join(tmpdir, "active_episodic.db")
            backup_db = os.path.join(tmpdir, "backup_episodic.db")

            # Initialize active DB with sample table
            conn = sqlite3.connect(active_db)
            conn.execute("CREATE TABLE test_events (id INTEGER PRIMARY KEY, name TEXT);")
            conn.execute("INSERT INTO test_events (name) VALUES ('event_1');")
            conn.commit()
            conn.close()

            engine = SQLiteBackupEngine()
            assert engine.verify_integrity(active_db) is True

            # Run full crash recovery drill
            success, msg = engine.run_crash_recovery_drill(active_db, backup_db)
            assert success is True
            assert "PASSED successfully" in msg
            assert engine.verify_integrity(active_db) is True
class TestCleanInstallAndRestart:
    def test_clean_install_and_restart_survival(self):
        from scripts.verify_clean_install_and_restart import run_clean_install_and_restart_verification
        res = run_clean_install_and_restart_verification()
        assert res["clean_install_status"] == "SUCCESS"
        assert res["process_restart_status"] == "SUCCESS"
        assert res["state_survival_status"] == "SUCCESS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
