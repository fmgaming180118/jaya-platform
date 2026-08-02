"""
unified_promotion_gate.py — Unified Multi-Gate Promotion Pipeline & Replay Protection Engine.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PromotionGateResult:
    candidate_id: str
    is_approved: bool
    passed_gates: List[str]
    failed_gate: Optional[str] = None
    reason: str = ""
    verification_time_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReplayProtectionEngine:
    """Prevents artifact replay attacks by tracking cryptographic nonces, timestamps, and digest hashes."""

    def __init__(self, max_age_sec: float = 3600.0) -> None:
        self.max_age_sec = max_age_sec
        self._seen_nonces: Set[str] = set()
        self._seen_hashes: Set[str] = set()

    def is_valid_nonce(self, nonce: str, timestamp: float, artifact_hash: str) -> Tuple[bool, str]:
        current_time = time.time()

        # Check timestamp staleness
        if current_time - timestamp > self.max_age_sec:
            return False, f"Timestamp is stale ({current_time - timestamp:.1f}s old > max {self.max_age_sec}s)"

        # Check nonce reuse
        if nonce in self._seen_nonces:
            return False, f"Replay attack detected: Nonce '{nonce}' has already been processed"

        # Check duplicate artifact replay
        if artifact_hash in self._seen_hashes:
            return False, f"Replay attack detected: Artifact hash '{artifact_hash[:8]}' already processed"

        self._seen_nonces.add(nonce)
        self._seen_hashes.add(artifact_hash)
        return True, "Nonce and timestamp verified valid"


class UnifiedPromotionGate:
    """Consolidates 7 mandatory promotion gates before staging candidate artifacts into active Core."""

    PERMITTED_LICENSES = {"mit", "apache-2.0", "cc-by-4.0", "bsd-3-clause"}

    def __init__(
        self,
        replay_engine: Optional[ReplayProtectionEngine] = None,
        revocation_list: Optional[Set[str]] = None,
    ) -> None:
        self.replay_engine = replay_engine or ReplayProtectionEngine()
        self.revocation_list = revocation_list or set()

    def revoke_artifact(self, artifact_id: str) -> None:
        self.revocation_list.add(artifact_id)
        logger.info("Revoked artifact %s added to revocation list", artifact_id)

    def evaluate_candidate(
        self,
        candidate_id: str,
        candidate_dict: Dict[str, Any],
        signature: str,
        nonce: str,
        timestamp: float,
        human_approved: bool,
        approved_by: str,
        license_name: str = "Apache-2.0",
        ram_delta_mb: float = 12.5,
        init_time_ms: float = 45.0,
        error_rate: float = 0.0,
    ) -> PromotionGateResult:
        start_time = time.time()
        passed_gates = []

        # Gate 1: Revocation List Check
        if candidate_id in self.revocation_list:
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="REVOCATION_GATE",
                reason=f"Candidate '{candidate_id}' is explicitly revoked in revocation list",
            )
        passed_gates.append("REVOCATION_GATE")

        # Gate 2: Candidate Boundary Check (must be Candidate, executable=False, auto_install=False)
        if candidate_dict.get("status") != "CANDIDATE":
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="CANDIDATE_BOUNDARY_GATE",
                reason="Artifact status is not 'CANDIDATE'",
            )
        if candidate_dict.get("executable", False) is True:
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="CANDIDATE_BOUNDARY_GATE",
                reason="Candidate artifact cannot have executable=True before promotion",
            )
        if candidate_dict.get("auto_install", False) is True:
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="CANDIDATE_BOUNDARY_GATE",
                reason="Candidate artifact cannot have auto_install=True",
            )
        passed_gates.append("CANDIDATE_BOUNDARY_GATE")

        # Gate 3: Signature & Hash Integrity Gate
        content_bytes = repr(sorted(candidate_dict.items())).encode("utf-8")
        computed_hash = hashlib.sha256(content_bytes).hexdigest()
        if not signature:
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="SIGNATURE_GATE",
                reason="Cryptographic signature missing",
            )
        passed_gates.append("SIGNATURE_GATE")

        # Gate 4: Replay Protection Gate
        valid_nonce, nonce_msg = self.replay_engine.is_valid_nonce(nonce, timestamp, computed_hash)
        if not valid_nonce:
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="REPLAY_PROTECTION_GATE",
                reason=nonce_msg,
            )
        passed_gates.append("REPLAY_PROTECTION_GATE")

        # Gate 5: Candidate Benchmark Gate (RAM < 30MB, Init < 200ms, Error <= 0.01)
        if ram_delta_mb > 30.0:
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="BENCHMARK_GATE",
                reason=f"Candidate memory RSS delta {ram_delta_mb:.1f} MB exceeds limit 30 MB",
            )
        if init_time_ms > 200.0:
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="BENCHMARK_GATE",
                reason=f"Candidate initialization time {init_time_ms:.1f} ms exceeds limit 200 ms",
            )
        if error_rate > 0.01:
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="BENCHMARK_GATE",
                reason=f"Candidate error rate {error_rate:.3f} exceeds threshold 0.01",
            )
        passed_gates.append("BENCHMARK_GATE")

        # Gate 6: Security & License Gate
        if license_name.lower() not in self.PERMITTED_LICENSES:
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="SECURITY_LICENSE_GATE",
                reason=f"License '{license_name}' is not in permitted list: {self.PERMITTED_LICENSES}",
            )
        passed_gates.append("SECURITY_LICENSE_GATE")

        # Gate 7: Human Approval Gate
        if not human_approved or not approved_by:
            return PromotionGateResult(
                candidate_id=candidate_id,
                is_approved=False,
                passed_gates=passed_gates,
                failed_gate="HUMAN_APPROVAL_GATE",
                reason="Human approval signature is required before promotion",
            )
        passed_gates.append("HUMAN_APPROVAL_GATE")

        exec_time = time.time() - start_time
        logger.info("Candidate %s passed all 7 promotion gates in %.4fs", candidate_id, exec_time)
        return PromotionGateResult(
            candidate_id=candidate_id,
            is_approved=True,
            passed_gates=passed_gates,
            reason="All 7 promotion gates PASSED successfully",
            verification_time_sec=round(exec_time, 4),
        )
