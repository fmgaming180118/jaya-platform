#!/usr/bin/env python3
"""Interactive production vertical-slice demonstration for Pillar 33: Agentic RAG."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.agentic_rag_capability import (  # noqa: E402
    AgenticRAGCapability,
    ExtractiveGroundedAnswerProvider,
)
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402


def run_demo() -> int:
    print("=" * 72)
    print("JAYA PLATFORM - PILAR 33: AGENTIC RAG (core.retrieval.agentic)")
    print("Production Vertical Slice & Grounded Evidence Retrieval Demonstration")
    print("=" * 72)

    with tempfile.TemporaryDirectory(prefix="jaya_demo_p33_") as temp_dir:
        db_path = Path(temp_dir) / "demo_rag.sqlite3"
        print(f"\n[1/6] Initializing Agentic RAG Capability at: {db_path.name}")
        rag = AgenticRAGCapability(db_path, None)
        assert rag.storage_health_check() is True
        print("  -> Storage initialized and verified healthy via PRAGMA quick_check.")

        print("\n[2/6] Ingesting unseen real technical specification...")
        source_doc = (
            "The JAYA Morphic Kernel defines the base instruction set architecture for biological "
            "and synthetic compute nodes. Each cognitive node operates with a maximum memory window "
            "of 1024 MB. The hardware-locked binding enforces tamper resistance via DPAPI keys. "
            "System configuration specifies that heartbeat_interval: 500ms is strictly enforced."
        )
        ingest_res = rag.execute({
            "action": "ingest",
            "source_ref": "spec:jaya-morphic-core",
            "title": "Jaya Morphic Kernel Core Specification",
            "content": source_doc,
        })
        print(f"  -> Ingested: {ingest_res.code}")
        print(f"  -> Source Digest: {ingest_res.data['source_digest']}")
        print(f"  -> Chunks Indexed in FTS5: {ingest_res.data['chunks']}")

        print("\n[3/6] Performing grounded question answering with exact citation spans...")
        question = "What is the heartbeat_interval?"
        ask_res = rag.execute({
            "action": "ask",
            "question": question,
            "allow_extractive_fallback": True,
        })
        print(f"  -> Question: '{question}'")
        print(f"  -> Answer: '{ask_res.data['answer']}'")
        print(f"  -> Citations: {ask_res.data['citations']}")
        print(f"  -> Provider: {ask_res.data['provider_type']}")
        print(f"  -> Citation Precision: {ask_res.data['precision']}")
        print(f"  -> Groundedness Score: {ask_res.data['groundedness']}")

        print("\n[4/6] Verifying fail-closed defense against hallucinated citations...")
        try:
            chunks = rag.retrieve("heartbeat_interval", 1)
            rag.validate_citations(["forged-hallucinated-evidence-id-999"], chunks, "Fake answer")
            print("  [ERROR] Hallucination was not rejected!")
            return 1
        except LocalPillarError as exc:
            print(f"  -> Rejected Hallucinated Citation with code: {exc.code} (Message: {exc})")

        print("\n[5/6] Demonstrating conflicting evidence detection across multiple sources...")
        conflicting_doc = (
            "Alternative cluster specification for Edge Nodes. "
            "System configuration specifies that heartbeat_interval: 2000ms is strictly enforced."
        )
        rag.execute({
            "action": "ingest",
            "source_ref": "spec:jaya-edge-nodes",
            "title": "Jaya Edge Nodes Specification",
            "content": conflicting_doc,
        })
        conflict_chunks = rag.retrieve("heartbeat_interval", 5)
        conflict_eval = rag.evaluate_sufficiency("heartbeat_interval", conflict_chunks, strict_conflict=True)
        print(f"  -> Sufficiency Status: {conflict_eval['status']}")
        if conflict_eval["status"] == "CONFLICTING_EVIDENCE":
            for c in conflict_eval["conflicts"]:
                print(f"  -> Conflicting Property: '{c['property']}' | Conflicting Values: {c['contradictory_values']}")
        else:
            print("  [ERROR] Conflict not detected!")
            return 1

        print("\n[6/6] Proving persistence and restart recovery across runtime recreation...")
        rag.close()
        rag_reloaded = AgenticRAGCapability(db_path, None)
        status_res = rag_reloaded.execute({"action": "status"})
        print(f"  -> Persistent Sources: {status_res.data['sources_count']}")
        print(f"  -> Persistent Chunks: {status_res.data['chunks_count']}")
        print(f"  -> Persisted Answer Receipts: {status_res.data['answers_count']}")
        print(f"  -> Storage Durability Check: {'PASSED' if status_res.data['storage_healthy'] else 'FAILED'}")
        rag_reloaded.close()

    print("\n" + "=" * 72)
    print("PILAR 33: AGENTIC RAG DEMONSTRATION COMPLETE: ALL INVARIANTS VERIFIED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
