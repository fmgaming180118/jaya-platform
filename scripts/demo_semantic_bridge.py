#!/usr/bin/env python3
"""Interactive vertical slice demo for Pillar 26 Semantic Bridge."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.cognitive.runtime import JayaCoreRuntime  # noqa: E402
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402
from jaya_core.pillars.semantic_bridge import (  # noqa: E402
    SEMANTIC_CAPABILITY_ID,
    SemanticBridgeCapability,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", default=str(ROOT / "artifacts" / "demo-semantic-bridge")
    )
    args = parser.parse_args()
    data_dir = Path(args.data_dir).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "semantic_demo.sqlite3"
    bridge = SemanticBridgeCapability(db_path)

    print("=" * 70)
    print(" PILAR 26: SEMANTIC BRIDGE — LIVE VERTICAL SLICE DEMO")
    print("=" * 70)
    print(f"Database: {db_path}\n")

    # Step 1: Ingest Fact, Hypothesis, and Inferred Claims
    print("1. Ingesting Multi-Source Documents with Epistemic Statuses...")
    sources = [
        (
            "doc:fact-1",
            "model:JayaTransformer -trained_on-> dataset:VerifiedTokens and evaluated_by person:Ada",
            None,
        ),
        (
            "doc:hypo-1",
            "hypothesis: concept:AGI -requires-> concept:SelfAwareness",
            None,
        ),
        (
            "doc:inf-1",
            "implies: model:JayaTransformer -accelerates-> concept:AutomatedResearch",
            None,
        ),
        (
            "doc:ambig-1",
            "person:Mercury authored artifact:ChemicalTreatise",
            None,
        ),
        (
            "doc:ambig-2",
            "concept:Mercury has_density concept:HeavyLiquid",
            None,
        ),
    ]

    for s_ref, content, ep_status in sources:
        req = {
            "action": "ingest",
            "source_ref": s_ref,
            "content": content,
            "namespace": "demo",
        }
        if ep_status:
            req["epistemic_status"] = ep_status
        res = bridge.execute(req)
        print(f"   [+] Ingested {s_ref:12s} | Method: {res.data['method']} | Entities: {len(res.data['entities'])} | Claims: {len(res.data['claims'])}")

    print()

    # Step 2: Query Claims by Epistemic Status
    print("2. Querying Epistemic Claims Distribution...")
    for st in ["FACT", "INFERENCE", "UNVERIFIED"]:
        claims = bridge.execute({"action": "query_claims", "epistemic_status": st})
        print(f"   Status {st:10s} -> Count: {claims.data['count']}")
        for c in claims.data["claims"][:2]:
            print(f"      - {c['subject_value']} ({c['subject_type']}) -[{c['predicate']}]-> {c['target_value']} ({c['target_type']}) [conf={c['confidence']}]")

    print()

    # Step 3: Entity Ambiguity Resolution
    print("3. Querying Ambiguous Entity 'Mercury' Across Sources...")
    ambig = bridge.execute({"action": "query", "value": "mercury", "namespace": "demo"})
    print(f"   Found matches: {len(ambig.data['matches'])} | Ambiguous: {ambig.data['ambiguous']} | Types: {ambig.data['candidate_types']}")
    print()

    # Step 4: Provenance Verification
    print("4. Verifying Exact Citation Spans and SHA-256 Digest...")
    prov = bridge.execute({"action": "verify_provenance", "source_ref": "doc:fact-1"})
    print(f"   Source: {prov.data['source_ref']}")
    print(f"   Digest: {prov.data['source_digest']}")
    print(f"   Spans Verified: {prov.data['entities_verified']} mentions, {prov.data['relations_verified']} relations, {prov.data['claims_verified']} claims")
    print(f"   Result: PROVENANCE {'VERIFIED' if prov.data['verified'] else 'FAILED'}\n")

    # Step 5: Failure Paths Drill
    print("5. Executing Failure Paths Drills...")
    # 5a. Tamper mention
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE semantic_mentions SET raw_text='tampered:Text' WHERE source_ref='doc:hypo-1'")
    try:
        bridge.execute({"action": "verify_provenance", "source_ref": "doc:hypo-1"})
        print("   [!] FAILED: Tampered citation was not caught!")
    except LocalPillarError as err:
        print(f"   [x] Tampered Citation Rejected: {err.code} ({err})")

    # 5b. Source conflict
    try:
        bridge.execute({"action": "ingest", "source_ref": "doc:fact-1", "content": "model:Different"})
        print("   [!] FAILED: Source conflict was not caught!")
    except LocalPillarError as err:
        print(f"   [x] Source Conflict Rejected: {err.code} ({err})")

    # 5c. Unsupported media
    try:
        bridge.execute({"action": "ingest", "source_ref": "doc:img", "content": "model:A", "media_type": "image/jpeg"})
        print("   [!] FAILED: Invalid media type was not caught!")
    except LocalPillarError as err:
        print(f"   [x] Unsupported Media Rejected: {err.code} ({err})")

    print()

    # Step 6: Canonical Vertical Slice Integration (P26 Semantic -> P27 Temporal -> P08 Holographic)
    print("6. Executing Canonical Vertical Slice: Integrated Memory Cycle...")
    core_db = data_dir / "core.sqlite3"
    runtime = JayaCoreRuntime(db_path=core_db, local_pillar_data_dir=data_dir / "pillars")
    now = time.time()
    try:
        cycle = runtime.execute_integrated_memory_cycle(
            {
                "source_ref": "demo:integrated-source",
                "content": "artifact:ArchitectureSpec -defines-> concept:CognitiveContinuity and model:JayaCore",
                "namespace": "demo-cycle",
                "record_id": f"temporal-demo-{uuid.uuid4().hex[:8]}",
                "event_id": f"memory-demo-{uuid.uuid4().hex[:8]}",
                "session_id": "session-demo",
                "goal_id": "goal-demo",
                "owner_id": "owner-demo",
                "policy": "internal",
                "base_score": 0.95,
                "confidence": 0.90,
                "observed_at": now,
                "evaluated_at": now,
                "decay_rate": 0.02,
                "sequence_number": 1,
            }
        )
        print(f"   Status:            {cycle['status']}")
        print(f"   Pillars Involved:  {cycle['pillars']}")
        print(f"   Semantic Digest:   {cycle['semantic']['source_digest']}")
        print(f"   Memory Cycle ID:   {cycle['cycle_id']}")
    finally:
        runtime.close()

    print("\n" + "=" * 70)
    print(" PILAR 26: SEMANTIC BRIDGE DEMONSTRATION COMPLETED SUCCESSFULLY")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
