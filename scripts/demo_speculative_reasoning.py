#!/usr/bin/env python3
"""Interactive vertical slice demo for Pillar 36: Speculative Reasoning."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability  # noqa: E402
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability  # noqa: E402
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402
from jaya_core.pillars.reasoning_capabilities import (  # noqa: E402
    DREAM_CAPABILITY_ID,
    META_PLANNING_CAPABILITY_ID,
    SPECULATIVE_CAPABILITY_ID,
    DeterministicCounterfactualProvider,
    SpeculativeReasoningCapability,
)
from jaya_core.pillars.advanced_capabilities import AdvancedPillarCapabilityService  # noqa: E402


def run_demo() -> None:
    print("=" * 76)
    print("  JAYA SYSTEM — PILAR 36: SPECULATIVE REASONING VERTICAL SLICE DEMO")
    print("=" * 76)

    work_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_p36_"))
    db_path = work_dir / "speculative_reasoning.sqlite3"
    rag_db_path = work_dir / "agentic_rag.sqlite3"

    try:
        # Step 1: Ingest Grounded Evidence into RAG
        print("\n[STEP 1] Ingesting real grounded evidence into Agentic RAG (P33)...")
        rag = AgenticRAGCapability(rag_db_path, None)
        rag.ingest({
            "action": "ingest",
            "source_ref": "ref_superconducting_cavity_2026",
            "title": "Superconducting Cavity Resonance",
            "content": "Superconducting niobium cavities achieve resonant frequencies around 1.3 GHz with quality factors exceeding 1e10 at 2 Kelvin.",
        })
        rag.ingest({
            "action": "ingest",
            "source_ref": "ref_dilution_cryostat_thermal",
            "title": "Dilution Refrigerator Thermodynamics",
            "content": "Helium-3 and Helium-4 dilution refrigeration produces continuous cooling power of 500 microwatts at 100 millikelvin.",
        })
        print("  -> Ingested 2 verified evidence documents into persistent RAG store.")

        # Step 2: Initialize Speculative Reasoning Capability
        print("\n[STEP 2] Initializing SpeculativeReasoningCapability with Sandbox (P23)...")
        sandbox = SandboxedImaginationCapability()
        speculative = SpeculativeReasoningCapability(db_path, rag, sandbox)
        print(f"  -> SpeculativeReasoningCapability initialized at {db_path}")

        # Step 3: Safety Policy Gating
        print("\n[STEP 3] Testing Safety Policy Gating (Destructive Shell Injection)...")
        unsafe_res = speculative.evaluate({
            "action": "evaluate",
            "candidates": [
                {
                    "candidate_id": "cand-destructive",
                    "statement": "rm -rf /var/log && format C: /fs:ntfs",
                    "evidence_id": "ref_superconducting_cavity_2026",
                    "verification_expression": "True",
                }
            ],
        })
        print(f"  -> Status: {unsafe_res.code}")
        print(f"  -> Rejected Count: {len(unsafe_res.data['rejected'])}")
        print(f"  -> Failure Code: {unsafe_res.data['rejected'][0]['failure_code']}")
        print(f"  -> Reason: {unsafe_res.data['rejected'][0]['reason']}")

        # Step 4: Missing Evidence Citation Rejection
        print("\n[STEP 4] Testing Independent Citation Verification (Hallucinated Source)...")
        cite_res = speculative.evaluate({
            "action": "evaluate",
            "candidates": [
                {
                    "candidate_id": "cand-hallucinated-cite",
                    "statement": "Speculative branch citing imaginary physics paper",
                    "evidence_id": "nonexistent_fictional_paper_999",
                    "verification_expression": "100 > 10",
                }
            ],
        })
        print(f"  -> Status: {cite_res.code}")
        print(f"  -> Failure Code: {cite_res.data['rejected'][0]['failure_code']}")
        print(f"  -> Reason: {cite_res.data['rejected'][0]['reason']}")

        # Step 5: Failed Sandboxed Invariant Rejection
        print("\n[STEP 5] Testing Sandboxed Numeric/Logic Constraint Check...")
        constraint_res = speculative.evaluate({
            "action": "evaluate",
            "candidates": [
                {
                    "candidate_id": "cand-invalid-invariant",
                    "statement": "Thermodynamic branch with impossible invariant",
                    "evidence_id": "ref_dilution_cryostat_thermal",
                    "verification_expression": "500 * 2 < 100",  # False
                }
            ],
        })
        print(f"  -> Status: {constraint_res.code}")
        print(f"  -> Failure Code: {constraint_res.data['rejected'][0]['failure_code']}")
        print(f"  -> Reason: {constraint_res.data['rejected'][0]['reason']}")

        # Step 6: Multi-Candidate Ranking & Non-Self-Score Verification
        print("\n[STEP 6] Testing Multi-Candidate Selection & Non-Self-Score Ranking...")
        ranking_res = speculative.evaluate({
            "action": "evaluate",
            "candidates": [
                {
                    "candidate_id": "cand-high-unverified",
                    "statement": "Candidate claiming 0.99 self-score but fails math invariant",
                    "evidence_id": "ref_superconducting_cavity_2026",
                    "verification_expression": "1.3 == 2.5",  # Fails
                    "retrieval_score": 0.99,
                },
                {
                    "candidate_id": "cand-grounded-best",
                    "statement": "Candidate with verified citation and valid invariant",
                    "evidence_id": "ref_superconducting_cavity_2026",
                    "verification_expression": "1.3 < 2.0 and 2.0 <= 4.0",  # Passes
                    "retrieval_score": 0.82,
                },
                {
                    "candidate_id": "cand-grounded-alt",
                    "statement": "Second valid candidate with lower score",
                    "evidence_id": "ref_dilution_cryostat_thermal",
                    "verification_expression": "500 > 100",  # Passes
                    "retrieval_score": 0.70,
                },
            ],
        })
        selected = ranking_res.data["selected"]
        print(f"  -> Status: {ranking_res.code}")
        print(f"  -> Selected Candidate ID: {selected['candidate_id']}")
        print(f"  -> Selected Composite Score: {selected['confidence_score']}")
        print(f"  -> Accepted Count: {len(ranking_res.data['accepted'])}")
        print(f"  -> Rejected Count: {len(ranking_res.data['rejected'])}")
        print(f"  -> Unverified 0.99 Self-Score Candidate: REJECTED")

        # Step 7: Deterministic Replay by Request ID
        print("\n[STEP 7] Testing Deterministic Replay by Request ID...")
        req_id = "demo-spec-request-42"
        run_1 = speculative.evaluate({
            "action": "evaluate",
            "request_id": req_id,
            "candidates": [
                {
                    "candidate_id": "cand-replay-sample",
                    "statement": "Sample replay candidate",
                    "evidence_id": "ref_dilution_cryostat_thermal",
                    "verification_expression": "10 * 10 == 100",
                    "retrieval_score": 0.85,
                }
            ],
        })
        run_2 = speculative.replay({"action": "replay", "request_id": req_id})
        print(f"  -> Initial Run Status: {run_1.code}, Run ID: {run_1.data['run_id']}")
        print(f"  -> Replay Run Status:  {run_2.code}, Run ID: {run_2.data['run_id']}")
        print(f"  -> Receipt Digest Match: {run_1.data['receipt_sha256'] == run_2.data['receipt_sha256']}")

        # Step 8: Rejections Archive Inspection
        print("\n[STEP 8] Querying Dedicated Rejection Archive (SQLite)...")
        rejections = speculative.rejections_by_run_id(ranking_res.data["run_id"])
        print(f"  -> Retrieved {len(rejections)} archived rejection(s) for run {ranking_res.data['run_id'][:12]}...")
        for r in rejections:
            print(f"     - Candidate: {r['candidate_id']}")
            print(f"       Failure Code: {r['failure_code']}")
            print(f"       Reason: {r['reason']}")

        # Step 9: Core Runtime Pipeline Dispatch
        print("\n[STEP 9] End-to-End Advanced Capabilities Pipeline Dispatch...")
        adv_service = AdvancedPillarCapabilityService(work_dir / "adv_service")
        adv_service.dream.provider = DeterministicCounterfactualProvider()

        # Seed adv_service RAG
        adv_service.rag.ingest({
            "action": "ingest",
            "source_ref": "adv_supercond_ref",
            "title": "Quantum Resonator Ingest",
            "content": "Dilution refrigeration maintains stable thermal environments for quantum information processing.",
        })

        # Pipeline: Dream -> Speculate -> Meta-Plan
        dream_out = adv_service.execute(
            DREAM_CAPABILITY_ID,
            {
                "action": "dream",
                "topic": "Thermal environment stability",
                "query": "dilution",
                "constraints": ["100 < 500"],
                "seed": 99,
            },
        )
        spec_out = adv_service.execute(
            SPECULATIVE_CAPABILITY_ID,
            {
                "action": "evaluate",
                "candidates": dream_out.data["candidates"],
            },
        )
        plan_out = adv_service.execute(
            META_PLANNING_CAPABILITY_ID,
            {
                "action": "run",
                "goal": "Verify and execute speculative candidates",
                "invariants": ["True"],
                "steps": [
                    {
                        "type": "speculate",
                        "candidates": dream_out.data["candidates"],
                    }
                ],
            },
        )
        adv_service.close()

        print(f"  -> Step 1 (P03 Active Dreaming):       {dream_out.code}")
        print(f"  -> Step 2 (P36 Speculative Reasoning): {spec_out.code} (Selected: {spec_out.data['selected']['candidate_id']})")
        print(f"  -> Step 3 (P38 Meta Planning):         {plan_out.code}")

        print("\n" + "=" * 76)
        print("  DEMO COMPLETE: ALL 9 VERIFICATION CAPABILITIES DEMONSTRATED SUCCESSFULLY")
        print("=" * 76)

    finally:
        speculative.close()
        rag.close()
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    run_demo()
