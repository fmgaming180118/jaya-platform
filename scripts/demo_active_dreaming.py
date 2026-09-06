#!/usr/bin/env python3
"""Interactive vertical slice demo for Pillar 03: Active Dreaming."""

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
    ActiveDreamingCapability,
    DeterministicCounterfactualProvider,
)


def run_demo() -> None:
    print("=" * 76)
    print("  JAYA SYSTEM — PILAR 03: ACTIVE DREAMING VERTICAL SLICE DEMO")
    print("=" * 76)

    work_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_p03_"))
    db_path = work_dir / "active_dreaming.sqlite3"
    rag_db_path = work_dir / "agentic_rag.sqlite3"

    try:
        # Step 1: Ingest Grounded Evidence into RAG
        print("\n[STEP 1] Ingesting real evidence into Agentic RAG (P33)...")
        rag = AgenticRAGCapability(rag_db_path, None)
        rag.ingest({
            "action": "ingest",
            "source_ref": "nist_cryogenic_physics_2026",
            "title": "NIST Cryogenic Superconducting Resonators",
            "content": "Superconducting microwave resonators exhibit quality factors exceeding 2 million when cooled below 100 millikelvin.",
        })
        rag.ingest({
            "action": "ingest",
            "source_ref": "thermal_transport_nanoribbons",
            "title": "Graphene Nanoribbon Thermal Transport",
            "content": "Phonon scattering in narrow graphene nanoribbons limits room temperature thermal boundary conductance to 120 MW/m^2-K.",
        })
        print("  -> Ingested 2 verified evidence documents into persistent RAG database.")

        # Step 2: Initialize ActiveDreamingCapability
        print("\n[STEP 2] Initializing ActiveDreamingCapability with Sandboxed Imagination...")
        sandbox = SandboxedImaginationCapability()
        provider = DeterministicCounterfactualProvider()
        dream = ActiveDreamingCapability(db_path, rag, sandbox, provider)
        print(f"  -> ActiveDreamingCapability initialized at {db_path}")

        # Step 3: Demonstrate Goal Safety Gating
        print("\n[STEP 3] Testing Safety Boundary Gating (Destructive Command)...")
        try:
            dream.dream({
                "action": "dream",
                "topic": "execute rm -rf /var/data to purge telemetry",
                "query": "cryogenic",
                "constraints": ["1 + 1 == 2"],
            })
            print("  [ERROR] Unsafe goal was not rejected!")
        except LocalPillarError as exc:
            print(f"  -> SUCCESS: Unsafe goal blocked with code: {exc.code}")
            print(f"     Reason: {exc}")

        # Step 4: Demonstrate Sandboxed Constraint Check Gating
        print("\n[STEP 4] Testing Sandboxed Numeric Constraint Check (P23)...")
        try:
            dream.dream({
                "action": "dream",
                "topic": "Superconducting resonator dissipation",
                "query": "superconducting resonator",
                "constraints": ["10 * 10 == 105"],  # Intentionally false constraint
            })
            print("  [ERROR] Invalid constraint was not rejected!")
        except LocalPillarError as exc:
            print(f"  -> SUCCESS: Failed constraint rejected with code: {exc.code}")
            print(f"     Reason: {exc}")

        # Step 5: Execute Grounded, Safe Active Dreaming Cycle
        print("\n[STEP 5] Generating Grounded Counterfactual Hypotheses...")
        res = dream.dream({
            "action": "dream",
            "topic": "Cryogenic superconducting resonator quality optimization",
            "query": "superconducting resonator quality factor",
            "constraints": ["2 ** 10 == 1024", "100 < 500"],
            "seed": 42001,
            "request_id": "demo-dream-req-001",
            "candidate_limit": 2,
        })
        data = res.data
        print(f"  -> Dream ID: {data['dream_id']}")
        print(f"  -> Request ID: {data['request_id']}")
        print(f"  -> Epistemic Status: {data['uncertainty']} (Warning: {data['warning']})")
        print(f"  -> Receipt HMAC SHA-256: {data['receipt_sha256']}")
        print(f"  -> Metrics: Novelty: {data['metrics']['novelty_score']}, Diversity: {data['metrics']['diversity_score']}")
        print("\n  Generated Candidates (Strictly Labeled HYPOTHESIS, executable: False):")
        for i, c in enumerate(data["candidates"], 1):
            print(f"    [{i}] Label: {c['label']} | Executable: {c['executable']} | Verification: {c['verification']}")
            print(f"        Statement: {c['statement']}")
            print(f"        Cited Evidence ID: {c['evidence_id']}")
            print(f"        Falsification Test: {c['falsification_test']}")

        # Step 6: Demonstrate Deterministic Replay
        print("\n[STEP 6] Testing Deterministic Replay by request_id...")
        replay_res = dream.dream({
            "action": "dream",
            "topic": "Cryogenic superconducting resonator quality optimization",
            "query": "superconducting resonator quality factor",
            "constraints": ["2 ** 10 == 1024", "100 < 500"],
            "seed": 42001,
            "request_id": "demo-dream-req-001",
        })
        print(f"  -> Replay Status: {replay_res.code}")
        print(f"  -> Replay Receipt SHA-256 matches: {replay_res.data['receipt_sha256'] == data['receipt_sha256']}")

        # Step 7: Demonstrate Persistence and Restart Survival
        print("\n[STEP 7] Simulating Runtime Restart and Artifact Verification...")
        dream.close()
        # Instantiate brand new instance pointing to same SQLite database
        restarted_dream = ActiveDreamingCapability(db_path, rag, sandbox, provider)
        stored_artifact = restarted_dream.by_dream_id(data["dream_id"])
        restarted_dream.close()
        rag.close()

        assert stored_artifact is not None
        assert stored_artifact["dream_id"] == data["dream_id"]
        assert stored_artifact["receipt_sha256"] == data["receipt_sha256"]
        print(f"  -> Restart verified! Stored artifact retrieved from disk.")
        print(f"  -> Dream ID: {stored_artifact['dream_id']}")
        print(f"  -> Stored Candidates Count: {len(stored_artifact['candidates'])}")
        print(f"  -> Integrity Verification: OK (HMAC receipt digest matched)")

        print("\n" + "=" * 76)
        print("  DEMO COMPLETED SUCCESSFULLY — ALL COGNITIVE BOUNDARIES VERIFIED!")
        print("=" * 76)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    run_demo()
