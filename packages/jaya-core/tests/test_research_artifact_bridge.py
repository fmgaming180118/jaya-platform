from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from jaya_core.rag.research_artifact import ResearchArtifactVerificationError
from jaya_core.rag.research_bridge import ResearchBridge, ResearchInboxError


def _artifact(**overrides: object) -> dict[str, object]:
    artifact: dict[str, object] = {
        "schema_version": "1.0",
        "artifact_id": "JAYPATCH-boundary-001",
        "artifact_type": "knowledge_candidate",
        "finding_id": "HYP-boundary-001",
        "evidence_kind": "EMPIRICAL",
        "status": "PENDING_REVIEW",
        "subject": "Verified boundary fact",
        "payload": {
            "statement": "A reproduced observation entered through the inbox.",
            "executable": False,
        },
        "provenance": {
            "source_hashes": ["a" * 64],
            "dataset_sha256": "b" * 64,
        },
        "reproducibility": {"reproduced": True, "run_count": 2},
        "license": {"id": "CC-BY-4.0"},
        "confidence": 0.73,
        "created_at": "2026-07-29T00:00:00+00:00",
        "producer": "JAYA_RESEARCH",
    }
    artifact.update(overrides)
    canonical = json.dumps(
        artifact,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    artifact["content_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return artifact


def _bridge(tmp_path: Path) -> tuple[ResearchBridge, Path, Path]:
    data_root = tmp_path / "core-data"
    inbox = data_root / "research_inbox"
    database = data_root / "rag.db"
    inbox.mkdir(parents=True)
    return (
        ResearchBridge(
            inbox_path=inbox,
            rag_db_path=database,
            core_data_root=data_root,
        ),
        inbox,
        database,
    )


def test_bridge_ingests_only_verified_artifact_and_preserves_confidence(
    tmp_path: Path,
) -> None:
    bridge, inbox, database = _bridge(tmp_path)
    candidate = _artifact()
    (inbox / "candidate.json").write_text(json.dumps(candidate), encoding="utf-8")

    assert bridge.sync() == {
        "status": "ok",
        "synced": 1,
        "skipped": 0,
        "total_artifacts": 1,
    }
    assert bridge.sync()["skipped"] == 1
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT id, topic, content, confidence FROM agentic_facts"
        ).fetchone()
    assert row == (
        candidate["content_sha256"],
        "Verified boundary fact",
        "A reproduced observation entered through the inbox.",
        0.73,
    )


def test_tampering_fails_before_any_fact_is_written(tmp_path: Path) -> None:
    bridge, inbox, database = _bridge(tmp_path)
    candidate = _artifact()
    candidate["confidence"] = 0.99
    (inbox / "tampered.json").write_text(json.dumps(candidate), encoding="utf-8")

    with pytest.raises(ResearchInboxError, match="digest mismatch"):
        bridge.sync()
    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM agentic_facts").fetchone()[0]
    assert count == 0


def test_simulation_and_missing_confidence_never_enter_core(tmp_path: Path) -> None:
    bridge, inbox, _ = _bridge(tmp_path)
    simulated = _artifact(
        evidence_kind="SIMULATION",
        status="SIMULATION_ONLY",
    )
    (inbox / "simulation.json").write_text(json.dumps(simulated), encoding="utf-8")
    with pytest.raises(ResearchInboxError, match="only reviewable"):
        bridge.sync()

    missing_confidence = _artifact()
    missing_confidence.pop("confidence")
    missing_confidence.pop("content_sha256")
    unsigned = json.dumps(
        missing_confidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    missing_confidence["content_sha256"] = hashlib.sha256(
        unsigned.encode("utf-8")
    ).hexdigest()
    with pytest.raises(ResearchArtifactVerificationError, match="confidence"):
        from jaya_core.rag.research_artifact import verify_research_artifact

        verify_research_artifact(missing_confidence)


def test_bridge_rejects_paths_outside_core_data(tmp_path: Path) -> None:
    data_root = tmp_path / "core-data"
    outside = tmp_path / "external-inbox"
    with pytest.raises(ResearchInboxError, match="Core data directory"):
        ResearchBridge(
            inbox_path=outside,
            rag_db_path=data_root / "rag.db",
            core_data_root=data_root,
        )


def test_legacy_core_scripts_have_no_research_data_path() -> None:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    for name in (
        "deploy_adapter.py",
        "deploy_student.py",
        "merge_student_adapter.py",
        "promote_adapter.py",
        "promote_research_artifact.py",
        "promote_student.py",
    ):
        source = (scripts / name).read_text(encoding="utf-8")
        assert "JAYA_RESEARCH" not in source
        assert "../JAYA_RESEARCH" not in source
        assert "from _legacy_promotion import disabled_main" in source
        assert "shutil" not in source
        assert "copytree(" not in source


def test_legacy_promoted_discovery_is_quarantined() -> None:
    core_root = Path(__file__).resolve().parents[1]
    discovery_path = (
        core_root
        / "src"
        / "jaya_core"
        / "brain_v2"
        / "engine"
        / "research"
        / "discovery.py"
    )
    source = discovery_path.read_text(encoding="utf-8")
    forbidden = (
        "while True",
        "random.",
        "ImmuneSystem",
        "open(target_path",
        "add_experience(",
        '"SUCCESS"',
        "--forever",
    )

    assert all(token not in source for token in forbidden)
    assert not Path(f"{discovery_path}.manifest.json").exists()

    from jaya_core.brain_v2.engine.research.discovery import (
        LegacyDiscoveryDisabled,
        ScientificDiscovery,
    )

    with pytest.raises(LegacyDiscoveryDisabled, match="immutable Research candidate"):
        ScientificDiscovery()
