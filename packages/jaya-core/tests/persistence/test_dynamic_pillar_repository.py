from pathlib import Path

import pytest

from jaya_core.pillars import (
    DynamicPillarRegistry,
    PillarDefinition,
    PillarStatus,
    PillarStorageError,
    PillarValidationError,
)
from jaya_core.pillars.repository import PillarRepository

ROOT = Path(__file__).resolve().parents[4]
BASELINE = (
    ROOT
    / "packages"
    / "jaya-core"
    / "src"
    / "jaya_core"
    / "contracts"
    / "40_pillars.yaml"
)
CANDIDATE = (
    ROOT
    / "packages"
    / "jaya-core"
    / "examples"
    / "pillar-041-adaptive-evidence.yaml"
)


def _registry(tmp_path: Path) -> DynamicPillarRegistry:
    return DynamicPillarRegistry(
        database_path=tmp_path / "pillars.db",
        manifest_paths=(BASELINE,),
    )


def test_bootstrap_and_restart_preserve_the_canonical_40(tmp_path: Path) -> None:
    first = _registry(tmp_path)
    assert first.health_check()
    assert first.catalog_snapshot()["canonical_40_present"] is True
    assert len(first.list()) == 40

    restarted = _registry(tmp_path)
    assert len(restarted.list()) == 40
    assert restarted.get(33).definition.name == "Agentic RAG"
    assert restarted.repository.events("P001")[0]["event_type"] == "BASELINE_SEEDED"


def test_candidate_registration_is_idempotent_and_survives_restart(tmp_path: Path) -> None:
    first = _registry(tmp_path)
    record, created = first.register_candidate_file(
        CANDIDATE,
        idempotency_key="test:adaptive-evidence:v1",
        actor="test:operator",
    )
    duplicate, duplicate_created = first.register_candidate_file(
        CANDIDATE,
        idempotency_key="test:adaptive-evidence:v1",
        actor="test:operator",
    )

    assert created is True
    assert duplicate_created is False
    assert record.definition.pillar_id == "P041"
    assert duplicate.definition.digest() == record.definition.digest()

    restarted = _registry(tmp_path)
    recovered = restarted.get("P041")
    assert recovered.definition.name == "Adaptive Evidence Calibration"
    assert recovered.status is PillarStatus.PLANNED
    assert len(restarted.list()) == 41


def test_idempotency_conflict_is_rejected(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.register_candidate_file(
        CANDIDATE,
        idempotency_key="test:conflict:v1",
        actor="test:operator",
    )
    changed = PillarDefinition.from_mapping(
        {
            "id": 42,
            "name": "Different Candidate",
            "layer": "TRANSCENDENTAL",
            "architectural_owners": ["RESEARCH"],
            "status": "IDEA",
            "dependencies": [1],
        }
    )

    with pytest.raises(PillarValidationError) as error:
        registry.register_candidate(
            changed,
            origin="candidate:different.yaml",
            idempotency_key="test:conflict:v1",
            actor="test:operator",
        )

    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_status_transition_requires_real_dependency_evidence(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    pending_dependency = PillarDefinition.from_mapping(
        {
            "id": 41,
            "name": "Pending Dependency",
            "layer": "TRANSCENDENTAL",
            "architectural_owners": ["RESEARCH"],
            "status": "PLANNED",
            "dependencies": [22],
        }
    )
    registry.register_candidate(
        pending_dependency,
        origin="candidate:pending-dependency-test",
        idempotency_key="test:pending-dependency:v1",
        actor="test:operator",
    )
    blocked_candidate = PillarDefinition.from_mapping(
        {
            "id": 42,
            "name": "Blocked Dependency Candidate",
            "layer": "TRANSCENDENTAL",
            "architectural_owners": ["RESEARCH"],
            "status": "PLANNED",
            "dependencies": [41],
        }
    )
    record, _ = registry.register_candidate(
        blocked_candidate,
        origin="candidate:blocked-dependency-test",
        idempotency_key="test:transition:v1",
        actor="test:operator",
    )
    prototype = registry.transition_status(
        record.definition.pillar_id,
        PillarStatus.PROTOTYPE,
        expected_revision=record.revision,
        evidence_refs=(),
        actor="test:operator",
    )

    with pytest.raises(PillarValidationError) as error:
        registry.transition_status(
            prototype.definition.pillar_id,
            PillarStatus.IMPLEMENTED_LOCAL,
            expected_revision=prototype.revision,
            evidence_refs=("test:test_dynamic_pillar_repository",),
            actor="test:operator",
        )

    assert error.value.code == "DEPENDENCY_NOT_IMPLEMENTED"


def test_corrupt_and_future_schema_databases_fail_closed(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_text("not a sqlite database", encoding="utf-8")
    with pytest.raises(PillarStorageError):
        PillarRepository(corrupt)

    import sqlite3

    future = tmp_path / "future.db"
    with sqlite3.connect(future) as connection:
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(PillarStorageError) as error:
        PillarRepository(future)
    assert error.value.code == "SCHEMA_TOO_NEW"
