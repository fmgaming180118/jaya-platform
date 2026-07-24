"""
Experimental Memory Module for JAYA_RESEARCH.
Persists outcomes of experimental trials to prevent repeating failed configurations
and to provide context for learning loops.
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ExperimentalMemory:
    """
    Stores history of executed experiments and failed parameter combinations.
    """

    def __init__(self, memory_path: Optional[Path] = None):
        if memory_path is None:
            self.memory_path = Path("data/experimental_memory.json")
        else:
            self.memory_path = Path(memory_path)

        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.records: List[Dict[str, Any]] = []
        self._load_memory()

    def _load_memory(self):
        if self.memory_path.exists():
            try:
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    self.records = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load experimental memory: {e}")
                self.records = []
        else:
            self.records = []

    def save_memory(self):
        try:
            with open(self.memory_path, "w", encoding="utf-8") as f:
                json.dump(self.records, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving experimental memory: {e}")

    def compute_config_hash(self, experiment_design: Dict[str, Any]) -> str:
        """Computes a unique MD5 hash for an experiment configuration."""
        hyp_id = experiment_design.get("hypothesis_id", "")
        vars_info = json.dumps(experiment_design.get("variables", {}), sort_keys=True)
        raw_str = f"{hyp_id}:{vars_info}"
        return hashlib.md5(raw_str.encode("utf-8")).hexdigest()

    def record_run(self, experiment_design: Dict[str, Any], run_result: Dict[str, Any]):
        """Records an experiment execution run."""
        config_hash = self.compute_config_hash(experiment_design)
        record = {
            "run_id": run_result.get("run_id"),
            "experiment_id": experiment_design.get("experiment_id"),
            "hypothesis_id": experiment_design.get("hypothesis_id"),
            "config_hash": config_hash,
            "status": run_result.get("status", "UNKNOWN"),
            "success": run_result.get("status") == "COMPLETED" and run_result.get("p_value", 1.0) < 0.05,
            "p_value": run_result.get("p_value", 1.0),
            "outcome_summary": run_result.get("outcome_summary", ""),
            "timestamp": datetime.now().isoformat(),
        }
        self.records.append(record)
        self.save_memory()

    def is_failed_configuration(self, experiment_design: Dict[str, Any]) -> bool:
        """Checks if identical configuration previously failed."""
        config_hash = self.compute_config_hash(experiment_design)
        for rec in self.records:
            if rec.get("config_hash") == config_hash and not rec.get("success", False):
                return True
        return False

    def get_recent_runs(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Returns the N most recent experimental runs."""
        return self.records[-limit:]
