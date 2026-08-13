"""Evidence-gated dataset collection and real-backend LoRA orchestration.

JAYA_RESEARCH prepares reviewable training data. It does not fabricate adapter
weights or training metrics. A caller must inject an actual training backend;
otherwise the operation returns a fail-closed ``BLOCKED_NO_TRAINING_BACKEND``
status and creates no adapter.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Tuple

from research.research_artifact import (
    ArtifactStatus,
    ArtifactValidationError,
    EvidenceKind,
    validate_artifact_dict,
)

MAX_ADAPTER_BYTES = 30 * 1024 * 1024


class LoRATrainingBackend(Protocol):
    """Interface implemented by an actual PEFT/LoRA training integration."""

    def train(
        self,
        *,
        dataset_path: Path,
        output_dir: Path,
        epochs: int,
        learning_rate: float,
    ) -> Mapping[str, Any]:
        """Train an adapter and return its path plus measured metrics."""


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


class AutoDatasetCollector:
    """Build SFT JSONL only from immutable, review-ready empirical artifacts."""

    def __init__(
        self,
        artifact_dir: Optional[Path] = None,
        output_jsonl: Optional[Path] = None,
    ):
        research_root = Path(__file__).resolve().parent.parent
        self.artifact_dir = (
            artifact_dir or research_root / "data" / "artifact_outbox"
        ).resolve()
        self.output_jsonl = (
            output_jsonl or research_root / "data" / "auto_sft_dataset.jsonl"
        ).resolve()
        self.rejections: list[dict[str, str]] = []

    @staticmethod
    def _to_training_entry(artifact: Mapping[str, Any]) -> dict[str, Any]:
        payload = artifact.get("payload")
        if not isinstance(payload, Mapping):
            raise ArtifactValidationError("Artifact payload must be an object")

        proposal = str(
            payload.get("proposal_text")
            or payload.get("statement")
            or payload.get("summary")
            or ""
        ).strip()
        if not proposal:
            raise ArtifactValidationError("Artifact has no textual research output")

        return {
            "instruction": (
                "Assess the supplied empirical research candidate while preserving "
                "its evidence limitations and provenance."
            ),
            "input": str(artifact["subject"]),
            "output": proposal,
            "artifact_id": str(artifact["artifact_id"]),
            "finding_id": str(artifact["finding_id"]),
            "evidence_kind": str(artifact["evidence_kind"]),
            "artifact_status": str(artifact["status"]),
            "content_sha256": str(artifact["content_sha256"]),
            "provenance": artifact.get("provenance", {}),
            "license": artifact.get("license", {}),
        }

    def collect_and_export(self) -> Tuple[int, Path]:
        """Validate artifacts and atomically export eligible training examples."""
        self.rejections.clear()
        entries: list[dict[str, Any]] = []

        if self.artifact_dir.is_dir():
            for artifact_path in sorted(self.artifact_dir.glob("*.json")):
                try:
                    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                    if not isinstance(artifact, dict):
                        raise ArtifactValidationError("Artifact root must be an object")
                    validate_artifact_dict(artifact)
                    if artifact.get("evidence_kind") != EvidenceKind.EMPIRICAL.value:
                        raise ArtifactValidationError(
                            "Only empirical artifacts may enter training data"
                        )
                    if artifact.get("status") != ArtifactStatus.PENDING_REVIEW.value:
                        raise ArtifactValidationError(
                            "Artifact has not reached PENDING_REVIEW"
                        )
                    entries.append(self._to_training_entry(artifact))
                except (
                    ArtifactValidationError,
                    json.JSONDecodeError,
                    KeyError,
                    OSError,
                    TypeError,
                ) as exc:
                    self.rejections.append(
                        {"file": artifact_path.name, "reason": str(exc)}
                    )

        serialized = "".join(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
            for entry in entries
        )
        _atomic_write_text(self.output_jsonl, serialized)
        return len(entries), self.output_jsonl


class LoRAAdapterTrainer:
    """Invoke an injected real trainer and verify its resulting adapter artifact."""

    def __init__(
        self,
        adapter_dir: Optional[Path] = None,
        backend: Optional[LoRATrainingBackend] = None,
    ):
        research_root = Path(__file__).resolve().parent.parent
        self.adapter_dir = (
            adapter_dir or research_root / "data" / "adapters"
        ).resolve()
        self.backend = backend
        self.metadata_file = self.adapter_dir / "adapter_metadata.json"

    @staticmethod
    def _load_dataset(dataset_path: Path) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        with dataset_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid dataset JSON at line {line_number}"
                    ) from exc
                if not isinstance(entry, dict):
                    raise ValueError(
                        f"Dataset entry at line {line_number} must be an object"
                    )
                entries.append(entry)
        return entries

    def train_lora_step(
        self, dataset_path: Path, epochs: int = 3, lr: float = 0.001
    ) -> dict[str, Any]:
        """Run real training or return an explicit blocked/failure receipt."""
        dataset_path = Path(dataset_path).resolve()
        if not dataset_path.is_file():
            return {
                "success": False,
                "status": "BLOCKED_DATASET_MISSING",
                "error": f"Dataset file does not exist: {dataset_path}",
            }
        if epochs < 1:
            return {
                "success": False,
                "status": "BLOCKED_INVALID_CONFIGURATION",
                "error": "epochs must be at least 1",
            }
        if not 0.0 < lr <= 1.0:
            return {
                "success": False,
                "status": "BLOCKED_INVALID_CONFIGURATION",
                "error": "learning rate must be greater than 0 and at most 1",
            }

        try:
            entries = self._load_dataset(dataset_path)
        except (OSError, ValueError) as exc:
            return {
                "success": False,
                "status": "BLOCKED_INVALID_DATASET",
                "error": str(exc),
            }
        if not entries:
            return {
                "success": False,
                "status": "BLOCKED_EMPTY_DATASET",
                "error": "Dataset contains no eligible examples",
            }
        if self.backend is None:
            return {
                "success": False,
                "status": "BLOCKED_NO_TRAINING_BACKEND",
                "error": "Inject a real LoRATrainingBackend; no adapter was created.",
                "total_samples": len(entries),
            }

        self.adapter_dir.mkdir(parents=True, exist_ok=True)
        try:
            backend_result = dict(
                self.backend.train(
                    dataset_path=dataset_path,
                    output_dir=self.adapter_dir,
                    epochs=epochs,
                    learning_rate=lr,
                )
            )
        except Exception as exc:  # Backend failures need an actionable receipt.
            return {
                "success": False,
                "status": "TRAINING_BACKEND_FAILED",
                "error": f"{type(exc).__name__}: {exc}",
                "total_samples": len(entries),
            }

        adapter_value = backend_result.get("adapter_path")
        if not isinstance(adapter_value, (str, os.PathLike)):
            return {
                "success": False,
                "status": "TRAINING_RESULT_INVALID",
                "error": "Backend did not return adapter_path",
            }
        adapter_path = Path(adapter_value).resolve()
        try:
            adapter_path.relative_to(self.adapter_dir)
        except ValueError:
            return {
                "success": False,
                "status": "TRAINING_RESULT_INVALID",
                "error": "Backend adapter_path is outside the configured adapter directory",
            }
        if not adapter_path.is_file():
            return {
                "success": False,
                "status": "TRAINING_RESULT_INVALID",
                "error": "Backend adapter artifact does not exist",
            }

        adapter_size = adapter_path.stat().st_size
        if adapter_size > MAX_ADAPTER_BYTES:
            return {
                "success": False,
                "status": "TRAINING_RESULT_REJECTED",
                "error": "Adapter exceeds the configured 30 MiB limit",
                "adapter_size_bytes": adapter_size,
            }

        adapter_sha256 = hashlib.sha256(adapter_path.read_bytes()).hexdigest()
        metrics = backend_result.get("metrics")
        if not isinstance(metrics, Mapping):
            metrics = {}
        metadata = {
            "status": "COMPLETED_REAL_BACKEND",
            "backend": type(self.backend).__name__,
            "adapter_path": str(adapter_path),
            "adapter_size_bytes": adapter_size,
            "adapter_sha256": adapter_sha256,
            "total_samples": len(entries),
            "epochs": epochs,
            "learning_rate": lr,
            "measured_metrics": dict(metrics),
        }
        _atomic_write_text(
            self.metadata_file,
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
        )
        return {"success": True, **metadata}


def run_auto_finetune_cycle(
    *,
    backend: Optional[LoRATrainingBackend] = None,
    artifact_dir: Optional[Path] = None,
    output_jsonl: Optional[Path] = None,
    adapter_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Prepare evidence-gated data and optionally invoke a real backend."""
    collector = AutoDatasetCollector(
        artifact_dir=artifact_dir, output_jsonl=output_jsonl
    )
    count, dataset_path = collector.collect_and_export()
    if count == 0:
        return {
            "success": False,
            "status": "BLOCKED_NO_ELIGIBLE_EMPIRICAL_ARTIFACTS",
            "artifacts_processed": 0,
            "dataset_path": str(dataset_path),
            "rejections": collector.rejections,
        }

    training_result = LoRAAdapterTrainer(
        adapter_dir=adapter_dir, backend=backend
    ).train_lora_step(dataset_path, epochs=3)
    return {
        "success": training_result.get("success", False),
        "status": training_result.get("status", "UNKNOWN"),
        "artifacts_processed": count,
        "dataset_path": str(dataset_path),
        "rejections": collector.rejections,
        "training_result": training_result,
    }


if __name__ == "__main__":
    print(json.dumps(run_auto_finetune_cycle(), indent=2))
