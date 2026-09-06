#!/usr/bin/env python3
"""Interactive vertical slice demo for Pillar 34: Dynamic Sparsity MoE."""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402
from jaya_core.pillars.moe_capability import (  # noqa: E402
    MOE_CAPABILITY_ID,
    DynamicSparsityMoECapability,
)

DEMO_SIGNING_KEY = b"demo-sparse-moe-signing-key-32b!"


def _create_signed_expert(
    root: Path,
    expert_id: str,
    *,
    weights: list[list[float]],
    bias: list[float],
    routing: list[float],
    capacity: int = 5,
    key: bytes = DEMO_SIGNING_KEY,
) -> Path:
    manifest = {
        "schema_version": 1,
        "expert_id": expert_id,
        "version": "1.0",
        "task_kinds": ["RESEARCH_SCORE", "REASONING_SYNTHESIS"],
        "input_dimension": len(routing),
        "output_dimension": len(bias),
        "weight_matrix": weights,
        "bias": bias,
        "routing_vector": routing,
        "capacity": capacity,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    wrapper = {"manifest": manifest, "signature": sig}

    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{expert_id}.expert.json"
    target.write_text(json.dumps(wrapper, indent=2), encoding="utf-8")
    return target


def run_demo() -> None:
    print("=" * 80)
    print("  JAYA SYSTEM — PILAR 34: DYNAMIC SPARSITY MOE VERTICAL SLICE DEMO")
    print("=" * 80)

    work_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_p34_"))
    expert_root = work_dir / "experts"
    db_path = work_dir / "moe.sqlite3"

    try:
        # -------------------------------------------------------------
        # STAGE 1: Creating Signed Production Expert Artifacts
        # -------------------------------------------------------------
        print("\n[STAGE 1] Creating HMAC-SHA256 Signed Production Expert Artifacts...")
        # Expert 1: Logic Engine (prioritizes dimension 0)
        _create_signed_expert(
            expert_root,
            "logic-expert-01",
            weights=[[1.5, 0.1, 0.0], [0.0, 1.2, -0.1]],
            bias=[0.1, -0.1],
            routing=[1.0, 0.1, 0.0],
            capacity=3,
        )
        # Expert 2: Evidence Engine (prioritizes dimension 1)
        _create_signed_expert(
            expert_root,
            "evidence-expert-02",
            weights=[[0.2, 1.4, 0.1], [0.1, 1.0, 0.2]],
            bias=[0.0, 0.2],
            routing=[0.1, 1.0, 0.1],
            capacity=3,
        )
        # Expert 3: Risk Engine (prioritizes dimension 2)
        _create_signed_expert(
            expert_root,
            "risk-expert-03",
            weights=[[0.1, 0.2, 1.6], [0.3, 0.1, 0.9]],
            bias=[-0.1, 0.0],
            routing=[0.0, 0.2, 1.0],
            capacity=3,
        )
        print(f"  -> Generated 3 signed experts in: {expert_root.name}/")

        # -------------------------------------------------------------
        # STAGE 2: Capability Initialization and Discovery
        # -------------------------------------------------------------
        print("\n[STAGE 2] Initializing Dynamic Sparsity MoE and Verifying Signatures...")
        moe = DynamicSparsityMoECapability(
            expert_root=expert_root, database_path=db_path, signing_key=DEMO_SIGNING_KEY
        )
        healthy = moe.health_check()
        print(f"  -> Capability ID: {MOE_CAPABILITY_ID}")
        print(f"  -> Health Check: {'HEALTHY' if healthy else 'UNHEALTHY'}")
        experts = moe.experts()
        print(f"  -> Loaded Verified Experts ({len(experts)}):")
        for exp in experts:
            print(f"     - ID: {exp['expert_id']} (dim: {exp['input_dimension']}->{exp['output_dimension']}, capacity: {exp['capacity']}, digest: {exp['artifact_digest'][:24]}...)")
        assert healthy is True
        assert len(experts) == 3

        # -------------------------------------------------------------
        # STAGE 3: Dynamic Top-k Sparse Routing (Logic Vector)
        # -------------------------------------------------------------
        print("\n[STAGE 3] Executing Top-2 Sparse Routing for Logic-Aligned Vector...")
        logic_vec = [0.95, 0.15, 0.05]
        res_logic = moe.execute(
            {
                "action": "run",
                "task_kind": "RESEARCH_SCORE",
                "vector": logic_vec,
                "top_k": 2,
                "maximum_quality_regression": 1.0,
                "temperature": 0.5,
            }
        )
        print(f"  -> Run ID: {res_logic.data['run_id'][:16]}...")
        print(f"  -> Experts Available: {res_logic.data['experts_available']}")
        print(f"  -> Experts Executed: {res_logic.data['experts_executed']}")
        print(f"  -> Selected Experts:")
        for se in res_logic.data["selected_experts"]:
            print(f"     - {se['expert_id']}: routing weight = {se['routing_weight']:.4f}, latency = {se['latency_ns']} ns")
        print(f"  -> Output Vector: {res_logic.data['output']}")
        print(f"  -> Result Digest: {res_logic.data['result_digest'][:16]}...")
        assert res_logic.data["selected_experts"][0]["expert_id"] == "logic-expert-01"

        # -------------------------------------------------------------
        # STAGE 4: Observable Distinct Output Across Domains (Risk Vector)
        # -------------------------------------------------------------
        print("\n[STAGE 4] Executing Top-2 Sparse Routing for Risk-Aligned Vector...")
        risk_vec = [0.05, 0.15, 0.95]
        res_risk = moe.execute(
            {
                "action": "run",
                "task_kind": "RESEARCH_SCORE",
                "vector": risk_vec,
                "top_k": 2,
                "maximum_quality_regression": 1.0,
                "temperature": 0.5,
            }
        )
        print(f"  -> Selected Experts:")
        for se in res_risk.data["selected_experts"]:
            print(f"     - {se['expert_id']}: routing weight = {se['routing_weight']:.4f}, latency = {se['latency_ns']} ns")
        print(f"  -> Output Vector: {res_risk.data['output']}")
        diff = float(np.linalg.norm(np.array(res_logic.data["output"]) - np.array(res_risk.data["output"])))
        print(f"  -> Euclidean Distance between Logic & Risk Outputs: {diff:.4f}")
        assert res_risk.data["selected_experts"][0]["expert_id"] == "risk-expert-03"
        assert diff > 0.5

        # -------------------------------------------------------------
        # STAGE 5: Dense Baseline Comparison & Quality Regression
        # -------------------------------------------------------------
        print("\n[STAGE 5] Comparing Sparse Output vs Full Dense Baseline...")
        print(f"  -> Sparse Top-2 Output: {res_logic.data['output']}")
        print(f"  -> Dense (All 3) Output: {res_logic.data['dense_baseline']}")
        print(f"  -> Relative L2 Quality Regression: {res_logic.data['quality_regression']:.6f}")
        assert res_logic.data["quality_regression"] >= 0.0

        # -------------------------------------------------------------
        # STAGE 6: Dynamic Capacity Overflow & Rerouting
        # -------------------------------------------------------------
        print("\n[STAGE 6] Testing Dynamic Capacity Overflow & Rerouting...")
        print(f"  -> Simulating heavy load on logic-expert-01 (load: 5, capacity: 3)...")
        moe.set_expert_load("logic-expert-01", 5)

        res_overflow = moe.execute(
            {
                "action": "run",
                "task_kind": "RESEARCH_SCORE",
                "vector": logic_vec,
                "top_k": 2,
                "maximum_quality_regression": 1.0,
            }
        )
        sel_overflow = [e["expert_id"] for e in res_overflow.data["selected_experts"]]
        print(f"  -> Selected Experts (after overflow): {sel_overflow}")
        print(f"  -> Overflows Captured: {res_overflow.data['overflows']}")
        assert "logic-expert-01" not in sel_overflow
        assert sel_overflow == ["evidence-expert-02", "risk-expert-03"]
        assert len(res_overflow.data["overflows"]) == 1

        # Reset load
        moe.set_expert_load("logic-expert-01", 0)

        # -------------------------------------------------------------
        # STAGE 7: Tampered Signature & Corrupt Expert Rejection
        # -------------------------------------------------------------
        print("\n[STAGE 7] Testing Cryptographic Tamper Rejection on Forged Expert...")
        tampered_file = expert_root / "logic-expert-01.expert.json"
        raw_wrapper = json.loads(tampered_file.read_text(encoding="utf-8"))
        raw_wrapper["manifest"]["weight_matrix"][0][0] = 999.99  # Unauthorized modification
        tampered_file.write_text(json.dumps(raw_wrapper), encoding="utf-8")

        try:
            moe.experts()
            raise AssertionError("Should have rejected tampered expert artifact")
        except LocalPillarError as exc:
            print(f"  -> Successfully Caught Tamper: {exc.code} ({exc})")
            assert exc.code == "EXPERT_SIGNATURE_INVALID"

        # Restore valid expert
        _create_signed_expert(
            expert_root,
            "logic-expert-01",
            weights=[[1.5, 0.1, 0.0], [0.0, 1.2, -0.1]],
            bias=[0.1, -0.1],
            routing=[1.0, 0.1, 0.0],
            capacity=3,
        )

        # -------------------------------------------------------------
        # STAGE 8: Dimension Incompatibility & Unavailability Rejection
        # -------------------------------------------------------------
        print("\n[STAGE 8] Testing Dimension Incompatibility Rejection...")
        _create_signed_expert(
            expert_root,
            "incompat-expert",
            weights=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.5, 0.5, 0.5]],
            bias=[0.0, 0.0, 0.0],
            routing=[0.1, 0.1, 0.9],
        )
        try:
            moe.execute(
                {
                    "action": "run",
                    "task_kind": "RESEARCH_SCORE",
                    "vector": logic_vec,
                    "top_k": 2,
                }
            )
            raise AssertionError("Should have rejected incompatible output dimensions")
        except LocalPillarError as exc:
            print(f"  -> Successfully Caught Incompatible Expert: {exc.code} ({exc})")
            assert exc.code == "EXPERT_INCOMPATIBLE"

        (expert_root / "incompat-expert.expert.json").unlink()

        # -------------------------------------------------------------
        # STAGE 9: Cryptographic Receipts & Storage Integrity
        # -------------------------------------------------------------
        print("\n[STAGE 9] Verifying SQLite WAL Persistence & Cryptographic Receipts...")
        integrity = moe.verify_integrity()
        print(f"  -> Integrity Status: {integrity.data['status']}")
        print(f"  -> Receipts Checked: {integrity.data['receipts_checked']}")
        assert integrity.data["status"] == "HEALTHY"

        history = moe.history(limit=5)
        print(f"  -> Total Executed Runs in DB: {len(history['runs'])}")
        print(f"  -> Total Signed Receipts: {len(history['receipts'])}")
        print(f"  -> Total Audit Events: {len(history['audit_events'])}")

        utils = moe.utilization()
        print(f"  -> Expert Utilization Statistics:")
        for u in utils:
            print(f"     - [{u['expert_id']}] selected: {u['selected_count']}, execs: {u['execution_count']}, overflows: {u['overflow_count']}")

        print("\n" + "=" * 80)
        print("  ALL 9 VERTICAL SLICE STAGES COMPLETED SUCCESSFULLY!")
        print("  Pilar 34: Dynamic Sparsity MoE operational & verified.")
        print("=" * 80)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    run_demo()
