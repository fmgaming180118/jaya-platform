"""Persistent experiment memory for the digital twin.

Stores experiment outcomes as JSON lines so the twin can learn from
previous runs, even across restarts.
"""
import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

MEM_PATH = os.path.join(os.path.dirname(__file__), "experiments.jsonl")


@dataclass
class ExperimentRecord:
    timestamp: float
    code: str
    outcome: Dict[str, Any]  # variables returned by exec
    score: float             # higher is better; 0 if unknown
    label: str = "UNKNOWN"   # OPTIMIZE / EXPLORE / REPAIR / ERROR


class ExperimentMemory:
    """Lightweight append-only experiment log backed by a JSONL file.

    Parameters
    ----------
    path:
        Location of the JSONL persistence file.  Defaults to a file
        next to this module.  Ignored when *in_memory* is ``True``.
    in_memory:
        When ``True`` the instance is ephemeral — nothing is loaded
        from or written to disk.  Useful for unit tests and sandboxed
        experiments.
    """

    def __init__(self, path: str = MEM_PATH, in_memory: bool = False):
        self._in_memory = in_memory
        self.path = path if not in_memory else ""
        self._cache: List[ExperimentRecord] = []
        if not in_memory:
            self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, code: str, outcome: Dict[str, Any],
               score: float = 0.0, label: str = "EXPLORE") -> ExperimentRecord:
        """Save an experiment result to memory."""
        rec = ExperimentRecord(
            timestamp=time.time(),
            code=code,
            outcome=outcome,
            score=score,
            label=label,
        )
        self._cache.append(rec)
        self._append(rec)
        return rec

    def recent(self, n: int = 10) -> List[ExperimentRecord]:
        """Return the *n* most recent records."""
        return self._cache[-n:]

    def best(self, n: int = 5) -> List[ExperimentRecord]:
        """Return top-*n* records by score."""
        return sorted(self._cache, key=lambda r: r.score, reverse=True)[:n]

    def failed(self, n: int = 5) -> List[ExperimentRecord]:
        """Return most recent records labelled ERROR."""
        errs = [r for r in self._cache if r.label == "ERROR"]
        return errs[-n:]

    @property
    def records(self) -> List[ExperimentRecord]:
        """Public read-only view of the internal cache."""
        return self._cache

    def summary(self) -> Dict[str, Any]:
        total: int = len(self._cache)
        errors: int = sum(1 for r in self._cache if r.label == "ERROR")
        avg_score: float = (sum(r.score for r in self._cache) / total) if total else 0.0
        return {"total": total, "errors": errors, "avg_score": round(avg_score, 4)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        self._cache.append(ExperimentRecord(**data))
        except Exception:
            pass  # corrupted log — start fresh

    def _append(self, rec: ExperimentRecord):
        if self._in_memory:
            return
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(rec)) + "\n")
        except Exception:
            pass
