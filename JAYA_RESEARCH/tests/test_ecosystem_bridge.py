"""
test_ecosystem_bridge.py — Integration test for JAYA_RESEARCH & JAYA_CORE Ecosystem Bridge
"""

import os
import sys
import pytest

# Ensure sys.path contains workspace root and JAYA_RESEARCH
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESEARCH_DIR = os.path.join(ROOT_DIR, "JAYA_RESEARCH")
CORE_DIR = os.path.join(ROOT_DIR, "JAYA_CORE")

for d in [ROOT_DIR, RESEARCH_DIR, CORE_DIR]:
    if os.path.exists(d) and d not in sys.path:
        sys.path.insert(0, d)

from JAYA_RESEARCH.src.research.ecosystem_bridge import ResearchEcosystemBridge, ResearchFinding
from src.brain_v2.engine.evolution_gate import EvolutionGate, EvolutionCandidate


def test_research_finding_conversion():
    """Test converting a research finding into a JAYA_CORE EvolutionCandidate."""
    finding = ResearchFinding(
        finding_id="find-001",
        paper_title="Autonomous Quantized Attention Optimization",
        authors=["JAYA Academic Agent"],
        topic="attention_sparsity",
        gap_summary="Dynamic top-k attention reduces memory footprint by 15%",
        suggested_patch_type="sparsity_patch",
        patch_code="def optimized_sparsity(x): return x * 0.85",
        confidence_score=0.96
    )

    bridge = ResearchEcosystemBridge()
    candidate = bridge.convert_finding_to_candidate(finding)

    assert isinstance(candidate, EvolutionCandidate)
    assert candidate.candidate_id == "candidate-find-001"
    assert candidate.metadata["author"] == "JAYA_RESEARCH_AUTONOMOUS"
    assert candidate.metadata["patch_type"] == "sparsity_patch"


def test_submit_research_upgrade_end_to_end():
    """Test end-to-end flow: JAYA_RESEARCH finding -> ResearchEcosystemBridge -> JAYA_CORE EvolutionGate."""
    finding = ResearchFinding(
        finding_id="find-002",
        paper_title="Morphic Kernel Safety Enhancement",
        authors=["JAYA Research Agent"],
        topic="zero_trust_governance",
        gap_summary="Zero-trust cryptographic verification gate enhancement",
        suggested_patch_type="governance_patch",
        patch_code="def verify_kernel(): return True",
        confidence_score=0.99
    )

    bridge = ResearchEcosystemBridge()
    result = bridge.submit_research_upgrade(finding)

    assert isinstance(result, dict)
    assert result["finding_id"] == "find-002"
    assert result["candidate_id"] == "candidate-find-002"
    assert "gate_passed" in result
    assert len(bridge.get_submission_history()) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
