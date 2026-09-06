"""Production-local tests for the P26 semantic bridge and P27 temporal policy."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.foundation_capabilities import (
    TEMPORAL_CAPABILITY_ID,
    TemporalWeightingCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.semantic_bridge import SEMANTIC_CAPABILITY_ID, SemanticBridgeCapability


def test_p026_persists_entities_relations_and_exact_citations(tmp_path: Path) -> None:
    database = tmp_path / "semantic.sqlite3"
    bridge = SemanticBridgeCapability(database)
    content = "model:Jaya -trained_on-> dataset:Corpus_ID and concept:Reasoning"
    ingested = bridge.execute(
        {
            "action": "ingest",
            "source_ref": "artifact:research-note-1",
            "content": content,
            "namespace": "jaya-research",
        }
    )
    restarted = SemanticBridgeCapability(database)
    source = restarted.execute(
        {"action": "source", "source_ref": "artifact:research-note-1"}
    )

    assert ingested.data["method"] == "RULE_BASED_TYPED_GRAMMAR"
    assert ingested.data["relations"][0]["predicate"] == "trained_on"
    assert source.data["source_digest"] == ingested.data["source_digest"]
    for mention in source.data["entities"]:
        assert content[mention["start_offset"] : mention["end_offset"]] == mention["raw_text"]


def test_p026_links_across_sources_and_reports_type_ambiguity(tmp_path: Path) -> None:
    bridge = SemanticBridgeCapability(tmp_path / "semantic.sqlite3")
    for source_ref, content in (
        ("source:a", "person:Mercury studies concept:Mercury"),
        ("source:b", "person:Mercury reviews artifact:Report"),
    ):
        bridge.execute({"action": "ingest", "source_ref": source_ref, "content": content})

    ambiguous = bridge.execute({"action": "query", "value": "mercury"})
    person = bridge.execute(
        {"action": "query", "value": "mercury", "entity_type": "person"}
    )

    assert ambiguous.data["ambiguous"] is True
    assert ambiguous.data["candidate_types"] == ["concept", "person"]
    assert {item["source_ref"] for item in person.data["matches"]} == {"source:a", "source:b"}
    assert len({item["entity_id"] for item in person.data["matches"]}) == 1


def test_p026_is_idempotent_and_rejects_source_conflict_and_invalid_media(tmp_path: Path) -> None:
    bridge = SemanticBridgeCapability(tmp_path / "semantic.sqlite3")
    request = {"action": "ingest", "source_ref": "source:stable", "content": "model:Jaya"}
    bridge.execute(request)
    duplicate = bridge.execute(request)
    assert duplicate.code == "SEMANTIC_SOURCE_READ"
    with pytest.raises(LocalPillarError) as conflict:
        bridge.execute({**request, "content": "model:Other"})
    assert conflict.value.code == "SOURCE_CONFLICT"
    with pytest.raises(LocalPillarError) as media:
        bridge.execute({**request, "source_ref": "source:image", "media_type": "image/png"})
    assert media.value.code == "UNSUPPORTED_MEDIA_TYPE"


def test_p026_fails_closed_on_newer_storage_schema(tmp_path: Path) -> None:
    database = tmp_path / "semantic.sqlite3"
    SemanticBridgeCapability(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE semantic_meta SET value='999' WHERE key='schema_version'"
        )
    with pytest.raises(LocalPillarError) as newer:
        SemanticBridgeCapability(database)
    assert newer.value.code == "STORAGE_SCHEMA_UNSUPPORTED"


def test_runtime_dispatches_p026_then_p027_and_persists_both(tmp_path: Path) -> None:
    database = tmp_path / "core.sqlite3"
    pillar_data = tmp_path / "pillar-data"
    runtime = JayaCoreRuntime(db_path=database, local_pillar_data_dir=pillar_data)
    now = time.time()
    try:
        semantic = runtime.execute_local_pillar(
            SEMANTIC_CAPABILITY_ID,
            {
                "action": "ingest",
                "source_ref": "source:runtime",
                "content": "artifact:Evidence -supports-> concept:Claim",
            },
        )
        runtime.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID,
            {
                "action": "add",
                "record_id": "temporal-runtime-1",
                "source_ref": semantic.data["source_ref"],
                "base_score": 0.9,
                "observed_at": now,
                "payload": {"source_digest": semantic.data["source_digest"]},
            },
        )
    finally:
        runtime.close()

    restarted = JayaCoreRuntime(db_path=database, local_pillar_data_dir=pillar_data)
    try:
        found = restarted.execute_local_pillar(
            SEMANTIC_CAPABILITY_ID, {"action": "query", "value": "evidence"}
        )
        ranked = restarted.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID,
            {"action": "rank", "decay_rate": 0.01, "now": now},
        )
        assert found.data["matches"][0]["source_ref"] == "source:runtime"
        assert ranked.data["records"][0]["record_id"] == "temporal-runtime-1"
    finally:
        restarted.close()


def test_p027_expiry_supersession_retention_and_legal_hold_are_auditable(
    tmp_path: Path,
) -> None:
    database = tmp_path / "temporal.sqlite3"
    temporal = TemporalWeightingCapability(database)
    now = time.time()
    old_request = {
        "action": "add",
        "record_id": "policy-v1",
        "source_ref": "policy:release-v1",
        "base_score": 1.0,
        "observed_at": now - 7_200,
        "valid_until": now - 3_600,
        "retention_until": now - 60,
        "clock_source": "EXTERNAL_SIGNED",
        "payload": {"version": 1, "evidence_digest": "sha256:old"},
    }
    temporal.execute(old_request)
    temporal.execute(
        {
            "action": "add",
            "record_id": "policy-v2",
            "source_ref": "policy:release-v2",
            "base_score": 0.8,
            "observed_at": now - 30,
            "valid_until": now + 3_600,
            "retention_until": now + 7_200,
            "supersedes": "policy-v1",
            "payload": {"version": 2, "evidence_digest": "sha256:new"},
        }
    )
    hold_request = {
        "action": "set_legal_hold",
        "event_id": "hold-policy-v1",
        "record_id": "policy-v1",
        "enabled": True,
        "reason": "retain superseded release evidence",
        "changed_at": now - 10,
    }
    temporal.execute(hold_request)
    duplicate = temporal.execute(hold_request)

    restarted = TemporalWeightingCapability(database)
    ranked = restarted.execute(
        {"action": "rank", "decay_rate": 0.01, "now": now}
    )
    history = restarted.execute({"action": "history", "as_of": now})
    by_id = {item["record_id"]: item for item in history.data["records"]}

    assert [item["record_id"] for item in ranked.data["records"]] == ["policy-v2"]
    assert by_id["policy-v1"]["status"] == "SUPERSEDED"
    assert by_id["policy-v1"]["retention_status"] == "LEGAL_HOLD"
    assert by_id["policy-v1"]["latest_policy_event_id"] == "hold-policy-v1"
    assert by_id["policy-v1"]["clock_source"] == "EXTERNAL_SIGNED"
    assert by_id["policy-v2"]["status"] == "ACTIVE"
    assert duplicate.code == "TEMPORAL_POLICY_EVENT_DUPLICATE"
    with pytest.raises(LocalPillarError) as conflict:
        restarted.execute({**hold_request, "enabled": False})
    assert conflict.value.code == "TEMPORAL_CONFLICT"


def test_p027_history_is_reproducible_for_explicit_as_of(tmp_path: Path) -> None:
    temporal = TemporalWeightingCapability(tmp_path / "temporal.sqlite3")
    now = time.time()
    temporal.execute(
        {
            "action": "add",
            "record_id": "fact-v1",
            "source_ref": "fact:one",
            "base_score": 0.9,
            "observed_at": now - 100,
            "payload": {"fact": "old"},
        }
    )
    temporal.execute(
        {
            "action": "add",
            "record_id": "fact-v2",
            "source_ref": "fact:two",
            "base_score": 0.7,
            "observed_at": now - 50,
            "supersedes": "fact-v1",
            "payload": {"fact": "new"},
        }
    )

    before = temporal.execute({"action": "history", "as_of": now - 75})
    after = temporal.execute({"action": "history", "as_of": now})
    repeated = temporal.execute({"action": "history", "as_of": now})

    assert before.data["records"][0]["record_id"] == "fact-v1"
    assert before.data["records"][0]["status"] == "ACTIVE"
    assert {item["record_id"]: item["status"] for item in after.data["records"]} == {
        "fact-v1": "SUPERSEDED",
        "fact-v2": "ACTIVE",
    }
    assert repeated.data == after.data


def test_p027_migrates_v1_store_and_rejects_newer_schema(tmp_path: Path) -> None:
    database = tmp_path / "temporal.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE temporal_records(
                record_id TEXT PRIMARY KEY,
                source_ref TEXT NOT NULL,
                base_score REAL NOT NULL,
                observed_at REAL NOT NULL,
                supersedes TEXT,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY(supersedes) REFERENCES temporal_records(record_id)
            );
            INSERT INTO temporal_records VALUES(
                'legacy','legacy:source',0.5,1.0,NULL,'{"legacy":true}',1.0
            );
            """
        )

    migrated = TemporalWeightingCapability(database)
    history = migrated.execute({"action": "history", "as_of": 2.0})
    assert history.data["records"][0]["record_id"] == "legacy"
    assert history.data["records"][0]["clock_source"] == "SYSTEM_UTC"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE temporal_meta SET value='999' WHERE key='schema_version'"
        )
    with pytest.raises(LocalPillarError) as newer:
        TemporalWeightingCapability(database)
    assert newer.value.code == "STORAGE_SCHEMA_UNSUPPORTED"


def test_p027_fails_closed_on_corrupt_payload_and_deadline(tmp_path: Path) -> None:
    database = tmp_path / "temporal.sqlite3"
    temporal = TemporalWeightingCapability(database)
    now = time.time()
    temporal.execute(
        {
            "action": "add",
            "record_id": "corrupt-me",
            "source_ref": "artifact:corrupt",
            "base_score": 0.5,
            "observed_at": now,
            "payload": {"valid": True},
        }
    )
    with pytest.raises(LocalPillarError) as timeout:
        temporal.execute(
            {
                "action": "history",
                "as_of": now,
                "timeout_seconds": 0.000001,
            }
        )
    assert timeout.value.code == "TIMEOUT"

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE temporal_records SET base_score='invalid' WHERE record_id='corrupt-me'"
        )
    with pytest.raises(LocalPillarError) as numeric_corrupt:
        temporal.execute({"action": "rank", "decay_rate": 0.1, "now": now})
    assert numeric_corrupt.value.code == "STORAGE_CORRUPT"

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE temporal_records SET base_score=0.5,payload_json='not-json' "
            "WHERE record_id='corrupt-me'"
        )
    with pytest.raises(LocalPillarError) as corrupt:
        temporal.execute({"action": "rank", "decay_rate": 0.1, "now": now})
    assert corrupt.value.code == "STORAGE_CORRUPT"


def test_p027_rank_uses_latest_append_only_legal_hold_event(tmp_path: Path) -> None:
    temporal = TemporalWeightingCapability(tmp_path / "temporal.sqlite3")
    now = time.time()
    temporal.execute(
        {
            "action": "add",
            "record_id": "held-active",
            "source_ref": "artifact:held-active",
            "base_score": 0.8,
            "observed_at": now - 30,
            "payload": {"value": "active"},
        }
    )
    temporal.execute(
        {
            "action": "set_legal_hold",
            "event_id": "hold-active",
            "record_id": "held-active",
            "enabled": True,
            "reason": "audit investigation",
            "changed_at": now - 20,
        }
    )
    held_rank = temporal.execute(
        {"action": "rank", "decay_rate": 0.1, "now": now - 15}
    )
    temporal.execute(
        {
            "action": "set_legal_hold",
            "event_id": "release-active",
            "record_id": "held-active",
            "enabled": False,
            "reason": "audit investigation completed",
            "changed_at": now - 10,
        }
    )
    released_rank = temporal.execute(
        {"action": "rank", "decay_rate": 0.1, "now": now}
    )

    assert held_rank.data["records"][0]["legal_hold"] is True
    assert released_rank.data["records"][0]["legal_hold"] is False


def test_p027_rejects_invalid_policy_windows_and_missing_parent(tmp_path: Path) -> None:
    temporal = TemporalWeightingCapability(tmp_path / "temporal.sqlite3")
    now = time.time()
    request = {
        "action": "add",
        "record_id": "invalid-window",
        "source_ref": "artifact:invalid",
        "base_score": 0.5,
        "observed_at": now,
        "payload": {"value": 1},
    }
    with pytest.raises(LocalPillarError) as validity:
        temporal.execute({**request, "valid_until": now - 1})
    assert validity.value.code == "INVALID_INPUT"
    with pytest.raises(LocalPillarError) as missing_parent:
        temporal.execute({**request, "record_id": "child", "supersedes": "missing"})
    assert missing_parent.value.code == "SUPERSESSION_NOT_FOUND"
    with pytest.raises(LocalPillarError) as nonfinite:
        temporal.execute({**request, "record_id": "nan", "base_score": "nan"})
    assert nonfinite.value.code == "INVALID_INPUT"
