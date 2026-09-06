"""Comprehensive unit and integration tests for Pillar 37: Hybrid Consciousness."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.control_capabilities import (
    HybridRoutingCapability,
    RemoteModelProviderProtocol,
)
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.media_capability import MediaObservationCapability


class MockRetrievalProvider:
    provider_type = "TEST_IMPLEMENTATION"

    def health_check(self) -> bool:
        return True

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return {
            "answer": f"Answer based on: {evidence[0]['content']}",
            "citations": [evidence[0]["evidence_id"]],
        }


class MockRemoteModelProvider(RemoteModelProviderProtocol):
    def __init__(self, healthy: bool = True, should_fail: bool = False) -> None:
        self.is_healthy = healthy
        self.should_fail = should_fail

    def health_check(self) -> bool:
        return self.is_healthy

    def ask(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.should_fail:
            raise RuntimeError("Remote cloud gateway timeout (504)")
        prompt = payload.get("prompt", payload.get("question", ""))
        return {
            "answer": f"Cloud LLM generated response for: {prompt}",
            "model_id": "cloud-deep-reasoner-v1",
            "citations": ["remote-ref-001"],
        }


def _setup_fixture(tmp_path: Path) -> tuple[AgenticRAGCapability, MediaObservationCapability, SandboxedImaginationCapability]:
    rag = AgenticRAGCapability(tmp_path / "rag.sqlite3", MockRetrievalProvider())
    rag.execute(
        {
            "action": "ingest",
            "source_ref": "doc:hybrid-spec",
            "title": "Hybrid Architecture Spec",
            "content": "Hybrid architecture combines rule execution, local retrieval, and models.",
        }
    )
    media_root = tmp_path / "media"
    media_root.mkdir()
    # Create sample media file
    sample_png = media_root / "sample.png"
    sample_png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82")
    media = MediaObservationCapability(root=media_root, database_path=tmp_path / "media.sqlite3")
    sandbox = SandboxedImaginationCapability()
    return rag, media, sandbox


def test_hybrid_routing_initialization_and_wal(tmp_path: Path) -> None:
    rag, media, sandbox = _setup_fixture(tmp_path)
    db_path = tmp_path / "routes.sqlite3"
    router = HybridRoutingCapability(db_path, rag, sandbox, media)

    assert router.health_check() is True

    # Check WAL mode and Schema version 2
    conn = sqlite3.connect(db_path)
    try:
        jmode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert jmode.upper() == "WAL"
        schema_ver = conn.execute("SELECT schema_version FROM hybrid_routing_schema").fetchone()[0]
        assert schema_ver == 2
        providers = conn.execute("SELECT count(*) FROM hybrid_providers").fetchone()[0]
        assert providers >= 4
    finally:
        conn.close()


def test_rule_based_route_execution(tmp_path: Path) -> None:
    rag, media, sandbox = _setup_fixture(tmp_path)
    router = HybridRoutingCapability(tmp_path / "routes.sqlite3", rag, sandbox, media)

    res = router.execute(
        {
            "action": "route",
            "request_kind": "expression",
            "sensitivity": "restricted",
            "payload": {"expression": "25 * 4 == 100"},
        }
    )
    assert res.data["provider_type"] == "RULE_BASED"
    assert res.data["result"]["result"] is True
    assert res.data["latency_ns"] > 0
    assert "route_id" in res.data


def test_retrieval_route_execution_and_citations(tmp_path: Path) -> None:
    rag, media, sandbox = _setup_fixture(tmp_path)
    router = HybridRoutingCapability(tmp_path / "routes.sqlite3", rag, sandbox, media)

    res = router.execute(
        {
            "action": "route",
            "request_kind": "retrieval",
            "sensitivity": "internal",
            "payload": {"query": "hybrid architecture rule execution"},
        }
    )
    assert res.data["provider_type"] == "RETRIEVAL"
    assert len(res.data["result"]["evidence"]) > 0
    assert len(res.data["citations"]) > 0


def test_grounded_answer_local_model_route(tmp_path: Path) -> None:
    rag, media, sandbox = _setup_fixture(tmp_path)
    router = HybridRoutingCapability(tmp_path / "routes.sqlite3", rag, sandbox, media)

    res = router.execute(
        {
            "action": "route",
            "request_kind": "grounded_answer",
            "sensitivity": "internal",
            "payload": {"question": "What does hybrid architecture combine?"},
        }
    )
    assert res.data["provider_type"] == "LOCAL_MODEL"
    assert "Answer based on:" in res.data["result"]["answer"]
    assert len(res.data["citations"]) > 0


def test_remote_model_route_and_privacy_gating(tmp_path: Path) -> None:
    rag, media, sandbox = _setup_fixture(tmp_path)
    remote = MockRemoteModelProvider(healthy=True)
    router = HybridRoutingCapability(
        tmp_path / "routes.sqlite3", rag, sandbox, media, remote_provider=remote
    )

    # Privacy Gating: RESTRICTED sensitivity must be blocked from remote route
    with pytest.raises(LocalPillarError) as exc_privacy:
        router.execute(
            {
                "action": "route",
                "request_kind": "remote_answer",
                "sensitivity": "restricted",
                "payload": {"prompt": "Analyze confidential corporate strategy"},
            }
        )
    assert exc_privacy.value.code == "PRIVACY_DENIAL"

    # Public/Internal sensitivity permitted to route to remote model
    res_public = router.execute(
        {
            "action": "route",
            "request_kind": "remote_answer",
            "sensitivity": "public",
            "payload": {"prompt": "Summarize general machine learning concepts"},
        }
    )
    assert res_public.data["provider_type"] == "REMOTE_MODEL"
    assert "Cloud LLM generated" in res_public.data["result"]["answer"]


def test_offline_mode_prohibits_cloud_egress(tmp_path: Path) -> None:
    rag, media, sandbox = _setup_fixture(tmp_path)
    remote = MockRemoteModelProvider(healthy=True)
    router_offline = HybridRoutingCapability(
        tmp_path / "routes.sqlite3",
        rag,
        sandbox,
        media,
        remote_provider=remote,
        offline_mode=True,
    )

    # Without fallback: raises OFFLINE_REQUIRED
    with pytest.raises(LocalPillarError) as exc_offline:
        router_offline.execute(
            {
                "action": "route",
                "request_kind": "remote_answer",
                "sensitivity": "public",
                "payload": {"prompt": "Question requiring remote cloud LLM"},
                "allow_fallback": False,
            }
        )
    assert exc_offline.value.code == "OFFLINE_REQUIRED"

    # With fallback: gracefully degrades to local model
    res_fallback = router_offline.execute(
        {
            "action": "route",
            "request_kind": "remote_answer",
            "sensitivity": "public",
            "payload": {"question": "What does hybrid architecture combine?"},
            "allow_fallback": True,
        }
    )
    assert res_fallback.data["provider_type"] == "LOCAL_MODEL"
    assert len(res_fallback.data["failover_history"]) == 1
    assert res_fallback.data["failover_history"][0]["fallback_from"] == "REMOTE_MODEL"
    assert res_fallback.data["failover_history"][0]["fell_back_to"] == "LOCAL_MODEL"


def test_failover_chain_when_remote_provider_fails(tmp_path: Path) -> None:
    rag, media, sandbox = _setup_fixture(tmp_path)
    remote_failing = MockRemoteModelProvider(healthy=True, should_fail=True)
    router = HybridRoutingCapability(
        tmp_path / "routes.sqlite3", rag, sandbox, media, remote_provider=remote_failing
    )

    # Remote failure with allow_fallback=True falls back to LOCAL_MODEL
    res = router.execute(
        {
            "action": "route",
            "request_kind": "remote_answer",
            "sensitivity": "public",
            "payload": {"question": "What does hybrid architecture combine?"},
            "allow_fallback": True,
        }
    )
    assert res.data["provider_type"] == "LOCAL_MODEL"
    assert len(res.data["failover_history"]) == 1
    assert "Remote cloud gateway timeout" in res.data["failover_history"][0]["reason"]

    # Remote failure with allow_fallback=False raises REMOTE_UNAVAILABLE
    with pytest.raises(LocalPillarError) as exc_fail:
        router.execute(
            {
                "action": "route",
                "request_kind": "remote_answer",
                "sensitivity": "public",
                "payload": {"question": "What does hybrid architecture combine?"},
                "allow_fallback": False,
            }
        )
    assert exc_fail.value.code == "REMOTE_UNAVAILABLE"


def test_media_tool_observation_route(tmp_path: Path) -> None:
    rag, media, sandbox = _setup_fixture(tmp_path)
    router = HybridRoutingCapability(tmp_path / "routes.sqlite3", rag, sandbox, media)

    res = router.execute(
        {
            "action": "route",
            "request_kind": "media",
            "sensitivity": "internal",
            "payload": {"path": "sample.png"},
        }
    )
    assert res.data["provider_type"] == "TOOL"
    assert "observation_id" in res.data["result"]
    assert res.data["result"]["modality"] == "IMAGE"


def test_tamper_detection_and_receipt_integrity(tmp_path: Path) -> None:
    rag, media, sandbox = _setup_fixture(tmp_path)
    db_path = tmp_path / "tamper_routes.sqlite3"
    router = HybridRoutingCapability(db_path, rag, sandbox, media)

    router.execute(
        {
            "action": "route",
            "request_kind": "expression",
            "sensitivity": "internal",
            "payload": {"expression": "10 + 20"},
        }
    )

    # Initial integrity check passes
    check_ok = router.execute({"action": "verify_integrity"})
    assert check_ok.data["status"] == "HEALTHY"

    # Malicious tampering of result digest in SQLite
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE hybrid_routes SET result_digest='tampered_corrupt_hash'")
        conn.commit()
    finally:
        conn.close()

    # Integrity verification must detect tampering
    with pytest.raises(LocalPillarError) as exc_tamper:
        router.execute({"action": "verify_integrity"})
    assert exc_tamper.value.code == "STORAGE_CORRUPT"


def test_provider_registry_and_history(tmp_path: Path) -> None:
    rag, media, sandbox = _setup_fixture(tmp_path)
    router = HybridRoutingCapability(tmp_path / "routes.sqlite3", rag, sandbox, media)

    # Register custom provider
    reg_res = router.execute(
        {
            "action": "register_provider",
            "provider_name": "cloud_deepseek_v3",
            "provider_type": "REMOTE_MODEL",
            "endpoint": "https://api.deepseek.com/v1",
            "capabilities": ["chat", "code", "reasoning"],
            "ttl_seconds": 120.0,
        }
    )
    assert reg_res.data["provider_name"] == "cloud_deepseek_v3"

    # List providers
    p_list = router.execute({"action": "providers"})
    names = [p["provider_name"] for p in p_list.data["providers"]]
    assert "cloud_deepseek_v3" in names
    assert "rule_sandbox" in names

    # History contains executed routes
    router.execute(
        {
            "action": "route",
            "request_kind": "expression",
            "sensitivity": "public",
            "payload": {"expression": "5 * 5"},
        }
    )
    hist = router.execute({"action": "history", "limit": 10})
    assert len(hist.data["routes"]) >= 1
    assert len(hist.data["audit_events"]) >= 1
    assert len(hist.data["receipts"]) >= 1
