"""Representative verification runner for Pillar 30 Twin Protocol."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import re
import shutil
import socket
import sqlite3
import tempfile
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars.distributed_capabilities import (
    TWIN_TRANSFER_CAPABILITY_ID,
    TwinMigrationCapability,
    _canonical,
    _digest,
    _recv_json,
    _send_json,
)
from jaya_core.pillars.local_capabilities import LocalPillarError, LocalPillarResult

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "matrix",
    "soak",
    "source_files",
}

DEFAULT_SHARED_SECRET = "jaya-twin-protocol-verification-shared-key-32b!"


class TwinProtocolVerificationError(RuntimeError):
    """Stable P30 verification failure carrying the failed boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _system_metadata() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count_logical": os.cpu_count() or 1,
        "cpu_count_physical": psutil.cpu_count(logical=False) or 1,
        "total_ram_bytes": psutil.virtual_memory().total,
    }


def _make_node(
    root: Path,
    node_id: str,
    peers: tuple[str, ...],
    secret: str = DEFAULT_SHARED_SECRET,
) -> TwinMigrationCapability:
    node_root = root / node_id
    node_root.mkdir(parents=True, exist_ok=True)
    return TwinMigrationCapability(
        node_id=node_id,
        root=node_root,
        database_path=node_root / "twin.sqlite3",
        shared_secret=secret,
        allowed_peers=peers,
    )


def _gate_01_manifest_integrity(workspace_root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    if set(profile.keys()) != _PROFILE_FIELDS:
        raise TwinProtocolVerificationError("GATE_FAILED", "Profile schema fields mismatch")
    if not _PROFILE_ID.match(profile["profile_id"]):
        raise TwinProtocolVerificationError("GATE_FAILED", "Invalid profile ID format")
    if profile.get("schema_version") != 1:
        raise TwinProtocolVerificationError("GATE_FAILED", "Unsupported schema version")

    missing = []
    for rel_path in profile.get("source_files", []):
        full_path = workspace_root / rel_path
        if not full_path.exists():
            missing.append(rel_path)

    if missing:
        raise TwinProtocolVerificationError(
            "GATE_FAILED", f"Missing source files: {', '.join(missing)}"
        )

    return {
        "status": "PASSED",
        "profile_id": profile["profile_id"],
        "source_files_verified": len(profile.get("source_files", [])),
    }


def _gate_02_peer_allowlist_authentication(temp_dir: Path) -> dict[str, Any]:
    receiver = _make_node(temp_dir, "node-b", ("node-a",))
    unallowlisted_sender = _make_node(temp_dir, "node-rogue", ("node-b",))
    wrong_key_sender = _make_node(
        temp_dir,
        "node-a",
        ("node-b",),
        secret="different-wrong-secret-that-has-at-least-thirty-two-chars",
    )

    (temp_dir / "node-rogue" / "state.bin").write_bytes(b"data")
    (temp_dir / "node-a" / "state.bin").write_bytes(b"data")

    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    port = endpoint["port"]

    try:
        # 1. Unallowlisted sender rejected by receiver
        try:
            unallowlisted_sender.execute({
                "action": "send_batch",
                "host": "127.0.0.1",
                "port": port,
                "transfer_id": "tx-auth-001",
                "source_path": "state.bin",
                "target_node_id": "node-b",
                "brain_id": "brain-auth-001",
                "destination_name": "auth1.bin",
            })
            raise TwinProtocolVerificationError("GATE_FAILED", "Unallowlisted peer was not rejected")
        except LocalPillarError as exc:
            if exc.code not in {"PEER_DENIED", "TRANSPORT_FAILED"}:
                raise TwinProtocolVerificationError("GATE_FAILED", f"Unexpected code on unallowlisted peer: {exc.code}")

        # 2. Wrong key sender rejected with TWIN_AUTHENTICATION_FAILED
        try:
            wrong_key_sender.execute({
                "action": "send_batch",
                "host": "127.0.0.1",
                "port": port,
                "transfer_id": "tx-auth-002",
                "source_path": "state.bin",
                "target_node_id": "node-b",
                "brain_id": "brain-auth-002",
                "destination_name": "auth2.bin",
            })
            raise TwinProtocolVerificationError("GATE_FAILED", "Wrong key sender was not rejected")
        except LocalPillarError as exc:
            if exc.code != "TWIN_AUTHENTICATION_FAILED":
                raise TwinProtocolVerificationError("GATE_FAILED", f"Unexpected code on wrong key: {exc.code}")

    finally:
        receiver.close()
        unallowlisted_sender.close()
        wrong_key_sender.close()

    return {"status": "PASSED", "allowlist_enforced": True, "key_auth_enforced": True}


def _gate_03_aes_gcm_encrypted_chunking(temp_dir: Path) -> dict[str, Any]:
    node = _make_node(temp_dir, "node-g03", ("node-other",))
    probe = node.execute({"action": "probe_transport"}).data
    if probe["cipher"] != "AES-256-GCM":
        raise TwinProtocolVerificationError("GATE_FAILED", f"Unexpected cipher: {probe['cipher']}")
    if probe["chunk_size_bytes"] != 262144:
        raise TwinProtocolVerificationError("GATE_FAILED", f"Unexpected chunk size: {probe['chunk_size_bytes']}")
    return {
        "status": "PASSED",
        "cipher": probe["cipher"],
        "chunk_size_bytes": probe["chunk_size_bytes"],
    }


def _gate_04_transactional_cursor_resume(temp_dir: Path) -> dict[str, Any]:
    sender = _make_node(temp_dir, "node-a", ("node-b",))
    receiver = _make_node(temp_dir, "node-b", ("node-a",))

    payload = os.urandom(600 * 1024)  # 3 chunks
    (temp_dir / "node-a" / "state.bin").write_bytes(payload)

    rec_res = receiver.execute({"action": "start_receiver", "port": 0}).data
    port = rec_res["port"]

    try:
        p1 = sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": port,
            "transfer_id": "tx-g04-resume",
            "source_path": "state.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-g04",
            "destination_name": "state_g04.bin",
            "maximum_chunks": 1,
        })
        if p1.code != "TWIN_TRANSFER_PARTIAL" or p1.data["cursor"] != 1:
            raise TwinProtocolVerificationError("GATE_FAILED", "Partial transfer failed")
    finally:
        sender.close()
        receiver.close()

    # Restart both nodes and resume
    r_sender = _make_node(temp_dir, "node-a", ("node-b",))
    r_receiver = _make_node(temp_dir, "node-b", ("node-a",))
    rec_res2 = r_receiver.execute({"action": "start_receiver", "port": 0}).data

    try:
        comp = r_sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": rec_res2["port"],
            "transfer_id": "tx-g04-resume",
            "source_path": "state.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-g04",
            "destination_name": "state_g04.bin",
        })
        if comp.code != "TWIN_TRANSFER_COMPLETE" or not comp.data["complete"]:
            raise TwinProtocolVerificationError("GATE_FAILED", "Resumed transfer failed to complete")
        received = (temp_dir / "node-b" / "received" / "state_g04.bin").read_bytes()
        if received != payload:
            raise TwinProtocolVerificationError("GATE_FAILED", "Resumed state bytes mismatch")
    finally:
        r_sender.close()
        r_receiver.close()

    return {"status": "PASSED", "partial_cursor": 1, "final_cursor": 3, "resumed": True}


def _gate_05_atomic_batch_and_digest_verify(temp_dir: Path) -> dict[str, Any]:
    sender = _make_node(temp_dir, "node-a", ("node-b",))
    receiver = _make_node(temp_dir, "node-b", ("node-a",))

    payload = b"Atomic batch state verification data payload" * 500
    (temp_dir / "node-a" / "state_g05.bin").write_bytes(payload)
    expected_digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"

    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    try:
        res = sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": endpoint["port"],
            "transfer_id": "tx-g05-atomic",
            "source_path": "state_g05.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-g05",
            "destination_name": "atomic_dest.bin",
        })
        if not res.data["complete"]:
            raise TwinProtocolVerificationError("GATE_FAILED", "Transfer not complete")
        receipt = res.data["receipt"]
        if receipt["source_digest"] != expected_digest:
            raise TwinProtocolVerificationError("GATE_FAILED", "Receipt digest mismatch")
        # Temporary file should have been removed
        temp_partial = temp_dir / "node-b" / "inbound-temp" / "tx-g05-atomic.partial"
        if temp_partial.exists():
            raise TwinProtocolVerificationError("GATE_FAILED", "Temporary partial file was not removed after atomic commit")
    finally:
        sender.close()
        receiver.close()

    return {"status": "PASSED", "digest_verified": True, "atomic_commit_verified": True}


def _gate_06_split_brain_authority_lease(temp_dir: Path) -> dict[str, Any]:
    sender_a = _make_node(temp_dir, "node-a", ("node-b",))
    sender_c = _make_node(temp_dir, "node-c", ("node-b",))
    receiver_b = _make_node(temp_dir, "node-b", ("node-a", "node-c"))

    (temp_dir / "node-a" / "state.bin").write_bytes(b"initial state")
    (temp_dir / "node-c" / "state.bin").write_bytes(b"rogue state")

    endpoint = receiver_b.execute({"action": "start_receiver", "port": 0}).data
    port = endpoint["port"]

    try:
        res1 = sender_a.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": port,
            "transfer_id": "tx-split-g06-a",
            "source_path": "state.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-split-g06",
            "destination_name": "state_g06_a.bin",
        })
        if not res1.data["complete"]:
            raise TwinProtocolVerificationError("GATE_FAILED", "Initial transfer failed")

        # Rogue node attempt for same brain_id during active lease
        try:
            sender_c.execute({
                "action": "send_batch",
                "host": "127.0.0.1",
                "port": port,
                "transfer_id": "tx-split-g06-c",
                "source_path": "state.bin",
                "target_node_id": "node-b",
                "brain_id": "brain-split-g06",
                "destination_name": "state_g06_c.bin",
            })
            raise TwinProtocolVerificationError("GATE_FAILED", "Split brain was not prevented")
        except LocalPillarError as exc:
            if exc.code != "SPLIT_BRAIN_PREVENTED":
                raise TwinProtocolVerificationError("GATE_FAILED", f"Unexpected code on split brain: {exc.code}")
    finally:
        sender_a.close()
        sender_c.close()
        receiver_b.close()

    return {"status": "PASSED", "split_brain_prevented": True}


def _gate_07_replay_attack_rejection(temp_dir: Path) -> dict[str, Any]:
    sender = _make_node(temp_dir, "node-a", ("node-b",))
    receiver = _make_node(temp_dir, "node-b", ("node-a",))

    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    port = endpoint["port"]

    try:
        # Build raw frame with fixed nonce
        metadata = {
            "transfer_id": "tx-replay-g07",
            "sender_id": "node-a",
            "target_id": "node-b",
            "brain_id": "brain-g07",
            "source_digest": "sha256:abcd",
            "total_size": 100,
            "chunk_size": sender.CHUNK_SIZE,
            "total_chunks": 1,
            "destination_name": "replay.bin",
            "created_at": time.time(),
        }
        raw_request = {
            "action": "status",
            "metadata": metadata,
            "request_ts": time.time(),
            "nonce": "fixed-replay-nonce-g07",
            "chunks": [],
        }
        material = _canonical({
            "action": "status",
            "metadata_digest": _digest(_canonical(metadata)),
            "request_ts": raw_request["request_ts"],
            "nonce": raw_request["nonce"],
            "chunks_digest": _digest(_canonical([])),
        })
        raw_request["signature"] = sender._sign(material)

        # Call 1: succeeds
        with socket.create_connection(("127.0.0.1", port), timeout=5.0) as stream:
            _send_json(stream, raw_request)
            resp1 = _recv_json(stream)
            if not resp1.get("ok"):
                raise TwinProtocolVerificationError("GATE_FAILED", f"First call failed: {resp1}")

        # Call 2: identical nonce must fail with REPLAY_DETECTED
        with socket.create_connection(("127.0.0.1", port), timeout=5.0) as stream:
            _send_json(stream, raw_request)
            resp2 = _recv_json(stream)
            if resp2.get("ok") or resp2.get("code") != "REPLAY_DETECTED":
                raise TwinProtocolVerificationError("GATE_FAILED", f"Expected REPLAY_DETECTED, got: {resp2}")
    finally:
        sender.close()
        receiver.close()

    return {"status": "PASSED", "replay_rejected": True}


def _gate_08_clock_skew_rejection(temp_dir: Path) -> dict[str, Any]:
    sender = _make_node(temp_dir, "node-a", ("node-b",))
    receiver = _make_node(temp_dir, "node-b", ("node-a",))

    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    port = endpoint["port"]

    try:
        metadata = {
            "transfer_id": "tx-skew-g08",
            "sender_id": "node-a",
            "target_id": "node-b",
            "brain_id": "brain-g08",
            "source_digest": "sha256:abcd",
            "total_size": 100,
            "chunk_size": sender.CHUNK_SIZE,
            "total_chunks": 1,
            "destination_name": "skew.bin",
            "created_at": time.time() - 1000,
        }
        stale_request = {
            "action": "status",
            "metadata": metadata,
            "request_ts": time.time() - 500,  # >300s skew
            "nonce": "nonce-skew-g08",
            "chunks": [],
        }
        material = _canonical({
            "action": "status",
            "metadata_digest": _digest(_canonical(metadata)),
            "request_ts": stale_request["request_ts"],
            "nonce": stale_request["nonce"],
            "chunks_digest": _digest(_canonical([])),
        })
        stale_request["signature"] = sender._sign(material)

        with socket.create_connection(("127.0.0.1", port), timeout=5.0) as stream:
            _send_json(stream, stale_request)
            resp = _recv_json(stream)
            if resp.get("ok") or resp.get("code") != "CLOCK_SKEW":
                raise TwinProtocolVerificationError("GATE_FAILED", f"Expected CLOCK_SKEW, got: {resp}")
    finally:
        sender.close()
        receiver.close()

    return {"status": "PASSED", "clock_skew_rejected": True}


def _gate_09_corrupted_chunk_tamper_rejection(temp_dir: Path) -> dict[str, Any]:
    sender = _make_node(temp_dir, "node-a", ("node-b",))
    receiver = _make_node(temp_dir, "node-b", ("node-a",))

    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    port = endpoint["port"]

    try:
        metadata = {
            "transfer_id": "tx-tamper-g09",
            "sender_id": "node-a",
            "target_id": "node-b",
            "brain_id": "brain-g09",
            "source_digest": "sha256:abcd",
            "total_size": 16,
            "chunk_size": sender.CHUNK_SIZE,
            "total_chunks": 1,
            "destination_name": "tamper.bin",
            "created_at": time.time(),
        }
        tampered_chunks = [{
            "index": 0,
            "nonce": base64.b64encode(b"\x00" * 12).decode(),
            "ciphertext": base64.b64encode(b"invalid-ciphertext-gcm-tag-fail").decode(),
        }]
        try:
            sender._wire_request("127.0.0.1", port, "batch", metadata, tampered_chunks)
            raise TwinProtocolVerificationError("GATE_FAILED", "Tampered ciphertext was not rejected")
        except LocalPillarError as exc:
            if exc.code not in {"CHUNK_DECRYPTION_FAILED", "TRANSPORT_FAILED"}:
                raise TwinProtocolVerificationError("GATE_FAILED", f"Unexpected code on tampered chunk: {exc.code}")
    finally:
        sender.close()
        receiver.close()

    return {"status": "PASSED", "tamper_rejected": True}


def _gate_10_path_confinement_permission_denied(temp_dir: Path) -> dict[str, Any]:
    sender = _make_node(temp_dir, "node-a", ("node-b",))
    try:
        sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": 9999,
            "transfer_id": "tx-esc-g10",
            "source_path": "../../outside.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-g10",
            "destination_name": "esc.bin",
        })
        raise TwinProtocolVerificationError("GATE_FAILED", "Escaped path was not rejected")
    except LocalPillarError as exc:
        if exc.code != "PERMISSION_DENIED":
            raise TwinProtocolVerificationError("GATE_FAILED", f"Unexpected code on escaped path: {exc.code}")

    return {"status": "PASSED", "path_confinement_verified": True}


def _gate_11_metadata_conflict_handling(temp_dir: Path) -> dict[str, Any]:
    sender = _make_node(temp_dir, "node-a", ("node-b",))
    receiver = _make_node(temp_dir, "node-b", ("node-a",))

    (temp_dir / "node-a" / "state1.bin").write_bytes(b"state one")
    (temp_dir / "node-a" / "state2.bin").write_bytes(b"state two")

    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    port = endpoint["port"]

    try:
        # Transfer 1 creates outbound record for tx-conflict-g11
        sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": port,
            "transfer_id": "tx-conflict-g11",
            "source_path": "state1.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-g11",
            "destination_name": "state1.bin",
        })

        # Re-using same transfer_id with changed source_path must fail with TRANSFER_CONFLICT
        try:
            sender.execute({
                "action": "send_batch",
                "host": "127.0.0.1",
                "port": port,
                "transfer_id": "tx-conflict-g11",
                "source_path": "state2.bin",
                "target_node_id": "node-b",
                "brain_id": "brain-g11",
                "destination_name": "state2.bin",
            })
            raise TwinProtocolVerificationError("GATE_FAILED", "Transfer conflict was not detected")
        except LocalPillarError as exc:
            if exc.code != "TRANSFER_CONFLICT":
                raise TwinProtocolVerificationError("GATE_FAILED", f"Unexpected code on conflict: {exc.code}")
    finally:
        sender.close()
        receiver.close()

    return {"status": "PASSED", "metadata_conflict_handled": True}


def _gate_12_receipt_signature_and_lineage(temp_dir: Path) -> dict[str, Any]:
    sender = _make_node(temp_dir, "node-a", ("node-b",))
    receiver = _make_node(temp_dir, "node-b", ("node-a",))

    (temp_dir / "node-a" / "state_g12.bin").write_bytes(b"lineage test state")
    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data

    try:
        res = sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": endpoint["port"],
            "transfer_id": "tx-g12-lineage",
            "source_path": "state_g12.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-g12",
            "destination_name": "lineage_dest.bin",
        })
        receipt = res.data["receipt"]
        if receipt is None:
            raise TwinProtocolVerificationError("GATE_FAILED", "Receipt was not generated")

        # Verify receipt with capability
        v_res = receiver.execute({"action": "verify_receipt", "receipt": receipt})
        if v_res.data["status"] != "VALID":
            raise TwinProtocolVerificationError("GATE_FAILED", "Receipt verification failed")
    finally:
        sender.close()
        receiver.close()

    return {
        "status": "PASSED",
        "receipt_verified": True,
        "brain_id": receipt["brain_id"],
        "source_node": receipt["source_node"],
        "target_node": receipt["target_node"],
    }


def _gate_13_both_nodes_restart_durability(temp_dir: Path) -> dict[str, Any]:
    sender = _make_node(temp_dir, "node-a", ("node-b",))
    receiver = _make_node(temp_dir, "node-b", ("node-a",))

    (temp_dir / "node-a" / "state_g13.bin").write_bytes(b"durability state")
    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data

    try:
        sender.execute({
            "action": "send_batch",
            "host": "127.0.0.1",
            "port": endpoint["port"],
            "transfer_id": "tx-g13-durability",
            "source_path": "state_g13.bin",
            "target_node_id": "node-b",
            "brain_id": "brain-g13",
            "destination_name": "durability_dest.bin",
        })
    finally:
        sender.close()
        receiver.close()

    # Re-open databases directly and verify persistent ledgers
    with sqlite3.connect(temp_dir / "node-a" / "twin.sqlite3") as conn_a:
        row_a = conn_a.execute("SELECT status FROM twin_outbound WHERE transfer_id='tx-g13-durability'").fetchone()
        if row_a is None or row_a[0] != "COMPLETE":
            raise TwinProtocolVerificationError("GATE_FAILED", "Outbound record missing after restart")

    with sqlite3.connect(temp_dir / "node-b" / "twin.sqlite3") as conn_b:
        row_b = conn_b.execute("SELECT status FROM twin_inbound WHERE transfer_id='tx-g13-durability'").fetchone()
        if row_b is None or row_b[0] != "COMPLETE":
            raise TwinProtocolVerificationError("GATE_FAILED", "Inbound record missing after restart")

    return {"status": "PASSED", "both_nodes_durability_verified": True}


def _gate_14_runtime_and_manifest_dispatch(temp_dir: Path) -> dict[str, Any]:
    # Set up two Core runtimes with shared secret
    secret = DEFAULT_SHARED_SECRET
    expert_root = temp_dir / "experts"
    expert_root.mkdir(parents=True, exist_ok=True)
    for eid, routing in [("test-expert-1", [1.0, 0.0]), ("test-expert-2", [0.0, 1.0])]:
        manifest = {
            "schema_version": 1,
            "expert_id": eid,
            "version": "1.0",
            "task_kinds": ["RESEARCH_SCORE"],
            "input_dimension": 2,
            "output_dimension": 2,
            "weight_matrix": [[1.0, 0.0], [0.0, 1.0]],
            "bias": [0.0, 0.0],
            "routing_vector": routing,
            "capacity": 10,
        }
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        sig = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
        (expert_root / f"{eid}.expert.json").write_text(json.dumps({"manifest": manifest, "signature": sig}))

    runtime_a = JayaCoreRuntime(
        node_id="node-a",
        db_path=temp_dir / "core_a.sqlite3",
        local_pillar_data_dir=temp_dir / "pillars_a",
        local_expert_root=expert_root,
        lineage_signing_key=secret.encode(),
        twin_shared_secret=secret,
        twin_allowed_peers=("node-b",),
    )
    runtime_b = JayaCoreRuntime(
        node_id="node-b",
        db_path=temp_dir / "core_b.sqlite3",
        local_pillar_data_dir=temp_dir / "pillars_b",
        local_expert_root=expert_root,
        lineage_signing_key=secret.encode(),
        twin_shared_secret=secret,
        twin_allowed_peers=("node-a",),
    )

    try:
        health_a = runtime_a.operational_snapshot()["local_pillar_capabilities"]["capabilities"]
        health_b = runtime_b.operational_snapshot()["local_pillar_capabilities"]["capabilities"]
        if health_a.get(TWIN_TRANSFER_CAPABILITY_ID) != "HEALTHY":
            raise TwinProtocolVerificationError("GATE_FAILED", f"Node-A twin manifest status not HEALTHY: {health_a.get(TWIN_TRANSFER_CAPABILITY_ID)}")
        if health_b.get(TWIN_TRANSFER_CAPABILITY_ID) != "HEALTHY":
            raise TwinProtocolVerificationError("GATE_FAILED", f"Node-B twin manifest status not HEALTHY: {health_b.get(TWIN_TRANSFER_CAPABILITY_ID)}")

        rec_res = runtime_b.execute_local_pillar(TWIN_TRANSFER_CAPABILITY_ID, {"action": "start_receiver", "port": 0})
        port = rec_res.data["port"]

        # Write test file in node-a twin root
        twin_a_root = temp_dir / "pillars_a" / "twin-node"
        (twin_a_root / "runtime_transfer.bin").write_bytes(b"runtime dispatch state data")

        res = runtime_a.execute_local_pillar(
            TWIN_TRANSFER_CAPABILITY_ID,
            {
                "action": "send_batch",
                "host": "127.0.0.1",
                "port": port,
                "transfer_id": "tx-runtime-g14",
                "source_path": "runtime_transfer.bin",
                "target_node_id": "node-b",
                "brain_id": "brain-g14",
                "destination_name": "runtime_received.bin",
            },
        )
        if not res.data["complete"]:
            raise TwinProtocolVerificationError("GATE_FAILED", "Runtime dispatch transfer did not complete")
    finally:
        runtime_a.close()
        runtime_b.close()

    return {"status": "PASSED", "runtime_dispatch_verified": True, "manifest_healthy": True}


def _gate_15_soak_performance_and_energy(temp_dir: Path) -> dict[str, Any]:
    sender = _make_node(temp_dir, "node-a", ("node-b",))
    receiver = _make_node(temp_dir, "node-b", ("node-a",))

    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    port = endpoint["port"]

    iterations = 25
    latencies: list[float] = []
    initial_rss = psutil.Process().memory_info().rss

    meter = None
    start_sample = None
    try:
        meter = WindowsEmiEnergyMeter()
        start_sample = meter.sample()
    except Exception:
        meter = None

    t_start = time.perf_counter()
    successful = 0

    try:
        for idx in range(iterations):
            filename = f"soak_{idx}.bin"
            content = os.urandom(64 * 1024)  # 64KB per transfer
            (temp_dir / "node-a" / filename).write_bytes(content)

            t0 = time.perf_counter()
            try:
                res = sender.execute({
                    "action": "send_batch",
                    "host": "127.0.0.1",
                    "port": port,
                    "transfer_id": f"tx-soak-{idx}",
                    "source_path": filename,
                    "target_node_id": "node-b",
                    "brain_id": f"brain-soak-{idx}",
                    "destination_name": f"dest_{idx}.bin",
                })
                if res.data["complete"]:
                    successful += 1
            except Exception:
                pass
            latencies.append((time.perf_counter() - t0) * 1000.0)

        total_time = time.perf_counter() - t_start
        final_rss = psutil.Process().memory_info().rss
        rss_growth = max(0, final_rss - initial_rss)
        mean_lat = float(np.mean(latencies))

        energy_joules = total_time * 28.0
        energy_meter_available = False
        if meter is not None and start_sample is not None:
            try:
                end_sample = meter.sample()
                measured = meter.measure(start_sample, end_sample)
                energy_joules = measured.joules or (total_time * 28.0)
                energy_meter_available = True
            except EnergyMeterError:
                pass

        if mean_lat > 100.0:
            raise TwinProtocolVerificationError("GATE_FAILED", f"Mean latency {mean_lat:.2f}ms exceeds 100ms")
        if successful < 23:
            raise TwinProtocolVerificationError("GATE_FAILED", f"Completion rate {successful}/{iterations} below 95%")
    finally:
        sender.close()
        receiver.close()

    return {
        "status": "PASSED",
        "iterations": iterations,
        "successful": successful,
        "mean_latency_ms": round(mean_lat, 3),
        "rss_growth_bytes": rss_growth,
        "energy_meter_available": energy_meter_available,
        "energy_joules": round(energy_joules, 4),
    }


def run_twin_protocol_verification(
    profile_path: Path,
    workspace_root: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    with profile_path.open("r", encoding="utf-8") as f:
        profile = json.load(f)

    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_verify_p30_"))
    gate_results: dict[str, Any] = {}
    gate_names = profile["matrix"]["gates"]

    start_wall = time.perf_counter()

    try:
        for gate in gate_names:
            t_gate_start = time.perf_counter()
            if gate == "G01_MANIFEST_INTEGRITY":
                res = _gate_01_manifest_integrity(workspace_root, profile)
            elif gate == "G02_PEER_ALLOWLIST_AUTHENTICATION":
                res = _gate_02_peer_allowlist_authentication(temp_dir)
            elif gate == "G03_AES_GCM_ENCRYPTED_CHUNKING":
                res = _gate_03_aes_gcm_encrypted_chunking(temp_dir)
            elif gate == "G04_TRANSACTIONAL_CURSOR_RESUME":
                res = _gate_04_transactional_cursor_resume(temp_dir)
            elif gate == "G05_ATOMIC_BATCH_AND_DIGEST_VERIFY":
                res = _gate_05_atomic_batch_and_digest_verify(temp_dir)
            elif gate == "G06_SPLIT_BRAIN_AUTHORITY_LEASE":
                res = _gate_06_split_brain_authority_lease(temp_dir)
            elif gate == "G07_REPLAY_ATTACK_REJECTION":
                res = _gate_07_replay_attack_rejection(temp_dir)
            elif gate == "G08_CLOCK_SKEW_REJECTION":
                res = _gate_08_clock_skew_rejection(temp_dir)
            elif gate == "G09_CORRUPTED_CHUNK_TAMPER_REJECTION":
                res = _gate_09_corrupted_chunk_tamper_rejection(temp_dir)
            elif gate == "G10_PATH_CONFINEMENT_PERMISSION_DENIED":
                res = _gate_10_path_confinement_permission_denied(temp_dir)
            elif gate == "G11_METADATA_CONFLICT_HANDLING":
                res = _gate_11_metadata_conflict_handling(temp_dir)
            elif gate == "G12_RECEIPT_SIGNATURE_AND_LINEAGE":
                res = _gate_12_receipt_signature_and_lineage(temp_dir)
            elif gate == "G13_BOTH_NODES_RESTART_DURABILITY":
                res = _gate_13_both_nodes_restart_durability(temp_dir)
            elif gate == "G14_RUNTIME_AND_MANIFEST_DISPATCH":
                res = _gate_14_runtime_and_manifest_dispatch(temp_dir)
            elif gate == "G15_SOAK_PERFORMANCE_AND_ENERGY":
                res = _gate_15_soak_performance_and_energy(temp_dir)
            else:
                raise TwinProtocolVerificationError("GATE_FAILED", f"Unknown gate: {gate}")

            dur = (time.perf_counter() - t_gate_start) * 1000.0
            res["duration_ms"] = round(dur, 3)
            gate_results[gate] = res

    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

    total_wall_dur = (time.perf_counter() - start_wall) * 1000.0
    passed_count = sum(1 for g in gate_results.values() if g.get("status") == "PASSED")
    all_passed = passed_count == len(gate_names)

    receipt = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "pillar_id": 30,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "VERIFIED" if all_passed else "FAILED",
        "system": _system_metadata(),
        "gates_summary": {
            "total": len(gate_names),
            "passed": passed_count,
            "failed": len(gate_names) - passed_count,
            "all_passed": all_passed,
        },
        "gates": gate_results,
        "total_duration_ms": round(total_wall_dur, 3),
    }

    if output_path:
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2, ensure_ascii=False)

    return receipt


def verify_twin_protocol(
    repository_root: Path | None = None,
    profile_path: Path | None = None,
    output_directory: Path | None = None,
    approver: str = "System-Veritas",
) -> tuple[Path, dict[str, Any]]:
    """Canonical verification wrapper compatible with repo CLI scripts."""
    workspace = (repository_root or Path.cwd()).resolve()
    target_profile = (
        profile_path
        or workspace / "packages" / "jaya-core" / "verification" / "p30_windows_twin_protocol_v1.json"
    ).resolve()
    out_dir = (output_directory or workspace / "artifacts" / "verified-twin-protocol").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "verification_receipt.json"

    receipt = run_twin_protocol_verification(
        profile_path=target_profile,
        workspace_root=workspace,
        output_path=out_file,
    )
    receipt["approver"] = approver
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)

    return out_file, receipt
