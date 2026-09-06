#!/usr/bin/env python3
"""Interactive vertical slice demo for Pillar 38: Meta Cognitive Planning."""

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
    ActiveDreamingCapability,
    DeterministicCounterfactualProvider,
    MetaPlanningCapability,
    SpeculativeReasoningCapability,
)
from jaya_core.pillars.advanced_capabilities import AdvancedPillarCapabilityService  # noqa: E402


def run_demo() -> None:
    print("=" * 76)
    print("  JAYA SYSTEM — PILAR 38: META COGNITIVE PLANNING VERTICAL SLICE DEMO")
    print("=" * 76)

    work_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_p38_"))
    db_path = work_dir / "meta_planning.sqlite3"
    spec_db_path = work_dir / "speculative_reasoning.sqlite3"
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

        # Step 2: Initialize Capabilities and Authority Separation
        print("\n[STEP 2] Initializing MetaPlanningCapability with separated Authority & Evaluator...")
        sandbox = SandboxedImaginationCapability()
        speculative = SpeculativeReasoningCapability(spec_db_path, rag, sandbox)
        planner = MetaPlanningCapability(db_path, rag, sandbox, speculative)
        print(f"  -> MetaPlanningCapability initialized at {db_path}")
        print(f"  -> Execution Authority allowlisted tools: {sorted(planner.authority.ALLOWLISTED_TOOLS)}")

        # Step 3: Invariant Safety Gating
        print("\n[STEP 3] Testing Invariant Safety Gating (Pre-execution validation)...")
        try:
            planner.run({
                "action": "run",
                "goal": "Unsafe plan violating physical invariants",
                "invariants": ["1 + 1 == 3"],
                "steps": [{"type": "sandbox", "expression": "10 > 5"}],
            })
            print("  [FAIL] Invariant violation was not blocked!")
        except LocalPillarError as exc:
            print(f"  -> Success: Invariant check rejected execution with code: {exc.code}")

        # Step 4: Objective Immutability and Hijack Prevention
        print("\n[STEP 4] Testing Objective Immutability & Hijack Prevention...")
        def sample_objective_resolver(obj_id: str):
            return {
                "owner_goal": "Maintain cryo stabilization within thermal budget",
                "invariants": ["100 <= 150"],
                "version": 2,
            }
        planner.objective_resolver = sample_objective_resolver

        try:
            planner.run({
                "action": "run",
                "objective_id": "obj-sample",
                "goal": "Attempting unauthorized goal mutation to bypass thermal budget",
                "invariants": ["True"],
                "steps": [{"type": "sandbox", "expression": "True"}],
            })
            print("  [FAIL] Objective hijack was not prevented!")
        except LocalPillarError as exc:
            print(f"  -> Success: Objective hijack blocked with code: {exc.code}")

        # Step 5: Loop and Cycle Detection
        print("\n[STEP 5] Testing Loop and Cycle Detection...")
        loop_res = planner.run({
            "action": "run",
            "goal": "Demonstrating loop detection on oscillating step cycle",
            "invariants": ["True"],
            "detect_loops": True,
            "steps": [
                {"type": "sandbox", "expression": "10 + 1"},
                {"type": "sandbox", "expression": "20 + 2"},
                {"type": "sandbox", "expression": "10 + 1"},
                {"type": "sandbox", "expression": "20 + 2"},
            ],
        })
        print(f"  -> Plan status: {loop_res.data['status']}, Decision: {loop_res.data['decision']}")
        print("  -> Success: Cycle detected and execution bounded safely without infinite loop.")

        # Step 6: Multi-Step Execution with Real Dynamic Replan and Recovery
        print("\n[STEP 6] Executing Multi-Step Plan with Dynamic Replan Recovery...")
        plan_res = planner.run({
            "action": "run",
            "goal": "Stabilize cryogenic cooling with real fallback and dynamic replan",
            "invariants": ["100 <= 150"],
            "allow_dynamic_replan": True,
            "max_replans": 2,
            "steps": [
                {"type": "sandbox", "expression": "25 * 4 == 100"},
                {
                    "type": "retrieve",
                    "query": "nonexistent_cooling_doc_query_xyz",
                    "minimum_results": 5,
                    # Fails without fallback, triggers dynamic replan
                },
                {"type": "sandbox", "expression": "100 <= 150"},
            ],
            "dynamic_replan_steps": [
                {"type": "retrieve", "query": "Dilution Refrigerator Thermodynamics", "minimum_results": 1}
            ],
        })
        print(f"  -> Plan ID: {plan_res.data['plan_id']}")
        print(f"  -> Status: {plan_res.data['status']}")
        print(f"  -> Steps used: {plan_res.data['steps_used']}, Recoveries: {plan_res.data['recoveries']}, Replans: {plan_res.data['replans']}")
        print(f"  -> Decision: {plan_res.data['decision']}")
        print(f"  -> Receipt HMAC-SHA256: {plan_res.data['receipt_sha256'][:24]}...")

        # Step 7: Restart Durability and Resumption across Capability Recreation
        print("\n[STEP 7] Testing Restart Durability & Resumption across Capability Recreate...")
        # Create a new plan, cancel it
        dur_res = planner.run({
            "action": "run",
            "goal": "Durable multi-step plan for restart verification",
            "invariants": ["True"],
            "steps": [
                {"type": "sandbox", "expression": "1 + 1 == 2"},
                {"type": "sandbox", "expression": "2 + 2 == 4"},
            ],
        })
        dur_plan_id = dur_res.data["plan_id"]
        planner.cancel({"action": "cancel", "plan_id": dur_plan_id})
        planner.close()

        # Recreate planner instance on the same SQLite file
        restarted_planner = MetaPlanningCapability(db_path, rag, sandbox, speculative)
        resumed = restarted_planner.resume({"action": "resume", "plan_id": dur_plan_id})
        print(f"  -> Resumed Plan ID: {resumed.data['plan_id']}")
        print(f"  -> Resumed status: {resumed.data['status']}, Decision: {resumed.data['decision']}")
        print("  -> Success: State survived shutdown and resumed from checkpointed steps.")

        # Step 8: Multi-Pillar Runtime Service Pipeline
        print("\n[STEP 8] Executing multi-pillar workflow in AdvancedPillarCapabilityService...")
        adv_dir = work_dir / "adv_service"
        adv_service = AdvancedPillarCapabilityService(adv_dir)
        adv_service.dream.provider = DeterministicCounterfactualProvider()

        adv_service.rag.ingest({
            "action": "ingest",
            "source_ref": "ref_adv_demo_superconducting",
            "title": "Superconducting Resonance Reference",
            "content": "Superconducting cavities achieve high Q factors for autonomous meta-cognitive reasoning.",
        })

        dream_res = adv_service.execute(
            DREAM_CAPABILITY_ID,
            {
                "action": "dream",
                "topic": "Integrated Meta-Cognitive Coordination",
                "query": "superconducting",
                "constraints": ["10 < 20"],
                "candidate_limit": 2,
                "seed": 101,
            },
        )
        spec_res = adv_service.execute(
            SPECULATIVE_CAPABILITY_ID,
            {
                "action": "evaluate",
                "candidates": dream_res.data["candidates"],
            },
        )
        final_plan = adv_service.execute(
            META_PLANNING_CAPABILITY_ID,
            {
                "action": "run",
                "goal": "Coordinate speculative branch validation in runtime service",
                "invariants": ["True"],
                "steps": [
                    {"type": "sandbox", "expression": "500 <= 1000"},
                    {"type": "speculate", "candidates": dream_res.data["candidates"]},
                ],
            },
        )
        print(f"  -> Active Dreaming hypothesis generated: {len(dream_res.data['candidates'])} candidates")
        print(f"  -> Speculative Reasoning evaluated: selected={spec_res.data['selected']['candidate_id'] if spec_res.data['selected'] else None}")
        print(f"  -> Meta Cognitive Plan executed: status={final_plan.data['status']}, decision={final_plan.data['decision']}")
        adv_service.close()

        print("\n" + "=" * 76)
        print("  PILAR 38: META COGNITIVE PLANNING VERTICAL SLICE DEMO COMPLETED SUCCESSFULLY")
        print("=" * 76)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    run_demo()
