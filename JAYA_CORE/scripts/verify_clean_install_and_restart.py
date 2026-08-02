"""
verify_clean_install_and_restart.py — Verifies clean installation & process restart state survival for Phase B.
"""

from __future__ import annotations

import gc
import json
import os
import sys
import tempfile
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

from src.cognitive.contracts import UserRequest
from src.cognitive.runtime import JayaCoreRuntime
from src.identity.models import AuthorityLevel, JayaIdentity, NodeClass, NodeIdentity, NodeRole


def run_clean_install_and_restart_verification() -> dict:
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "clean_install_episodic.db")

    try:
        # -------------------------------------------------------------
        # STEP 1: CLEAN INSTALLATION & INITIALIZATION (Zero-State)
        # -------------------------------------------------------------
        runtime1 = JayaCoreRuntime(
            db_path=db_path,
            node_id="target-prod-node-01",
            jaya_identity_id="jaya-owner-main",
            node_class=NodeClass.STANDARD,
        )
        is_ready_before = runtime1.is_ready()

        # Execute first user request to write state to SQLite
        req1 = UserRequest(
            request_id="req-clean-01",
            raw_prompt="Initial prompt before system restart drill",
            user_id="user-prod-01",
        )
        res1 = runtime1.process(req1)

        # -------------------------------------------------------------
        # STEP 2: SIMULATE PROCESS SHUTDOWN & RESTART
        # -------------------------------------------------------------
        # Explicitly close SQLite DB handle and tear down runtime1 instance
        runtime1.episodic_memory.close()
        del runtime1
        gc.collect()

        # Re-initialize fresh runtime pointing to the same persistent SQLite store
        runtime2 = JayaCoreRuntime(
            db_path=db_path,
            node_id="target-prod-node-01",
            jaya_identity_id="jaya-owner-main",
            node_class=NodeClass.STANDARD,
        )
        is_ready_after = runtime2.is_ready()

        # Query episodic memory to verify event survival pasca-restart
        events_after = runtime2.episodic_memory.get_recent_events(limit=10)
        event_survived = any(e.event_id is not None for e in events_after)

        # Execute second request post-restart
        req2 = UserRequest(
            request_id="req-clean-02",
            raw_prompt="Follow-up prompt after process restart drill",
            user_id="user-prod-01",
        )
        res2 = runtime2.process(req2)

        runtime2.episodic_memory.close()
        del runtime2
        gc.collect()

        results = {
            "clean_install_status": "SUCCESS" if is_ready_before else "FAILED",
            "process_restart_status": "SUCCESS" if is_ready_after else "FAILED",
            "state_survival_status": "SUCCESS" if event_survived else "FAILED",
            "initial_request_status": res1.status.value if hasattr(res1.status, "value") else str(res1.status),
            "post_restart_request_status": res2.status.value if hasattr(res2.status, "value") else str(res2.status),
            "persisted_events_count": len(events_after),
            "db_path": db_path,
        }

        return results
    finally:
        try:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def main() -> int:
    print("VERIFIKASI CLEAN INSTALL DAN RESTART DRILL...")
    res = run_clean_install_and_restart_verification()
    print(json.dumps(res, indent=2))

    if (
        res["clean_install_status"] == "SUCCESS"
        and res["process_restart_status"] == "SUCCESS"
        and res["state_survival_status"] == "SUCCESS"
    ):
        print("\nClean install dan process restart drill VERIFIED SUCCESSFUL!")
        return 0

    print("\nClean install dan process restart drill FAILED!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
