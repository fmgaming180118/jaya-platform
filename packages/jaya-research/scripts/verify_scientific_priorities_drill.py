"""
verify_scientific_priorities_drill.py — Drill script for Scientific Priorities 1-5 (JAYA_RESEARCH domain).

Executes scientific drills 1-6 within the JAYA_RESEARCH domain boundary.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from jaya_research.research.citation_audit import (
    CitationSynthesisAuditEngine,
    EvidenceChunk,
    HumanNoveltyReviewRecord,
    NoveltyClaimRecord,
    NoveltyGapHumanReviewGate,
    NoveltyStatus,
)
from jaya_research.research.empirical_gold_pipeline import EmpiricalGoldReproductionPipeline
from jaya_research.research.multimodal_gold import GoldPDFCorpusLoader, GoldPDFDocument, RealOCRTableFigureProvider
from jaya_research.research.rag_dataset import (
    DatasetStatusElevationError,
    GoldRAGDatasetSpec,
    HumanApprovalRecord,
    RAGRepresentativeDatasetGate,
    RepresentationStatus,
)
from jaya_research.research.scientific_worker import JobScientificStatus, ScientificGateWorkerHardening


def run_scientific_priorities_drill() -> dict:
    results = {}

    # Drill 1: RAG Dataset & Approval Gate
    gate1 = RAGRepresentativeDatasetGate()
    spec = GoldRAGDatasetSpec(
        dataset_id="rag-gold-001",
        version="1.0.0",
        license_id="Apache-2.0",
        representation_status=RepresentationStatus.CANDIDATE_UNREVIEWED,
        entries_count=100,
    )
    # Elevation without approval MUST raise error
    unapproved_rejected = False
    try:
        gate1.promote_status(spec, RepresentationStatus.APPROVED_REPRESENTATIVE)
    except DatasetStatusElevationError:
        unapproved_rejected = True

    # Elevation WITH valid approval
    app_record = HumanApprovalRecord(
        approver_id="expert-human-01",
        approved_at=time.time(),
        signature="sha256_valid_signature_human_review_001",
        notes="Verified domain balance and non-synthetic gold data",
    )
    promoted_spec = gate1.promote_status(spec, RepresentationStatus.APPROVED_REPRESENTATIVE, app_record)
    drill1_pass = unapproved_rejected and promoted_spec.representation_status == RepresentationStatus.APPROVED_REPRESENTATIVE
    results["drill_1_rag_dataset_gate"] = "SUCCESS" if drill1_pass else "FAILED"

    # Drill 2: Citation Synthesis Audit
    audit_engine = CitationSynthesisAuditEngine()
    chunk1 = EvidenceChunk(chunk_id="chk-01", content="Lawson criterion requires n * tau * T >= 1e21 m^-3 s keV for fusion.", source_uri="paper_01.pdf")
    synthesis_good = "According to fusion principles [chk-01], Lawson criterion requires n * tau * T >= 1e21 m^-3 s keV for fusion."
    report_good = audit_engine.audit_synthesis("synth-1", synthesis_good, [chunk1])

    synthesis_bad = "Arbitrary unreferenced claim about warp drive without any evidence."
    report_bad = audit_engine.audit_synthesis("synth-2", synthesis_bad, [chunk1])

    drill2_pass = (report_good.status == "VERIFIED") and (report_bad.status == "ABSTAIN")
    results["drill_2_citation_synthesis_audit"] = "SUCCESS" if drill2_pass else "FAILED"

    # Drill 3: Novelty Gap Human Review Gate
    novelty_gate = NoveltyGapHumanReviewGate()
    claim = NoveltyClaimRecord(
        claim_id="nov-001",
        hypothesis_text="New magnetohydrodynamic nozzle configuration for plasma confinement",
        corpus_searched="ArXiv 2020-2026",
        search_period="2020-2026",
        query_method="semantic_embedding_knn",
    )
    novelty_gate.submit_for_review(claim)
    rev_record = HumanNoveltyReviewRecord(
        reviewer_id="peer-reviewer-42",
        decision="APPROVED",
        comments="Novel configuration confirmed against existing literature",
        reviewed_at=time.time(),
        signature="sha256_signature_peer_reviewer_42_ok",
    )
    reviewed_claim = novelty_gate.review_claim(claim, rev_record)
    drill3_pass = reviewed_claim.status == NoveltyStatus.VERIFIED_NOVELTY
    results["drill_3_novelty_human_review_gate"] = "SUCCESS" if drill3_pass else "FAILED"

    # Drill 4: Multimodal Gold PDF Corpus & OCR/Table Extractor
    jurnal_dir = repo_root / "data" / "jaya-research" / "jurnal_pdf"
    if not jurnal_dir.exists():
        jurnal_dir.mkdir(parents=True, exist_ok=True)
    sample_txt = jurnal_dir / "sample_paper.txt"
    sample_txt.write_text(
        "# High-Field Superconducting Magnet Analysis\n\n"
        "Figure 1: Magnetic flux density distribution in HTS coil\n\n"
        "| Parameter | Value |\n|---|---|\n| Field (T) | 20.5 |\n| Temp (K) | 4.2 |\n",
        encoding="utf-8",
    )
    loader = GoldPDFCorpusLoader(jurnal_dir)
    doc = loader.load_document(sample_txt)
    ocr_provider = RealOCRTableFigureProvider()
    extracted_doc = ocr_provider.extract_structured_content(doc)
    drill4_pass = (len(extracted_doc.tables) > 0) and (len(extracted_doc.figures) > 0) and bool(extracted_doc.sha256)
    results["drill_4_multimodal_gold_pdf_ocr"] = "SUCCESS" if drill4_pass else "FAILED"

    # Drill 5: Empirical Reproduction Pipeline
    repro_pipeline = EmpiricalGoldReproductionPipeline()
    repro_res = repro_pipeline.run_reproduction_trial(
        experiment_id="exp-repro-01",
        dataset_spec=promoted_spec,
        trial_scores=[0.85, 0.88, 0.82, 0.89, 0.86],
        baseline_scores=[0.50, 0.52, 0.48, 0.51, 0.49],
        num_hypotheses_tested=2,
    )
    drill5_pass = repro_res.reproduction_status == "INDEPENDENT_REPRODUCTION_PASSED" and repro_res.statistics.cohens_d > 1.0
    results["drill_5_empirical_reproduction_pipeline"] = "SUCCESS" if drill5_pass else "FAILED"

    # Drill 6: Scientific Gate Worker Hardening
    worker_hardening = ScientificGateWorkerHardening()
    eval_ok = worker_hardening.evaluate_job_scientific_readiness("job-01", report_good, repro_res)
    eval_bad = worker_hardening.evaluate_job_scientific_readiness("job-02", report_bad, None)
    drill6_pass = eval_ok.is_allowed and (eval_bad.scientific_status == JobScientificStatus.SUSPENDED_UNSCIENTIFIC)
    results["drill_6_scientific_worker_hardening"] = "SUCCESS" if drill6_pass else "FAILED"

    return results


def main() -> int:
    print("VERIFIKASI DRILL PRIORITAS ILMIAH (JAYA_RESEARCH DOMAIN)...")
    res = run_scientific_priorities_drill()
    print(json.dumps(res, indent=2))

    if all(status == "SUCCESS" for status in res.values()):
        print("\nSeluruh drill prioritas ilmiah VERIFIED SUCCESSFUL!")
        return 0

    print("\nDrill prioritas ilmiah FAILED!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
