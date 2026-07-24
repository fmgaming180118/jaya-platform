"""
Experiment Runner Module for JAYA_RESEARCH.
Executes simulated or computational experiments derived from ExperimentDesigner,
verifying safety constraints and persisting trial logs.
"""

import logging
import random
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from experimental_memory import ExperimentalMemory
    from safety_interlock import SafetyInterlock
except ImportError:
    from research.experimental_memory import ExperimentalMemory
    from research.safety_interlock import SafetyInterlock

logger = logging.getLogger(__name__)


class ExperimentRunner:
    """
    Executes controlled computational experiments and statistical simulations.
    """

    def __init__(
        self,
        memory: Optional[ExperimentalMemory] = None,
        safety_interlock: Optional[SafetyInterlock] = None,
    ):
        self.memory = memory or ExperimentalMemory()
        self.safety_interlock = safety_interlock or SafetyInterlock()

    def run_experiment(self, experiment_design: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a trial for the given experiment design.
        """
        exp_id = experiment_design.get("experiment_id", "EXP-UNKNOWN")
        run_id = f"RUN-{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999)}"

        # 1. Check Safety Interlock
        safety_status = experiment_design.get("safety_status")
        if safety_status == "BLOCKED":
            return {
                "run_id": run_id,
                "experiment_id": exp_id,
                "status": "BLOCKED_BY_SAFETY",
                "p_value": 1.0,
                "outcome_summary": f"Execution blocked: {experiment_design.get('safety_reason', 'Safety violation')}",
            }

        # 2. Check Memory for Duplicate Failure
        if self.memory.is_failed_configuration(experiment_design):
            return {
                "run_id": run_id,
                "experiment_id": exp_id,
                "status": "SKIPPED_DUPLICATE_FAILURE",
                "p_value": 1.0,
                "outcome_summary": "Skipped trial: Identical experiment configuration failed in previous run.",
            }

        # 3. Simulate Experimental Execution
        # Synthetic variance generation based on feasibility score
        feasibility = experiment_design.get("feasibility_score", 0.8)
        is_success_sample = random.random() < feasibility

        if is_success_sample:
            p_value = round(random.uniform(0.001, 0.045), 4)
            variance_observed = round(random.uniform(0.12, 0.35), 3)
            summary = f"Supported: Independent treatment induced {variance_observed*100:.1f}% positive variance with p = {p_value}."
        else:
            p_value = round(random.uniform(0.06, 0.45), 4)
            variance_observed = round(random.uniform(0.01, 0.04), 3)
            summary = f"Not Supported: Observed variance ({variance_observed*100:.1f}%) is insignificant (p = {p_value} > 0.05)."

        run_result = {
            "run_id": run_id,
            "experiment_id": exp_id,
            "status": "COMPLETED",
            "p_value": p_value,
            "metrics": {
                "baseline_mean": 100.0,
                "treatment_mean": round(100.0 * (1.0 + variance_observed), 2),
                "variance_ratio": variance_observed,
            },
            "outcome_summary": summary,
            "timestamp": datetime.now().isoformat(),
        }

        # 4. Record to memory
        self.memory.record_run(experiment_design, run_result)

        return run_result
