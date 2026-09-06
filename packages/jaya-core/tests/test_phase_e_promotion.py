"""
test_phase_e_promotion.py — Unit tests for Phase E Safe Ecosystem Promotion (Unified Multi-Gate, Replay Protection, Candidate Benchmark, & Revocation).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "packages" / "jaya-core" / "src"))

from jaya_core.artifacts.candidate_benchmark import CleanCandidateBenchmarkEngine
from jaya_core.artifacts.unified_promotion_gate import ReplayProtectionEngine, UnifiedPromotionGate


class TestUnifiedPromotionGate:
    def test_candidate_passes_all_7_promotion_gates(self):
        gate = UnifiedPromotionGate()
        cand_id = "cand-prod-100"
        candidate_dict = {
            "artifact_id": cand_id,
            "status": "CANDIDATE",
            "executable": False,
            "auto_install": False,
        }

        res = gate.evaluate_candidate(
            candidate_id=cand_id,
            candidate_dict=candidate_dict,
            signature="valid_sig_sha256",
            nonce="nonce-unique-001",
            timestamp=time.time(),
            human_approved=True,
            approved_by="master-identity-owner",
            license_name="Apache-2.0",
            ram_delta_mb=10.0,
            init_time_ms=50.0,
            error_rate=0.0,
        )

        assert res.is_approved is True
        assert len(res.passed_gates) == 7
        assert res.failed_gate is None

    def test_rejection_of_unapproved_or_executable_candidate(self):
        gate = UnifiedPromotionGate()

        # Missing human approval
        res_no_approval = gate.evaluate_candidate(
            candidate_id="cand-no-app",
            candidate_dict={"artifact_id": "cand-no-app", "status": "CANDIDATE"},
            signature="sig",
            nonce="nonce-002",
            timestamp=time.time(),
            human_approved=False,
            approved_by="",
        )
        assert res_no_approval.is_approved is False
        assert res_no_approval.failed_gate == "HUMAN_APPROVAL_GATE"

        # Executable=True candidate
        res_exec = gate.evaluate_candidate(
            candidate_id="cand-exec",
            candidate_dict={"artifact_id": "cand-exec", "status": "CANDIDATE", "executable": True},
            signature="sig",
            nonce="nonce-003",
            timestamp=time.time(),
            human_approved=True,
            approved_by="owner",
        )
        assert res_exec.is_approved is False
        assert res_exec.failed_gate == "CANDIDATE_BOUNDARY_GATE"


class TestReplayProtectionEngine:
    def test_replay_protection_blocks_duplicate_nonce_and_stale_timestamp(self):
        engine = ReplayProtectionEngine(max_age_sec=10.0)

        # Valid nonce
        ok, _ = engine.is_valid_nonce("nonce-111", time.time(), "hash-111")
        assert ok is True

        # Replayed nonce -> REJECT
        ok_dup, msg_dup = engine.is_valid_nonce("nonce-111", time.time(), "hash-222")
        assert ok_dup is False
        assert "Replay attack" in msg_dup

        # Stale timestamp -> REJECT
        ok_stale, msg_stale = engine.is_valid_nonce("nonce-333", time.time() - 20.0, "hash-333")
        assert ok_stale is False
        assert "stale" in msg_stale


class TestCandidateBenchmarkEngine:
    def test_clean_candidate_benchmark_metrics(self):
        bench = CleanCandidateBenchmarkEngine(max_ram_delta_mb=30.0, max_init_ms=200.0, max_error_rate=0.01)
        candidate = {"artifact_id": "cand-bench-1"}

        metrics = bench.evaluate_candidate_performance(candidate, simulated_error_rate=0.005)
        assert metrics.is_passed is True
        assert metrics.ram_delta_mb <= 30.0
        assert metrics.init_time_ms <= 200.0

        # Oversized error rate benchmark
        metrics_fail = bench.evaluate_candidate_performance(candidate, simulated_error_rate=0.05)
        assert metrics_fail.is_passed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
