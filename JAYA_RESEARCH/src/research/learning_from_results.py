"""Evidence-aware learning that refuses to learn from simulations."""

from __future__ import annotations

import math
from typing import Any


class LearningFromResults:
    """Update confidence only from reproducible empirical evidence."""

    def __init__(self, default_prior: float = 0.50):
        if not 0.0 <= default_prior <= 1.0:
            raise ValueError("default_prior must be between 0 and 1")
        self.default_prior = float(default_prior)

    def update_hypothesis_confidence(
        self,
        hypothesis: dict[str, Any],
        run_result: dict[str, Any],
        prior_confidence: float | None = None,
    ) -> tuple[float, float, str, str]:
        """Return a conservative update and an honest recommendation."""
        del hypothesis
        prior = (
            self.default_prior if prior_confidence is None else float(prior_confidence)
        )
        if not 0.0 <= prior <= 1.0:
            raise ValueError("prior_confidence must be between 0 and 1")

        evidence_kind = str(run_result.get("evidence_kind") or "UNVERIFIED")
        status = str(run_result.get("status") or "UNKNOWN")
        if evidence_kind != "EMPIRICAL" or status != "COMPLETED_EMPIRICAL":
            return (
                prior,
                0.0,
                "HOLD",
                f"No confidence update: {evidence_kind} result with status {status}.",
            )

        try:
            from research.experiment_runner import (
                ExperimentInputError,
                validate_experiment_result_receipt,
            )
        except ImportError:
            from .experiment_runner import (
                ExperimentInputError,
                validate_experiment_result_receipt,
            )
        try:
            validate_experiment_result_receipt(run_result)
        except ExperimentInputError as exc:
            return (
                prior,
                0.0,
                "HOLD",
                f"Empirical result receipt is invalid: {exc}.",
            )

        reproduction = run_result.get("reproduction")
        if not isinstance(reproduction, dict):
            reproduction = {}
        if (
            reproduction.get("reproduced") is not True
            or int(reproduction.get("run_count") or 0) < 2
        ):
            return (
                prior,
                0.0,
                "REPRODUCE_REQUIRED",
                "Empirical run recorded, but an independent reproduction is required.",
            )

        p_value = float(run_result.get("p_value"))
        metrics = run_result.get("metrics")
        if (
            not math.isfinite(p_value)
            or not 0.0 <= p_value <= 1.0
            or not isinstance(metrics, dict)
        ):
            return prior, 0.0, "HOLD", "Invalid empirical statistics."

        effect_size = float(metrics.get("effect_size_cohen_d") or 0.0)
        if not math.isfinite(effect_size):
            return prior, 0.0, "HOLD", "Invalid empirical effect size."

        alpha = 0.05
        if p_value < alpha and effect_size > 0:
            strength = min(1.0, (1.0 - (p_value / alpha)) * min(effect_size, 2.0))
            posterior = min(0.99, prior + ((1.0 - prior) * 0.5 * strength))
            recommendation = "ACCEPT_HYPOTHESIS"
            summary = (
                "Reproduced empirical evidence supports the expected positive effect; "
                f"p={p_value:.6g}, Cohen d={effect_size:.6g}."
            )
        elif p_value < alpha and effect_size < 0:
            strength = min(1.0, (1.0 - (p_value / alpha)) * min(abs(effect_size), 2.0))
            posterior = max(0.01, prior - (prior * 0.5 * strength))
            recommendation = "REJECT_HYPOTHESIS"
            summary = (
                "Reproduced empirical evidence shows a significant opposite effect; "
                f"p={p_value:.6g}, Cohen d={effect_size:.6g}."
            )
        else:
            posterior = prior
            recommendation = "REFINE_EXPERIMENT"
            summary = (
                "Reproduced result is inconclusive at alpha=0.05; "
                f"p={p_value:.6g}, Cohen d={effect_size:.6g}."
            )

        posterior = round(posterior, 6)
        delta = round(posterior - prior, 6)
        return posterior, delta, recommendation, summary
