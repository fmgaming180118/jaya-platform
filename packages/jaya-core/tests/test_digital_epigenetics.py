"""Comprehensive unit, integration, failure, and persistence tests for Pillar 25 Digital Epigenetics."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.local_capabilities import (
    LINEAGE_CAPABILITY_ID,
    DigitalEpigeneticsService,
    LocalPillarError,
)

TEST_SIGNING_KEY = bytes(range(32))


def test_epigenetic_v2_schema_and_automatic_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_v1.sqlite3"
    # Create an authentic schema v1 database
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE pillar_schema (component TEXT PRIMARY KEY, version INTEGER NOT NULL);
            INSERT INTO pillar_schema(component, version) VALUES ('digital_epigenetics', 1);
            CREATE TABLE epigenetic_lineage (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                generation_id TEXT NOT NULL UNIQUE,
                parent_digest TEXT,
                payload_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                approval_ref TEXT NOT NULL,
                created_at TEXT NOT NULL,
                entry_digest TEXT NOT NULL UNIQUE,
                signature TEXT NOT NULL
            );
            """
        )

    # Initialize service; should automatically migrate to v2
    service = DigitalEpigeneticsService(db_path, TEST_SIGNING_KEY)
    assert service.SCHEMA_VERSION == 2

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT version FROM pillar_schema WHERE component = 'digital_epigenetics'"
        ).fetchone()
        assert row[0] == 2
        cols = {
            c[1] for c in conn.execute("PRAGMA table_info(epigenetic_lineage)").fetchall()
        }
        assert "parent_generation_id" in cols
        assert "mutation_type" in cols
        assert "evidence_digest" in cols
        assert "policy_json" in cols
        assert "signer_id" in cols
        assert "rollback_target" in cols

        # Check active state table
        active_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='epigenetic_active_state'"
        ).fetchone()
        assert active_table is not None


def test_immutable_fields_violation(tmp_path: Path) -> None:
    service = DigitalEpigeneticsService(tmp_path / "lineage.sqlite3", TEST_SIGNING_KEY)

    forbidden_fields = [
        "brain_id",
        "dna_profile",
        "immutable_hash",
        "identity_anchor",
        "security_policy",
        "owner_goal",
        "ethics_invariants",
        "pure_logic_axioms",
        "authority",
        "risk_boundary",
    ]

    for field in forbidden_fields:
        with pytest.raises(LocalPillarError) as exc:
            service.append(
                generation_id=f"gen-forbidden-{field}",
                payload={field: "malicious_mutation"},
                evidence_refs=["artifact:test"],
                approval_ref="approval:test",
            )
        assert exc.value.code == "IMMUTABLE_FIELD_VIOLATION"
        assert field in str(exc.value)

    # Test nested immutable field
    with pytest.raises(LocalPillarError) as nested_exc:
        service.append(
            generation_id="gen-forbidden-nested",
            payload={"config": {"security_policy": "bypass"}},
            evidence_refs=["artifact:test"],
            approval_ref="approval:test",
        )
    assert nested_exc.value.code == "IMMUTABLE_FIELD_VIOLATION"


def test_mutable_traits_bounds(tmp_path: Path) -> None:
    service = DigitalEpigeneticsService(tmp_path / "lineage.sqlite3", TEST_SIGNING_KEY)

    # Valid mutation
    valid_res = service.append(
        generation_id="gen-valid-traits",
        payload={
            "batch_size": 32,
            "cache_limit_mb": 4096,
            "temperature": 0.7,
            "timeout_seconds": 15.0,
            "retention_days": 90,
            "log_level": "INFO",
            "max_concurrency": 16,
            "metric": 0.95,
        },
        evidence_refs=["artifact:bench-v1"],
        approval_ref="approval:admin",
    )
    assert valid_res.code == "LINEAGE_ENTRY_APPENDED"

    # Out-of-bounds batch_size
    with pytest.raises(LocalPillarError) as err_batch:
        service.append(
            generation_id="gen-invalid-batch",
            payload={"batch_size": 2048},  # max 1024
            evidence_refs=["artifact:test"],
            approval_ref="approval:test",
        )
    assert err_batch.value.code == "INVALID_INPUT"

    # Out-of-bounds temperature
    with pytest.raises(LocalPillarError) as err_temp:
        service.append(
            generation_id="gen-invalid-temp",
            payload={"temperature": 2.5},  # max 2.0
            evidence_refs=["artifact:test"],
            approval_ref="approval:test",
        )
    assert err_temp.value.code == "INVALID_INPUT"

    # Invalid log level
    with pytest.raises(LocalPillarError) as err_log:
        service.append(
            generation_id="gen-invalid-log",
            payload={"log_level": "VERBOSE"},
            evidence_refs=["artifact:test"],
            approval_ref="approval:test",
        )
    assert err_log.value.code == "INVALID_INPUT"


def test_privacy_scope_violation(tmp_path: Path) -> None:
    service = DigitalEpigeneticsService(tmp_path / "lineage.sqlite3", TEST_SIGNING_KEY)

    # Payload with credential / secret
    with pytest.raises(LocalPillarError) as exc_secret:
        service.append(
            generation_id="gen-leak-secret",
            payload={"api_key": "sk-secret-1234567890abcdef"},
            evidence_refs=["artifact:public"],
            approval_ref="approval:test",
        )
    assert exc_secret.value.code == "PRIVACY_VIOLATION"

    # Payload with SSN pattern
    with pytest.raises(LocalPillarError) as exc_ssn:
        service.append(
            generation_id="gen-leak-ssn",
            payload={"user_info": "SSN is 123-45-6789"},
            evidence_refs=["artifact:public"],
            approval_ref="approval:test",
        )
    assert exc_ssn.value.code == "PRIVACY_VIOLATION"

    # Evidence ref with private pattern
    with pytest.raises(LocalPillarError) as exc_ev:
        service.append(
            generation_id="gen-leak-ev",
            payload={"tuning": "ok"},
            evidence_refs=["bearer_token=abc12345xyz"],
            approval_ref="approval:test",
        )
    assert exc_ev.value.code == "PRIVACY_VIOLATION"


def test_stale_mutation_and_fork_conflict(tmp_path: Path) -> None:
    service = DigitalEpigeneticsService(tmp_path / "lineage.sqlite3", TEST_SIGNING_KEY)

    gen1 = service.append(
        generation_id="gen-001",
        payload={"batch_size": 16},
        evidence_refs=["artifact:gen1"],
        approval_ref="approval:gen1",
    )

    gen2 = service.append(
        generation_id="gen-002",
        payload={"batch_size": 32},
        evidence_refs=["artifact:gen2"],
        approval_ref="approval:gen2",
        expected_parent_generation_id="gen-001",
        expected_parent_digest=gen1.data["entry_digest"],
    )
    assert gen2.code == "LINEAGE_ENTRY_APPENDED"

    # Stale attempt referencing gen-001 as parent when head is gen-002
    with pytest.raises(LocalPillarError) as stale_err:
        service.append(
            generation_id="gen-003-conflict",
            payload={"batch_size": 64},
            evidence_refs=["artifact:gen3"],
            approval_ref="approval:gen3",
            expected_parent_generation_id="gen-001",  # Head is gen-002
        )
    assert stale_err.value.code == "STALE_MUTATION"

    # Fork conflict attempt with mismatched digest
    with pytest.raises(LocalPillarError) as fork_err:
        service.append(
            generation_id="gen-003-fork",
            payload={"batch_size": 64},
            evidence_refs=["artifact:gen3"],
            approval_ref="approval:gen3",
            expected_parent_generation_id="gen-002",
            expected_parent_digest="sha256:wrongdigest00000000000000000000000000000000000000000000000000000000",
        )
    assert fork_err.value.code == "LINEAGE_FORK_CONFLICT"


def test_rollback_execution_and_active_state(tmp_path: Path) -> None:
    service = DigitalEpigeneticsService(tmp_path / "lineage.sqlite3", TEST_SIGNING_KEY)

    # Initial state is empty
    initial_active = service.get_active_state()
    assert initial_active.data["generation_id"] is None

    # Gen 1
    gen1 = service.append(
        generation_id="gen-config-v1",
        payload={"batch_size": 16, "temperature": 0.5},
        evidence_refs=["artifact:test-v1"],
        approval_ref="approval:v1",
    )
    active1 = service.get_active_state()
    assert active1.data["generation_id"] == "gen-config-v1"
    assert active1.data["traits"] == {"batch_size": 16, "temperature": 0.5}

    # Gen 2
    service.append(
        generation_id="gen-config-v2",
        payload={"batch_size": 64, "temperature": 1.2},
        evidence_refs=["artifact:test-v2"],
        approval_ref="approval:v2",
    )
    active2 = service.get_active_state()
    assert active2.data["generation_id"] == "gen-config-v2"
    assert active2.data["traits"] == {"batch_size": 64, "temperature": 1.2}

    # Rollback to Gen 1
    rb = service.rollback(
        target_generation_id="gen-config-v1",
        approval_ref="approval:rollback-admin",
        generation_id="rollback-to-v1",
    )
    assert rb.code == "LINEAGE_ROLLBACK_APPLIED"
    assert rb.data["mutation_type"] == "ROLLBACK"
    assert rb.data["rollback_target"] == "gen-config-v1"
    assert rb.data["restored_traits"] == {"batch_size": 16, "temperature": 0.5}

    # Active state restored to Gen 1 traits
    active_after = service.get_active_state()
    assert active_after.data["generation_id"] == "rollback-to-v1"
    assert active_after.data["traits"] == {"batch_size": 16, "temperature": 0.5}

    # Entire chain verifies perfectly
    verified = service.verify()
    assert verified.code == "LINEAGE_VERIFIED"
    assert verified.data["entries"] == 3

    # Rollback to non-existent generation fails
    with pytest.raises(LocalPillarError) as missing_rb:
        service.rollback(
            target_generation_id="gen-does-not-exist",
            approval_ref="approval:test",
        )
    assert missing_rb.value.code == "GENERATION_NOT_FOUND"


def test_active_state_persistence_across_restart(tmp_path: Path) -> None:
    database = tmp_path / "lineage_durability.sqlite3"
    service1 = DigitalEpigeneticsService(database, TEST_SIGNING_KEY)

    service1.append(
        generation_id="gen-durable-01",
        payload={"batch_size": 32, "log_level": "WARNING"},
        evidence_refs=["artifact:durable"],
        approval_ref="approval:durable",
    )

    # Simulate process restart
    service2 = DigitalEpigeneticsService(database, TEST_SIGNING_KEY)
    active = service2.get_active_state()
    assert active.data["generation_id"] == "gen-durable-01"
    assert active.data["traits"] == {"batch_size": 32, "log_level": "WARNING"}
    assert service2.health_check() is True


def test_runtime_local_pillar_dispatch_and_propagation(tmp_path: Path) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "local-pillars",
        lineage_signing_key=TEST_SIGNING_KEY,
    )
    try:
        # Append via runtime
        res_append = runtime.execute_local_pillar(
            LINEAGE_CAPABILITY_ID,
            {
                "action": "append",
                "generation_id": "rt-gen-001",
                "payload": {"batch_size": 64, "temperature": 0.8},
                "evidence_refs": ["artifact:runtime-test"],
                "approval_ref": "approval:runtime",
            },
        )
        assert res_append.code == "LINEAGE_ENTRY_APPENDED"

        # Get active state via runtime
        res_active = runtime.execute_local_pillar(
            LINEAGE_CAPABILITY_ID,
            {"action": "get_active_state"},
        )
        assert res_active.code == "ACTIVE_STATE_READ"
        assert res_active.data["generation_id"] == "rt-gen-001"
        assert res_active.data["traits"]["batch_size"] == 64

        # Rollback via runtime
        res_rb = runtime.execute_local_pillar(
            LINEAGE_CAPABILITY_ID,
            {
                "action": "rollback",
                "target_generation_id": "rt-gen-001",
                "approval_ref": "approval:rt-rollback",
                "generation_id": "rt-gen-002-rb",
            },
        )
        assert res_rb.code == "LINEAGE_ROLLBACK_APPLIED"

        # Verify via runtime
        res_verify = runtime.execute_local_pillar(
            LINEAGE_CAPABILITY_ID,
            {"action": "verify"},
        )
        assert res_verify.code == "LINEAGE_VERIFIED"
        assert res_verify.data["entries"] == 2
    finally:
        runtime.close()
