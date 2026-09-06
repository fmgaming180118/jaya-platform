#!/usr/bin/env python3
"""Vertical slice interactive demo for Pilar 32: Collective Pulse."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.distributed_capabilities import (
    CollectiveEvidenceCapability,
    LocalPillarError,
)
from jaya_core.pillars.reasoning_capabilities import AgenticRAGCapability

SHARED_SECRET = "jaya-collective-pulse-demo-key-32-chars-long!"


def _setup_node(temp_dir: Path, node_id: str, allowed_peers: tuple[str, ...]) -> tuple[CollectiveEvidenceCapability, AgenticRAGCapability, str]:
    node_dir = temp_dir / node_id
    node_dir.mkdir(parents=True, exist_ok=True)
    rag = AgenticRAGCapability(node_dir / "rag.sqlite3", None)
    rag.execute({
        "action": "ingest",
        "source_ref": "collective-pulse-demo-v1",
        "title": "Collective Intelligence Consensus",
        "content": "Consented peer evidence ground truth for collective pulse multi-node aggregation.",
    })
    evidence_id = rag.retrieve("collective intelligence consensus", 1)[0]["evidence_id"]
    cap = CollectiveEvidenceCapability(
        node_id=node_id,
        database_path=node_dir / "collective.sqlite3",
        shared_secret=SHARED_SECRET,
        allowed_peers=allowed_peers,
        rag=rag,
    )
    return cap, rag, evidence_id


def run_demo() -> int:
    print("=" * 70)
    print("  JAYA PILAR 32: COLLECTIVE PULSE — VERTICAL SLICE DEMO")
    print("=" * 70)
    print(f"[*] Workspace Root: {ROOT}")

    with tempfile.TemporaryDirectory(prefix="jaya_demo_p32_") as tmp:
        temp_dir = Path(tmp)
        print(f"[*] Ephemeral Root: {temp_dir}\n")

        # STAGE 1
        print("--- STAGE 1: TRI-NODE TOPOLOGY & ZERO-TRUST CONFIGURATION ---")
        node_a, _, evidence_a = _setup_node(temp_dir, "node-a", ("node-b", "node-c"))
        node_b, _, evidence_b = _setup_node(temp_dir, "node-b", ("node-a", "node-c"))
        node_c, _, evidence_c = _setup_node(temp_dir, "node-c", ("node-a", "node-b"))

        probe_b = node_b.execute({"action": "probe"}).data
        print(f"  [+] Node-B Status:            {probe_b['healthy']} (Capability: {probe_b['capability_id']})")
        print(f"  [+] Allowed Peers:            {probe_b['allowed_peers']}")
        print(f"  [+] Aggregation Strategy:     {probe_b['aggregation_strategy']}")
        print(f"  [+] Quorum Required:          {probe_b['min_peers_required']} peers minimum")
        print(f"  [+] Max Privacy Budget:       {probe_b['max_privacy_budget_per_node']} per node")
        print(f"  [+] Local Authority Weight:   {probe_b['local_authority_weight']} (Peer Median: {probe_b['peer_median_weight']})")

        # STAGE 2
        print("\n--- STAGE 2: EVIDENCE GROUNDING & CONSENT ISSUANCE ---")
        now = time.time()
        consent_a = node_a.execute({
            "action": "issue_consent",
            "evidence_id": evidence_a,
            "max_privacy_budget": 0.15,
            "expires_at": now + 3600,
        }).data["receipt"]
        print(f"  [+] Node-A Issued Consent:    Nonce={consent_a['nonce'][:12]}... Budget={consent_a['max_privacy_budget']}")
        print(f"  [+] Cryptographic Signature:  {consent_a['signature'][:16]}...")

        consent_c = node_c.execute({
            "action": "issue_consent",
            "evidence_id": evidence_c,
            "max_privacy_budget": 0.20,
            "expires_at": now + 3600,
        }).data["receipt"]
        print(f"  [+] Node-C Issued Consent:    Nonce={consent_c['nonce'][:12]}... Budget={consent_c['max_privacy_budget']}")

        # STAGE 3
        print("\n--- STAGE 3: SIGNED CONTRIBUTION PACKETS & SECURITY GUARDS ---")
        packet_a = node_a.execute({
            "action": "create",
            "evidence_id": evidence_a,
            "value": 0.72,
            "trust": 0.95,
            "quality": 0.90,
            "privacy_budget": 0.08,
            "consent_receipt": consent_a,
        }).data["packet"]
        print(f"  [+] Created Packet A:         Value={packet_a['value']}, Trust={packet_a['trust']}, Quality={packet_a['quality']}")

        packet_c = node_c.execute({
            "action": "create",
            "evidence_id": evidence_c,
            "value": 0.88,
            "trust": 0.92,
            "quality": 0.89,
            "privacy_budget": 0.10,
            "consent_receipt": consent_c,
        }).data["packet"]
        print(f"  [+] Created Packet C:         Value={packet_c['value']}, Trust={packet_c['trust']}, Quality={packet_c['quality']}")

        # Test poisoning rejection
        print("  [*] Testing Poisoning Guard (injecting low trust=0.30)...")
        poisoned = node_a.execute({
            "action": "create",
            "evidence_id": evidence_a,
            "value": 0.99,
            "trust": 0.30,
            "quality": 0.90,
            "privacy_budget": 0.05,
            "consent_receipt": consent_a,
        }).data["packet"]
        try:
            node_b.execute({"action": "ingest", "packet": poisoned})
            print("  [-] ERROR: Poisoning was not rejected!")
            return 1
        except LocalPillarError as exc:
            print(f"  [+] Successfully blocked: Code='{exc.code}', Message='{exc}'")

        # Ingest valid packets
        node_b.execute({"action": "ingest", "packet": packet_a})
        node_b.execute({"action": "ingest", "packet": packet_c})
        print("  [+] Valid packets from Node-A and Node-C successfully ingested into Node-B.")

        # STAGE 4
        print("\n--- STAGE 4: ROBUST MEDIAN AGGREGATION & LOCAL AUTHORITY PRESERVATION ---")
        local_val = 0.80
        agg_res = node_b.execute({
            "action": "aggregate",
            "local_evidence_id": evidence_b,
            "local_value": local_val,
        }).data
        print(f"  [+] Local Value:              {agg_res['local_value']}")
        print(f"  [+] Peer Count:               {agg_res['peer_count']}")
        print(f"  [+] Peer Median:              {agg_res['peer_median']:.4f} (from [0.72, 0.88])")
        print(f"  [+] Peer Spread:              {agg_res['spread']:.4f}")
        print(f"  [+] Conflict Detected:        {agg_res['conflict_detected']}")
        print(f"  [+] Final Recommendation:     {agg_res['recommendation']:.4f} (0.7 * 0.80 + 0.3 * 0.80)")
        print(f"  [+] Overrides Local Authority: {agg_res['overrides_local_authority']}")
        print(f"  [+] Total Privacy Spent:      {agg_res['privacy_budget_spent']:.4f}")
        print(f"  [+] Aggregate ID:             {agg_res['aggregate_id']}")

        # STAGE 5
        print("\n--- STAGE 5: CRYPTOGRAPHIC REVOCATION & NODE RESTART DURABILITY ---")
        print("  [*] Node-A issuing cryptographic revocation for its contribution...")
        rev_payload = node_a.create_revocation(str(packet_a["contribution_id"]))
        rev_res = node_b.execute({"action": "revoke", **rev_payload})
        print(f"  [+] Revocation Processed:     Code='{rev_res.code}', ContributionID='{rev_res.data['contribution_id']}'")

        print("  [*] Attempting aggregation after revocation (only 1 peer remains)...")
        try:
            node_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": local_val})
            print("  [-] ERROR: Aggregation succeeded without quorum!")
            return 1
        except LocalPillarError as exc:
            print(f"  [+] Quorum Enforced:          Code='{exc.code}', Message='{exc}'")

        print("  [*] Testing multi-node durability: restarting Node-B from persistent SQLite...")
        restarted_rag = AgenticRAGCapability(temp_dir / "node-b" / "rag.sqlite3", None)
        restarted_b = CollectiveEvidenceCapability(
            node_id="node-b",
            database_path=temp_dir / "node-b" / "collective.sqlite3",
            shared_secret=SHARED_SECRET,
            allowed_peers=("node-a", "node-c"),
            rag=restarted_rag,
        )
        contribs = restarted_b.execute({"action": "get_contributions", "include_revoked": True}).data
        print(f"  [+] Rehydrated Contributions: {contribs['count']} total records found in SQLite")
        aggs = restarted_b.execute({"action": "get_aggregates"}).data
        print(f"  [+] Rehydrated Aggregates:    {aggs['count']} historical recommendations in SQLite")

    print("\n" + "=" * 70)
    print("  COLLECTIVE PULSE VERTICAL SLICE DEMO COMPLETED SUCCESSFULLY")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
