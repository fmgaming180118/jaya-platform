#!/usr/bin/env python3
"""Interactive demonstration of Pillar 28 Self Bootstrapping lifecycle."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.maintenance_capabilities import SelfBootstrappingCapability

SIGNING_KEY = bytes(range(32))


def _sign(key: bytes, material: bytes) -> str:
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_bootstrap_"))
    bootstrap_root = temp_dir / "bootstrap"
    bootstrap_root.mkdir(parents=True, exist_ok=True)
    db_path = bootstrap_root / "bootstrap.sqlite3"
    rag_db = temp_dir / "rag.sqlite3"

    print("=" * 75)
    print(" JAYA COGNITIVE ARCHITECTURE — PILAR 28: SELF BOOTSTRAPPING DEMO")
    print("=" * 75)
    print(f"Bootstrap Root: {bootstrap_root}\n")

    rag = AgenticRAGCapability(rag_db, None)
    service = SelfBootstrappingCapability(bootstrap_root, db_path, SIGNING_KEY, rag)

    # Step 1: Ingest Evidence
    print("[1] Ingesting capability gap evidence into RAG...")
    rag.execute({
        "action": "ingest",
        "source_ref": "audit:gap-observational-stats",
        "title": "Observational mean gap",
        "content": "The cognitive organism requires a bounded declarative mean aggregation capability.",
    })
    evidence_id = rag.retrieve("declarative mean aggregation", 1)[0]["evidence_id"]
    print(f"    Evidence ID: {evidence_id}")

    # Step 2: Propose Declarative Candidate
    print("\n[2] Proposing declarative candidate capability (mean-aggregator-prod)...")
    prop_res = service.propose({
        "action": "propose",
        "candidate_id": "mean-aggregator-prod",
        "capability_id": "cognitive.math.mean",
        "capability_gap": "Bounded declarative mean calculation",
        "operation": "mean",
        "evidence_ids": [evidence_id],
        "acceptance_cases": [
            {"values": [10.0, 20.0, 30.0], "expected": 20.0},
            {"values": [100.0, 200.0], "expected": 150.0},
        ],
    })
    art_digest = prop_res.data["artifact_digest"]
    print(f"    Status:          {prop_res.code}")
    print(f"    Candidate ID:    {prop_res.data['candidate_id']}")
    print(f"    Artifact Digest: {art_digest}")

    # Step 3: Dependency Planning
    print("\n[3] Planning dependencies and checking offline default-deny policy...")
    plan_res = service.plan_dependencies({
        "action": "plan_dependencies",
        "candidate_id": "mean-aggregator-prod",
        "dependencies": [
            {"capability_id": "core.runtime.base", "depends_on": []},
            {"capability_id": "cognitive.math.mean", "depends_on": ["core.runtime.base"]},
        ],
    })
    print(f"    Status:          {plan_res.code}")
    print(f"    Execution Order: {plan_res.data['execution_order']}")
    print(f"    Offline Policy:  {plan_res.data['offline_policy']}")

    # Step 4: Sandbox Validation
    print("\n[4] Executing acceptance test cases in sandbox...")
    val_res = service.validate({
        "action": "validate",
        "candidate_id": "mean-aggregator-prod",
    })
    val_digest = val_res.data["validation_digest"]
    print(f"    Status:            {val_res.code}")
    print(f"    Passed:            {val_res.data['passed']}")
    print(f"    Validation Digest: {val_digest}")
    assert val_res.data["passed"] is True

    # Step 5: Atomic Staging
    print("\n[5] Staging candidate to staged/ folder...")
    stage_res = service.stage({
        "action": "stage",
        "candidate_id": "mean-aggregator-prod",
    })
    print(f"    Status:      {stage_res.code}")
    print(f"    Staged Path: {stage_res.data['staged_path']}")

    # Step 6: Owner Approval & Installation with Canary
    print("\n[6] Signing owner approval and installing candidate with canary check...")
    approver = "operator:alice"
    approval_id = "approval:upgrade-001"
    install_material = f"install|mean-aggregator-prod|{art_digest}|{val_digest}|{approval_id}|{approver}".encode()
    signature = _sign(SIGNING_KEY, install_material)

    install_res = service.install({
        "action": "install",
        "candidate_id": "mean-aggregator-prod",
        "approval_id": approval_id,
        "approved_by": approver,
        "signature": signature,
    })
    print(f"    Status:        {install_res.code}")
    print(f"    Canary Check:  {install_res.data['canary']}")
    print(f"    Capability ID: {install_res.data['capability_id']}")

    # Step 7: Runtime Invocation
    print("\n[7] Invoking installed capability on live test dataset...")
    test_values = [25.0, 75.0, 50.0, 100.0, 0.0]
    inv_res = service.invoke({
        "action": "invoke",
        "candidate_id": "mean-aggregator-prod",
        "values": test_values,
    })
    expected_val = 50.0
    print(f"    Input values: {test_values}")
    print(f"    Mean result:  {inv_res.data['result']} (Expected: {expected_val})")
    assert math.isclose(inv_res.data["result"], expected_val)

    # Step 8: Restart Durability & Metrics
    print("\n[8] Testing restart durability and querying catalog metrics...")
    restarted = SelfBootstrappingCapability(bootstrap_root, db_path, SIGNING_KEY, rag)
    assert restarted.health_check() is True
    metrics_res = restarted.metrics().data
    print(f"    Total Candidates: {metrics_res['total_candidates']}")
    print(f"    Installed:        {metrics_res['installed']}")

    # Step 9: Authorized Rollback
    print("\n[9] Executing authorized cryptographic rollback...")
    rb_id = "rollback:emergency-001"
    rb_material = f"rollback_bootstrap|mean-aggregator-prod|{art_digest}|{rb_id}|{approver}".encode()
    rb_sig = _sign(SIGNING_KEY, rb_material)

    rb_res = restarted.rollback({
        "action": "rollback",
        "candidate_id": "mean-aggregator-prod",
        "rollback_id": rb_id,
        "approved_by": approver,
        "signature": rb_sig,
    })
    print(f"    Status: {rb_res.code}")

    # Verify fail-closed post rollback
    retired_blocked = False
    try:
        restarted.invoke({
            "action": "invoke",
            "candidate_id": "mean-aggregator-prod",
            "values": [1.0, 2.0],
        })
    except LocalPillarError as exc:
        if exc.code == "CANDIDATE_CORRUPT":
            retired_blocked = True
    print(f"    Retired invocation fails closed: {retired_blocked}")
    assert retired_blocked is True

    print("\n" + "=" * 75)
    print(" DEMO COMPLETED SUCCESSFULLY — ZERO SELF-MODIFICATION, FULLY VERIFIED")
    print("=" * 75)

    shutil.rmtree(temp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
