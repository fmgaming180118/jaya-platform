"""
Learning From Results Module for JAYA_RESEARCH.
Performs Bayesian Confidence Updates on hypotheses based on experimental outcome data,
calculating delta confidence and recommendation for iteration.
"""

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


class LearningFromResults:
    """
    Bayesian Learning Engine.
    Updates hypothesis confidence score using empirical experiment evidence.
    """

    def __init__(self, default_prior: float = 0.50):
        self.default_prior = default_prior

    def update_hypothesis_confidence(
        self,
        hypothesis: Dict[str, Any],
        run_result: Dict[str, Any],
        prior_confidence: float = 0.50,
    ) -> Tuple[float, float, str, str]:
        """
        Calculates posterior confidence using Bayesian update formula.
        Returns: (posterior_confidence, delta_confidence, recommendation, analysis_summary)
        """
        p_val = run_result.get("p_value", 1.0)
        status = run_result.get("status", "UNKNOWN")

        if status != "COMPLETED":
            return (
                prior_confidence,
                0.0,
                "HOLD",
                f"No Bayesian update applied because experiment status is '{status}'.",
            )

        # Likelihood calculation: P(Data | Hypothesis is True)
        if p_val < 0.01:
            likelihood_true = 0.92
            likelihood_false = 0.05
        elif p_val < 0.05:
            likelihood_true = 0.80
            likelihood_false = 0.15
        elif p_val < 0.10:
            likelihood_true = 0.55
            likelihood_false = 0.40
        else:
            likelihood_true = 0.20
            likelihood_false = 0.70

        # Bayes Theorem: P(H|D) = (P(D|H) * P(H)) / [P(D|H)*P(H) + P(D|~H)*(1-P(H))]
        num = likelihood_true * prior_confidence
        den = num + (likelihood_false * (1.0 - prior_confidence))

        posterior = round(num / den, 3) if den > 0 else prior_confidence
        delta_confidence = round(posterior - prior_confidence, 3)

        if posterior >= 0.75:
            recommendation = "ACCEPT_HYPOTHESIS"
            summary = f"Strong empirical support (Posterior: {posterior}, Delta: +{delta_confidence}). Hypothesis is validated."
        elif posterior <= 0.25:
            recommendation = "REJECT_HYPOTHESIS"
            summary = f"Hypothesis rejected (Posterior: {posterior}, Delta: {delta_confidence}). Empirical evidence refutes statement."
        else:
            recommendation = "REFINE_EXPERIMENT"
            summary = f"Inconclusive evidence (Posterior: {posterior}, Delta: {delta_confidence}). Recommend refining variables."

        return posterior, delta_confidence, recommendation, summary
