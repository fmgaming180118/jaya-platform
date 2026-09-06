"""Encrypted recovery, bootstrap, and migration tests for P9/P28/P19."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.maintenance_capabilities import (
    BOOTSTRAP_CAPABILITY_ID,
    LEGACY_CAPABILITY_ID,
    REGENERATION_CAPABILITY_ID,
    LegacyProtocolCapability,
    NeuralRegenerationCapability,
    SelfBootstrappingCapability,
)

MAINTENANCE_KEY = b"maintenance-test-key-that-is-longer-than-thirty-two-bytes"


class RetrievalTestProvider:
    provider_type = "TEST_IMPLEMENTATION"

    def health_check(self) -> bool:
        return True

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return {"answer": question, "citations": [evidence[0]["evidence_id"]]}


def _signature(material: bytes) -> str:
    return hmac.new(MAINTENANCE_KEY, material, hashlib.sha256).hexdigest()


def _rag(tmp_path: Path) -> tuple[AgenticRAGCapability, str]:
    rag = AgenticRAGCapability(tmp_path / "rag.sqlite3", RetrievalTestProvider())
    rag.execute(
        {
            "action": "ingest",
            "source_ref": "artifact:maintenance-evidence",
            "title": "Capability gap evidence",
            "content": "Repeated measurements require a reusable local mean aggregation capability.",
        }
    )
    return rag, rag.retrieve("measurements mean aggregation", 2)[0]["evidence_id"]


def test_p009_encrypted_backup_restore_quarantine_canary_and_restart(tmp_path: Path) -> None:
    root = tmp_path / "recovery"
    source = root / "state" / "settings.json"
    source.parent.mkdir(parents=True)
    original = b'{"mode":"verified","revision":7}'
    source.write_bytes(original)
    database = tmp_path / "recovery.sqlite3"
    recovery = NeuralRegenerationCapability(root, database, MAINTENANCE_KEY)
    backup = recovery.execute(
        {
            "action": "backup",
            "artifact_id": "settings",
            "version": 1,
            "source_path": "state/settings.json",
            "content_type": "JSON",
        }
    )
    wrapper_path = root / "recovery-points" / "settings-1.recovery.json"
    assert original not in wrapper_path.read_bytes()
    source.write_bytes(b"corrupt")
    restarted = NeuralRegenerationCapability(root, database, MAINTENANCE_KEY)
    restored = restarted.execute(
        {
            "action": "restore",
            "artifact_id": "settings",
            "version": 1,
            "destination_path": "state/settings.json",
            "corruption_signal": "CHECKSUM_MISMATCH",
        }
    )
    assert source.read_bytes() == original
    assert restored.data["canary"] == "PASSED"
    assert restored.data["previous_state_quarantined"] is True
    assert backup.data["plaintext_digest"] == restored.data["content_digest"]


def test_p009_fails_closed_for_corrupt_recovery_and_missing_key(tmp_path: Path) -> None:
    root = tmp_path / "recovery"
    source = root / "state.bin"
    root.mkdir()
    source.write_bytes(b"trusted-state")
    recovery = NeuralRegenerationCapability(root, tmp_path / "recovery.sqlite3", MAINTENANCE_KEY)
    recovery.execute(
        {
            "action": "backup",
            "artifact_id": "state",
            "version": 1,
            "source_path": "state.bin",
            "content_type": "BINARY",
        }
    )
    wrapper = root / "recovery-points" / "state-1.recovery.json"
    wrapper.write_bytes(wrapper.read_bytes()[:-8] + b"broken!!")
    with pytest.raises(LocalPillarError) as corrupt:
        recovery.execute(
            {
                "action": "restore",
                "artifact_id": "state",
                "version": 1,
                "destination_path": "restored.bin",
                "corruption_signal": "READ_FAILURE",
            }
        )
    assert corrupt.value.code == "RECOVERY_POINT_CORRUPT"
    unavailable = NeuralRegenerationCapability(
        tmp_path / "unavailable", tmp_path / "unavailable.sqlite3", None
    )
    assert unavailable.health_check() is False


def test_p028_builds_tests_installs_executes_and_rolls_back_candidate(tmp_path: Path) -> None:
    rag, evidence_id = _rag(tmp_path)
    root = tmp_path / "bootstrap"
    database = tmp_path / "bootstrap.sqlite3"
    bootstrap = SelfBootstrappingCapability(root, database, MAINTENANCE_KEY, rag)
    proposed = bootstrap.execute(
        {
            "action": "propose",
            "candidate_id": "mean-aggregator-v1",
            "capability_id": "research.aggregate.mean",
            "capability_gap": "Aggregate bounded local measurements reproducibly",
            "operation": "mean",
            "evidence_ids": [evidence_id],
            "acceptance_cases": [
                {"values": [1, 2, 3], "expected": 2},
                {"values": [4, 8], "expected": 6},
            ],
        }
    )
    validated = bootstrap.execute({"action": "validate", "candidate_id": "mean-aggregator-v1"})
    material = (
        f"install|mean-aggregator-v1|{proposed.data['artifact_digest']}|"
        f"{validated.data['validation_digest']}|approval-1|owner-a"
    ).encode()
    installed = bootstrap.execute(
        {
            "action": "install",
            "candidate_id": "mean-aggregator-v1",
            "approval_id": "approval-1",
            "approved_by": "owner-a",
            "signature": _signature(material),
        }
    )
    restarted = SelfBootstrappingCapability(root, database, MAINTENANCE_KEY, rag)
    invoked = restarted.execute(
        {"action": "invoke", "candidate_id": "mean-aggregator-v1", "values": [10, 20, 30]}
    )
    rollback_material = (
        f"rollback_bootstrap|mean-aggregator-v1|{proposed.data['artifact_digest']}|"
        "rollback-1|owner-a"
    ).encode()
    rolled_back = restarted.execute(
        {
            "action": "rollback",
            "candidate_id": "mean-aggregator-v1",
            "rollback_id": "rollback-1",
            "approved_by": "owner-a",
            "signature": _signature(rollback_material),
        }
    )
    assert validated.data["passed"] is True
    assert installed.data["canary"] == "PASSED"
    assert invoked.data["result"] == 20
    assert rolled_back.code == "BOOTSTRAP_CANDIDATE_ROLLED_BACK"
    with pytest.raises(LocalPillarError) as retired:
        restarted.execute(
            {"action": "invoke", "candidate_id": "mean-aggregator-v1", "values": [1, 2]}
        )
    assert retired.value.code == "CANDIDATE_CORRUPT"


def test_p028_rejects_failed_acceptance_and_invalid_approval(tmp_path: Path) -> None:
    rag, evidence_id = _rag(tmp_path)
    bootstrap = SelfBootstrappingCapability(
        tmp_path / "bootstrap", tmp_path / "bootstrap.sqlite3", MAINTENANCE_KEY, rag
    )
    bootstrap.execute(
        {
            "action": "propose",
            "candidate_id": "bad-sum",
            "capability_id": "research.aggregate.bad",
            "capability_gap": "A deliberately failing acceptance gate",
            "operation": "sum",
            "evidence_ids": [evidence_id],
            "acceptance_cases": [{"values": [1, 2], "expected": 99}],
        }
    )
    validation = bootstrap.execute({"action": "validate", "candidate_id": "bad-sum"})
    assert validation.data["passed"] is False
    with pytest.raises(LocalPillarError) as install:
        bootstrap.execute(
            {
                "action": "install",
                "candidate_id": "bad-sum",
                "approval_id": "approval",
                "approved_by": "owner",
                "signature": "0" * 64,
            }
        )
    assert install.value.code == "CANDIDATE_NOT_VALIDATED"


def test_p019_migrates_preserves_sections_verifies_restart_and_rolls_back(tmp_path: Path) -> None:
    root = tmp_path / "migration"
    root.mkdir()
    payload = {
        "schema_version": 1,
        "brain_id": "brain-legacy-1",
        "identity": {"owner_id": "owner-a"},
        "memory": [{"event": "legacy-memory"}],
        "policy": {"remote": False},
    }
    source = root / "legacy.jaya1"
    source_bytes = LegacyProtocolCapability.LEGACY_MAGIC + json.dumps(payload).encode()
    source.write_bytes(source_bytes)
    source_digest = f"sha256:{hashlib.sha256(source_bytes).hexdigest()}"
    material = f"migrate|{source_digest}|current.jaya|approval-1|owner-a".encode()
    database = tmp_path / "migration.sqlite3"
    legacy = LegacyProtocolCapability(root, database, MAINTENANCE_KEY)
    migrated = legacy.execute(
        {
            "action": "migrate",
            "source_path": "legacy.jaya1",
            "output_path": "current.jaya",
            "owner_id": "owner-a",
            "approval_id": "approval-1",
            "signature": _signature(material),
        }
    )
    assert source.read_bytes() == source_bytes
    restarted = LegacyProtocolCapability(root, database, MAINTENANCE_KEY)
    inspected = restarted.execute({"action": "inspect", "path": "current.jaya"})
    assert inspected.data["brain_id"] == "brain-legacy-1"
    assert inspected.data["sections"] == ["identity", "memory", "policy"]
    rollback_material = (
        f"rollback_migration|{migrated.data['migration_id']}|{migrated.data['output_digest']}|"
        "rollback-1|owner-a"
    ).encode()
    restarted.execute(
        {
            "action": "rollback",
            "migration_id": migrated.data["migration_id"],
            "rollback_id": "rollback-1",
            "owner_id": "owner-a",
            "signature": _signature(rollback_material),
        }
    )
    assert not (root / "current.jaya").exists()
    assert source.read_bytes() == source_bytes


def test_p019_rejects_unknown_and_truncated_legacy_formats(tmp_path: Path) -> None:
    root = tmp_path / "migration"
    root.mkdir()
    (root / "unknown.bin").write_bytes(b"UNKNOWN\n{}")
    legacy = LegacyProtocolCapability(root, tmp_path / "migration.sqlite3", MAINTENANCE_KEY)
    with pytest.raises(LocalPillarError) as unknown:
        legacy.execute(
            {
                "action": "migrate",
                "source_path": "unknown.bin",
                "output_path": "out.jaya",
                "owner_id": "owner",
                "approval_id": "approval",
                "signature": "0" * 64,
            }
        )
    assert unknown.value.code == "LEGACY_VERSION_UNSUPPORTED"


def test_runtime_dispatches_maintenance_chain(tmp_path: Path) -> None:
    pillar_data = tmp_path / "pillars"
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=pillar_data,
        lineage_signing_key=MAINTENANCE_KEY,
        ollama_base_url="http://127.0.0.1:11434",
        local_model_name="qwen3.5:0.8b",
    )
    try:
        health = runtime.operational_snapshot()["local_pillar_capabilities"]["capabilities"]
        assert health[REGENERATION_CAPABILITY_ID] == "HEALTHY"
        assert health[BOOTSTRAP_CAPABILITY_ID] == "HEALTHY"
        assert health[LEGACY_CAPABILITY_ID] == "HEALTHY"
        recovery_root = pillar_data / "maintenance" / "recovery"
        (recovery_root / "runtime.json").write_text('{"ready":true}', encoding="utf-8")
        created = runtime.execute_local_pillar(
            REGENERATION_CAPABILITY_ID,
            {
                "action": "backup",
                "artifact_id": "runtime-state",
                "version": 1,
                "source_path": "runtime.json",
                "content_type": "JSON",
            },
        )
        assert created.code == "ENCRYPTED_RECOVERY_POINT_CREATED"
    finally:
        runtime.close()
