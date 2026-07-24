"""
Experiment Designer Module for JAYA_RESEARCH.
Generates structured scientific experiment designs based on hypotheses,
integrating ProtocolDatabase templates and enforcing SafetyInterlock checks.
"""

import logging
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from safety_interlock import SafetyInterlock
    from protocol_database import ProtocolDatabase
except ImportError:
    from research.safety_interlock import SafetyInterlock
    from research.protocol_database import ProtocolDatabase

logger = logging.getLogger(__name__)


class ExperimentDesigner:
    """
    Autonomous Experiment Designer.
    Transforms hypotheses into actionable, controlled, and safety-verified scientific experiment plans.
    """

    def __init__(
        self,
        protocol_db: Optional[ProtocolDatabase] = None,
        safety_interlock: Optional[SafetyInterlock] = None,
    ):
        self.protocol_db = protocol_db or ProtocolDatabase()
        self.safety_interlock = safety_interlock or SafetyInterlock()

    def design_experiment(self, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transforms a hypothesis dictionary into a structured experiment design.
        """
        hyp_id = hypothesis.get("hypothesis_id", f"HYP-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        statement = hypothesis.get("statement", "Hypothesis statement under evaluation.")
        variables = hypothesis.get("variables", {})

        independent_vars = variables.get("independent", ["Treatment_Factor"])
        dependent_vars = variables.get("dependent", ["Response_Metric"])
        control_vars = variables.get("control", ["Environment_Baseline"])

        # Determine protocol template
        protocol_type = "controlled_comparison"
        if len(independent_vars) > 1:
            protocol_type = "sensitivity_analysis"

        proto_template = self.protocol_db.get_protocol(protocol_type)
        raw_steps = proto_template.get("steps", [])

        # Format concrete procedure steps
        procedure_steps = []
        for step in raw_steps:
            formatted_step = (
                step.replace("independent variable", ", ".join(independent_vars))
                .replace("dependent metric", ", ".join(dependent_vars))
            )
            procedure_steps.append(formatted_step)

        expected_outcome = f"Significant variance (> 10%) observed in {', '.join(dependent_vars)} when altering {', '.join(independent_vars)}."

        # Safety evaluation
        safety_payload = {
            "hypothesis": statement,
            "variables": variables,
            "steps": procedure_steps,
        }
        is_safe, reason, risk_score = self.safety_interlock.evaluate_safety(safety_payload)

        feasibility_score = round(max(0.1, min(0.98, 0.85 - (risk_score * 0.5))), 2)

        exp_id = f"EXP-{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999)}"

        experiment_design = {
            "experiment_id": exp_id,
            "hypothesis_id": hyp_id,
            "design_type": proto_template.get("name", "Controlled Comparison"),
            "variables": {
                "independent": independent_vars,
                "dependent": dependent_vars,
                "control": control_vars,
            },
            "procedure_steps": procedure_steps,
            "expected_outcome": expected_outcome,
            "feasibility_score": feasibility_score,
            "safety_status": "APPROVED" if is_safe else "BLOCKED",
            "safety_reason": reason,
            "timestamp": datetime.now().isoformat(),
        }

        return experiment_design
