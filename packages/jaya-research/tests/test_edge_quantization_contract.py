"""
test_edge_quantization_contract.py — Unit tests for Student Dataset Spec & GGUF Quantization Contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "packages" / "jaya-research" / "src"))

from jaya_research.edge.dataset_spec import StudentDatasetSpec, StudentDatasetValidator
from jaya_research.edge.quantizer_contract import GGUFQuantizationContract, ModelQuantizationMetrics


class TestEdgeQuantizationContract:
    def test_student_dataset_validator(self):
        validator = StudentDatasetValidator()
        valid_spec = StudentDatasetSpec(
            dataset_id="ds-student-v1",
            name="JAYA Multilingual Distillation Dataset",
            version="1.0",
            license_name="Apache-2.0",
            sample_count=5000,
            provenance_uri="https://jaya-research.org/datasets/student-v1",
            is_legal_cleared=True,
        )

        is_valid, reasons = validator.validate_spec(valid_spec)
        assert is_valid is True
        assert len(reasons) == 0

        # Invalid spec test
        invalid_spec = StudentDatasetSpec(
            dataset_id="ds-invalid",
            name="Uncleared Dataset",
            version="1.0",
            license_name="PROPRIETARY_UNAUTHENTICATED",
            sample_count=10,
            provenance_uri="",
            is_legal_cleared=False,
        )
        is_valid_inv, reasons_inv = validator.validate_spec(invalid_spec)
        assert is_valid_inv is False
        assert len(reasons_inv) >= 3

    def test_gguf_quantization_contract_compliance(self):
        contract = GGUFQuantizationContract(
            max_size_mb=300.0,
            max_ram_mb=512.0,
            max_latency_ms=500.0,
            max_temp_c=45.0,
        )

        # Compliant model metrics
        compliant_metrics = ModelQuantizationMetrics(
            model_id="student-q4-v1",
            quant_type="Q4_K_M",
            size_mb=280.0,
            ram_usage_mb=420.0,
            avg_latency_ms=120.0,
            peak_surface_temp_c=38.5,
        )
        res1 = contract.evaluate(compliant_metrics)
        assert res1.is_compliant is True
        assert len(res1.violations) == 0

        # Non-compliant model metrics (size 350MB, RAM 600MB, temp 48°C)
        non_compliant_metrics = ModelQuantizationMetrics(
            model_id="heavy-quant-model",
            quant_type="Q5_K_M",
            size_mb=350.0,
            ram_usage_mb=600.0,
            avg_latency_ms=650.0,
            peak_surface_temp_c=48.0,
        )
        res2 = contract.evaluate(non_compliant_metrics)
        assert res2.is_compliant is False
        assert len(res2.violations) == 4
        assert any("size" in v for v in res2.violations)
        assert any("RAM" in v for v in res2.violations)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
