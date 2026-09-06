"""Controlled empirical and explicitly labelled simulation experiment runner."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import random
import statistics
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from experimental_memory import ExperimentalMemory
    from safety_interlock import SafetyInterlock
except ImportError:
    from jaya_research.research.experimental_memory import ExperimentalMemory
    from jaya_research.research.safety_interlock import SafetyInterlock


logger = logging.getLogger(__name__)


class ExperimentInputError(ValueError):
    """Raised when an experiment lacks valid observations or provenance."""


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_experiment_result_receipt(result: dict[str, Any]) -> None:
    """Validate the immutable digest of a completed experiment result."""
    supplied_digest = str(result.get("result_sha256") or "")
    unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
    expected_digest = _canonical_sha256(unsigned)
    if not supplied_digest or not hmac.compare_digest(
        supplied_digest,
        expected_digest,
    ):
        raise ExperimentInputError("Experiment result digest mismatch")
    if result.get("status") not in {
        "COMPLETED_EMPIRICAL",
        "COMPLETED_SIMULATION",
    }:
        raise ExperimentInputError("Prior result is not a completed experiment")


def _finite_values(values: Any, field_name: str) -> list[float]:
    if not isinstance(values, list) or len(values) < 2:
        raise ExperimentInputError(f"{field_name} requires at least 2 observations")
    normalized: list[float] = []
    for value in values:
        if isinstance(value, bool):
            raise ExperimentInputError(f"{field_name} contains a boolean")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ExperimentInputError(
                f"{field_name} contains a non-numeric observation"
            ) from exc
        if not math.isfinite(numeric):
            raise ExperimentInputError(f"{field_name} contains a non-finite value")
        normalized.append(numeric)
    return normalized


def _welch_statistics(
    baseline: list[float],
    treatment: list[float],
) -> tuple[float, float, float]:
    """Return p-value, effect size, and mean delta using Welch's t-test."""
    baseline_mean = statistics.fmean(baseline)
    treatment_mean = statistics.fmean(treatment)
    baseline_variance = statistics.variance(baseline)
    treatment_variance = statistics.variance(treatment)
    denominator = math.sqrt(
        (baseline_variance / len(baseline)) + (treatment_variance / len(treatment))
    )
    t_value = (
        0.0 if denominator == 0 else (treatment_mean - baseline_mean) / denominator
    )

    try:
        from scipy.stats import ttest_ind

        scipy_result = ttest_ind(
            treatment,
            baseline,
            equal_var=False,
            nan_policy="raise",
        )
        p_value = float(scipy_result.pvalue)
    except ImportError:
        # Conservative two-sided normal approximation when SciPy is unavailable.
        p_value = math.erfc(abs(t_value) / math.sqrt(2.0))

    pooled_denominator = len(baseline) + len(treatment) - 2
    pooled_variance = (
        ((len(baseline) - 1) * baseline_variance)
        + ((len(treatment) - 1) * treatment_variance)
    ) / pooled_denominator
    pooled_std = math.sqrt(max(pooled_variance, 0.0))
    effect_size = (
        0.0 if pooled_std == 0 else (treatment_mean - baseline_mean) / pooled_std
    )
    return p_value, effect_size, treatment_mean - baseline_mean


def _assess_reproduction(
    *,
    current_result: dict[str, Any],
    prior_runs: Any,
    tolerance: float,
) -> dict[str, Any]:
    """Verify independent prior empirical receipts against the current result."""
    if not 0.0 <= tolerance <= 1.0 or not math.isfinite(tolerance):
        raise ExperimentInputError("reproduction_tolerance must be between 0 and 1")
    if not isinstance(prior_runs, list):
        raise ExperimentInputError("prior_empirical_runs must be a list")

    verified_run_ids: list[str] = []
    rejection_reasons: list[str] = []
    current_metrics = dict(current_result["metrics"])
    current_delta = float(current_metrics["mean_delta"])
    for prior in prior_runs:
        if not isinstance(prior, dict):
            rejection_reasons.append("prior run is not an object")
            continue
        try:
            validate_experiment_result_receipt(prior)
        except ExperimentInputError as exc:
            rejection_reasons.append(str(exc))
            continue
        if (
            prior.get("evidence_kind") != "EMPIRICAL"
            or prior.get("status") != "COMPLETED_EMPIRICAL"
        ):
            rejection_reasons.append("prior run is not empirical")
            continue
        if prior.get("hypothesis_id") != current_result.get("hypothesis_id"):
            rejection_reasons.append("prior run belongs to another hypothesis")
            continue
        if prior.get("method") != current_result.get("method"):
            rejection_reasons.append("prior run used another method")
            continue
        if prior.get("dataset_sha256") == current_result.get("dataset_sha256"):
            rejection_reasons.append("prior run reused the same dataset")
            continue
        if prior.get("runner_identity") == current_result.get("runner_identity"):
            rejection_reasons.append("prior run reused the same runner identity")
            continue
        if prior.get("environment_id") == current_result.get("environment_id"):
            rejection_reasons.append("prior run reused the same environment")
            continue

        prior_metrics = prior.get("metrics")
        if not isinstance(prior_metrics, dict):
            rejection_reasons.append("prior run metrics are missing")
            continue
        try:
            prior_delta = float(prior_metrics["mean_delta"])
        except (KeyError, TypeError, ValueError):
            rejection_reasons.append("prior run mean delta is invalid")
            continue
        if not math.isfinite(prior_delta):
            rejection_reasons.append("prior run mean delta is non-finite")
            continue
        same_direction = (
            current_delta == 0.0 and prior_delta == 0.0
        ) or current_delta * prior_delta > 0.0
        scale = max(abs(current_delta), abs(prior_delta), 1e-12)
        relative_difference = abs(current_delta - prior_delta) / scale
        if not same_direction or relative_difference > tolerance:
            rejection_reasons.append(
                "prior run effect is outside the reproduction tolerance"
            )
            continue
        verified_run_ids.append(str(prior.get("run_id") or "unknown"))

    return {
        "reproduced": bool(verified_run_ids),
        "run_count": 1 + len(verified_run_ids),
        "verified_prior_run_ids": verified_run_ids,
        "tolerance": tolerance,
        "rejection_reasons": rejection_reasons,
    }


class ExperimentRunner:
    """Runs measured observations or an explicitly labelled deterministic simulation."""

    def __init__(
        self,
        memory: ExperimentalMemory | None = None,
        safety_interlock: SafetyInterlock | None = None,
    ):
        self.memory = memory or ExperimentalMemory()
        self.safety_interlock = safety_interlock or SafetyInterlock()

    def _simulation_observations(
        self,
        experiment_design: dict[str, Any],
    ) -> tuple[list[float], list[float], int]:
        seed_value = experiment_design.get("simulation_seed")
        if seed_value is None:
            seed_value = int(_canonical_sha256(experiment_design)[:16], 16)
        try:
            seed = int(seed_value)
        except (TypeError, ValueError) as exc:
            raise ExperimentInputError("simulation_seed must be an integer") from exc

        sample_size = int(experiment_design.get("simulation_sample_size") or 30)
        if not 2 <= sample_size <= 10_000:
            raise ExperimentInputError(
                "simulation_sample_size must be between 2 and 10000"
            )
        effect = float(experiment_design.get("simulation_effect") or 0.0)
        noise = float(experiment_design.get("simulation_noise") or 1.0)
        if not math.isfinite(effect) or not math.isfinite(noise) or noise <= 0:
            raise ExperimentInputError("simulation effect/noise is invalid")

        rng = random.Random(seed)
        baseline = [rng.gauss(0.0, noise) for _ in range(sample_size)]
        treatment = [rng.gauss(effect, noise) for _ in range(sample_size)]
        return baseline, treatment, seed

    def run_experiment(self, experiment_design: dict[str, Any]) -> dict[str, Any]:
        """Execute one trial without ever disguising synthetic data as empirical."""
        experiment_id = str(experiment_design.get("experiment_id") or "EXP-UNKNOWN")
        hypothesis_id = str(experiment_design.get("hypothesis_id") or "HYP-UNKNOWN")
        run_id = f"RUN-{uuid.uuid4().hex}"
        safety_status = str(experiment_design.get("safety_status") or "UNKNOWN")
        if safety_status != "APPROVED":
            return {
                "run_id": run_id,
                "experiment_id": experiment_id,
                "status": "BLOCKED_BY_SAFETY",
                "evidence_kind": "UNVERIFIED",
                "promotion_eligible": False,
                "p_value": None,
                "outcome_summary": (
                    "Execution blocked: "
                    + str(
                        experiment_design.get("safety_reason")
                        or "Safety approval is missing"
                    )
                ),
            }

        if self.memory.is_failed_configuration(experiment_design):
            return {
                "run_id": run_id,
                "experiment_id": experiment_id,
                "status": "SKIPPED_DUPLICATE_FAILURE",
                "evidence_kind": "UNVERIFIED",
                "promotion_eligible": False,
                "p_value": None,
                "outcome_summary": "Identical empirical configuration already failed.",
            }

        execution_mode = str(
            experiment_design.get("execution_mode") or "SIMULATION"
        ).upper()
        try:
            if execution_mode == "EMPIRICAL":
                observations = experiment_design.get("observations")
                if not isinstance(observations, dict):
                    raise ExperimentInputError(
                        "EMPIRICAL mode requires an observations mapping"
                    )
                baseline = _finite_values(
                    observations.get("baseline"), "observations.baseline"
                )
                treatment = _finite_values(
                    observations.get("treatment"), "observations.treatment"
                )
                provenance = experiment_design.get("provenance")
                if not isinstance(provenance, dict):
                    raise ExperimentInputError(
                        "EMPIRICAL mode requires provenance metadata"
                    )
                source_hashes = provenance.get("source_hashes")
                license_id = str(provenance.get("license_id") or "").strip()
                runner_identity = str(provenance.get("runner_id") or "").strip()
                environment_id = str(provenance.get("environment_id") or "").strip()
                if not isinstance(source_hashes, list) or not source_hashes:
                    raise ExperimentInputError(
                        "EMPIRICAL provenance requires source_hashes"
                    )
                if not license_id:
                    raise ExperimentInputError(
                        "EMPIRICAL provenance requires license_id"
                    )
                if not runner_identity:
                    raise ExperimentInputError(
                        "EMPIRICAL provenance requires runner_id"
                    )
                if not environment_id:
                    raise ExperimentInputError(
                        "EMPIRICAL provenance requires environment_id"
                    )
                dataset_sha256 = _canonical_sha256(observations)
                evidence_kind = "EMPIRICAL"
                status = "COMPLETED_EMPIRICAL"
                simulation_seed = None
            elif execution_mode == "SIMULATION":
                baseline, treatment, simulation_seed = self._simulation_observations(
                    experiment_design
                )
                provenance = {
                    "source_hashes": [],
                    "license_id": "SYNTHETIC",
                }
                dataset_sha256 = _canonical_sha256(
                    {"baseline": baseline, "treatment": treatment}
                )
                evidence_kind = "SIMULATION"
                status = "COMPLETED_SIMULATION"
                runner_identity = "JAYA_DETERMINISTIC_SIMULATOR"
                environment_id = f"simulation-seed:{simulation_seed}"
            else:
                raise ExperimentInputError(
                    "execution_mode must be EMPIRICAL or SIMULATION"
                )

            p_value, effect_size, mean_delta = _welch_statistics(
                baseline,
                treatment,
            )
        except (ExperimentInputError, ValueError, OverflowError) as exc:
            result = {
                "run_id": run_id,
                "experiment_id": experiment_id,
                "status": "INVALID_EXPERIMENT_INPUT",
                "evidence_kind": "UNVERIFIED",
                "promotion_eligible": False,
                "p_value": None,
                "error": str(exc),
                "outcome_summary": f"Experiment input rejected: {exc}",
            }
            self.memory.record_run(experiment_design, result)
            return result

        result = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "hypothesis_id": hypothesis_id,
            "status": status,
            "evidence_kind": evidence_kind,
            "p_value": round(float(p_value), 8),
            "metrics": {
                "baseline_mean": statistics.fmean(baseline),
                "treatment_mean": statistics.fmean(treatment),
                "mean_delta": mean_delta,
                "effect_size_cohen_d": effect_size,
                "baseline_n": len(baseline),
                "treatment_n": len(treatment),
            },
            "raw_observations": {
                "baseline": baseline,
                "treatment": treatment,
            },
            "dataset_sha256": dataset_sha256,
            "experiment_config_sha256": _canonical_sha256(experiment_design),
            "source_hashes": list(provenance.get("source_hashes") or []),
            "license": {"id": str(provenance.get("license_id") or "")},
            "runner_identity": runner_identity,
            "environment_id": environment_id,
            "simulation_seed": simulation_seed,
            "method": "welch_t_test_two_sided",
            "statistical_plan": dict(experiment_design.get("statistical_plan") or {}),
            "outcome_summary": (
                f"{evidence_kind} comparison completed; "
                f"mean delta={mean_delta:.6g}, Cohen d={effect_size:.6g}, "
                f"p={p_value:.6g}."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if evidence_kind == "EMPIRICAL":
            try:
                reproduction = _assess_reproduction(
                    current_result=result,
                    prior_runs=experiment_design.get("prior_empirical_runs") or [],
                    tolerance=float(
                        experiment_design.get("reproduction_tolerance") or 0.25
                    ),
                )
            except (ExperimentInputError, TypeError, ValueError) as exc:
                invalid_result = {
                    "run_id": run_id,
                    "experiment_id": experiment_id,
                    "hypothesis_id": hypothesis_id,
                    "status": "INVALID_EXPERIMENT_INPUT",
                    "evidence_kind": "UNVERIFIED",
                    "promotion_eligible": False,
                    "p_value": None,
                    "error": str(exc),
                    "outcome_summary": f"Reproduction input rejected: {exc}",
                }
                self.memory.record_run(experiment_design, invalid_result)
                return invalid_result
        else:
            reproduction = {
                "reproduced": False,
                "run_count": 1,
                "verified_prior_run_ids": [],
                "tolerance": None,
                "rejection_reasons": [
                    "Simulation cannot satisfy empirical reproduction"
                ],
            }
        result["reproduction"] = reproduction
        result["promotion_eligible"] = (
            evidence_kind == "EMPIRICAL"
            and reproduction["reproduced"] is True
            and reproduction["run_count"] >= 2
        )
        result["result_sha256"] = _canonical_sha256(result)
        self.memory.record_run(experiment_design, result)
        return result
