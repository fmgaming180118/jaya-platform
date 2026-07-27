import json
from dataclasses import replace
from pathlib import Path

import pytest

from auto_finetune import (
    AutoDatasetCollector,
    LoRAAdapterTrainer,
    run_auto_finetune_cycle,
)
from research.research_artifact import (
    ArtifactStatus,
    ArtifactValidationError,
    EvidenceKind,
    ResearchArtifactOutbox,
    build_research_artifact,
    validate_artifact_dict,
)


def _artifact(
    *,
    artifact_id: str,
    evidence_kind: EvidenceKind,
    reproduced: bool = False,
    run_count: int = 1,
):
    empirical = evidence_kind is EvidenceKind.EMPIRICAL
    return build_research_artifact(
        artifact_id=artifact_id,
        artifact_type="knowledge_candidate",
        finding_id=f"finding-{artifact_id}",
        evidence_kind=evidence_kind,
        subject="Measured system behavior",
        payload={"statement": "A measured candidate statement.", "executable": False},
        provenance={
            "source_hashes": ["a" * 64] if empirical else [],
            "dataset_sha256": "b" * 64 if empirical else "",
        },
        reproducibility={"reproduced": reproduced, "run_count": run_count},
        license_info={"id": "CC-BY-4.0" if empirical else "SYNTHETIC"},
        confidence=0.75,
    )


def test_artifact_digest_detects_tampering():
    serialized = _artifact(
        artifact_id="candidate-001",
        evidence_kind=EvidenceKind.SIMULATION,
    ).to_dict()
    validate_artifact_dict(serialized)

    serialized["payload"]["statement"] = "Tampered"
    with pytest.raises(ArtifactValidationError, match="digest"):
        validate_artifact_dict(serialized)


def test_simulation_cannot_claim_pending_review_even_with_recomputed_digest():
    artifact = _artifact(
        artifact_id="candidate-002",
        evidence_kind=EvidenceKind.SIMULATION,
    )
    forged = replace(artifact, status=ArtifactStatus.PENDING_REVIEW).to_dict()

    with pytest.raises(ArtifactValidationError, match="does not match"):
        validate_artifact_dict(forged)


def test_outbox_rejects_duplicate_artifact(tmp_path):
    outbox = ResearchArtifactOutbox(tmp_path / "outbox")
    artifact = _artifact(
        artifact_id="candidate-003",
        evidence_kind=EvidenceKind.SIMULATION,
    )

    outbox.publish(artifact)
    with pytest.raises(FileExistsError):
        outbox.publish(artifact)


def test_dataset_collector_accepts_only_review_ready_empirical_artifacts(tmp_path):
    outbox = ResearchArtifactOutbox(tmp_path / "outbox")
    outbox.publish(
        _artifact(
            artifact_id="simulation-001",
            evidence_kind=EvidenceKind.SIMULATION,
        )
    )
    outbox.publish(
        _artifact(
            artifact_id="empirical-draft-001",
            evidence_kind=EvidenceKind.EMPIRICAL,
        )
    )
    outbox.publish(
        _artifact(
            artifact_id="empirical-ready-001",
            evidence_kind=EvidenceKind.EMPIRICAL,
            reproduced=True,
            run_count=2,
        )
    )
    dataset_path = tmp_path / "dataset.jsonl"
    collector = AutoDatasetCollector(
        artifact_dir=tmp_path / "outbox",
        output_jsonl=dataset_path,
    )

    count, exported_path = collector.collect_and_export()

    assert count == 1
    assert exported_path == dataset_path.resolve()
    entry = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert entry["artifact_id"] == "empirical-ready-001"
    assert entry["evidence_kind"] == "EMPIRICAL"
    assert len(collector.rejections) == 2


def test_missing_training_backend_creates_no_adapter(tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "instruction": "Assess evidence",
                "input": "topic",
                "output": "candidate",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    adapter_dir = tmp_path / "adapters"

    result = LoRAAdapterTrainer(adapter_dir=adapter_dir).train_lora_step(dataset_path)

    assert result["success"] is False
    assert result["status"] == "BLOCKED_NO_TRAINING_BACKEND"
    assert not adapter_dir.exists()
    assert list(tmp_path.rglob("*.pt")) == []


class RealTestBackend:
    def train(
        self,
        *,
        dataset_path: Path,
        output_dir: Path,
        epochs: int,
        learning_rate: float,
    ):
        assert dataset_path.is_file()
        assert epochs == 3
        assert learning_rate == 0.001
        adapter_path = output_dir / "adapter.safetensors"
        adapter_path.write_bytes(b"real-backend-test-artifact")
        return {
            "adapter_path": str(adapter_path),
            "metrics": {"measured_eval_loss": 0.42},
        }


def test_injected_backend_artifact_is_verified_and_hashed(tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps({"instruction": "i", "input": "x", "output": "y"}) + "\n",
        encoding="utf-8",
    )
    trainer = LoRAAdapterTrainer(
        adapter_dir=tmp_path / "adapters",
        backend=RealTestBackend(),
    )

    result = trainer.train_lora_step(dataset_path)

    assert result["success"] is True
    assert result["status"] == "COMPLETED_REAL_BACKEND"
    assert len(result["adapter_sha256"]) == 64
    assert result["measured_metrics"]["measured_eval_loss"] == 0.42
    assert trainer.metadata_file.is_file()


def test_full_cycle_blocks_when_no_empirical_artifacts_exist(tmp_path):
    result = run_auto_finetune_cycle(
        artifact_dir=tmp_path / "missing-outbox",
        output_jsonl=tmp_path / "dataset.jsonl",
        adapter_dir=tmp_path / "adapters",
    )

    assert result["success"] is False
    assert result["status"] == "BLOCKED_NO_ELIGIBLE_EMPIRICAL_ARTIFACTS"
    assert list(tmp_path.rglob("*.pt")) == []
