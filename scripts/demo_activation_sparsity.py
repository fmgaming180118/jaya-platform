#!/usr/bin/env python3
"""Vertical slice demonstration for Pillar 35 Activation Sparsity."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.activation_sparsity import (  # noqa: E402
    ActivationSparsityCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_p35_"))
    db_path = temp_dir / "demo_activation_sparsity.sqlite3"
    print("=" * 70)
    print("  JAYA PILAR 35: ACTIVATION SPARSITY — VERTICAL SLICE DEMO")
    print("=" * 70)
    print(f"[*] Workspace Root: {ROOT}")
    print(f"[*] Ephemeral Database: {db_path}")

    cap = ActivationSparsityCapability(database_path=db_path)

    # -------------------------------------------------------------------------
    # Stage 1: Hardware Capability Probe
    # -------------------------------------------------------------------------
    print("\n--- STAGE 1: HARDWARE CAPABILITY PROBE ---")
    probe = cap.probe_hardware()
    print(f"  [+] Provider Type:       {probe['provider_type']}")
    print(f"  [+] Execution Mode:      {probe['execution_mode']}")
    print(f"  [+] Architecture:        {probe['architecture']}")
    print(f"  [+] CPU Logical Cores:   {probe['cpu_count_logical']}")
    print(f"  [+] SIMD Instructions:   {', '.join(probe['simd_instructions'])}")
    print(f"  [+] Labeled Fallback:    {probe['labeled_dense_fallback_available']}")

    # -------------------------------------------------------------------------
    # Stage 2: Top-K Sparse Activation vs Dense Baseline
    # -------------------------------------------------------------------------
    print("\n--- STAGE 2: TOP-K SPARSE ACTIVATION VS DENSE BASELINE ---")
    activations = [-12.5, 4.2, 0.1, -0.05, 8.7, -3.1, 0.4, -0.02, 15.0, -1.8]
    print(f"  [*] Input activations (len={len(activations)}): {activations}")

    res_relu = cap.execute({
        "action": "run",
        "values": activations,
        "top_k": 3,
        "operation": "relu",
        "maximum_quality_regression": 1.0,
    })
    print("  [+] Top-K Sparse ReLU (top_k=3):")
    print(f"      - Selected Indices:      {res_relu.data['indices']}")
    print(f"      - Operations Executed:   {res_relu.data['operations_executed']} (Dense: {res_relu.data['dense_operations']})")
    print(f"      - Compute Reduction:     {res_relu.data['compute_reduction'] * 100:.1f}%")
    print(f"      - Achieved Sparsity:     {res_relu.data['achieved_sparsity'] * 100:.1f}%")
    print(f"      - Quality Regression L2: {res_relu.data['quality_regression']:.4f}")
    print(f"      - Output Vector:         {res_relu.data['values']}")
    print(f"      - Receipt ID:            {res_relu.data['receipt_id']}")

    res_gelu = cap.execute({
        "action": "run",
        "values": activations,
        "top_k": 3,
        "operation": "gelu",
        "maximum_quality_regression": 1.0,
    })
    print("  [+] Top-K Sparse GELU (top_k=3):")
    print(f"      - Output Vector (sample): {[round(v, 3) for v in res_gelu.data['values'][:5]]}...")
    print(f"      - Compute Reduction:     {res_gelu.data['compute_reduction'] * 100:.1f}%")

    # -------------------------------------------------------------------------
    # Stage 3: Magnitude Threshold Gating
    # -------------------------------------------------------------------------
    print("\n--- STAGE 3: MAGNITUDE THRESHOLD GATING ---")
    threshold = 3.5
    print(f"  [*] Gating threshold: |x| >= {threshold}")
    res_thresh = cap.execute({
        "action": "run",
        "values": activations,
        "threshold": threshold,
        "operation": "identity",
        "maximum_quality_regression": 1.0,
    })
    print(f"  [+] Selected Indices:    {res_thresh.data['indices']}")
    print(f"  [+] Skipped Compute:     {res_thresh.data['compute_reduction'] * 100:.1f}% skipped")
    print(f"  [+] Output Vector:       {res_thresh.data['values']}")

    # -------------------------------------------------------------------------
    # Stage 4: Dense Quality Budgeting & Fail-Closed Security
    # -------------------------------------------------------------------------
    print("\n--- STAGE 4: DENSE QUALITY BUDGETING & FAIL-CLOSED SECURITY ---")
    uniform_vals = [2.0, 2.0, 2.0, 2.0]
    strict_budget = 0.05
    print(f"  [*] Attempting sparse execution with strict budget {strict_budget} on uniform activations...")
    try:
        cap.execute({
            "action": "run",
            "values": uniform_vals,
            "top_k": 1,
            "operation": "identity",
            "maximum_quality_regression": strict_budget,
        })
        print("  [!] ERROR: Expected QUALITY_BUDGET_EXCEEDED!")
        return 1
    except LocalPillarError as exc:
        print(f"  [+] Successfully rejected: Code='{exc.code}', Message='{exc}'")

    # -------------------------------------------------------------------------
    # Stage 5: Tamper-Evident Receipts & Restart Durability
    # -------------------------------------------------------------------------
    print("\n--- STAGE 5: TAMPER-EVIDENT RECEIPTS & DURABILITY ACROSS RESTART ---")
    int_res = cap.execute({"action": "verify_integrity"})
    print(f"  [+] Integrity Verification: {int_res.data['status']} ({int_res.data['receipts_checked']} receipts verified)")

    # Simulate restart
    cap.close()
    cap_restarted = ActivationSparsityCapability(database_path=db_path)
    try:
        hist = cap_restarted.execute({"action": "history", "limit": 10})
        print(f"  [+] Persisted Runs after Restart: {hist.data['count']}")
        int_restart = cap_restarted.execute({"action": "verify_integrity"})
        print(f"  [+] Integrity after Restart:      {int_restart.data['status']}")
    finally:
        cap_restarted.close()
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    print("  ACTIVATION SPARSITY VERTICAL SLICE DEMO COMPLETED SUCCESSFULLY")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
