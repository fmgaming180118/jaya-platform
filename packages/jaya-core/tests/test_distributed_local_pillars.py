"""Real loopback transport and evidence federation tests for P30 and P32."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.distributed_capabilities import (
    COLLECTIVE_EVIDENCE_CAPABILITY_ID,
    TWIN_TRANSFER_CAPABILITY_ID,
    CollectiveEvidenceCapability,
    TwinMigrationCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError

SHARED_SECRET = "test-distributed-secret-with-at-least-thirty-two-characters"
SOURCE_CONTENT = (
    "Collective measurements are accepted only with evidence, consent, trust, quality, "
    "and a bounded privacy budget. The local node retains final authority."
)


def _twin(
    tmp_path: Path,
    node_id: str,
    peers: tuple[str, ...],
    *,
    secret: str = SHARED_SECRET,
) -> TwinMigrationCapability:
    root = tmp_path / node_id
    return TwinMigrationCapability(
        node_id=node_id,
        root=root,
        database_path=root / "twin.sqlite3",
        shared_secret=secret,
        allowed_peers=peers,
        timeout_seconds=5,
    )


def _rag(tmp_path: Path, node_id: str) -> tuple[AgenticRAGCapability, str]:
    rag = AgenticRAGCapability(tmp_path / node_id / "rag.sqlite3", None)
    rag.execute(
        {
            "action": "ingest",
            "source_ref": "artifact:collective-policy-v1",
            "title": "Collective evidence policy",
            "content": SOURCE_CONTENT,
        }
    )
    evidence_id = rag.retrieve("collective evidence consent privacy", 1)[0]["evidence_id"]
    return rag, evidence_id


def _collective(
    tmp_path: Path,
    node_id: str,
    peers: tuple[str, ...],
) -> tuple[CollectiveEvidenceCapability, str]:
    rag, evidence_id = _rag(tmp_path, node_id)
    return (
        CollectiveEvidenceCapability(
            node_id=node_id,
            database_path=tmp_path / node_id / "collective.sqlite3",
            shared_secret=SHARED_SECRET,
            allowed_peers=peers,
            rag=rag,
        ),
        evidence_id,
    )


def _contribution(
    capability: CollectiveEvidenceCapability,
    evidence_id: str,
    value: float,
    *,
    trust: float = 0.9,
    privacy_budget: float = 0.1,
) -> dict[str, object]:
    consent = capability.execute(
        {
            "action": "issue_consent",
            "evidence_id": evidence_id,
            "max_privacy_budget": privacy_budget,
            "expires_at": time.time() + 60,
        }
    ).data["receipt"]
    return capability.execute(
        {
            "action": "create",
            "evidence_id": evidence_id,
            "value": value,
            "trust": trust,
            "quality": 0.9,
            "privacy_budget": privacy_budget,
            "consent_receipt": consent,
        }
    ).data["packet"]


def test_p030_resumes_encrypted_transfer_after_both_nodes_restart(tmp_path: Path) -> None:
    sender = _twin(tmp_path, "node-a", ("node-b",))
    receiver = _twin(tmp_path, "node-b", ("node-a",))
    source = tmp_path / "node-a" / "state.bin"
    payload = (b"JAYA-TWIN-STATE\x00" * 50_000)[:700_000]
    source.write_bytes(payload)
    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    request = {
        "action": "send_batch",
        "host": endpoint["host"],
        "port": endpoint["port"],
        "transfer_id": "transfer-restart-001",
        "source_path": "state.bin",
        "target_node_id": "node-b",
        "brain_id": "brain-local-001",
        "destination_name": "state-received.bin",
    }
    try:
        partial = sender.execute({**request, "maximum_chunks": 1})
        assert partial.code == "TWIN_TRANSFER_PARTIAL"
        assert partial.data["cursor"] == 1
    finally:
        sender.close()
        receiver.close()

    restarted_sender = _twin(tmp_path, "node-a", ("node-b",))
    restarted_receiver = _twin(tmp_path, "node-b", ("node-a",))
    endpoint = restarted_receiver.execute({"action": "start_receiver", "port": 0}).data
    try:
        completed = restarted_sender.execute(
            {**request, "host": endpoint["host"], "port": endpoint["port"]}
        )
        assert completed.code == "TWIN_TRANSFER_COMPLETE"
        assert completed.data["complete"] is True
        assert completed.data["receipt"]["target_node"] == "node-b"
        assert completed.data["transport"] == "TCP_LOOPBACK_AES_256_GCM"
        assert (tmp_path / "node-b" / "received" / "state-received.bin").read_bytes() == payload
    finally:
        restarted_sender.close()
        restarted_receiver.close()


def test_p030_rejects_wrong_key_unknown_field_and_escaped_path(tmp_path: Path) -> None:
    receiver = _twin(tmp_path, "node-b", ("node-a",))
    sender = _twin(
        tmp_path,
        "node-a",
        ("node-b",),
        secret="different-test-secret-that-is-also-longer-than-thirty-two",
    )
    (tmp_path / "node-a" / "state.bin").write_bytes(b"authenticated state")
    endpoint = receiver.execute({"action": "start_receiver", "port": 0}).data
    request = {
        "action": "send_batch",
        "host": endpoint["host"],
        "port": endpoint["port"],
        "transfer_id": "wrong-key-001",
        "source_path": "state.bin",
        "target_node_id": "node-b",
        "brain_id": "brain-local-002",
        "destination_name": "wrong-key.bin",
    }
    try:
        with pytest.raises(LocalPillarError) as authentication:
            sender.execute(request)
        assert authentication.value.code == "TWIN_AUTHENTICATION_FAILED"
        with pytest.raises(LocalPillarError) as unknown:
            receiver.execute({"action": "stop_receiver", "unexpected": True})
        assert unknown.value.code == "UNKNOWN_FIELD"
        with pytest.raises(LocalPillarError) as escaped:
            sender.execute({**request, "source_path": "../outside.bin"})
        assert escaped.value.code == "PERMISSION_DENIED"
        with pytest.raises(LocalPillarError) as oversized_batch:
            sender.execute({**request, "maximum_chunks": 33})
        assert oversized_batch.value.code == "RESOURCE_LIMIT"
    finally:
        sender.close()
        receiver.close()


def test_p032_persists_signed_peer_evidence_and_enforces_revocation(tmp_path: Path) -> None:
    node_a, evidence_a = _collective(tmp_path, "node-a", ("node-b", "node-c"))
    node_b, evidence_b = _collective(tmp_path, "node-b", ("node-a", "node-c"))
    node_c, evidence_c = _collective(tmp_path, "node-c", ("node-a", "node-b"))
    assert evidence_a == evidence_b == evidence_c
    packet_a = _contribution(node_a, evidence_a, 0.7)
    packet_c = _contribution(node_c, evidence_c, 0.9)
    node_b.execute({"action": "ingest", "packet": packet_a})
    node_b.execute({"action": "ingest", "packet": packet_c})

    restarted_b, restarted_evidence = _collective(tmp_path, "node-b", ("node-a", "node-c"))
    aggregate = restarted_b.execute(
        {"action": "aggregate", "local_evidence_id": restarted_evidence, "local_value": 0.8}
    )
    assert aggregate.data["peer_count"] == 2
    assert aggregate.data["peer_median"] == pytest.approx(0.8)
    assert aggregate.data["recommendation"] == pytest.approx(0.8)
    assert aggregate.data["overrides_local_authority"] is False

    with pytest.raises(LocalPillarError) as replay:
        restarted_b.execute({"action": "ingest", "packet": packet_a})
    assert replay.value.code == "REPLAY_DETECTED"
    reused_consent = node_a.execute(
        {
            "action": "create",
            "evidence_id": evidence_a,
            "value": 0.75,
            "trust": 0.9,
            "quality": 0.9,
            "privacy_budget": 0.1,
            "consent_receipt": packet_a["consent_receipt"],
        }
    ).data["packet"]
    with pytest.raises(LocalPillarError) as consent_replay:
        restarted_b.execute({"action": "ingest", "packet": reused_consent})
    assert consent_replay.value.code == "REPLAY_DETECTED"
    poisoned = _contribution(node_a, evidence_a, 0.8, trust=0.2)
    with pytest.raises(LocalPillarError) as poisoning:
        restarted_b.execute({"action": "ingest", "packet": poisoned})
    assert poisoning.value.code == "POISONING_GUARD"

    revocation = node_a.create_revocation(str(packet_a["contribution_id"]))
    revoked = restarted_b.execute({"action": "revoke", **revocation})
    assert revoked.code == "COLLECTIVE_CONTRIBUTION_REVOKED"
    with pytest.raises(LocalPillarError) as insufficient:
        restarted_b.execute(
            {"action": "aggregate", "local_evidence_id": restarted_evidence, "local_value": 0.8}
        )
    assert insufficient.value.code == "INSUFFICIENT_PEERS"


def test_runtime_dispatches_real_p030_and_p032_between_local_nodes(tmp_path: Path) -> None:
    runtimes = {
        node_id: JayaCoreRuntime(
            db_path=tmp_path / node_id / "core.sqlite3",
            local_pillar_data_dir=tmp_path / node_id / "pillars",
            node_id=node_id,
            twin_shared_secret=SHARED_SECRET,
            twin_allowed_peers=tuple(peer for peer in ("node-a", "node-b", "node-c") if peer != node_id),
        )
        for node_id in ("node-a", "node-b", "node-c")
    }
    try:
        for runtime in runtimes.values():
            runtime.advanced_pillar_capabilities.rag.execute(
                {
                    "action": "ingest",
                    "source_ref": "artifact:collective-policy-v1",
                    "title": "Collective evidence policy",
                    "content": SOURCE_CONTENT,
                }
            )
        evidence = runtimes["node-b"].advanced_pillar_capabilities.rag.retrieve(
            "collective evidence consent privacy", 1
        )[0]["evidence_id"]
        packets = []
        for node_id, value in (("node-a", 0.6), ("node-c", 0.8)):
            consent = runtimes[node_id].execute_local_pillar(
                COLLECTIVE_EVIDENCE_CAPABILITY_ID,
                {
                    "action": "issue_consent",
                    "evidence_id": evidence,
                    "max_privacy_budget": 0.1,
                    "expires_at": time.time() + 60,
                },
            ).data["receipt"]
            packets.append(
                runtimes[node_id].execute_local_pillar(
                    COLLECTIVE_EVIDENCE_CAPABILITY_ID,
                    {
                        "action": "create",
                        "evidence_id": evidence,
                        "value": value,
                        "trust": 0.9,
                        "quality": 0.9,
                        "privacy_budget": 0.1,
                        "consent_receipt": consent,
                    },
                ).data["packet"]
            )
        for packet in packets:
            runtimes["node-b"].execute_local_pillar(
                COLLECTIVE_EVIDENCE_CAPABILITY_ID,
                {"action": "ingest", "packet": packet},
            )
        collective = runtimes["node-b"].execute_local_pillar(
            COLLECTIVE_EVIDENCE_CAPABILITY_ID,
            {"action": "aggregate", "local_evidence_id": evidence, "local_value": 0.7},
        )
        assert collective.data["recommendation"] == pytest.approx(0.7)

        twin_root = tmp_path / "node-a" / "pillars" / "twin-node"
        source = twin_root / "runtime-state.json"
        source.write_text('{"brain":"runtime-dispatched","version":1}', encoding="utf-8")
        endpoint = runtimes["node-b"].execute_local_pillar(
            TWIN_TRANSFER_CAPABILITY_ID, {"action": "start_receiver", "port": 0}
        ).data
        transferred = runtimes["node-a"].execute_local_pillar(
            TWIN_TRANSFER_CAPABILITY_ID,
            {
                "action": "send_batch",
                "host": endpoint["host"],
                "port": endpoint["port"],
                "transfer_id": "runtime-transfer-001",
                "source_path": "runtime-state.json",
                "target_node_id": "node-b",
                "brain_id": "runtime-brain-001",
                "destination_name": "runtime-state-received.json",
            },
        )
        assert transferred.code == "TWIN_TRANSFER_COMPLETE"
        assert (
            tmp_path
            / "node-b"
            / "pillars"
            / "twin-node"
            / "received"
            / "runtime-state-received.json"
        ).read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    finally:
        for runtime in runtimes.values():
            runtime.close()
