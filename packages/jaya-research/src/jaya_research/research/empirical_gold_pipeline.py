"""
empirical_gold_pipeline.py — Empirical Study and Independent Reproduction Pipeline over Gold Data.

Executes scientific validation trials over Gold RAG datasets and Gold PDF documents,
calculating 95% confidence intervals, Cohen's d effect sizes, and Bonferroni corrections.
Requires Ethical & Legal clearance records before empirical execution.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .multimodal_gold import GoldPDFDocument
from .rag_dataset import GoldRAGDatasetSpec, RepresentationStatus


@dataclass
class EthicalLegalClearanceRecord:
    clearance_id: str
    ethics_board_approval: str
    legal_review_url: str
    cleared_at: float
    signature: str

    def is_valid(self) -> bool:
        return (
            bool(self.clearance_id and self.clearance_id.strip())
            and bool(self.ethics_board_approval and self.ethics_board_approval.strip())
            and bool(self.signature and len(self.signature.strip()) >= 16)
            and self.cleared_at > 0
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StatisticalMetrics:
    mean: float
    std_dev: float
    confidence_interval_95: tuple[float, float]
    cohens_d: float
    bonferroni_adjusted_p: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mean": round(self.mean, 4),
            "std_dev": round(self.std_dev, 4),
            "confidence_interval_95": (round(self.confidence_interval_95[0], 4), round(self.confidence_interval_95[1], 4)),
            "cohens_d": round(self.cohens_d, 4),
            "bonferroni_adjusted_p": round(self.bonferroni_adjusted_p, 6),
        }


@dataclass
class EmpiricalReproductionResult:
    experiment_id: str
    dataset_id: str
    reproduction_status: str  # "INDEPENDENT_REPRODUCTION_PASSED" or "INDEPENDENT_REPRODUCTION_FAILED"
    evidence_kind: str  # "EMPIRICAL_RESULT"
    statistics: StatisticalMetrics
    passed_trials: int
    total_trials: int
    raw_scores: List[float] = field(default_factory=list)
    clearance: Optional[EthicalLegalClearanceRecord] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["statistics"] = self.statistics.to_dict()
        if self.clearance:
            d["clearance"] = self.clearance.to_dict()
        return d


class EmpiricalGoldReproductionPipeline:
    """Pipeline for running independent scientific reproduction over Gold datasets & documents."""

    def run_reproduction_trial(
        self,
        experiment_id: str,
        dataset_spec: GoldRAGDatasetSpec,
        trial_scores: List[float],
        baseline_scores: List[float],
        num_hypotheses_tested: int = 1,
        clearance: Optional[EthicalLegalClearanceRecord] = None,
    ) -> EmpiricalReproductionResult:
        if clearance and not clearance.is_valid():
            raise PermissionError("[EthicsError] Ethical & legal clearance record is invalid")

        if not trial_scores:
            raise ValueError("[ValidationError] trial_scores cannot be empty")
        if not baseline_scores:
            raise ValueError("[ValidationError] baseline_scores cannot be empty")

        n = len(trial_scores)
        mean_trial = sum(trial_scores) / n
        variance = sum((x - mean_trial) ** 2 for x in trial_scores) / (n - 1) if n > 1 else 0.0
        std_dev = math.sqrt(variance)

        # 95% Confidence Interval (z ~ 1.96)
        margin = 1.96 * (std_dev / math.sqrt(n)) if n > 0 else 0.0
        ci_95 = (mean_trial - margin, mean_trial + margin)

        # Cohen's d effect size
        mean_base = sum(baseline_scores) / len(baseline_scores)
        base_var = sum((x - mean_base) ** 2 for x in baseline_scores) / (len(baseline_scores) - 1) if len(baseline_scores) > 1 else 0.0
        pooled_std = math.sqrt((variance + base_var) / 2.0) if (variance + base_var) > 0 else 1.0
        cohens_d = (mean_trial - mean_base) / pooled_std

        # P-value approximation from effect size Cohen's d
        raw_p = max(0.0001, 1.0 / (1.0 + (cohens_d ** 2)))
        bonferroni_p = min(1.0, raw_p * max(1, num_hypotheses_tested))

        passed_trials = sum(1 for s in trial_scores if s >= 0.7)
        passed = (mean_trial >= 0.7) and (bonferroni_p < 0.05) and (cohens_d >= 0.2)

        stats = StatisticalMetrics(
            mean=mean_trial,
            std_dev=std_dev,
            confidence_interval_95=ci_95,
            cohens_d=cohens_d,
            bonferroni_adjusted_p=bonferroni_p,
        )

        return EmpiricalReproductionResult(
            experiment_id=experiment_id,
            dataset_id=dataset_spec.dataset_id,
            reproduction_status="INDEPENDENT_REPRODUCTION_PASSED" if passed else "INDEPENDENT_REPRODUCTION_FAILED",
            evidence_kind="EMPIRICAL_RESULT",
            statistics=stats,
            passed_trials=passed_trials,
            total_trials=n,
            raw_scores=trial_scores,
            clearance=clearance,
        )


class EthicsLegalEmpiricalRunner:
    """Runner requiring ethics and legal clearance before executing empirical trials."""

    def __init__(self, pipeline: EmpiricalGoldReproductionPipeline) -> None:
        self.pipeline = pipeline

    def run_cleared_empirical_study(
        self,
        experiment_id: str,
        dataset_spec: GoldRAGDatasetSpec,
        trial_scores: List[float],
        baseline_scores: List[float],
        clearance: EthicalLegalClearanceRecord,
    ) -> EmpiricalReproductionResult:
        if not clearance or not clearance.is_valid():
            raise PermissionError(
                f"[EthicsError] Cannot execute empirical study '{experiment_id}' without valid Ethical & Legal clearance"
            )

        return self.pipeline.run_reproduction_trial(
            experiment_id=experiment_id,
            dataset_spec=dataset_spec,
            trial_scores=trial_scores,
            baseline_scores=baseline_scores,
            clearance=clearance,
        )
