"""Structured experiment design with explicit evidence requirements."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from safety_interlock import SafetyInterlock
    from protocol_database import ProtocolDatabase
except ImportError:
    from jaya_research.research.safety_interlock import SafetyInterlock
    from jaya_research.research.protocol_database import ProtocolDatabase


class ExperimentDesigner:
    """Transform a hypothesis into a bounded empirical or simulation plan."""

    def __init__(
        self,
        protocol_db: ProtocolDatabase | None = None,
        safety_interlock: SafetyInterlock | None = None,
    ):
        self.protocol_db = protocol_db or ProtocolDatabase()
        self.safety_interlock = safety_interlock or SafetyInterlock()

    def design_experiment(
        self,
        hypothesis: dict[str, Any],
        *,
        execution_mode: str | None = None,
    ) -> dict[str, Any]:
        """Create a plan; no data means an explicitly labelled simulation."""
        hypothesis_id = str(
            hypothesis.get("hypothesis_id") or f"HYP-{uuid.uuid4().hex}"
        )
        statement = str(
            hypothesis.get("statement") or "Hypothesis statement under evaluation."
        )
        variables = dict(hypothesis.get("variables") or {})
        independent = list(variables.get("independent") or ["Treatment_Factor"])
        dependent = list(variables.get("dependent") or ["Response_Metric"])
        control = list(variables.get("control") or ["Environment_Baseline"])

        protocol_type = (
            "sensitivity_analysis" if len(independent) > 1 else "controlled_comparison"
        )
        protocol = self.protocol_db.get_protocol(protocol_type)
        steps = [
            str(step)
            .replace("independent variable", ", ".join(independent))
            .replace("dependent metric", ", ".join(dependent))
            for step in protocol.get("steps", [])
        ]
        safety_payload = {
            "hypothesis": statement,
            "variables": variables,
            "steps": steps,
        }
        is_safe, reason, risk_score = self.safety_interlock.evaluate_safety(
            safety_payload
        )

        requested_mode = str(
            execution_mode
            or hypothesis.get("execution_mode")
            or ("EMPIRICAL" if hypothesis.get("observations") else "SIMULATION")
        ).upper()
        if requested_mode not in {"EMPIRICAL", "SIMULATION"}:
            raise ValueError("execution_mode must be EMPIRICAL or SIMULATION")

        seed_material = json.dumps(
            {
                "hypothesis_id": hypothesis_id,
                "statement": statement,
                "variables": variables,
            },
            sort_keys=True,
        )
        deterministic_seed = int(
            hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16],
            16,
        )
        plan = {
            "experiment_id": f"EXP-{uuid.uuid4().hex}",
            "hypothesis_id": hypothesis_id,
            "design_type": protocol.get("name", "Controlled Comparison"),
            "execution_mode": requested_mode,
            "evidence_kind": requested_mode,
            "variables": {
                "independent": independent,
                "dependent": dependent,
                "control": control,
            },
            "procedure_steps": steps,
            "expected_outcome": (
                f"Measure the effect of {', '.join(independent)} on "
                f"{', '.join(dependent)} without assuming significance."
            ),
            "feasibility_score": round(
                max(0.0, min(1.0, 1.0 - float(risk_score))),
                3,
            ),
            "safety_status": "APPROVED" if is_safe else "BLOCKED",
            "safety_reason": reason,
            "simulation_seed": deterministic_seed,
            "simulation_effect": float(hypothesis.get("simulation_effect") or 0.0),
            "observations": hypothesis.get("observations"),
            "provenance": dict(hypothesis.get("provenance") or {}),
            "prior_empirical_runs": list(hypothesis.get("prior_empirical_runs") or []),
            "reproduction_tolerance": float(
                hypothesis.get("reproduction_tolerance") or 0.25
            ),
            "statistical_plan": {
                "method": "welch_t_test_two_sided",
                "alpha": 0.05,
                "effect_size": "cohen_d",
                "multiplicity_correction": (
                    "not_applicable_single_preregistered_primary_test"
                ),
                "minimum_observations_per_group": 2,
                "independent_reproduction_required": True,
                "stop_rule": "fixed_sample_size_without_optional_peeking",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return plan
