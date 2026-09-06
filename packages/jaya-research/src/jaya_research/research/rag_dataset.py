"""
rag_dataset.py — Representative RAG Dataset Specification and Human-Approval Gate.

Enforces rule: A dataset cannot elevate its status from `SMOKE_ONLY` or
`CANDIDATE_UNREVIEWED` to `APPROVED_REPRESENTATIVE` without a verified,
signed `HumanApprovalRecord` and an explicit `SamplingFrameSpec`.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class RepresentationStatus(str, Enum):
    SMOKE_ONLY = "SMOKE_ONLY"
    CANDIDATE_UNREVIEWED = "CANDIDATE_UNREVIEWED"
    APPROVED_REPRESENTATIVE = "APPROVED_REPRESENTATIVE"


class DatasetStatusElevationError(PermissionError):
    """Raised when an illegal status elevation is attempted without human approval."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass
class HumanApprovalRecord:
    approver_id: str
    approved_at: float
    signature: str
    notes: str = ""

    def is_valid(self) -> bool:
        return (
            bool(self.approver_id and self.approver_id.strip())
            and bool(self.signature and len(self.signature.strip()) >= 16)
            and self.approved_at > 0
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SamplingFrameSpec:
    frame_id: str
    sampling_method: str  # "STRATIFIED_RANDOM" | "BALANCED_DOMAIN_SAMPLING"
    source_domains: Dict[str, float]  # domain -> target ratio
    sample_size: int
    license_url: str

    def is_valid(self) -> bool:
        if not self.frame_id or self.sample_size <= 0 or not self.license_url:
            return False
        if not self.source_domains:
            return False
        total_ratio = sum(self.source_domains.values())
        return 0.95 <= total_ratio <= 1.05

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GoldRAGDatasetSpec:
    dataset_id: str
    version: str
    license_id: str
    representation_status: RepresentationStatus = RepresentationStatus.CANDIDATE_UNREVIEWED
    domain_balance: Dict[str, float] = field(default_factory=dict)
    entries_count: int = 0
    provenance_hash: str = ""
    human_approval: Optional[HumanApprovalRecord] = None
    sampling_frame: Optional[SamplingFrameSpec] = None

    def compute_hash(self) -> str:
        payload = {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "license_id": self.license_id,
            "representation_status": self.representation_status.value,
            "domain_balance": self.domain_balance,
            "entries_count": self.entries_count,
            "provenance_hash": self.provenance_hash,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["representation_status"] = self.representation_status.value
        if self.human_approval:
            res["human_approval"] = self.human_approval.to_dict()
        if self.sampling_frame:
            res["sampling_frame"] = self.sampling_frame.to_dict()
        return res


class RAGRepresentativeDatasetGate:
    """Fail-closed gate for promoting RAG evaluation dataset representation status."""

    def promote_status(
        self,
        spec: GoldRAGDatasetSpec,
        target_status: RepresentationStatus,
        approval_record: Optional[HumanApprovalRecord] = None,
    ) -> GoldRAGDatasetSpec:
        """
        Promote a dataset's representation status.

        Rule: Elevating to `APPROVED_REPRESENTATIVE` REQUIRES a valid `HumanApprovalRecord`
        and a valid `SamplingFrameSpec`.
        """
        if target_status == RepresentationStatus.APPROVED_REPRESENTATIVE:
            approval = approval_record or spec.human_approval
            if not approval or not approval.is_valid():
                raise DatasetStatusElevationError(
                    "HUMAN_APPROVAL_REQUIRED",
                    f"Dataset {spec.dataset_id} cannot be promoted to APPROVED_REPRESENTATIVE "
                    "without a valid, signed HumanApprovalRecord",
                )
            if not spec.sampling_frame or not spec.sampling_frame.is_valid():
                raise DatasetStatusElevationError(
                    "SAMPLING_FRAME_REQUIRED",
                    f"Dataset {spec.dataset_id} requires a valid SamplingFrameSpec "
                    "specifying legal license and domain balance ratios",
                )
            spec.human_approval = approval
            spec.representation_status = RepresentationStatus.APPROVED_REPRESENTATIVE
            return spec

        spec.representation_status = target_status
        return spec

    def validate_dataset_spec(self, spec: GoldRAGDatasetSpec) -> List[str]:
        violations = []
        if not spec.dataset_id or not spec.version:
            violations.append("Missing dataset_id or version")
        if not spec.license_id:
            violations.append("Missing license_id (open-source or permitted academic license required)")
        if spec.entries_count <= 0:
            violations.append("entries_count must be greater than 0")
        if spec.representation_status == RepresentationStatus.APPROVED_REPRESENTATIVE:
            if not spec.human_approval or not spec.human_approval.is_valid():
                violations.append("Status is APPROVED_REPRESENTATIVE but human_approval record is missing or invalid")
            if not spec.sampling_frame or not spec.sampling_frame.is_valid():
                violations.append("Status is APPROVED_REPRESENTATIVE but sampling_frame is missing or invalid")
        return violations
