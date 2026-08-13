"""
test_empirical_discovery.py — Unit tests for Phase D Empirical Discovery (Experiment Store, Stats, Scientific Writer, & Ethics Gate).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_RESEARCH"))

from src.discovery.ethics_gate import EthicsCheckRequest, EthicsLicensePrivacyGate
from src.discovery.experiment_store import EmpiricalExperimentStore, ExperimentRun
from src.discovery.scientific_writer import EvidenceGatedScientificWriter, UnverifiedEvidenceError


class TestEmpiricalExperimentStore:
    def test_record_run_and_statistical_analysis(self):
        store = EmpiricalExperimentStore()
        run1 = ExperimentRun(
            run_id="run-exp-01",
            hypothesis_id="hyp-tokamak-01",
            dataset_hash="hash_abc123",
            seed=42,
            config={"magnetic_field_t": 5.5},
            environment_info={"os": "linux", "python": "3.12"},
            method="FEA_SIMULATION",
            stop_rule="max_iterations=1000",
            raw_results=[1.2, 1.4, 1.3, 1.5, 1.35],
        )
        store.record_run(run1)

        # Compute statistical analysis with Bonferroni correction for 5 tests
        stats = store.compute_statistics("hyp-tokamak-01", run1.raw_results, num_tests=5)
        assert stats.sample_size == 5
        assert stats.mean == 1.35
        assert stats.effect_size_cohen_d > 0.0
        assert stats.adjusted_p_value_bonferroni >= stats.raw_p_value

    def test_independent_reproduction_gate(self):
        store = EmpiricalExperimentStore()

        orig_run = ExperimentRun(
            run_id="run-orig-100",
            hypothesis_id="hyp-01",
            dataset_hash="dataset_sha256_xyz",
            seed=42,
            config={},
            environment_info={},
            method="test_method",
            stop_rule="stop",
            raw_results=[10.0, 10.2, 10.1],
            is_reproduction_run=False,
        )

        repro_run = ExperimentRun(
            run_id="run-repro-100",
            hypothesis_id="hyp-01",
            dataset_hash="dataset_sha256_xyz",
            seed=99,
            config={},
            environment_info={},
            method="test_method",
            stop_rule="stop",
            raw_results=[10.05, 10.15, 10.08],
            is_reproduction_run=True,
            reproduction_of_run_id="run-orig-100",
        )

        store.record_run(orig_run)
        store.record_run(repro_run)

        is_reproduced, msg = store.verify_independent_reproduction("run-orig-100", "run-repro-100")
        assert is_reproduced is True
        assert "VERIFIED" in msg


class TestEvidenceGatedScientificWriter:
    def test_writer_with_valid_evidence(self):
        writer = EvidenceGatedScientificWriter()
        evidence = [
            {"evidence_id": "ev-001", "provenance_type": "SOURCE_EVIDENCE"},
            {"evidence_id": "ev-002", "provenance_type": "EMPIRICAL_RESULT"},
        ]

        report = writer.generate_report("hyp-01", "Compact Fusion Analysis", evidence)
        assert report.status == "VERIFIED_DRAFT"
        assert len(report.evidence_references) == 2

    def test_writer_abstention_and_rejection_on_unverified_evidence(self):
        writer = EvidenceGatedScientificWriter()

        # Empty evidence -> ABSTAINED
        abstain_report = writer.generate_report("hyp-02", "No Evidence Report", [])
        assert abstain_report.status == "ABSTAINED"

        # Invalid provenance type -> Raises UnverifiedEvidenceError
        bad_evidence = [{"evidence_id": "ev-fake", "provenance_type": "UNVERIFIED_INFERENCE"}]
        with pytest.raises(UnverifiedEvidenceError):
            writer.generate_report("hyp-03", "Fake Evidence Report", bad_evidence)


class TestEthicsLicensePrivacyGate:
    def test_ethics_gate_pass(self):
        gate = EthicsLicensePrivacyGate(max_gpu_hours=24.0, max_cost_usd=100.0)
        req = EthicsCheckRequest(
            artifact_id="art-01",
            license_name="Apache-2.0",
            is_ethical_cleared=True,
            text_content="Scientific analysis of plasma stability in tokamak fusion.",
            estimated_gpu_hours=2.5,
            estimated_cost_usd=15.0,
        )

        is_passed, violations = gate.evaluate(req)
        assert is_passed is True
        assert len(violations) == 0

    def test_ethics_gate_violations(self):
        gate = EthicsLicensePrivacyGate(max_gpu_hours=24.0, max_cost_usd=100.0)
        req_bad = EthicsCheckRequest(
            artifact_id="art-bad",
            license_name="RESTRICTIVE_COMMERCIAL",
            is_ethical_cleared=False,
            text_content="User credit_card CVV details leak.",
            estimated_gpu_hours=50.0,
            estimated_cost_usd=300.0,
        )

        is_passed, violations = gate.evaluate(req_bad)
        assert is_passed is False
        assert len(violations) == 5  # Ethics, License, PII, GPU hours, Cost
        assert any("License" in v for v in violations)
        assert any("PII" in v for v in violations)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
