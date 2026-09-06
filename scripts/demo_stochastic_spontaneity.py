#!/usr/bin/env python3
"""Interactive production vertical-slice demonstration for Pillar 06: Stochastic Spontaneity."""

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

from jaya_core.brain_v2.engine.spontaneity import (  # noqa: E402
    ExplorationBudget,
    ExplorationError,
    ExplorationReceiptStore,
    ExplorationRequest,
    SpontaneityEngine,
)
from jaya_core.verification.stochastic_spontaneity import (  # noqa: E402
    DeterministicSeededVerificationProvider,
)


def run_demo() -> int:
    print("=" * 74)
    print("JAYA PLATFORM - PILAR 06: STOCHASTIC SPONTANEITY (core.exploration.spontaneous)")
    print("Production Vertical Slice, Seeded PRNG Replay, & Safety Review Demonstration")
    print("=" * 74)

    with tempfile.TemporaryDirectory(prefix="jaya_demo_p06_", ignore_cleanup_errors=True) as temp_dir:
        db_path = Path(temp_dir) / "demo_spontaneity.sqlite3"
        print(f"\n[1/7] Initializing Spontaneity Receipt Store at: {db_path.name}")
        provider = DeterministicSeededVerificationProvider()
        store = ExplorationReceiptStore(db_path)
        engine = SpontaneityEngine(store, provider)
        health = store.healthcheck()
        print(f"  -> SQLite Storage Health: {health['ok']} (Schema v{health['schema_version']})")

        print("\n[2/7] Verifying pre-execution fail-closed gate enforcement...")
        unauth_res = engine.explore(
            ExplorationRequest(topic="unauthorized inquiry", authorized=False)
        )
        print(f"  -> Unauthorized attempt blocked: {unauth_res['status']}")

        silence_res = engine.explore(
            ExplorationRequest(topic="silence inquiry", authorized=True, silence_active=True)
        )
        print(f"  -> Cognitive silence attempt blocked: {silence_res['status']}")

        no_model_engine = SpontaneityEngine(store, None)
        no_model_res = no_model_engine.explore(
            ExplorationRequest(topic="missing model", authorized=True)
        )
        print(f"  -> Unconfigured model attempt blocked: {no_model_res['status']} (Never fabricates!)")

        print("\n[3/7] Generating bounded candidates with deterministic seed 4242...")
        topic = "quantum dot topological insulators"
        exp_res = engine.explore(
            ExplorationRequest(
                topic=topic,
                authorized=True,
                seed=4242,
                request_id="demo-seed-4242",
                budget=ExplorationBudget(max_candidates=2),
                evidence_ids=("ev-spec-001", "ev-spec-002"),
            )
        )
        print(f"  -> Status: {exp_res['status']} | Label: {exp_res['label']}")
        print(f"  -> Generated {len(exp_res['candidates'])} candidates:")
        for idx, cand in enumerate(exp_res["candidates"]):
            meta = cand["metadata"]
            print(f"     [{idx + 1}] Hypothesis: '{cand['hypothesis_text']}'")
            print(f"         Label: {meta['label']} | Status: {meta['evidence_status']} | Executable: {meta['executable']}")
            print(f"         Confidence: {cand['confidence']} ({meta['confidence_kind']})")
        metrics = exp_res["metrics"]
        print(f"  -> Metrics: Novelty={metrics['novelty_score']} | Diversity={metrics['diversity_score']} | Acceptance={metrics['acceptance_rate']}")

        print("\n[4/7] Testing deterministic replay with identical request_id...")
        replay_res = engine.explore(
            ExplorationRequest(
                topic=topic,
                authorized=True,
                seed=4242,
                request_id="demo-seed-4242",
            )
        )
        print(f"  -> Replay Status: {replay_res['status']}")
        print(f"  -> Verified receipt SHA-256: {replay_res['receipt']['receipt_sha256'][:24]}...")
        assert replay_res["status"] == "REPLAYED_RECEIPT"

        print("\n[5/7] Safety Review: evaluating candidate with destructive shell action...")
        unsafe_provider = DeterministicSeededVerificationProvider(unsafe_candidate=True)
        unsafe_engine = SpontaneityEngine(store, unsafe_provider)
        unsafe_res = unsafe_engine.explore(
            ExplorationRequest(
                topic="adversarial security evaluation",
                authorized=True,
                seed=9999,
                request_id="demo-unsafe-test",
            )
        )
        for c in unsafe_res["candidates"]:
            m = c["metadata"]
            status_tag = "REJECTED" if not m["retained"] else "ACCEPTED"
            print(f"  -> [{status_tag}] '{c['hypothesis_text']}'")
            if not m["retained"]:
                print(f"     Rejection Reason: {m['rejection_reason']} (Label: {m['label']})")
        print(f"  -> Safety Acceptance Rate: {unsafe_res['metrics']['acceptance_rate']}")

        print("\n[6/7] Duplicate Detection across historical receipts...")
        dup_res = engine.explore(
            ExplorationRequest(
                topic=topic,
                authorized=True,
                seed=4242,
                request_id="demo-seed-4242-duplicate",
                budget=ExplorationBudget(max_candidates=2),
            )
        )
        print(f"  -> Duplicate run novelty score: {dup_res['metrics']['novelty_score']}")
        print(f"  -> Duplicate run accepted candidates: {dup_res['metrics']['accepted_candidates']}")
        assert dup_res["metrics"]["novelty_score"] == 0.0

        print("\n[7/7] Verifying tamper detection and persistent receipt durability...")
        store.close()
        # Tamper with the database
        conn = sqlite3.connect(db_path)
        with conn:
            conn.execute("UPDATE exploration_receipts SET seed = 12345 WHERE request_id = 'demo-seed-4242'")
        conn.close()

        reopened_store = ExplorationReceiptStore(db_path)
        tamper_detected = False
        try:
            reopened_store.by_request_id("demo-seed-4242")
        except ExplorationError as exc:
            if exc.code == "STORAGE_CORRUPT":
                tamper_detected = True
                print(f"  -> Tamper detection SUCCESS: caught '{exc.code}' ({exc})")

        assert tamper_detected is True
        reopened_store.close()

    print("\n" + "=" * 74)
    print("ALL PILAR 06 DEMONSTRATION STEPS COMPLETED SUCCESSFULLY!")
    print("STATUS: VERIFIED (Strict Evidence-Aware, Seeded PRNG, Safety-Gated)")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
