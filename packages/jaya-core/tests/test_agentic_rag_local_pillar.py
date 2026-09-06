"""Persistent retrieval, citation validation, and live Ollama tests for P33."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.core_config import ConfigurationError, CoreConfig
from jaya_core.pillars.agentic_rag_capability import (
    RAG_CAPABILITY_ID,
    AgenticRAGCapability,
    OllamaGroundedAnswerProvider,
)
from jaya_core.pillars.local_capabilities import LocalPillarError


class CitationTestProvider:
    provider_type = "TEST_IMPLEMENTATION"

    def __init__(self, *, invalid_citation: bool = False) -> None:
        self.invalid_citation = invalid_citation

    def health_check(self) -> bool:
        return True

    def answer(
        self, question: str, evidence: Sequence[Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        citation = "outside-retrieval" if self.invalid_citation else evidence[0]["evidence_id"]
        return {"answer": f"Grounded response for {question}", "citations": [citation]}


def _ingest(capability: AgenticRAGCapability) -> None:
    capability.execute(
        {
            "action": "ingest",
            "source_ref": "artifact:jaya-spec",
            "title": "Jaya local runtime specification",
            "content": (
                "The Jaya semantic bridge preserves exact citation spans and SHA-256 source "
                "digests. The temporal policy rejects observations beyond the allowed clock skew."
            ),
        }
    )


def test_p033_retrieves_unseen_persistent_source_and_validates_citations(tmp_path: Path) -> None:
    database = tmp_path / "rag.sqlite3"
    capability = AgenticRAGCapability(database, CitationTestProvider())
    _ingest(capability)
    duplicate = capability.execute(
        {
            "action": "ingest",
            "source_ref": "artifact:jaya-spec",
            "title": "Jaya local runtime specification",
            "content": (
                "The Jaya semantic bridge preserves exact citation spans and SHA-256 source "
                "digests. The temporal policy rejects observations beyond the allowed clock skew."
            ),
        }
    )
    restarted = AgenticRAGCapability(database, CitationTestProvider())
    answer = restarted.execute(
        {"action": "ask", "question": "What does the semantic bridge preserve?"}
    )

    assert duplicate.code == "RAG_SOURCE_DUPLICATE"
    assert answer.data["provider_type"] == "TEST_IMPLEMENTATION"
    assert answer.data["citations"] == [answer.data["evidence"][0]["evidence_id"]]
    cited = answer.data["evidence"][0]
    assert cited["source_ref"] == "artifact:jaya-spec"
    assert cited["end_offset"] > cited["start_offset"]


def test_p033_fails_on_empty_retrieval_invalid_citation_and_source_conflict(tmp_path: Path) -> None:
    database = tmp_path / "rag.sqlite3"
    capability = AgenticRAGCapability(database, CitationTestProvider())
    _ingest(capability)
    with pytest.raises(LocalPillarError) as empty:
        capability.execute({"action": "ask", "question": "quantum banana zebras"})
    assert empty.value.code == "EVIDENCE_UNAVAILABLE"
    invalid = AgenticRAGCapability(database, CitationTestProvider(invalid_citation=True))
    with pytest.raises(LocalPillarError) as citation:
        invalid.execute({"action": "ask", "question": "semantic bridge citation"})
    assert citation.value.code == "INVALID_CITATION"
    with pytest.raises(LocalPillarError) as conflict:
        capability.execute(
            {
                "action": "ingest",
                "source_ref": "artifact:jaya-spec",
                "title": "Changed",
                "content": "concept:Different content",
            }
        )
    assert conflict.value.code == "SOURCE_CONFLICT"


def test_p033_fails_closed_without_configured_model(tmp_path: Path) -> None:
    capability = AgenticRAGCapability(tmp_path / "rag.sqlite3", None)
    _ingest(capability)
    assert capability.health_check() is False
    with pytest.raises(LocalPillarError) as unavailable:
        capability.execute({"action": "ask", "question": "semantic bridge"})
    assert unavailable.value.code == "MODEL_NOT_CONFIGURED"


def test_local_model_config_requires_loopback_complete_pair(tmp_path: Path) -> None:
    base = {"JAYA_ENVIRONMENT": "test", "JAYA_CORE_DATA_DIR": str(tmp_path)}
    with pytest.raises(ConfigurationError):
        CoreConfig.from_env({**base, "JAYA_OLLAMA_BASE_URL": "http://example.com:11434"})
    config = CoreConfig.from_env(
        {
            **base,
            "JAYA_OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            "JAYA_LOCAL_PILLAR_MODEL": "qwen3.5:0.8b",
            "JAYA_LOCAL_MODEL_TIMEOUT_SECONDS": "120",
        }
    )
    assert config.ollama_base_url == "http://127.0.0.1:11434"
    assert config.local_pillar_model == "qwen3.5:0.8b"
    assert config.local_model_timeout_seconds == 120.0


@pytest.mark.integration
def test_runtime_calls_live_local_ollama_for_grounded_answer(tmp_path: Path) -> None:
    provider = OllamaGroundedAnswerProvider(
        base_url="http://127.0.0.1:11434", model="qwen3.5:0.8b", timeout_seconds=120
    )
    if not provider.health_check():
        pytest.skip("BLOCKED_EXTERNAL: configured Ollama test model is unavailable")
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
        ollama_base_url="http://127.0.0.1:11434",
        local_model_name="qwen3.5:0.8b",
        local_model_timeout_seconds=120,
    )
    try:
        runtime.execute_local_pillar(
            RAG_CAPABILITY_ID,
            {
                "action": "ingest",
                "source_ref": "artifact:live-ollama-source",
                "title": "Live local model evidence",
                "content": "The verified codename for this local demonstration is ORBIT-CEDAR-47.",
            },
        )
        result = runtime.execute_local_pillar(
            RAG_CAPABILITY_ID,
            {"action": "ask", "question": "What is the verified codename?", "top_k": 3},
        )
        health = runtime.operational_snapshot()["local_pillar_capabilities"]["capabilities"]
        assert "ORBIT-CEDAR-47" in result.data["answer"]
        assert result.data["provider_type"] == "LOCAL_MODEL"
        assert result.data["citations"]
        assert health[RAG_CAPABILITY_ID] == "HEALTHY"
    finally:
        runtime.close()
