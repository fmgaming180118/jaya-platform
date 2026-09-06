"""
test_scientific_external_items.py — Unit tests for Scientific & Deployment BLOCKED_EXTERNAL items.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from jaya_research.research.citation_audit import (
    DomainReviewerRecord,
    HumanEntailmentCitationAuditor,
    NoveltyClaimRecord,
    NoveltyGapDomainReviewerEvaluator,
    NoveltyStatus,
)
from jaya_research.research.empirical_gold_pipeline import (
    EmpiricalGoldReproductionPipeline,
    EthicalLegalClearanceRecord,
    EthicsLegalEmpiricalRunner,
)
from jaya_research.research.multimodal_gold import GoldPDFDocument, MultimodalRealWorldPDFEvaluator
from jaya_research.research.qa_eval_runner import QATargetEvidenceRunner
from jaya_research.research.rag_dataset import (
    DatasetStatusElevationError,
    GoldRAGDatasetSpec,
    HumanApprovalRecord,
    RAGRepresentativeDatasetGate,
    RepresentationStatus,
    SamplingFrameSpec,
)


class TestSamplingFrameAndRAGGate:
    def test_elevation_without_sampling_frame_is_denied(self):
        gate = RAGRepresentativeDatasetGate()
        spec = GoldRAGDatasetSpec(
            dataset_id="ds-no-frame",
            version="1.0",
            license_id="MIT",
            representation_status=RepresentationStatus.CANDIDATE_UNREVIEWED,
            entries_count=100,
        )
        app_record = HumanApprovalRecord(
            approver_id="rev-01", approved_at=time.time(), signature="valid_sha256_signature_001_signed"
        )

        with pytest.raises(DatasetStatusElevationError) as exc_info:
            gate.promote_status(spec, RepresentationStatus.APPROVED_REPRESENTATIVE, app_record)
        assert exc_info.value.code == "SAMPLING_FRAME_REQUIRED"

    def test_elevation_with_valid_sampling_frame_succeeds(self):
        gate = RAGRepresentativeDatasetGate()
        frame = SamplingFrameSpec(
            frame_id="frame-1",
            sampling_method="STRATIFIED_RANDOM",
            source_domains={"phys": 0.5, "eng": 0.5},
            sample_size=100,
            license_url="https://license.org/by",
        )
        spec = GoldRAGDatasetSpec(
            dataset_id="ds-frame-ok",
            version="1.0",
            license_id="MIT",
            representation_status=RepresentationStatus.CANDIDATE_UNREVIEWED,
            sampling_frame=frame,
            entries_count=100,
        )
        app_record = HumanApprovalRecord(
            approver_id="rev-01", approved_at=time.time(), signature="valid_sha256_signature_001_signed"
        )

        promoted = gate.promote_status(spec, RepresentationStatus.APPROVED_REPRESENTATIVE, app_record)
        assert promoted.representation_status == RepresentationStatus.APPROVED_REPRESENTATIVE


class TestQATargetEvidenceRunner:
    def test_attested_qa_run_achieves_85pct_target(self):
        runner = QATargetEvidenceRunner()
        spec = GoldRAGDatasetSpec(
            dataset_id="ds-qa-approved",
            version="1.0",
            license_id="MIT",
            representation_status=RepresentationStatus.APPROVED_REPRESENTATIVE,
            entries_count=100,
        )
        qa_results = [{"is_correct": True} for _ in range(86)] + [{"is_correct": False} for _ in range(14)]

        receipt = runner.execute_attested_qa_run("run-qa-100", spec, qa_results)
        assert receipt.status == "TARGET_ACHIEVED_PASS"
        assert receipt.accuracy_pct == 86.0

    def test_qa_run_fails_if_accuracy_below_85pct(self):
        runner = QATargetEvidenceRunner()
        spec = GoldRAGDatasetSpec(
            dataset_id="ds-qa-approved-2",
            version="1.0",
            license_id="MIT",
            representation_status=RepresentationStatus.APPROVED_REPRESENTATIVE,
            entries_count=100,
        )
        qa_results = [{"is_correct": True} for _ in range(75)] + [{"is_correct": False} for _ in range(25)]

        receipt = runner.execute_attested_qa_run("run-qa-101", spec, qa_results)
        assert receipt.status == "TARGET_FAILED"
        assert receipt.accuracy_pct == 75.0

    def test_load_and_eval_dataset_file_succeeds(self):
        runner = QATargetEvidenceRunner()
        dataset_file = repo_root / "data" / "evaluations" / "rag_representative_gold_v1.json"
        receipt = runner.load_and_eval_dataset_file(dataset_file_path=dataset_file)
        assert receipt.status == "TARGET_ACHIEVED_PASS"
        assert receipt.accuracy_pct >= 85.0


class TestNoveltyGapAndEntailmentAuditor:
    def test_domain_reviewer_evaluator(self):
        evaluator = NoveltyGapDomainReviewerEvaluator()
        claim = NoveltyClaimRecord(
            claim_id="c1",
            hypothesis_text="Hypothesis 1",
            corpus_searched="PubMed",
            search_period="2020-2026",
            query_method="knn",
            status=NoveltyStatus.VERIFIED_NOVELTY,
        )
        reviewer = DomainReviewerRecord(
            reviewer_id="rev-physics",
            domain_expertise="Physics",
            review_date=time.time(),
            signature="valid_sha256_signature_reviewer_physics",
            approved=True,
            corpus_version="v1",
        )

        res = evaluator.evaluate_novelty_corpus("corp-1", [claim], reviewer)
        assert res["status"] == "EVALUATION_APPROVED"
        assert res["approval_ratio"] == 1.0

    def test_human_entailment_auditor(self):
        auditor = HumanEntailmentCitationAuditor()
        report = auditor.audit_citation_entailment(
            audit_id="audit-1",
            synthesis_id="synth-1",
            auditor_id="auditor-100",
            entailment_score_pct=90.0,
            synthesis_quality_score_pct=85.0,
            signature="valid_sha256_signature_auditor_100",
        )
        assert report.is_attested is True


class TestMultimodalRealWorldPDFEvaluator:
    def test_pdf_evaluator_handles_corrupt_simulated_doc(self):
        evaluator = MultimodalRealWorldPDFEvaluator()
        doc = GoldPDFDocument(
            file_path="/tmp/corrupt.pdf",
            filename="corrupt.pdf",
            sha256="a" * 64,
            file_size_bytes=100,
            text_content="some text",
        )
        report = evaluator.evaluate_pdf_document(doc, is_corrupt_simulated=True)
        assert report.status == "PDF_EVALUATION_PASSED"
        assert report.is_corrupt_handled is True


class TestEthicsLegalEmpiricalRunner:
    def test_empirical_study_requires_ethics_clearance(self):
        pipeline = EmpiricalGoldReproductionPipeline()
        runner = EthicsLegalEmpiricalRunner(pipeline)
        spec = GoldRAGDatasetSpec(dataset_id="ds-emp", version="1.0", license_id="MIT")

        with pytest.raises(PermissionError) as exc_info:
            runner.run_cleared_empirical_study("exp-no-clearance", spec, [0.9], [0.5], clearance=None)
        assert "Ethical & Legal clearance" in str(exc_info.value)

    def test_empirical_study_with_valid_clearance_succeeds(self):
        pipeline = EmpiricalGoldReproductionPipeline()
        runner = EthicsLegalEmpiricalRunner(pipeline)
        spec = GoldRAGDatasetSpec(dataset_id="ds-emp-2", version="1.0", license_id="MIT")
        clearance = EthicalLegalClearanceRecord(
            clearance_id="clearance-01",
            ethics_board_approval="IRB-APPROVED-2026",
            legal_review_url="https://legal.url",
            cleared_at=time.time(),
            signature="valid_sha256_signature_clearance_01",
        )

        res = runner.run_cleared_empirical_study(
            "exp-cleared", spec, [0.88, 0.90, 0.87, 0.89], [0.50, 0.51, 0.49], clearance=clearance
        )
        assert res.reproduction_status == "INDEPENDENT_REPRODUCTION_PASSED"
        assert res.clearance is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
