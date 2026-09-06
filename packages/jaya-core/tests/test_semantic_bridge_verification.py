"""Unit, edge-case, and provenance verification tests for Pillar 26 Semantic Bridge."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.semantic_bridge import (
    ModelSemanticProviderAdapter,
    RuleBasedSemanticProvider,
    SemanticBridgeCapability,
)


def test_rule_based_provider_extraction_and_provenance(tmp_path: Path) -> None:
    db = tmp_path / "semantic.sqlite3"
    bridge = SemanticBridgeCapability(db)

    content = "model:Alpha -trained_on-> dataset:WikiCorpus and evaluated_by person:Ada"
    res = bridge.execute(
        {
            "action": "ingest",
            "source_ref": "doc:101",
            "content": content,
            "namespace": "research",
        }
    )

    assert res.code == "SEMANTIC_SOURCE_INGESTED"
    assert res.data["method"] == "RULE_BASED_TYPED_GRAMMAR"
    assert len(res.data["entities"]) == 3
    assert len(res.data["relations"]) == 1
    assert len(res.data["claims"]) == 1

    claim = res.data["claims"][0]
    assert claim["epistemic_status"] == "FACT"
    assert claim["confidence"] == 1.0
    assert claim["predicate"] == "trained_on"
    assert claim["raw_text"] == "model:Alpha -trained_on-> dataset:WikiCorpus"

    # Verify provenance
    prov = bridge.execute({"action": "verify_provenance", "source_ref": "doc:101"})
    assert prov.code == "SEMANTIC_PROVENANCE_VERIFIED"
    assert prov.data["verified"] is True
    assert prov.data["entities_verified"] == 3
    assert prov.data["relations_verified"] == 1
    assert prov.data["claims_verified"] == 1


def test_epistemic_labeling_fact_inference_unverified(tmp_path: Path) -> None:
    db = tmp_path / "semantic.sqlite3"
    bridge = SemanticBridgeCapability(db)

    # 1. Fact
    bridge.execute(
        {
            "action": "ingest",
            "source_ref": "src:fact",
            "content": "model:LLM -utilizes-> concept:Attention",
        }
    )

    # 2. Hypothesis / Unverified
    bridge.execute(
        {
            "action": "ingest",
            "source_ref": "src:hypo",
            "content": "hypothesis: concept:AGI -requires-> concept:Consciousness",
        }
    )

    # 3. Inferred
    bridge.execute(
        {
            "action": "ingest",
            "source_ref": "src:inf",
            "content": "implies: model:LLM -enables-> concept:Reasoning",
        }
    )

    # 4. Explicit override in request
    bridge.execute(
        {
            "action": "ingest",
            "source_ref": "src:override",
            "content": "model:ModelX -supports-> concept:FeatureY",
            "epistemic_status": "UNVERIFIED",
        }
    )

    claims_fact = bridge.execute({"action": "query_claims", "epistemic_status": "FACT"})
    claims_unverified = bridge.execute(
        {"action": "query_claims", "epistemic_status": "UNVERIFIED"}
    )
    claims_inferred = bridge.execute(
        {"action": "query_claims", "epistemic_status": "INFERENCE"}
    )

    assert claims_fact.code == "SEMANTIC_CLAIMS_FOUND"
    assert claims_fact.data["count"] == 1
    assert claims_fact.data["claims"][0]["predicate"] == "utilizes"

    assert claims_unverified.code == "SEMANTIC_CLAIMS_FOUND"
    assert claims_unverified.data["count"] == 2
    unverified_preds = {c["predicate"] for c in claims_unverified.data["claims"]}
    assert unverified_preds == {"requires", "supports"}

    assert claims_inferred.code == "SEMANTIC_CLAIMS_FOUND"
    assert claims_inferred.data["count"] == 1
    assert claims_inferred.data["claims"][0]["predicate"] == "enables"


def test_provenance_verification_detects_citation_mismatch(tmp_path: Path) -> None:
    db = tmp_path / "semantic.sqlite3"
    bridge = SemanticBridgeCapability(db)

    content = "model:TestModel -learns_from-> dataset:CleanData"
    bridge.execute({"action": "ingest", "source_ref": "src:tamper", "content": content})

    # Tamper mention in database directly
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE semantic_mentions SET raw_text='tampered:Text' WHERE source_ref='src:tamper'"
        )

    with pytest.raises(LocalPillarError) as err:
        bridge.execute({"action": "verify_provenance", "source_ref": "src:tamper"})
    assert err.value.code == "CITATION_MISMATCH"


def test_provenance_verification_detects_digest_mismatch(tmp_path: Path) -> None:
    db = tmp_path / "semantic.sqlite3"
    bridge = SemanticBridgeCapability(db)

    content = "model:ValidModel -analyzes-> artifact:ValidLog"
    bridge.execute({"action": "ingest", "source_ref": "src:digest", "content": content})

    # Tamper content in database directly
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE semantic_sources SET content='tampered content' WHERE source_ref='src:digest'"
        )

    with pytest.raises(LocalPillarError) as err:
        bridge.execute({"action": "verify_provenance", "source_ref": "src:digest"})
    assert err.value.code == "DIGEST_MISMATCH"


def test_rejects_empty_whitespace_and_oversized_sources(tmp_path: Path) -> None:
    db = tmp_path / "semantic.sqlite3"
    bridge = SemanticBridgeCapability(db)

    # Empty string
    with pytest.raises(LocalPillarError) as empty_err:
        bridge.execute({"action": "ingest", "source_ref": "src:empty", "content": ""})
    assert empty_err.value.code == "INVALID_INPUT"

    # Whitespace only
    with pytest.raises(LocalPillarError) as space_err:
        bridge.execute({"action": "ingest", "source_ref": "src:space", "content": "    \n\t  "})
    assert space_err.value.code == "INVALID_INPUT"

    # Oversized (> 1 MiB)
    huge_content = "concept:Big " * 100_000
    with pytest.raises(LocalPillarError) as huge_err:
        bridge.execute({"action": "ingest", "source_ref": "src:huge", "content": huge_content})
    assert huge_err.value.code == "RESOURCE_LIMIT"


def test_rejects_non_text_media_type_and_unknown_fields(tmp_path: Path) -> None:
    db = tmp_path / "semantic.sqlite3"
    bridge = SemanticBridgeCapability(db)

    with pytest.raises(LocalPillarError) as media_err:
        bridge.execute(
            {
                "action": "ingest",
                "source_ref": "src:img",
                "content": "model:A",
                "media_type": "image/jpeg",
            }
        )
    assert media_err.value.code == "UNSUPPORTED_MEDIA_TYPE"

    with pytest.raises(LocalPillarError) as field_err:
        bridge.execute(
            {
                "action": "ingest",
                "source_ref": "src:ok",
                "content": "model:A",
                "unknown_extra": 123,
            }
        )
    assert field_err.value.code == "UNKNOWN_FIELD"


def test_model_provider_adapter_fails_closed_when_unconfigured() -> None:
    adapter = ModelSemanticProviderAdapter(model_path=None)
    assert adapter.health_check() is False

    with pytest.raises(LocalPillarError) as err:
        adapter.parse(content="model:A", namespace="test", source_ref="src:1")
    assert err.value.code == "PROVIDER_UNAVAILABLE"


def test_corrupt_database_handling(tmp_path: Path) -> None:
    db = tmp_path / "corrupt.sqlite3"
    db.write_bytes(b"NOT A VALID SQLITE DATABASE FILE - CORRUPTED")

    with pytest.raises(LocalPillarError) as err:
        SemanticBridgeCapability(db)
    assert err.value.code in {"STORAGE_CORRUPT", "STORAGE_UNAVAILABLE"}


def test_query_claims_filtering(tmp_path: Path) -> None:
    db = tmp_path / "semantic.sqlite3"
    bridge = SemanticBridgeCapability(db)

    content = (
        "person:Alice -created-> artifact:Spec and "
        "person:Bob -reviewed-> artifact:Spec and "
        "organization:Jaya -published-> artifact:Spec"
    )
    bridge.execute({"action": "ingest", "source_ref": "doc:collab", "content": content})

    # Query by predicate
    reviewed = bridge.execute({"action": "query_claims", "predicate": "reviewed"})
    assert reviewed.code == "SEMANTIC_CLAIMS_FOUND"
    assert reviewed.data["count"] == 1
    assert reviewed.data["claims"][0]["subject_value"] == "bob"

    # Query by source_ref
    all_collab = bridge.execute({"action": "query_claims", "source_ref": "doc:collab"})
    assert all_collab.data["count"] == 3

    # Query nonexistent predicate
    none_found = bridge.execute({"action": "query_claims", "predicate": "nonexistent"})
    assert none_found.code == "SEMANTIC_CLAIM_NOT_FOUND"
    assert none_found.data["count"] == 0
