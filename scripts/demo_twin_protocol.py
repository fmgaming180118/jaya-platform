#!/usr/bin/env python3
"""Dedicated vertical slice demonstration for Pillar 30 Twin Protocol."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.distributed_capabilities import (  # noqa: E402
    TWIN_TRANSFER_CAPABILITY_ID,
    TwinMigrationCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402

DEMO_SECRET = "jaya-twin-demo-shared-key-must-have-thirty-two-bytes!"


def _make_node(root: Path, node_id: str, peers: tuple[str, ...]) -> TwinMigrationCapability:
    node_root = root / node_id
    node_root.mkdir(parents=True, exist_ok=True)
    return TwinMigrationCapability(
        node_id=node_id,
        root=node_root,
        database_path=node_root / "twin.sqlite3",
        shared_secret=DEMO_SECRET,
        allowed_peers=peers,
    )


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_p30_"))
    print("=" * 70)
    print("  JAYA PILAR 30: TWIN PROTOCOL — VERTICAL SLICE DEMO")
    print("=" * 70)
    print(f"[*] Workspace Root: {ROOT}")
    print(f"[*] Ephemeral Root: {temp_dir}")

    # -------------------------------------------------------------------------
    # Stage 1: Transport & Node Identity Configuration
    # -------------------------------------------------------------------------
    print("\n--- STAGE 1: TRANSPORT & NODE IDENTITY CONFIGURATION ---")
    node_a = _make_node(temp_dir, "node-a", ("node-b",))
    node_b = _make_node(temp_dir, "node-b", ("node-a", "node-c"))
    node_c = _make_node(temp_dir, "node-c", ("node-b",))

    probe = node_a.execute({"action": "probe_transport"}).data
    print(f"  [+] Transport:        {probe['transport_type']}")
    print(f"  [+] Cipher:           {probe['cipher']}")
    print(f"  [+] Signature:        {probe['signature_algorithm']}")
    print(f"  [+] Chunk Size:       {probe['chunk_size_bytes']} bytes ({probe['chunk_size_bytes'] / 1024:.0f} KB)")
    print(f"  [+] Max Batch Chunks: {probe['max_batch_chunks']}")
    print(f"  [+] Source Node:      node-a (allowed: {probe['allowed_peers']})")

    # -------------------------------------------------------------------------
    # Stage 2: Encrypted Chunking & Partial State Transfer
    # -------------------------------------------------------------------------
    print("\n--- STAGE 2: ENCRYPTED CHUNKING & PARTIAL TRANSFER ---")
    payload_size = 600 * 1024  # 600 KB -> 3 chunks (256KB + 256KB + 88KB)
    payload = os.urandom(payload_size)
    (temp_dir / "node-a" / "core_state.bin").write_bytes(payload)
    print(f"  [*] Created state file: core_state.bin ({payload_size / 1024:.1f} KB, expected 3 chunks)")

    rec_res = node_b.execute({"action": "start_receiver", "port": 0}).data
    port = rec_res["port"]
    print(f"  [+] Node-B receiver listening on 127.0.0.1:{port}")

    tx_id = "tx-twin-demo-001"
    brain_id = "brain-jaya-core-001"

    print("  [*] Sending 1 chunk only (simulating network interruption)...")
    partial_res = node_a.execute({
        "action": "send_batch",
        "host": "127.0.0.1",
        "port": port,
        "transfer_id": tx_id,
        "source_path": "core_state.bin",
        "target_node_id": "node-b",
        "brain_id": brain_id,
        "destination_name": "migrated_core_state.bin",
        "maximum_chunks": 1,
    })
    print(f"  [+] Result: {partial_res.code}")
    print(f"      - Cursor Committed: {partial_res.data['cursor']} / {partial_res.data['total_chunks']}")
    print(f"      - Transfer Complete: {partial_res.data['complete']}")

    # -------------------------------------------------------------------------
    # Stage 3: Dual-Node Shutdown, Restart & Resumption
    # -------------------------------------------------------------------------
    print("\n--- STAGE 3: DUAL-NODE RESTART & RESUMPTION FROM CURSOR ---")
    print("  [*] Shutting down Node-A and Node-B...")
    node_a.close()
    node_b.close()

    print("  [*] Re-instantiating Node-A and Node-B from SQLite state...")
    restarted_a = _make_node(temp_dir, "node-a", ("node-b",))
    restarted_b = _make_node(temp_dir, "node-b", ("node-a", "node-c"))

    rec_res2 = restarted_b.execute({"action": "start_receiver", "port": 0}).data
    port2 = rec_res2["port"]
    print(f"  [+] Node-B restarted on 127.0.0.1:{port2}")

    print("  [*] Resuming transfer from persistent cursor...")
    t0 = time.perf_counter()
    completed_res = restarted_a.execute({
        "action": "send_batch",
        "host": "127.0.0.1",
        "port": port2,
        "transfer_id": tx_id,
        "source_path": "core_state.bin",
        "target_node_id": "node-b",
        "brain_id": brain_id,
        "destination_name": "migrated_core_state.bin",
    })
    resume_ms = (time.perf_counter() - t0) * 1000.0
    print(f"  [+] Result: {completed_res.code} (in {resume_ms:.2f} ms)")
    print(f"      - Final Cursor: {completed_res.data['cursor']} / {completed_res.data['total_chunks']}")
    print(f"      - Complete:     {completed_res.data['complete']}")

    # -------------------------------------------------------------------------
    # Stage 4: Atomic Target Verification & Digest Assertion
    # -------------------------------------------------------------------------
    print("\n--- STAGE 4: ATOMIC TARGET VERIFICATION & RECEIPT ASSERTION ---")
    received_file = temp_dir / "node-b" / "received" / "migrated_core_state.bin"
    assert received_file.exists(), "Received file not found!"
    received_bytes = received_file.read_bytes()
    assert received_bytes == payload, "Received bytes mismatch!"
    print(f"  [+] Received File Size: {len(received_bytes)} bytes (exact match)")

    receipt = completed_res.data["receipt"]
    print(f"  [+] Receipt Source Node: {receipt['source_node']}")
    print(f"  [+] Receipt Target Node: {receipt['target_node']}")
    print(f"  [+] Receipt Digest:      {receipt['source_digest']}")

    v_res = restarted_b.execute({"action": "verify_receipt", "receipt": receipt})
    print(f"  [+] Receipt Cryptographic Verification: {v_res.data['status']}")

    # -------------------------------------------------------------------------
    # Stage 5: Authority Lease Handoff & Anti-Split-Brain
    # -------------------------------------------------------------------------
    print("\n--- STAGE 5: AUTHORITY LEASE HANDOFF & ANTI-SPLIT-BRAIN ---")
    auth = restarted_b.execute({"action": "query_authority", "brain_id": brain_id}).data
    print(f"  [+] Active Authority Holder: {auth['holder_node']}")
    print(f"  [+] Lease Active:            {auth['is_active']}")

    print("  [*] Attempting unauthorized transfer from Node-C for same brain_id...")
    (temp_dir / "node-c" / "rogue.bin").write_bytes(b"rogue data")
    try:
        node_c.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": port2,
            "transfer_id": "tx-rogue-001",
            "source_path": "rogue.bin",
            "target_node_id": "node-b",
            "brain_id": brain_id,
            "destination_name": "rogue.bin",
        })
        print("  [!] ERROR: Split brain was not prevented!")
        return 1
    except LocalPillarError as exc:
        print(f"  [+] Successfully blocked: Code='{exc.code}', Message='{exc}'")

    restarted_a.close()
    restarted_b.close()
    node_c.close()
    shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    print("  TWIN PROTOCOL VERTICAL SLICE DEMO COMPLETED SUCCESSFULLY")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
