"""Durable experiment-run index used to prevent repeated empirical failures."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ExperimentalMemoryError(RuntimeError):
    """Raised when experiment history cannot be validated or persisted."""


class ExperimentalMemory:
    """Persist experiment receipts atomically."""

    def __init__(self, memory_path: Optional[Path] = None):
        research_root = Path(__file__).resolve().parents[2]
        self.memory_path = Path(
            memory_path or research_root / "data" / "experimental_memory.json"
        ).resolve()
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.records: List[Dict[str, Any]] = []
        self._load_memory()

    def _load_memory(self) -> None:
        if not self.memory_path.exists():
            self.records = []
            return
        try:
            loaded = json.loads(self.memory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExperimentalMemoryError(
                f"Could not load experimental memory {self.memory_path}: {exc}"
            ) from exc
        if not isinstance(loaded, list) or not all(
            isinstance(record, dict) for record in loaded
        ):
            raise ExperimentalMemoryError(
                "Experimental memory root must be a list of objects"
            )
        self.records = loaded

    def save_memory(self) -> None:
        serialized = json.dumps(
            self.records,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self.memory_path.name}.",
            suffix=".tmp",
            dir=self.memory_path.parent,
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.memory_path)
        except (OSError, TypeError, ValueError) as exc:
            Path(temp_name).unlink(missing_ok=True)
            raise ExperimentalMemoryError(
                f"Could not save experimental memory: {exc}"
            ) from exc

    def compute_config_hash(self, experiment_design: Dict[str, Any]) -> str:
        """Compute a stable SHA-256 hash for a complete experiment configuration."""
        canonical = json.dumps(
            {
                "hypothesis_id": experiment_design.get("hypothesis_id", ""),
                "execution_mode": str(
                    experiment_design.get("execution_mode") or "SIMULATION"
                ),
                "variables": experiment_design.get("variables", {}),
                "provenance": experiment_design.get("provenance", {}),
                "statistical_plan": experiment_design.get("statistical_plan", {}),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def record_run(
        self,
        experiment_design: Dict[str, Any],
        run_result: Dict[str, Any],
    ) -> None:
        """Persist an experiment run summary and its immutable receipt digest."""
        config_hash = self.compute_config_hash(experiment_design)
        record = {
            "run_id": run_result.get("run_id"),
            "experiment_id": experiment_design.get("experiment_id"),
            "hypothesis_id": experiment_design.get("hypothesis_id"),
            "config_hash": config_hash,
            "status": run_result.get("status", "UNKNOWN"),
            "evidence_kind": run_result.get("evidence_kind", "UNVERIFIED"),
            "success": (
                run_result.get("status") == "COMPLETED_EMPIRICAL"
                and run_result.get("p_value") is not None
                and run_result.get("p_value", 1.0) < 0.05
            ),
            "p_value": run_result.get("p_value"),
            "dataset_sha256": run_result.get("dataset_sha256", ""),
            "result_sha256": run_result.get("result_sha256", ""),
            "reproduction": run_result.get("reproduction", {}),
            "outcome_summary": run_result.get("outcome_summary", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.records.append(record)
        self.save_memory()

    def is_failed_configuration(self, experiment_design: Dict[str, Any]) -> bool:
        """Return true only for a recorded failed empirical configuration."""
        config_hash = self.compute_config_hash(experiment_design)
        return any(
            record.get("config_hash") == config_hash
            and record.get("evidence_kind") == "EMPIRICAL"
            and not record.get("success", False)
            for record in self.records
        )

    def get_recent_runs(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return at most ``limit`` recent run records."""
        if limit < 0:
            raise ValueError("limit must be non-negative")
        return self.records[-limit:] if limit else []
