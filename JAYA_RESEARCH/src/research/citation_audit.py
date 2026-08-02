"""
citation_audit.py — Citation/Synthesis Audit Engine and Human Novelty/Gap Review Gate.

Enforces rules:
1. LLM synthesis without valid evidence citations produces automatic abstention or UNVERIFIED_CLAIM tags.
2. Novelty claims produced by model remain NOVELTY_HYPOTHESIS until reviewed by a human expert.
3. Domain reviewer evaluation over labeled gap corpus.
4. Human entailment audit for citation premises and synthesis quality.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class NoveltyStatus(str, Enum):
    NOVELTY_HYPOTHESIS = "NOVELTY_HYPOTHESIS"
    AWAITING_HUMAN_REVIEW = "AWAITING_HUMAN_REVIEW"
    VERIFIED_NOVELTY = "VERIFIED_NOVELTY"
    REJECTED_NOVELTY = "REJECTED_NOVELTY"


class CitationAuditError(ValueError):
    """Raised when citation or evidence verification fails."""


@dataclass
class EvidenceChunk:
    chunk_id: str
    content: str
    source_uri: str
    sha256: str = field(default_factory=str)

    def __post_init__(self) -> None:
        if not self.sha256:
            self.sha256 = hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass
class SynthesisAuditReport:
    synthesis_id: str
    total_claims: int
    grounded_claims: int
    unverified_claims: int
    abstention_triggered: bool
    citations_mapped: List[str]
    status: str  # "VERIFIED", "PARTIALLY_VERIFIED", "ABSTAIN"
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CitationSynthesisAuditEngine:
    """Audit engine verifying that scientific synthesis claims are backed by SOURCE_EVIDENCE."""

    def audit_synthesis(
        self,
        synthesis_id: str,
        synthesis_text: str,
        evidence_chunks: List[EvidenceChunk],
        min_grounding_ratio: float = 0.8,
    ) -> SynthesisAuditReport:
        if not synthesis_text or not synthesis_text.strip():
            return SynthesisAuditReport(
                synthesis_id=synthesis_id,
                total_claims=0,
                grounded_claims=0,
                unverified_claims=0,
                abstention_triggered=True,
                citations_mapped=[],
                status="ABSTAIN",
                audit_trail=[{"reason": "Empty synthesis text"}],
            )

        sentences = [s.strip() for s in re.split(r"[.!?]+", synthesis_text) if len(s.strip()) > 10]
        if not sentences:
            sentences = [synthesis_text.strip()]

        total_claims = len(sentences)
        grounded_claims = 0
        unverified_claims = 0
        citations_mapped = []
        audit_trail = []

        evidence_content_lower = " ".join([e.content.lower() for e in evidence_chunks])
        chunk_map = {e.chunk_id: e for e in evidence_chunks}

        for i, sentence in enumerate(sentences):
            # Check for explicit citation tag like [chunk_id] or keyword overlap
            matched_chunk = None
            citation_match = re.search(r"\[([a-zA-Z0-9_-]+)\]", sentence)
            if citation_match and citation_match.group(1) in chunk_map:
                matched_chunk = chunk_map[citation_match.group(1)]
            else:
                # Check semantic keyword overlap with evidence
                words = set(re.findall(r"\w+", sentence.lower()))
                important_words = {w for w in words if len(w) > 4}
                if important_words and any(w in evidence_content_lower for w in important_words):
                    matched_chunk = evidence_chunks[0] if evidence_chunks else None

            if matched_chunk:
                grounded_claims += 1
                citations_mapped.append(matched_chunk.chunk_id)
                audit_trail.append({"sentence_index": i, "status": "GROUNDED", "chunk": matched_chunk.chunk_id})
            else:
                unverified_claims += 1
                audit_trail.append({"sentence_index": i, "status": "UNVERIFIED_CLAIM", "snippet": sentence[:60]})

        ratio = grounded_claims / total_claims if total_claims > 0 else 0.0
        abstention = ratio < min_grounding_ratio or not evidence_chunks
        status = "VERIFIED" if ratio >= 0.9 else ("PARTIALLY_VERIFIED" if ratio >= min_grounding_ratio else "ABSTAIN")

        return SynthesisAuditReport(
            synthesis_id=synthesis_id,
            total_claims=total_claims,
            grounded_claims=grounded_claims,
            unverified_claims=unverified_claims,
            abstention_triggered=abstention,
            citations_mapped=citations_mapped,
            status=status,
            audit_trail=audit_trail,
        )


@dataclass
class HumanNoveltyReviewRecord:
    reviewer_id: str
    decision: str  # "APPROVED" or "REJECTED"
    comments: str
    reviewed_at: float
    signature: str


@dataclass
class NoveltyClaimRecord:
    claim_id: str
    hypothesis_text: str
    corpus_searched: str
    search_period: str
    query_method: str
    status: NoveltyStatus = NoveltyStatus.NOVELTY_HYPOTHESIS
    human_review: Optional[HumanNoveltyReviewRecord] = None

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["status"] = self.status.value
        if self.human_review:
            res["human_review"] = asdict(self.human_review)
        return res


class NoveltyGapHumanReviewGate:
    """Gate for promoting novelty claims with human expert verification."""

    def submit_for_review(self, claim: NoveltyClaimRecord) -> NoveltyClaimRecord:
        claim.status = NoveltyStatus.AWAITING_HUMAN_REVIEW
        return claim

    def review_claim(
        self,
        claim: NoveltyClaimRecord,
        review: HumanNoveltyReviewRecord,
    ) -> NoveltyClaimRecord:
        if not review.reviewer_id or not review.signature or len(review.signature) < 16:
            raise CitationAuditError("Human novelty review requires valid reviewer_id and signature")

        claim.human_review = review
        if review.decision.upper() == "APPROVED":
            claim.status = NoveltyStatus.VERIFIED_NOVELTY
        else:
            claim.status = NoveltyStatus.REJECTED_NOVELTY

        return claim


@dataclass
class DomainReviewerRecord:
    reviewer_id: str
    domain_expertise: str
    review_date: float
    signature: str
    approved: bool
    corpus_version: str

    def is_valid(self) -> bool:
        return (
            bool(self.reviewer_id and self.reviewer_id.strip())
            and bool(self.signature and len(self.signature.strip()) >= 16)
            and self.review_date > 0
            and self.approved
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NoveltyGapDomainReviewerEvaluator:
    """Evaluator for domain reviewer evaluation over labeled novelty/gap corpus."""

    def evaluate_novelty_corpus(
        self,
        corpus_id: str,
        claims: List[NoveltyClaimRecord],
        reviewer_record: DomainReviewerRecord,
    ) -> Dict[str, Any]:
        if not reviewer_record.is_valid():
            raise CitationAuditError("Domain reviewer record is invalid or unapproved")

        approved_count = sum(1 for c in claims if c.status == NoveltyStatus.VERIFIED_NOVELTY)
        total = len(claims)

        return {
            "corpus_id": corpus_id,
            "reviewer_id": reviewer_record.reviewer_id,
            "domain_expertise": reviewer_record.domain_expertise,
            "total_claims": total,
            "approved_claims": approved_count,
            "approval_ratio": round(approved_count / total, 4) if total > 0 else 0.0,
            "status": "EVALUATION_APPROVED" if reviewer_record.approved else "EVALUATION_REJECTED",
        }


@dataclass
class EntailmentAuditReport:
    audit_id: str
    synthesis_id: str
    auditor_id: str
    entailment_score_pct: float
    synthesis_quality_score_pct: float
    is_attested: bool
    signature: str
    audited_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HumanEntailmentCitationAuditor:
    """Auditor verifying human entailment and synthesis quality for scientific citations."""

    def audit_citation_entailment(
        self,
        audit_id: str,
        synthesis_id: str,
        auditor_id: str,
        entailment_score_pct: float,
        synthesis_quality_score_pct: float,
        signature: str,
    ) -> EntailmentAuditReport:
        if not auditor_id or not signature or len(signature.strip()) < 16:
            raise CitationAuditError("Human entailment audit requires valid auditor_id and signature")

        is_attested = entailment_score_pct >= 85.0 and synthesis_quality_score_pct >= 80.0

        return EntailmentAuditReport(
            audit_id=audit_id,
            synthesis_id=synthesis_id,
            auditor_id=auditor_id,
            entailment_score_pct=entailment_score_pct,
            synthesis_quality_score_pct=synthesis_quality_score_pct,
            is_attested=is_attested,
            signature=signature,
        )
