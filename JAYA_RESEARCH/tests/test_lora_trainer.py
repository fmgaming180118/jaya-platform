"""
test_lora_trainer.py — Unit tests for Edge LoRA Training & Empirical vs Simulation Isolation.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_RESEARCH"))

from src.edge.lora_trainer import EdgeLoRATrainer, LoRATrainingConfig


class TestEdgeLoRATrainer:
    def test_empirical_lora_training(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = EdgeLoRATrainer()
            config = LoRATrainingConfig(
                model_base_id="student-base-v1",
                dataset_id="ds-empirical-01",
                output_dir=tmpdir,
                is_simulation=False,
            )

            dataset_bytes = b"EMPIRICAL_DATASET_CONTENT_SAMPLE_12345"
            res = trainer.train(config, dataset_bytes)

            assert res.status == "COMPLETED"
            assert res.is_simulation is False
            assert res.provenance_type == "EMPIRICAL_RESULT"
            assert len(res.weights_sha256) == 64
            assert os.path.exists(res.output_adapter_path)

            can_promote, reason = trainer.can_promote_to_production(res)
            assert can_promote is True
            assert "verified" in reason

    def test_simulation_lora_training_rejection(self):
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

            assert res.status == "COMPLETED"
            assert res.is_simulation is True
            assert res.provenance_type == "SIMULATION"

            # Must be rejected for production promotion
            can_promote, reason = trainer.can_promote_to_production(res)
            assert can_promote is False
            assert "SIMULATION labeled adapters are strictly forbidden" in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
