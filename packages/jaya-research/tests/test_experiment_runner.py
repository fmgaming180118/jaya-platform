from pathlib import Path

import pytest

from jaya_research.research.experiment_designer import ExperimentDesigner
from jaya_research.research.experiment_runner import ExperimentRunner
from jaya_research.research.experimental_memory import ExperimentalMemory
from jaya_research.research.hypothesis_generator import HypothesisGenerator
from jaya_research.research.learning_from_results import LearningFromResults


def _runner(tmp_path: Path) -> ExperimentRunner:
    return ExperimentRunner(
        memory=ExperimentalMemory(memory_path=tmp_path / "experimental_memory.json")
    )


def test_simulation_is_deterministic_and_never_promotable(tmp_path):
    hypothesis = HypothesisGenerator().generate_hypothesis("Distributed Computing")
    plan = ExperimentDesigner().design_experiment(
        hypothesis,
        execution_mode="SIMULATION",
    )

    first = _runner(tmp_path / "first").run_experiment(plan)
    second = _runner(tmp_path / "second").run_experiment(plan)

    assert first["status"] == "COMPLETED_SIMULATION"
    assert first["evidence_kind"] == "SIMULATION"
    assert first["promotion_eligible"] is False
    assert first["dataset_sha256"] == second["dataset_sha256"]
    assert first["metrics"] == second["metrics"]


def test_simulation_does_not_update_hypothesis_confidence(tmp_path):
    hypothesis = HypothesisGenerator().generate_hypothesis("Edge Inference")
    plan = ExperimentDesigner().design_experiment(hypothesis)
    result = _runner(tmp_path).run_experiment(plan)

    posterior, delta, recommendation, summary = (
        LearningFromResults().update_hypothesis_confidence(
            hypothesis,
            result,
            prior_confidence=0.5,
        )
    )

    assert posterior == 0.5
    assert delta == 0.0
    assert recommendation == "HOLD"
    assert "SIMULATION" in summary


def test_empirical_run_requires_provenance(tmp_path):
    hypothesis = HypothesisGenerator().generate_hypothesis("Measured Latency")
    hypothesis["observations"] = {
        "baseline": [10.0, 10.5, 9.5],
        "treatment": [8.0, 8.5, 7.5],
    }
    plan = ExperimentDesigner().design_experiment(
        hypothesis,
        execution_mode="EMPIRICAL",
    )

    result = _runner(tmp_path).run_experiment(plan)

    assert result["status"] == "INVALID_EXPERIMENT_INPUT"
    assert result["evidence_kind"] == "UNVERIFIED"
    assert result["promotion_eligible"] is False
    assert "provenance" in result["error"]


def test_reproduced_empirical_run_can_reach_review_eligibility(tmp_path):
    hypothesis = HypothesisGenerator().generate_hypothesis("Measured Throughput")
    hypothesis.update(
        {
            "observations": {
                "baseline": [1.0, 1.1, 0.9, 1.05],
                "treatment": [3.0, 3.1, 2.9, 3.05],
            },
            "provenance": {
                "source_hashes": ["sha256:source-a"],
                "license_id": "CC-BY-4.0",
                "runner_id": "runner-a",
                "environment_id": "environment-a",
            },
        }
    )
    first_plan = ExperimentDesigner().design_experiment(
        hypothesis,
        execution_mode="EMPIRICAL",
    )
    first_result = _runner(tmp_path / "first").run_experiment(first_plan)

    assert first_result["status"] == "COMPLETED_EMPIRICAL"
    assert first_result["promotion_eligible"] is False
    assert first_result["reproduction"]["reproduced"] is False

    hypothesis["observations"] = {
        "baseline": [1.2, 1.3, 1.1, 1.25],
        "treatment": [3.2, 3.3, 3.1, 3.25],
    }
    hypothesis["provenance"] = {
        "source_hashes": ["sha256:source-b"],
        "license_id": "CC-BY-4.0",
        "runner_id": "runner-b",
        "environment_id": "environment-b",
    }
    hypothesis["prior_empirical_runs"] = [first_result]
    second_plan = ExperimentDesigner().design_experiment(
        hypothesis,
        execution_mode="EMPIRICAL",
    )
    result = _runner(tmp_path / "second").run_experiment(second_plan)

    assert result["status"] == "COMPLETED_EMPIRICAL"
    assert result["evidence_kind"] == "EMPIRICAL"
    assert result["promotion_eligible"] is True
    assert result["dataset_sha256"]
    assert result["source_hashes"] == ["sha256:source-b"]
    assert result["reproduction"]["verified_prior_run_ids"] == [first_result["run_id"]]
    assert result["result_sha256"]

    posterior, delta, recommendation, _ = (
        LearningFromResults().update_hypothesis_confidence(
            hypothesis,
            result,
            prior_confidence=0.5,
        )
    )
    assert posterior > 0.5
    assert delta > 0.0
    assert recommendation == "ACCEPT_HYPOTHESIS"


def test_reproduction_boolean_without_prior_receipt_has_no_effect(tmp_path):
    hypothesis = HypothesisGenerator().generate_hypothesis("Measured Throughput")
    hypothesis.update(
        {
            "observations": {
                "baseline": [1.0, 1.1, 0.9],
                "treatment": [2.0, 2.1, 1.9],
            },
            "provenance": {
                "source_hashes": ["sha256:source-a"],
                "license_id": "CC-BY-4.0",
                "runner_id": "runner-a",
                "environment_id": "environment-a",
            },
            "reproduction": {"reproduced": True, "run_count": 99},
        }
    )

    result = _runner(tmp_path).run_experiment(
        ExperimentDesigner().design_experiment(
            hypothesis,
            execution_mode="EMPIRICAL",
        )
    )

    assert result["promotion_eligible"] is False
    assert result["reproduction"]["run_count"] == 1


def test_safety_block_returns_typed_non_evidence(tmp_path):
    result = _runner(tmp_path).run_experiment(
        {
            "experiment_id": "EXP-UNSAFE-999",
            "safety_status": "BLOCKED",
            "safety_reason": "Prohibited operation",
        }
    )

    assert result["status"] == "BLOCKED_BY_SAFETY"
    assert result["evidence_kind"] == "UNVERIFIED"
    assert result["p_value"] is None


def test_invalid_learning_prior_is_rejected():
    with pytest.raises(ValueError, match="between 0 and 1"):
        LearningFromResults().update_hypothesis_confidence(
            {},
            {},
            prior_confidence=1.5,
        )
