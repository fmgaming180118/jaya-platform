"""
test_scientific_discovery.py — Unit tests for Scientific & Engineering Discovery Pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_RESEARCH"))

from src.discovery.contracts import (
    DiscoveryArtifactType,
    FeasibilityStatus,
    ScientificHypothesis,
)
from src.discovery.falsification_engine import PhysicsFalsificationEngine
from src.discovery.requirement_engine import FictionToRequirementTranslator


class TestFictionToRequirementTranslator:
    def test_translate_arc_reactor_fiction(self):
        translator = FictionToRequirementTranslator()
        req = translator.translate("Arc Reactor", "Reaktor portabel berdaya tinggi untuk zirah Tony Stark")

        assert req.concept_name == "Arc Reactor"
        assert req.feasibility_status == FeasibilityStatus.UNFEASIBLE_WITH_KNOWN_PHYSICS
        assert "max_diameter_cm" in req.target_specifications
        assert len(req.primary_blockers) >= 3
        assert len(req.researchable_subproblems) >= 3
        assert any("confinement" in b.lower() for b in req.primary_blockers)
        assert any("superconductor" in s.lower() or "hts" in s.lower() for s in req.researchable_subproblems)

    def test_translate_generic_engineering_concept(self):
        translator = FictionToRequirementTranslator()
        req = translator.translate("Sistem Pendingin Mikrokanal", "Pendingin untuk chip server tinggi")

        assert req.concept_name == "Sistem Pendingin Mikrokanal"
        assert req.feasibility_status == FeasibilityStatus.REQUIRES_FURTHER_SIMULATION


class TestPhysicsFalsificationEngine:
    def test_falsify_compact_fusion_tokamak_hypothesis(self):
        engine = PhysicsFalsificationEngine()
        hyp = ScientificHypothesis(
            hypothesis_id="hyp-fusion-mini-01",
            title="Miniature Tokamak Chest Reactor",
            statement="Tokamak 12cm yang menghasilkan 10MW continuous power",
            domain="plasma_fusion",
            governing_equations=["n * T * tau_E >= 3e21"],
        )

        specs = {"max_diameter_cm": 12.0, "continuous_power_mw": 10.0, "peak_power_mw": 100.0, "max_surface_temp_c": 40.0}
        res = engine.evaluate_hypothesis(hyp, specs)

        assert res.is_falsified is True
        assert "Lawson Criterion for Fusion Ignition" in res.violating_laws
        assert "Thermodynamic Heat Dissipation Limit" in res.violating_laws

        artifact = engine.export_artifact(hyp, res)
        assert artifact.artifact_type == DiscoveryArtifactType.REJECTED_HYPOTHESIS
        assert artifact.status == "REJECTED_HYPOTHESIS"
        assert "GAGAL UJI FALSIFIKASI" in artifact.summary

    def test_feasible_hypothesis_exports_discovery_candidate(self):
        engine = PhysicsFalsificationEngine()
        hyp = ScientificHypothesis(
            hypothesis_id="hyp-hts-magnet-01",
            title="Geometri Magnet HTS Kompak Terkoordinasi",
            statement="Konfigurasi lilitan pita YBCO untuk medan magnet 20 Tesla",
            domain="applied_superconductivity",
        )

        specs = {"max_diameter_cm": 40.0, "continuous_power_mw": 0.05}
        res = engine.evaluate_hypothesis(hyp, specs)

        assert res.is_falsified is False
        assert len(res.violating_laws) == 0

        artifact = engine.export_artifact(hyp, res)
        assert artifact.artifact_type == DiscoveryArtifactType.DISCOVERY_CANDIDATE
        assert artifact.status == "CANDIDATE"
        assert "LOLOS UJI FALSIFIKASI" in artifact.summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
