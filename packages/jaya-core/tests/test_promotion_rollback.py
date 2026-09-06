"""
test_promotion_rollback.py — Unit tests for Cognitive Promotion Engine & Automated Rollback Drill.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "packages" / "jaya-core" / "src"))

from jaya_core.artifacts.candidate_gate import CandidateArtifact, CandidateStatus, CognitiveArtifactGate
from jaya_core.artifacts.promotion_engine import CognitivePromotionEngine, PromotionStatus


class TestCognitivePromotionEngine:
    def test_stage_valid_canary_candidate(self):
        engine = CognitivePromotionEngine()
        cand = CandidateArtifact(
            artifact_id="art-cand-01",
            artifact_type="REASONING_STRATEGY",
            target_system="JAYA_CORE",
            provenance={"source": "arxiv", "paper_id": "2401.12345"},
            payload={"strategy": "tree_of_thought"},
            evidence_kind="EMPIRICAL_BENCHMARK",
            executable=False,
            auto_install=False,
            human_review_required=True,
            rollback_info={"rollback_supported": True, "rollback_strategy": "checkpoint"},
        )

        rec = engine.stage_canary(cand, canary_nodes=["node-canary-01"])
        assert rec.status == PromotionStatus.CANARY_STAGED
        assert rec.canary_node_ids == ["node-canary-01"]

    def test_automated_rollback_on_high_error_rate(self):
        engine = CognitivePromotionEngine()
        cand = CandidateArtifact(
            artifact_id="art-cand-02",
            artifact_type="REASONING_STRATEGY",
            target_system="JAYA_CORE",
            provenance={"source": "arxiv"},
            payload={"strategy": "experimental"},
            evidence_kind="EMPIRICAL_BENCHMARK",
            rollback_info={"rollback_supported": True},
        )

        engine.stage_canary(cand, canary_nodes=["node-canary-01"])
        rec = engine.report_canary_metrics("art-cand-02", error_rate=0.12, max_allowed_error_rate=0.05)

        assert rec.status == PromotionStatus.ROLLED_BACK
        assert rec.rollback_performed is True
        assert any("AUTOMATED ROLLBACK TRIGGERED" in h for h in rec.history)

    def test_promotion_requires_human_approval(self):
        engine = CognitivePromotionEngine()
        cand = CandidateArtifact(
            artifact_id="art-cand-03",
            artifact_type="MEMORY_STRATEGY",
            target_system="JAYA_CORE",
            provenance={"source": "arxiv"},
            payload={"strategy": "lru_eviction"},
            evidence_kind="EMPIRICAL_BENCHMARK",
            rollback_info={"rollback_supported": True},
        )

        engine.stage_canary(cand, canary_nodes=["node-canary-01"])
        rec_obs = engine.report_canary_metrics("art-cand-03", error_rate=0.01)
        assert rec_obs.status == PromotionStatus.OBSERVING

        # Promotion without human approval is rejected
        rec_no_app = engine.promote("art-cand-03", human_approved=False)
        assert rec_no_app.status == PromotionStatus.REJECTED

        # Stage again & promote with human approval
        engine.stage_canary(cand, canary_nodes=["node-canary-01"])
        rec_app = engine.promote("art-cand-03", human_approved=True)
        assert rec_app.status == PromotionStatus.PROMOTED
        assert rec_app.human_approved is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
