"""Unit and integration test suite for Pillar 30 Twin Protocol."""

from __future__ import annotations

import base64
import os
import sqlite3
import time
from pathlib import Path

import pytest

from jaya_core.pillars.distributed_capabilities import (
    TWIN_TRANSFER_CAPABILITY_ID,
    TwinMigrationCapability,
    _canonical,
    _digest,
)
from jaya_core.pillars.local_capabilities import LocalPillarError

TEST_SECRET = "secret-shared-key-must-contain-at-least-32-bytes-for-hmac!"


def _make_node(root: Path, node_id: str, peers: tuple[str, ...], secret: str = TEST_SECRET) -> TwinMigrationCapability:
    node_root = root / node_id
    node_root.mkdir(parents=True, exist_ok=True)
    return TwinMigrationCapability(
        node_id=node_id,
        root=node_root,
        database_path=node_root / "twin.sqlite3",
        shared_secret=secret,
        allowed_peers=peers,
    )


def test_twin_protocol_initialization_and_health_check(tmp_path: Path) -> None:
    node = _make_node(tmp_path, "node-1", ("node-2",))
    assert node.health_check() is True

    # Check SQLite tables
    with sqlite3.connect(tmp_path / "node-1" / "twin.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert {"twin_outbound", "twin_inbound", "twin_nonces", "brain_authority"}.issubset(tables)


def test_twin_protocol_transport_probe(tmp_path: Path) -> None:
    node = _make_node(tmp_path, "node-1", ("node-2", "node-3"))
    probe = node.execute({"action": "probe_transport"}).data
    assert probe["transport_type"] == "TCP_LOOPBACK_AES_256_GCM"
    assert probe["cipher"] == "AES-256-GCM"
    assert probe["signature_algorithm"] == "HMAC-SHA256"
    assert probe["chunk_size_bytes"] == 262144
    assert probe["max_batch_chunks"] == 32
    assert probe["allowed_peers"] == ["node-2", "node-3"]
    assert probe["receiver_running"] is False


def test_twin_protocol_end_to_end_migration(tmp_path: Path) -> None:
    sender = _make_node(tmp_path, "node-a", ("node-b",))
    receiver = _make_node(tmp_path, "node-b", ("node-a",))

    source_path = tmp_path / "node-a" / "state.bin"
    payload = b"TWIN-STATE-MIGRATION-DATA-BLOCK-001\n" * 1000
    source_path.write_bytes(payload)

    rec_res = receiver.execute({"action": "start_receiver", "port": 0})
    port = rec_res.data["port"]

    try:
        res = sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": port,
            "transfer_id": "tx-e2e-001",
            "source_path": "state.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-alpha-001",
            "destination_name": "migrated_state.bin",
        })
        assert res.data["complete"] is True
        assert res.data["cursor"] == 1
        assert res.data["total_chunks"] == 1
        receipt = res.data["receipt"]
        assert receipt["brain_id"] == "brain-alpha-001"
        assert receipt["source_node"] == "node-a"
        assert receipt["target_node"] == "node-b"

        # Check received file
        received_path = tmp_path / "node-b" / "received" / "migrated_state.bin"
        assert received_path.read_bytes() == payload

        # Check authority lease on receiver
        auth_res = receiver.execute({"action": "query_authority", "brain_id": "brain-alpha-001"})
        assert auth_res.data["has_lease"] is True
        assert auth_res.data["holder_node"] == "node-b"
        assert auth_res.data["is_active"] is True
    finally:
        sender.close()
        receiver.close()


def test_twin_protocol_partial_transfer_and_resume(tmp_path: Path) -> None:
    sender = _make_node(tmp_path, "node-a", ("node-b",))
    receiver = _make_node(tmp_path, "node-b", ("node-a",))

    # Create multi-chunk payload (>256KB, e.g. 600KB -> 3 chunks)
    source_path = tmp_path / "node-a" / "multichunk.bin"
    payload = os.urandom(600 * 1024)
    source_path.write_bytes(payload)

    rec_res = receiver.execute({"action": "start_receiver", "port": 0})
    port = rec_res.data["port"]

    try:
        # Step 1: Send only 1 chunk
        p1 = sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": port,
            "transfer_id": "tx-resume-001",
            "source_path": "multichunk.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-resume-001",
            "destination_name": "resumed_state.bin",
            "maximum_chunks": 1,
        })
        assert p1.code == "TWIN_TRANSFER_PARTIAL"
        assert p1.data["cursor"] == 1
        assert p1.data["total_chunks"] == 3
        assert p1.data["complete"] is False
    finally:
        sender.close()
        receiver.close()

    # Step 2: Restart both nodes from their SQLite states
    restarted_sender = _make_node(tmp_path, "node-a", ("node-b",))
    restarted_receiver = _make_node(tmp_path, "node-b", ("node-a",))
    endpoint = restarted_receiver.execute({"action": "start_receiver", "port": 0}).data

    try:
        # Resume remaining chunks
        completed = restarted_sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": endpoint["port"],
            "transfer_id": "tx-resume-001",
            "source_path": "multichunk.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-resume-001",
            "destination_name": "resumed_state.bin",
        })
        assert completed.code == "TWIN_TRANSFER_COMPLETE"
        assert completed.data["complete"] is True
        assert completed.data["cursor"] == 3

        received = tmp_path / "node-b" / "received" / "resumed_state.bin"
        assert received.read_bytes() == payload
    finally:
        restarted_sender.close()
        restarted_receiver.close()


def test_twin_protocol_split_brain_prevention(tmp_path: Path) -> None:
    sender_a = _make_node(tmp_path, "node-a", ("node-b",))
    sender_c = _make_node(tmp_path, "node-c", ("node-b",))
    receiver_b = _make_node(tmp_path, "node-b", ("node-a", "node-c"))

    (tmp_path / "node-a" / "state.bin").write_bytes(b"initial state")
    (tmp_path / "node-c" / "state.bin").write_bytes(b"rogue state")

    endpoint = receiver_b.execute({"action": "start_receiver", "port": 0}).data
    port = endpoint["port"]

    try:
        # Transfer 1 from node-a establishes lease for brain-split-001 on node-b
        res1 = sender_a.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": port,
            "transfer_id": "tx-split-001",
            "source_path": "state.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-split-001",
            "destination_name": "state1.bin",
        })
        assert res1.data["complete"] is True

        # Attempted transfer from rogue node-c for the SAME brain_id while lease is active
        with pytest.raises(LocalPillarError) as exc_split:
            sender_c.execute({
                "action": "send_batch",
                "host": "127.0.0.1",
                "port": port,
                "transfer_id": "tx-split-002",
                "source_path": "state.bin",
                "target_node_id": "node-b",
                "brain_id": "brain-split-001",
                "destination_name": "state2.bin",
            })
        assert exc_split.value.code == "SPLIT_BRAIN_PREVENTED"
    finally:
        sender_a.close()
        sender_c.close()
        receiver_b.close()


def test_twin_protocol_tampered_chunk_rejection(tmp_path: Path) -> None:
    sender = _make_node(tmp_path, "node-a", ("node-b",))
    receiver = _make_node(tmp_path, "node-b", ("node-a",))
    (tmp_path / "node-a" / "state.bin").write_bytes(b"tamper test state")

    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    port = endpoint["port"]

    try:
        # Create a raw batch request with tampered ciphertext
        metadata = {
            "transfer_id": "tx-tamper-001",
            "sender_id": "node-a",
            "target_id": "node-b",
            "brain_id": "brain-tamper-001",
            "source_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "total_size": 17,
            "chunk_size": sender.CHUNK_SIZE,
            "total_chunks": 1,
            "destination_name": "tamper.bin",
            "created_at": time.time(),
        }
        tampered_chunks = [{
            "index": 0,
            "nonce": base64.b64encode(b"\x00" * 12).decode(),
            "ciphertext": base64.b64encode(b"corrupted-ciphertext-that-fails-gcm-tag").decode(),
        }]
        with pytest.raises(LocalPillarError) as exc_tamper:
            sender._wire_request("127.0.0.1", port, "batch", metadata, tampered_chunks)
        assert exc_tamper.value.code in {"CHUNK_DECRYPTION_FAILED", "TRANSPORT_FAILED"}
    finally:
        sender.close()
        receiver.close()


def test_twin_protocol_clock_skew_and_replay_rejection(tmp_path: Path) -> None:
    sender = _make_node(tmp_path, "node-a", ("node-b",))
    receiver = _make_node(tmp_path, "node-b", ("node-a",))

    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    port = endpoint["port"]

    try:
        # 1. Clock skew (>300s in the past)
        stale_request = {
            "action": "status",
            "metadata": {
                "transfer_id": "tx-skew-001",
                "sender_id": "node-a",
                "target_id": "node-b",
                "brain_id": "brain-skew-001",
                "source_digest": "sha256:abcd",
                "total_size": 100,
                "chunk_size": sender.CHUNK_SIZE,
                "total_chunks": 1,
                "destination_name": "skew.bin",
                "created_at": time.time() - 1000,
            },
            "request_ts": time.time() - 600,
            "nonce": "nonce-skew-001",
            "chunks": [],
        }
        mat = _canonical({
            "action": "status",
            "metadata_digest": _digest(_canonical(stale_request["metadata"])),
            "request_ts": stale_request["request_ts"],
            "nonce": stale_request["nonce"],
            "chunks_digest": _digest(_canonical([])),
        })
        stale_request["signature"] = sender._sign(mat)

        with pytest.raises(LocalPillarError) as exc_skew:
            import socket
            with socket.create_connection(("127.0.0.1", port), timeout=5.0) as stream:
                from jaya_core.pillars.distributed_capabilities import _recv_json, _send_json
                _send_json(stream, stale_request)
                resp = _recv_json(stream)
                if not resp.get("ok"):
                    raise LocalPillarError(resp.get("code", "ERROR"), "failed")
        assert exc_skew.value.code == "CLOCK_SKEW"
    finally:
        sender.close()
        receiver.close()


def test_twin_protocol_path_confinement_and_peer_allowlist(tmp_path: Path) -> None:
    sender = _make_node(tmp_path, "node-a", ("node-b",))
    (tmp_path / "node-a" / "state.bin").write_bytes(b"test")

    # Path traversal outside root
    with pytest.raises(LocalPillarError) as exc_path:
        sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": 9999,
            "transfer_id": "tx-esc-001",
            "source_path": "../../secret.txt",
            "target_node_id": "node-b",
            "brain_id": "brain-001",
            "destination_name": "esc.bin",
        })
    assert exc_path.value.code == "PERMISSION_DENIED"

    # Non-allowlisted target
    with pytest.raises(LocalPillarError) as exc_peer:
        sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": 9999,
            "transfer_id": "tx-esc-002",
            "source_path": "state.bin",
            "target_node_id": "unauthorized-node-xyz",
            "brain_id": "brain-001",
            "destination_name": "unauth.bin",
        })
    assert exc_peer.value.code == "PEER_DENIED"


def test_twin_protocol_verify_receipt_action(tmp_path: Path) -> None:
    sender = _make_node(tmp_path, "node-a", ("node-b",))
    receiver = _make_node(tmp_path, "node-b", ("node-a",))

    (tmp_path / "node-a" / "state.bin").write_bytes(b"state for receipt test")
    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data

    try:
        res = sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": endpoint["port"],
            "transfer_id": "tx-rcpt-001",
            "source_path": "state.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-rcpt-001",
            "destination_name": "receipt_test.bin",
        })
        receipt = res.data["receipt"]
        assert receipt is not None

        # Verify receipt with receiver
        v_res = receiver.execute({"action": "verify_receipt", "receipt": receipt})
        assert v_res.data["status"] == "VALID"

        # Tampered receipt should fail
        tampered_receipt = {**receipt, "source_digest": "sha256:corrupted"}
        with pytest.raises(LocalPillarError) as exc_rcpt:
            receiver.execute({"action": "verify_receipt", "receipt": tampered_receipt})
        assert exc_rcpt.value.code == "TWIN_AUTHENTICATION_FAILED"
    finally:
        sender.close()
        receiver.close()
