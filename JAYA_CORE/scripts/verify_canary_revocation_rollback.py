"""
verify_canary_revocation_rollback.py — Demonstrates canary staging, revocation check, and automated rollback drill.
"""

from __future__ import annotations

import json
import sys
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

from src.artifacts.candidate_gate import CandidateArtifact
from src.artifacts.promotion_engine import CognitivePromotionEngine, PromotionStatus
from src.artifacts.unified_promotion_gate import ReplayProtectionEngine, UnifiedPromotionGate


def run_promotion_and_rollback_verification() -> dict:
    cand_id = "cand-cognitive-v2"

    candidate_dict = {
        "artifact_id": cand_id,
        "artifact_type": "COGNITIVE_UPDATE",
        "version": "2.0",
        "status": "CANDIDATE",
        "executable": False,
        "auto_install": False,
        "human_review_required": True,
        "rollback_info": {"rollback_supported": True, "target_version": "1.0"},
    }

    gate = UnifiedPromotionGate()
    timestamp = time.time()
    nonce = "nonce-unique-abc-123"
    signature = "sig-sha256-cryptographic-proof-ok"

    # 1. EVALUATION PASS DRILL
    res1 = gate.evaluate_candidate(
        candidate_id=cand_id,
        candidate_dict=candidate_dict,
        signature=signature,
        nonce=nonce,
        timestamp=timestamp,
        human_approved=True,
        approved_by="owner-human-reviewer",
        license_name="Apache-2.0",
    )

    # 2. REPLAY ATTACK REJECTION DRILL
    res_replay = gate.evaluate_candidate(
        candidate_id=cand_id,
        candidate_dict=candidate_dict,
        signature=signature,
        nonce=nonce,  # Re-using same nonce
        timestamp=timestamp,
        human_approved=True,
        approved_by="owner-human-reviewer",
    )

    # 3. REVOCATION LIST DRILL
    gate.revoke_artifact(cand_id)
    res_revoke = gate.evaluate_candidate(
        candidate_id=cand_id,
        candidate_dict=candidate_dict,
        signature=signature,
        nonce="nonce-new-xyz-999",
        timestamp=time.time(),
        human_approved=True,
        approved_by="owner-human-reviewer",
    )

    # 4. CANARY & AUTOMATED ROLLBACK DRILL
    promo_engine = CognitivePromotionEngine()
    cand_art = CandidateArtifact(
        artifact_id="cand-rollback-test",
        artifact_type="REASONING_STRATEGY",
        target_system="JAYA_CORE",
        provenance={"creator": "research", "evidence_id": "ev-100"},
        payload={"strategy": "tree_of_thought"},
        evidence_kind="EMPIRICAL_RESULT",
        executable=False,
        auto_install=False,
        human_review_required=True,
        rollback_info={"rollback_supported": True},
    )

    staged = promo_engine.stage_canary(cand_art, canary_nodes=["canary-node-01"])
    initial_staged_status = staged.status.value if hasattr(staged.status, "value") else str(staged.status)
    observed_record = promo_engine.report_canary_metrics(cand_art.artifact_id, error_rate=0.08)

    results = {
        "promotion_gate_drill": "SUCCESS" if res1.is_approved else "FAILED",
        "passed_gates_count": len(res1.passed_gates),
        "replay_rejection_drill": "SUCCESS" if not res_replay.is_approved and res_replay.failed_gate == "REPLAY_PROTECTION_GATE" else "FAILED",
        "revocation_rejection_drill": "SUCCESS" if not res_revoke.is_approved and res_revoke.failed_gate == "REVOCATION_GATE" else "FAILED",
        "canary_staging_status": initial_staged_status,
        "automated_rollback_drill": "SUCCESS" if observed_record.status == PromotionStatus.ROLLED_BACK else "FAILED",
    }

    return results


def main() -> int:
    print("VERIFIKASI UNIFIED PROMOTION GATE, REVOKASI, DAN AUTOMATED ROLLBACK DRILL...")
    res = run_promotion_and_rollback_verification()
    print(json.dumps(res, indent=2))

    if (
        res["promotion_gate_drill"] == "SUCCESS"
        and res["replay_rejection_drill"] == "SUCCESS"
        and res["revocation_rejection_drill"] == "SUCCESS"
        and res["automated_rollback_drill"] == "SUCCESS"
    ):
        print("\nUnified promotion gate, revocation, dan automated rollback drill VERIFIED SUCCESSFUL!")
        return 0

    print("\nPromotion gate verification drill FAILED!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
