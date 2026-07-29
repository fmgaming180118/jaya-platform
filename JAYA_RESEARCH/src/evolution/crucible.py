"""Review-only Crucible candidate exporter.

Crucible previously executed model-generated Python and described its stdout as
empirical proof.  Until an audited isolated runner is available, it only emits
immutable ``SIMULATION_ONLY`` candidates through the Research outbox.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from evolution.sandbox import EvolutionSandbox

_SAFE_WORKSPACE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
MAX_REQUESTED_TIMEOUT_SECONDS = 300


class Crucible:
    """Stage simulation code without executing or evaluating it."""

    def __init__(
        self,
        workspace_id: str = "default",
        *,
        source_root: str | Path | None = None,
        outbox_dir: str | Path | None = None,
    ) -> None:
        if not re.fullmatch(_SAFE_WORKSPACE_ID_PATTERN, workspace_id):
            raise ValueError("Invalid Crucible workspace_id")
        self.workspace_id = workspace_id
        self.sandbox = EvolutionSandbox(
            source_root=source_root,
            outbox_dir=outbox_dir,
        )

    def get_experiment_dir(self, exp_id: str) -> Path:
        """Return the historic logical path without creating it."""
        if not re.fullmatch(_SAFE_WORKSPACE_ID_PATTERN, exp_id):
            raise ValueError("Invalid experiment id")
        return Path("data") / "crucible" / self.workspace_id / exp_id

    def run_experiment(
        self,
        hypothesis: str,
        python_code: str,
        timeout_seconds: int = 60,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Export a simulation candidate and report that it was not run."""
        if not hypothesis.strip():
            return False, "CANDIDATE_REJECTED: hypothesis is required", {}
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= MAX_REQUESTED_TIMEOUT_SECONDS
        ):
            return (
                False,
                "CANDIDATE_REJECTED: timeout must be a bounded integer "
                f"between 1 and {MAX_REQUESTED_TIMEOUT_SECONDS}",
                {},
            )

        receipt = self.sandbox.run_code(
            python_code,
            timeout=timeout_seconds,
            candidate_name=f"crucible_{self.workspace_id}.py",
        )
        if receipt.get("status") != "SIMULATION_CANDIDATE_EXPORTED":
            return (
                False,
                f"{receipt.get('status', 'CANDIDATE_REJECTED')}: "
                f"{receipt.get('error', 'candidate rejected')}",
                receipt,
            )

        result = {
            **receipt,
            "hypothesis_status": "UNVERIFIED",
            "novelty_status": "NOT_ASSESSED",
            "benchmark_status": "NOT_RUN",
            "empirical_metrics": None,
            "workspace_id": self.workspace_id,
        }
        return (
            False,
            "SIMULATION_CANDIDATE_EXPORTED: execution blocked pending an "
            "audited isolated runner",
            result,
        )
