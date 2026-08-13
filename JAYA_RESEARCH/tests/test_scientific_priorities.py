"""
test_scientific_priorities.py — Unit tests for Scientific Priorities 1-5 (JAYA_RESEARCH domain).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from JAYA_RESEARCH.src.research.citation_audit import (
    CitationSynthesisAuditEngine,
    EvidenceChunk,
    HumanNoveltyReviewRecord,
    NoveltyClaimRecord,
    NoveltyGapHumanReviewGate,
    NoveltyStatus,
)
from JAYA_RESEARCH.src.research.empirical_gold_pipeline import EmpiricalGoldReproductionPipeline
from JAYA_RESEARCH.src.research.multimodal_gold import (
    GoldPDFCorpusLoader,
    GoldPDFDocument,
    OCRProviderError,
    RealOCRTableFigureProvider,
)
from JAYA_RESEARCH.src.research.rag_dataset import (
    DatasetStatusElevationError,
    GoldRAGDatasetSpec,
    HumanApprovalRecord,
    RAGRepresentativeDatasetGate,
    RepresentationStatus,
)
from JAYA_RESEARCH.src.research.scientific_worker import JobScientificStatus, ScientificGateWorkerHardening


class TestGoldRAGDatasetGate:
    def test_elevation_without_human_approval_is_denied(self):
        gate = RAGRepresentativeDatasetGate()
        spec = GoldRAGDatasetSpec(
            dataset_id="dataset-test-1",
            version="1.0",
            license_id="MIT",
            representation_status=RepresentationStatus.SMOKE_ONLY,
            entries_count=50,
        )

        with pytest.raises(DatasetStatusElevationError) as exc_info:
            gate.promote_status(spec, RepresentationStatus.APPROVED_REPRESENTATIVE)
        assert exc_info.value.code == "HUMAN_APPROVAL_REQUIRED"

    def test_elevation_with_valid_human_approval_succeeds(self):
        gate = RAGRepresentativeDatasetGate()
        spec = GoldRAGDatasetSpec(
            dataset_id="dataset-test-2",
            version="1.0",
            license_id="Apache-2.0",
            representation_status=RepresentationStatus.CANDIDATE_UNREVIEWED,
            entries_count=100,
        )
        record = HumanApprovalRecord(
            approver_id="reviewer-01",
            approved_at=time.time(),
            signature="valid_sha256_signature_001_signed",
            notes="Representative dataset verified",
        )

        promoted = gate.promote_status(spec, RepresentationStatus.APPROVED_REPRESENTATIVE, record)
        assert promoted.representation_status == RepresentationStatus.APPROVED_REPRESENTATIVE
        assert promoted.human_approval is not None


class TestCitationSynthesisAuditEngine:
    def test_grounded_synthesis_passes_audit(self):
        engine = CitationSynthesisAuditEngine()
        chunk = EvidenceChunk(chunk_id="chk-100", content="Superconducting magnets operate at 4 Kelvin.", source_uri="doc.pdf")
        synthesis = "Superconducting magnets operate at 4 Kelvin [chk-100]."

        report = engine.audit_synthesis("synth-100", synthesis, [chunk])
        assert report.status == "VERIFIED"
        assert report.abstention_triggered is False
        assert "chk-100" in report.citations_mapped

    def test_ungrounded_synthesis_triggers_abstention(self):
        engine = CitationSynthesisAuditEngine()
        chunk = EvidenceChunk(chunk_id="chk-101", content="Text about magnetics.", source_uri="doc.pdf")
        synthesis = "Hypothetical warp field emitter uses tachyons."

        report = engine.audit_synthesis("synth-101", synthesis, [chunk])
        assert report.status == "ABSTAIN"
        assert report.abstention_triggered is True


class TestNoveltyGapHumanReviewGate:
    def test_model_novelty_claim_remains_hypothesis_until_human_review(self):
        gate = NoveltyGapHumanReviewGate()
        claim = NoveltyClaimRecord(
            claim_id="nov-200",
            hypothesis_text="New superconductor alloy formulation",
            corpus_searched="PubMed",
            search_period="2020-2026",
            query_method="bm25",
        )
        assert claim.status == NoveltyStatus.NOVELTY_HYPOTHESIS

        gate.submit_for_review(claim)
        assert claim.status == NoveltyStatus.AWAITING_HUMAN_REVIEW

        review = HumanNoveltyReviewRecord(
            reviewer_id="expert-prof-smith",
            decision="APPROVED",
            comments="Verified against literature gap",
            reviewed_at=time.time(),
            signature="valid_sha256_expert_prof_smith_signature",
        )
        reviewed = gate.review_claim(claim, review)
        assert reviewed.status == NoveltyStatus.VERIFIED_NOVELTY


class TestGoldPDFCorpusLoaderAndOCR:
    def test_loader_and_ocr_extraction(self, tmp_path):
        sample_file = tmp_path / "paper.txt"
        sample_fs.write_text(
            "Title: Plasma Physics\nFigure 1: Tokamak layout\n| Parameter | Value |\n|---|---|\n| Current | 5MA |\n",
            encoding="utf-8",
        )
        loader = GoldPDFCorpusLoader(tmp_path)
        doc = loader.load_document(sample_file)

        ocr = RealOCRTableFigureProvider()
        extracted = ocr.extract_structured_content(doc)
        assert len(extracted.figures) == 1
        assert len(extracted.tables) == 1

    def test_loader_raises_error_on_empty_file(self, tmp_path):
        empty_file = tmp_path / "empty.txt"
        empty_fs.write_text("", encoding="utf-8")
        loader = GoldPDFCorpusLoader(tmp_path)

        with pytest.raises(OCRProviderError) as exc_info:
            loader.load_document(empty_file)
        assert exc_info.value.code == "EMPTY_FILE"


class TestEmpiricalGoldReproductionPipeline:
    def test_reproduction_trial_statistics(self):
        pipeline = EmpiricalGoldReproductionPipeline()
        spec = GoldRAGDatasetSpec(dataset_id="ds-eval", version="1.0", license_id="MIT", entries_count=50)

        res = pipeline.run_reproduction_trial(
            experiment_id="exp-100",
            dataset_spec=spec,
            trial_scores=[0.90, 0.92, 0.88, 0.91, 0.89],
            baseline_scores=[0.50, 0.51, 0.49, 0.52, 0.48],
            num_hypotheses_tested=1,
        )
        assert res.reproduction_status == "INDEPENDENT_REPRODUCTION_PASSED"
        assert res.statistics.cohens_d > 2.0
        assert res.statistics.bonferroni_adjusted_p < 0.05


class TestScientificGateWorkerHardening:
    def test_scientific_worker_suspends_unscientific_job(self):
        hardening = ScientificGateWorkerHardening()

        # Rejected when missing report/reproduction
        res = hardening.evaluate_job_scientific_readiness("job-test-1", audit_report=None, reproduction_result=None)
        assert res.is_allowed is False
        assert res.scientific_status == JobScientificStatus.SUSPENDED_UNSCIENTIFIC


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
