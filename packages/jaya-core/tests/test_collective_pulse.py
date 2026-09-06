"""Unit and integration tests for Pilar 32: Collective Pulse (core.collective.pulse)."""

from __future__ import annotations

import os
import time
from pathlib import Path
import pytest

from jaya_core.pillars.distributed_capabilities import (
    COLLECTIVE_EVIDENCE_CAPABILITY_ID,
    CollectiveEvidenceCapability,
    LocalPillarError,
)
from jaya_core.pillars.reasoning_capabilities import AgenticRAGCapability

SHARED_SECRET = "jaya-shared-collective-secret-32-chars-long-abc"


def _setup_node(tmp_path: Path, node_id: str, allowed_peers: tuple[str, ...]) -> tuple[CollectiveEvidenceCapability, AgenticRAGCapability, str]:
    db_path = tmp_path / node_id / "collective.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    rag_db = tmp_path / node_id / "rag.sqlite3"
    rag_db.parent.mkdir(parents=True, exist_ok=True)
    rag = AgenticRAGCapability(rag_db, None)
    rag.execute({
        "action": "ingest",
        "source_ref": "shared-policy-v1",
        "title": "Collective Evidence Policy",
        "content": "Consented peer evidence for collective pulse reasoning and aggregation.",
    })
    evidence_id = rag.retrieve("collective evidence policy", 1)[0]["evidence_id"]
    cap = CollectiveEvidenceCapability(
        node_id=node_id,
        database_path=db_path,
        shared_secret=SHARED_SECRET,
        allowed_peers=allowed_peers,
        rag=rag,
    )
    return cap, rag, evidence_id


def test_collective_pulse_initialization_and_probe(tmp_path: Path) -> None:
    cap, rag, evidence_id = _setup_node(tmp_path, "node-b", ("node-a", "node-c"))
    assert cap.health_check() is True

    res = cap.execute({"action": "probe"})
    assert res.code == "COLLECTIVE_PROBED"
    probe = res.data
    assert probe["capability_id"] == COLLECTIVE_EVIDENCE_CAPABILITY_ID
    assert probe["min_peers_required"] == 2
    assert probe["max_privacy_budget_per_node"] == 0.25
    assert probe["poisoning_trust_threshold"] == 0.5
    assert probe["local_authority_weight"] == 0.7
    assert probe["peer_median_weight"] == 0.3
    assert probe["healthy"] is True


def test_collective_pulse_consent_lifecycle(tmp_path: Path) -> None:
    cap, rag, evidence_id = _setup_node(tmp_path, "node-a", ("node-b", "node-c"))

    # Valid consent
    now = time.time()
    res = cap.execute({
        "action": "issue_consent",
        "evidence_id": evidence_id,
        "max_privacy_budget": 0.15,
        "expires_at": now + 3600,
    })
    assert res.code == "COLLECTIVE_CONSENT_ISSUED"
    receipt = res.data["receipt"]
    assert receipt["source_node"] == "node-a"
    assert receipt["max_privacy_budget"] == 0.15
    assert "signature" in receipt

    # Invalid evidence rejected
    with pytest.raises(LocalPillarError) as exc:
        cap.execute({
            "action": "issue_consent",
            "evidence_id": "nonexistent-evidence-id",
            "max_privacy_budget": 0.15,
            "expires_at": now + 3600,
        })
    assert exc.value.code == "INVALID_EVIDENCE"

    # Privacy budget > 0.25 rejected
    with pytest.raises(LocalPillarError) as exc:
        cap.execute({
            "action": "issue_consent",
            "evidence_id": evidence_id,
            "max_privacy_budget": 0.30,
            "expires_at": now + 3600,
        })
    assert exc.value.code == "INVALID_INPUT"


def test_collective_pulse_contribution_creation_and_ingestion(tmp_path: Path) -> None:
    node_a, _, evidence_a = _setup_node(tmp_path, "node-a", ("node-b", "node-c"))
    node_b, _, evidence_b = _setup_node(tmp_path, "node-b", ("node-a", "node-c"))

    consent = node_a.execute({
        "action": "issue_consent",
        "evidence_id": evidence_a,
        "max_privacy_budget": 0.2,
        "expires_at": time.time() + 3600,
    }).data["receipt"]

    create_res = node_a.execute({
        "action": "create",
        "evidence_id": evidence_a,
        "value": 0.85,
        "trust": 0.9,
        "quality": 0.88,
        "privacy_budget": 0.1,
        "consent_receipt": consent,
    })
    assert create_res.code == "COLLECTIVE_CONTRIBUTION_CREATED"
    packet = create_res.data["packet"]

    # Ingest into Node-B
    ingest_res = node_b.execute({"action": "ingest", "packet": packet})
    assert ingest_res.code == "COLLECTIVE_CONTRIBUTION_ACCEPTED"
    assert ingest_res.data["source_node"] == "node-a"

    # Verify packet helper
    v_res = node_b.execute({"action": "verify_packet", "packet": packet})
    assert v_res.code == "COLLECTIVE_PACKET_VERIFIED"
    assert v_res.data["valid"] is True


def test_collective_pulse_rejection_of_tampered_and_unallowlisted(tmp_path: Path) -> None:
    node_a, _, evidence_a = _setup_node(tmp_path, "node-a", ("node-b", "node-c"))
    node_b, _, _ = _setup_node(tmp_path, "node-b", ("node-a", "node-c"))

    consent = node_a.execute({
        "action": "issue_consent",
        "evidence_id": evidence_a,
        "max_privacy_budget": 0.2,
        "expires_at": time.time() + 3600,
    }).data["receipt"]

    packet = node_a.execute({
        "action": "create",
        "evidence_id": evidence_a,
        "value": 0.85,
        "trust": 0.9,
        "quality": 0.88,
        "privacy_budget": 0.1,
        "consent_receipt": consent,
    }).data["packet"]

    # Tampered value
    tampered = dict(packet)
    tampered["value"] = 0.99
    with pytest.raises(LocalPillarError) as exc:
        node_b.execute({"action": "ingest", "packet": tampered})
    assert exc.value.code == "SIGNATURE_INVALID"

    # Unallowlisted node
    rogue, _, evidence_rogue = _setup_node(tmp_path, "rogue-node", ("node-b",))
    rogue_consent = rogue.execute({
        "action": "issue_consent",
        "evidence_id": evidence_rogue,
        "max_privacy_budget": 0.1,
        "expires_at": time.time() + 3600,
    }).data["receipt"]
    rogue_packet = rogue.execute({
        "action": "create",
        "evidence_id": evidence_rogue,
        "value": 0.5,
        "trust": 0.9,
        "quality": 0.9,
        "privacy_budget": 0.05,
        "consent_receipt": rogue_consent,
    }).data["packet"]
    with pytest.raises(LocalPillarError) as exc:
        node_b.execute({"action": "ingest", "packet": rogue_packet})
    assert exc.value.code == "PEER_DENIED"


def test_collective_pulse_rejection_of_poisoning_and_clock_skew(tmp_path: Path) -> None:
    node_a, _, evidence_a = _setup_node(tmp_path, "node-a", ("node-b", "node-c"))
    node_b, _, _ = _setup_node(tmp_path, "node-b", ("node-a", "node-c"))

    consent = node_a.execute({
        "action": "issue_consent",
        "evidence_id": evidence_a,
        "max_privacy_budget": 0.2,
        "expires_at": time.time() + 3600,
    }).data["receipt"]

    # Poisoning: trust < 0.5
    poisoned = node_a.execute({
        "action": "create",
        "evidence_id": evidence_a,
        "value": 0.85,
        "trust": 0.3,
        "quality": 0.9,
        "privacy_budget": 0.1,
        "consent_receipt": consent,
    }).data["packet"]
    with pytest.raises(LocalPillarError) as exc:
        node_b.execute({"action": "ingest", "packet": poisoned})
    assert exc.value.code == "POISONING_GUARD"

    # Stale packet (clock skew > 300s)
    stale_packet = dict(node_a.execute({
        "action": "create",
        "evidence_id": evidence_a,
        "value": 0.85,
        "trust": 0.9,
        "quality": 0.9,
        "privacy_budget": 0.1,
        "consent_receipt": consent,
    }).data["packet"])
    stale_packet["created_at"] = time.time() - 400.0
    stale_packet["signature"] = node_a._sign(
        {k: v for k, v in stale_packet.items() if k != "signature"}
    )
    with pytest.raises(LocalPillarError) as exc:
        node_b.execute({"action": "ingest", "packet": stale_packet})
    assert exc.value.code == "CLOCK_SKEW"


def test_collective_pulse_replay_defense(tmp_path: Path) -> None:
    node_a, _, evidence_a = _setup_node(tmp_path, "node-a", ("node-b", "node-c"))
    node_b, _, _ = _setup_node(tmp_path, "node-b", ("node-a", "node-c"))

    consent = node_a.execute({
        "action": "issue_consent",
        "evidence_id": evidence_a,
        "max_privacy_budget": 0.2,
        "expires_at": time.time() + 3600,
    }).data["receipt"]

    packet = node_a.execute({
        "action": "create",
        "evidence_id": evidence_a,
        "value": 0.85,
        "trust": 0.9,
        "quality": 0.88,
        "privacy_budget": 0.1,
        "consent_receipt": consent,
    }).data["packet"]

    node_b.execute({"action": "ingest", "packet": packet})

    # Replay of packet
    with pytest.raises(LocalPillarError) as exc:
        node_b.execute({"action": "ingest", "packet": packet})
    assert exc.value.code == "REPLAY_DETECTED"


def test_collective_pulse_aggregation_and_conflict_spread(tmp_path: Path) -> None:
    node_a, _, evidence_a = _setup_node(tmp_path, "node-a", ("node-b", "node-c"))
    node_b, _, evidence_b = _setup_node(tmp_path, "node-b", ("node-a", "node-c"))
    node_c, _, evidence_c = _setup_node(tmp_path, "node-c", ("node-a", "node-b"))

    # Less than 2 peers raises INSUFFICIENT_PEERS
    with pytest.raises(LocalPillarError) as exc:
        node_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": 0.7})
    assert exc.value.code == "INSUFFICIENT_PEERS"

    # Ingest from Node-A (0.6) and Node-C (0.8)
    consent_a = node_a.execute({"action": "issue_consent", "evidence_id": evidence_a, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
    packet_a = node_a.execute({"action": "create", "evidence_id": evidence_a, "value": 0.6, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_a}).data["packet"]
    node_b.execute({"action": "ingest", "packet": packet_a})

    consent_c = node_c.execute({"action": "issue_consent", "evidence_id": evidence_c, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
    packet_c = node_c.execute({"action": "create", "evidence_id": evidence_c, "value": 0.8, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_c}).data["packet"]
    node_b.execute({"action": "ingest", "packet": packet_c})

    # Now aggregate with local_value = 0.7
    agg_res = node_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": 0.7})
    assert agg_res.code == "COLLECTIVE_RECOMMENDATION_CREATED"
    data = agg_res.data
    assert data["peer_count"] == 2
    assert data["peer_median"] == pytest.approx(0.7)  # median of [0.6, 0.8] is 0.7
    assert data["recommendation"] == pytest.approx(0.7)  # 0.7*0.7 + 0.3*0.7 = 0.7
    assert data["spread"] == pytest.approx(0.2)
    assert data["conflict_detected"] is False
    assert data["overrides_local_authority"] is False
    assert "aggregate_id" in data

    # Verify aggregates query
    aggs = node_b.execute({"action": "get_aggregates"}).data["aggregates"]
    assert len(aggs) >= 1
    assert aggs[0]["aggregate_id"] == data["aggregate_id"]


def test_collective_pulse_revocation_lifecycle(tmp_path: Path) -> None:
    node_a, _, evidence_a = _setup_node(tmp_path, "node-a", ("node-b", "node-c"))
    node_b, _, evidence_b = _setup_node(tmp_path, "node-b", ("node-a", "node-c"))
    node_c, _, evidence_c = _setup_node(tmp_path, "node-c", ("node-a", "node-b"))

    consent_a = node_a.execute({"action": "issue_consent", "evidence_id": evidence_a, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
    packet_a = node_a.execute({"action": "create", "evidence_id": evidence_a, "value": 0.6, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_a}).data["packet"]
    node_b.execute({"action": "ingest", "packet": packet_a})

    consent_c = node_c.execute({"action": "issue_consent", "evidence_id": evidence_c, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
    packet_c = node_c.execute({"action": "create", "evidence_id": evidence_c, "value": 0.8, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_c}).data["packet"]
    node_b.execute({"action": "ingest", "packet": packet_c})

    # Node-A revokes its contribution
    rev_payload = node_a.create_revocation(str(packet_a["contribution_id"]))
    rev_res = node_b.execute({"action": "revoke", **rev_payload})
    assert rev_res.code == "COLLECTIVE_CONTRIBUTION_REVOKED"

    # Aggregation now fails because only 1 active peer remains
    with pytest.raises(LocalPillarError) as exc:
        node_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": 0.7})
    assert exc.value.code == "INSUFFICIENT_PEERS"


def test_collective_pulse_durability_across_node_restart(tmp_path: Path) -> None:
    node_a, _, evidence_a = _setup_node(tmp_path, "node-a", ("node-b", "node-c"))
    node_b, _, evidence_b = _setup_node(tmp_path, "node-b", ("node-a", "node-c"))
    node_c, _, evidence_c = _setup_node(tmp_path, "node-c", ("node-a", "node-b"))

    consent_a = node_a.execute({"action": "issue_consent", "evidence_id": evidence_a, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
    packet_a = node_a.execute({"action": "create", "evidence_id": evidence_a, "value": 0.6, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_a}).data["packet"]
    node_b.execute({"action": "ingest", "packet": packet_a})

    consent_c = node_c.execute({"action": "issue_consent", "evidence_id": evidence_c, "max_privacy_budget": 0.2, "expires_at": time.time() + 3600}).data["receipt"]
    packet_c = node_c.execute({"action": "create", "evidence_id": evidence_c, "value": 0.8, "trust": 0.9, "quality": 0.9, "privacy_budget": 0.1, "consent_receipt": consent_c}).data["packet"]
    node_b.execute({"action": "ingest", "packet": packet_c})

    # Simulate Node-B crash and re-instantiation from SQLite
    db_path = tmp_path / "node-b" / "collective.sqlite3"
    rag_db = tmp_path / "node-b" / "rag.sqlite3"
    restarted_rag = AgenticRAGCapability(rag_db, None)
    restarted_b = CollectiveEvidenceCapability(
        node_id="node-b",
        database_path=db_path,
        shared_secret=SHARED_SECRET,
        allowed_peers=("node-a", "node-c"),
        rag=restarted_rag,
    )

    # Aggregation works immediately from persisted SQLite rows
    agg_res = restarted_b.execute({"action": "aggregate", "local_evidence_id": evidence_b, "local_value": 0.7})
    assert agg_res.code == "COLLECTIVE_RECOMMENDATION_CREATED"
    assert agg_res.data["peer_count"] == 2

    # Ingesting packet_a again still triggers REPLAY_DETECTED
    with pytest.raises(LocalPillarError) as exc:
        restarted_b.execute({"action": "ingest", "packet": packet_a})
    assert exc.value.code == "REPLAY_DETECTED"
