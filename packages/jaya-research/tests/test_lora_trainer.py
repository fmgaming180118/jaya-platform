"""
test_lora_trainer.py — Unit tests for Edge LoRA Training Prototype.

STATUS: Tests updated to verify PROTOTYPE behavior (NOT real training).

These tests verify that EdgeLoRATrainer correctly reports its prototype status
and does NOT claim to perform real LoRA training.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "packages" / "jaya-research" / "src"))

from jaya_research.edge.lora_trainer import EdgeLoRATrainer, LoRATrainingConfig


class TestEdgeLoRATrainer:
    def test_prototype_lora_training_returns_not_implemented(self):
        """Verify prototype returns NOT_IMPLEMENTED status (not COMPLETED)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = EdgeLoRATrainer()
            config = LoRATrainingConfig(
                model_base_id="student-base-v1",
                dataset_id="ds-empirical-01",
                output_dir=tmpdir,
                is_simulation=False,  # Even with is_simulation=False, it's still prototype
            )

            dataset_bytes = b"EMPIRICAL_DATASET_CONTENT_SAMPLE_12345"
            res = trainer.train(config, dataset_bytes)

            # PROTOTYPE: Should return NOT_IMPLEMENTED, not COMPLETED
            assert res.status == "NOT_IMPLEMENTED"
            assert res.is_simulation is True  # Prototype always marks as simulation
            assert res.provenance_type == "NOT_IMPLEMENTED"
            assert len(res.weights_sha256) == 64
            assert os.path.exists(res.output_adapter_path)
            assert "not implemented" in res.error_message.lower()

            # Must NOT be promotable to production
            can_promote, reason = trainer.can_promote_to_production(res)
            assert can_promote is False
            assert "not implemented" in reason.lower() or "prototype" in reason.lower()

    def test_prototype_simulation_lora_training_rejection(self):
        """Verify prototype correctly rejects simulation for production."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = EdgeLoRATrainer()
            config = LoRATrainingConfig(
                model_base_id="student-base-v1",
                dataset_id="ds-simulated-01",
                output_dir=tmpdir,
                is_simulation=True,
            )

            dataset_bytes = b"SIMULATED_SYNTHETIC_DATASET_CONTENT"
            res = trainer.train(config, dataset_bytes)

            # PROTOTYPE: Returns NOT_IMPLEMENTED
            assert res.status == "NOT_IMPLEMENTED"
            assert res.is_simulation is True
            assert res.provenance_type == "NOT_IMPLEMENTED"

            # Must be rejected for production promotion
            can_promote, reason = trainer.can_promote_to_production(res)
            assert can_promote is False
            assert "not implemented" in reason.lower() or "prototype" in reason.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
