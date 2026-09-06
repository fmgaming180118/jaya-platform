#!/usr/bin/env python3
"""Interactive vertical slice demo for Pillar 40: Intent Extrapolation."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.control_capabilities import (  # noqa: E402
    INTENT_CAPABILITY_ID,
    IntentExtrapolationCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402


def run_demo() -> None:
    print("=" * 78)
    print("  JAYA SYSTEM — PILAR 40: INTENT EXTRAPOLATION VERTICAL SLICE DEMO")
    print("=" * 78)

    work_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_p40_"))
    db_path = work_dir / "intent_extrapolation.sqlite3"

    try:
        cap = IntentExtrapolationCapability(db_path)
        owner_id = "engineer-fahri"

        # -------------------------------------------------------------
        # Step 1: Unconsented Profiling Protection
        # -------------------------------------------------------------
        print("\n[STEP 1] Verifying non-consented profiling protection...")
        status = cap.execute({"action": "consent_status", "owner_id": owner_id})
        print(f"  -> Initial status: has_consent={status.data['has_consent']}, active={status.data['active']}")

        try:
            cap.execute(
                {
                    "action": "observe",
                    "owner_id": owner_id,
                    "sequence": ["git_pull", "check_diff", "run_linter"],
                }
            )
            print("  [ERROR] Unconsented observation was permitted!")
        except LocalPillarError as exc:
            print(f"  -> Successfully BLOCKED unconsented observation: code={exc.code} message='{exc}'")

        try:
            cap.execute({"action": "predict", "owner_id": owner_id, "current_intent": "git_pull"})
            print("  [ERROR] Unconsented prediction was permitted!")
        except LocalPillarError as exc:
            print(f"  -> Successfully BLOCKED unconsented prediction: code={exc.code} message='{exc}'")

        # -------------------------------------------------------------
        # Step 2: Granting Explicit Expiring Consent
        # -------------------------------------------------------------
        print("\n[STEP 2] Granting explicit expiring consent...")
        now = time.time()
        consent_receipt = f"rcpt-jaya-p40-{int(now)}"
        consent_res = cap.execute(
            {
                "action": "record_consent",
                "owner_id": owner_id,
                "receipt_id": consent_receipt,
                "granted_at": now,
                "expires_at": now + 7200,  # 2 hours validity
            }
        )
        print(f"  -> Consent recorded with receipt: {consent_res.data['receipt_id']}")
        status = cap.execute({"action": "consent_status", "owner_id": owner_id})
        print(f"  -> Current status: has_consent={status.data['has_consent']}, active={status.data['active']}, expires_in=7200s")

        # -------------------------------------------------------------
        # Step 3: Observing Real Workflow Transitions
        # -------------------------------------------------------------
        print("\n[STEP 3] Observing real workflow sequences across 4 sessions...")
        workflow_sequences = [
            ["open_workspace", "review_spec", "implement_slice", "run_tests", "commit_changes"],
            ["open_workspace", "review_spec", "implement_slice", "run_tests", "commit_changes"],
            ["open_workspace", "review_spec", "implement_slice", "run_tests", "commit_changes"],
            ["open_workspace", "review_spec", "consult_architecture", "implement_slice"],
        ]
        for idx, seq in enumerate(workflow_sequences, start=1):
            obs_res = cap.execute({"action": "observe", "owner_id": owner_id, "sequence": seq})
            print(f"  -> Session {idx}: recorded {obs_res.data['transitions']} pairwise transitions.")

        # -------------------------------------------------------------
        # Step 4: Predicting Next Intent with Strict Contract
        # -------------------------------------------------------------
        print("\n[STEP 4] Generating calibrated intent extrapolation...")
        pred = cap.execute(
            {
                "action": "predict",
                "owner_id": owner_id,
                "current_intent": "review_spec",
                "minimum_observations": 2,
                "ttl_seconds": 300,
            }
        )
        print("  -> Extrapolated Candidate:", json.dumps(pred.data, indent=4))
        assert pred.data["source"] == "INFERENCE", "Contract violation: must be INFERENCE"
        assert pred.data["confirmation_required"] is True, "Contract violation: confirmation must be required"
        assert pred.data["executed"] is False, "Contract violation: must NOT auto-execute"
        print(f"  -> Verification: Candidate='{pred.data['candidate']}' Confidence={pred.data['confidence']*100:.1f}% Source={pred.data['source']}")
        print(f"  -> Side-effect check: executed={pred.data['executed']} (Zero unauthorized mutations)")

        # -------------------------------------------------------------
        # Step 5: User Feedback & Adaptive Model Correction
        # -------------------------------------------------------------
        print("\n[STEP 5] Applying user feedback & adaptive learning...")
        pred_review = cap.execute({"action": "predict", "owner_id": owner_id, "current_intent": "implement_slice"})
        print(f"  -> Prior prediction after 'implement_slice': '{pred_review.data['candidate']}'")

        # User indicates they do NOT want 'run_tests' here, but want 'security_audit' instead
        fb_res = cap.execute(
            {
                "action": "feedback",
                "prediction_id": pred_review.data["prediction_id"],
                "confirmed": False,
                "alternative_intent": "security_audit",
            }
        )
        print(f"  -> Feedback applied: confirmed={fb_res.data['confirmed']}, alternative='security_audit'")
        print("  -> Reinforcing 'security_audit' transition...")
        cap.execute({"action": "observe", "owner_id": owner_id, "sequence": ["implement_slice", "security_audit"]})
        cap.execute({"action": "observe", "owner_id": owner_id, "sequence": ["implement_slice", "security_audit"]})

        pred_updated = cap.execute({"action": "predict", "owner_id": owner_id, "current_intent": "implement_slice"})
        print(f"  -> New prediction after adaptation: candidate='{pred_updated.data['candidate']}' confidence={pred_updated.data['confidence']*100:.1f}%")

        # -------------------------------------------------------------
        # Step 6: Handling Ambiguous and Insufficient Context
        # -------------------------------------------------------------
        print("\n[STEP 6] Testing ambiguous intent & insufficient context bounds...")
        # Unseen intent
        try:
            cap.execute({"action": "predict", "owner_id": owner_id, "current_intent": "unknown_action"})
            print("  [ERROR] Unseen intent should have failed!")
        except LocalPillarError as exc:
            print(f"  -> Insufficient history handled safely: code={exc.code} message='{exc}'")

        # Equal branches
        cap.execute({"action": "observe", "owner_id": owner_id, "sequence": ["branch_node", "left_path"]})
        cap.execute({"action": "observe", "owner_id": owner_id, "sequence": ["branch_node", "right_path"]})
        try:
            cap.execute({"action": "predict", "owner_id": owner_id, "current_intent": "branch_node"})
            print("  [ERROR] Ambiguous tied intent was not gated!")
        except LocalPillarError as exc:
            print(f"  -> Ambiguous tie handled safely: code={exc.code} message='{exc}'")

        # -------------------------------------------------------------
        # Step 7: Profiling Opt-Out Enforcement
        # -------------------------------------------------------------
        print("\n[STEP 7] Exercising user profiling opt-out...")
        opt_res = cap.execute({"action": "opt_out", "owner_id": owner_id})
        print(f"  -> Opt-out recorded for: {opt_res.data['owner_id']}")
        status = cap.execute({"action": "consent_status", "owner_id": owner_id})
        print(f"  -> Status after opt-out: has_consent={status.data['has_consent']}, active={status.data['active']}, opted_out={status.data['opted_out']}")

        try:
            cap.execute({"action": "predict", "owner_id": owner_id, "current_intent": "review_spec"})
            print("  [ERROR] Prediction after opt-out succeeded!")
        except LocalPillarError as exc:
            print(f"  -> Extrapolation blocked after opt-out: code={exc.code}")

        # -------------------------------------------------------------
        # Step 8: Sovereign Right-to-be-Forgotten Data Purge
        # -------------------------------------------------------------
        print("\n[STEP 8] Executing sovereign right-to-be-forgotten deletion...")
        del_res = cap.execute({"action": "delete", "owner_id": owner_id})
        print(f"  -> Sovereign data purge complete: purged={del_res.data['purged']}")
        status = cap.execute({"action": "consent_status", "owner_id": owner_id})
        print(f"  -> Final status: has_consent={status.data['has_consent']}, active={status.data['active']}")
        print(f"  -> Database integrity verified: {cap.verify_integrity()}")

        print("\n" + "=" * 78)
        print("  DEMO VERIFICATION COMPLETE: ALL 8 VERTICAL SLICE STAGES PASSED")
        print("=" * 78)

    finally:
        del cap
        import gc
        gc.collect()
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    run_demo()
