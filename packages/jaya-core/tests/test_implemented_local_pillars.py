"""Real local behavior, persistence, failure, and runtime tests for P25/P29."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.core_config import CoreConfig
from jaya_core.pillars import DynamicPillarRegistry, PillarRuntimeView, load_manifest
from jaya_core.pillars.local_capabilities import (
    BINARY_DOT_CAPABILITY_ID,
    LINEAGE_CAPABILITY_ID,
    BinaryCortexService,
    DigitalEpigeneticsService,
    LocalPillarCapabilityService,
    LocalPillarError,
)

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "packages" / "jaya-core" / "src" / "jaya_core" / "contracts" / "40_pillars.yaml"
TEST_SIGNING_KEY = bytes(range(32))


def _append(store: DigitalEpigeneticsService, generation_id: str):
    return store.append(
        generation_id=generation_id,
        payload={"model_digest": f"sha256:{generation_id}", "metric": 0.73},
        evidence_refs=(f"artifact:{generation_id}",),
        approval_ref=f"approval:{generation_id}",
    )


def test_manifest_tracks_local_and_integrated_dependency_ready_pillars() -> None:
    definitions = {item.pillar_id: item for item in load_manifest(BASELINE)}

    assert definitions["P025"].initial_status.value == "VERIFIED"
    assert definitions["P025"].dependencies == ("P011", "P016", "P020")
    assert definitions["P025"].capability_id == LINEAGE_CAPABILITY_ID
    assert definitions["P029"].initial_status.value == "VERIFIED"
    assert definitions["P029"].dependencies == ("P002", "P013", "P021")
    assert definitions["P029"].capability_id == BINARY_DOT_CAPABILITY_ID
    assert definitions["P027"].initial_status.value == "VERIFIED"
    assert definitions["P023"].initial_status.value == "VERIFIED"
    assert definitions["P008"].initial_status.value == "VERIFIED"
    assert definitions["P026"].initial_status.value == "VERIFIED"
    assert all(
        definitions[pillar].initial_status.value == "INTEGRATED"
        for pillar in (
            "P004",
            "P009",
            "P019",
            "P028",
            "P040",
        )
    )
    assert all(
        definitions[pillar].initial_status.value == "INTEGRATED"
        for pillar in (
            "P003",
            "P033",
            "P036",
            "P037",
            "P038",
            "P039",
        )
    )


def test_p025_persists_reads_lists_and_verifies_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "lineage.sqlite3"
    first_store = DigitalEpigeneticsService(database, TEST_SIGNING_KEY)
    first = _append(first_store, "generation-001")

    restarted = DigitalEpigeneticsService(database, TEST_SIGNING_KEY)
    second = _append(restarted, "generation-002")

    assert second.status == "INTEGRATED"
    assert second.data["parent_digest"] == first.data["entry_digest"]
    assert restarted.get("generation-001").data["payload"]["metric"] == 0.73
    listed = restarted.list_entries(limit=10)
    assert [entry["generation_id"] for entry in listed.data["entries"]] == [
        "generation-001",
        "generation-002",
    ]
    verified = DigitalEpigeneticsService(database, TEST_SIGNING_KEY).verify()
    assert verified.data == {"entries": 2, "head_digest": second.data["entry_digest"]}


def test_p025_rejects_duplicate_unknown_fields_and_missing_generation(tmp_path: Path) -> None:
    store = DigitalEpigeneticsService(tmp_path / "lineage.sqlite3", TEST_SIGNING_KEY)
    _append(store, "generation-001")

    with pytest.raises(LocalPillarError) as duplicate:
        _append(store, "generation-001")
    assert duplicate.value.code == "DUPLICATE_GENERATION"

    with pytest.raises(LocalPillarError) as unknown:
        store.execute({"action": "verify", "unexpected": True})
    assert unknown.value.code == "UNKNOWN_FIELD"

    with pytest.raises(LocalPillarError) as missing:
        store.get("generation-missing")
    assert missing.value.code == "GENERATION_NOT_FOUND"


def test_p025_detects_tampering_and_wrong_key_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "lineage.sqlite3"
    store = DigitalEpigeneticsService(database, TEST_SIGNING_KEY)
    _append(store, "generation-001")

    wrong_key = b"w" * 32
    with pytest.raises(LocalPillarError) as wrong_key_error:
        DigitalEpigeneticsService(database, wrong_key).verify()
    assert wrong_key_error.value.code == "LINEAGE_SIGNATURE_INVALID"

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE epigenetic_lineage SET payload_json = ? WHERE generation_id = ?",
            ('{"metric":1}', "generation-001"),
        )
    with pytest.raises(LocalPillarError) as tampered:
        store.verify()
    assert tampered.value.code == "LINEAGE_SIGNATURE_INVALID"
    with pytest.raises(LocalPillarError) as append_after_tamper:
        _append(store, "generation-002")
    assert append_after_tamper.value.code == "LINEAGE_SIGNATURE_INVALID"
    assert store.health_check() is False


def test_p025_requires_persistent_storage_and_a_valid_secret(tmp_path: Path) -> None:
    with pytest.raises(LocalPillarError) as in_memory:
        DigitalEpigeneticsService(":memory:", TEST_SIGNING_KEY)
    assert in_memory.value.code == "INVALID_CONFIG"

    with pytest.raises(LocalPillarError) as short_key:
        DigitalEpigeneticsService(tmp_path / "lineage.sqlite3", b"short")
    assert short_key.value.code == "INVALID_CONFIG"

    with pytest.raises(LocalPillarError) as unavailable:
        DigitalEpigeneticsService(tmp_path, TEST_SIGNING_KEY)
    assert unavailable.value.code == "STORAGE_UNAVAILABLE"


def test_p025_enforces_payload_resource_limit(tmp_path: Path) -> None:
    store = DigitalEpigeneticsService(tmp_path / "lineage.sqlite3", TEST_SIGNING_KEY)
    with pytest.raises(LocalPillarError) as oversized:
        store.append(
            generation_id="generation-oversized",
            payload={"content": "x" * store.MAX_PAYLOAD_BYTES},
            evidence_refs=("artifact:oversized",),
            approval_ref="approval:oversized",
        )
    assert oversized.value.code == "RESOURCE_LIMIT"


def test_p029_executes_bitpacked_kernel_and_validates_inputs() -> None:
    service = BinaryCortexService()
    result = service.dot([1, -1, 1, 1], [1, 1, -1, 1])

    assert result.status == "INTEGRATED"
    assert result.data["matches"] == 2
    assert result.data["dot_product"] == 0
    assert result.data["packed_bytes"] == 1
    assert service.health_check() is True

    with pytest.raises(LocalPillarError) as shape:
        service.dot([1, -1], [1])
    assert shape.value.code == "SHAPE_MISMATCH"
    with pytest.raises(LocalPillarError) as value:
        service.dot([1.0], [1])
    assert value.value.code == "INVALID_INPUT"
    with pytest.raises(LocalPillarError) as empty:
        service.dot([], [])
    assert empty.value.code == "RESOURCE_LIMIT"


def test_p029_benchmark_measures_and_verifies_real_execution() -> None:
    service = BinaryCortexService()
    left = [1 if index % 3 else -1 for index in range(1_024)]
    right = [1 if index % 5 else -1 for index in range(1_024)]

    result = service.benchmark(left, right, iterations=25)

    assert result.data["elapsed_ns"] > 0
    assert result.data["operations_per_second"] > 0
    assert result.data["verified_against"] == "PYTHON_SCALAR_DOT"
    assert result.data["dot_product"] == sum(a * b for a, b in zip(left, right, strict=True))
    with pytest.raises(LocalPillarError) as unbounded:
        service.benchmark(left, right, iterations=10_001)
    assert unbounded.value.code == "RESOURCE_LIMIT"


def test_capability_service_fails_closed_without_p25_secret(tmp_path: Path) -> None:
    service = LocalPillarCapabilityService(data_dir=tmp_path)
    manifests = {item.capability_id: item for item in service.manifests()}

    assert manifests[LINEAGE_CAPABILITY_ID].health_status == "UNHEALTHY"
    assert manifests[BINARY_DOT_CAPABILITY_ID].health_status == "HEALTHY"
    with pytest.raises(LocalPillarError) as unavailable:
        service.execute(LINEAGE_CAPABILITY_ID, {"action": "verify"})
    assert unavailable.value.code == "CAPABILITY_UNAVAILABLE"
    assert not (tmp_path / "digital_epigenetics.sqlite3").exists()


def test_runtime_registers_and_executes_both_local_pillars_end_to_end(
    tmp_path: Path,
) -> None:
    registry = DynamicPillarRegistry(
        database_path=tmp_path / "pillar-registry.sqlite3",
        manifest_paths=(BASELINE,),
    )
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        pillar_registry=registry,
        local_pillar_data_dir=tmp_path / "local-pillars",
        lineage_signing_key=TEST_SIGNING_KEY,
    )
    runtime.pillar_runtime_view = PillarRuntimeView(registry, runtime.capability_registry)
    try:
        appended = runtime.execute_local_pillar(
            LINEAGE_CAPABILITY_ID,
            {
                "action": "append",
                "generation_id": "runtime-generation-001",
                "payload": {"model_digest": "sha256:runtime"},
                "evidence_refs": ["artifact:runtime-evaluation"],
                "approval_ref": "approval:runtime-owner",
            },
        )
        binary = runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {"left": [1, -1, 1], "right": [1, 1, -1]},
        )
        snapshot = runtime.operational_snapshot()
        pillars = {item["pillar_id"]: item for item in snapshot["pillars"]["pillars"]}

        assert appended.code == "LINEAGE_ENTRY_APPENDED"
        assert binary.data["dot_product"] == -1
        assert pillars["P025"]["runtime_available"] is True
        assert pillars["P029"]["runtime_available"] is True
        capabilities = snapshot["local_pillar_capabilities"]["capabilities"]
        assert capabilities[BINARY_DOT_CAPABILITY_ID] == "HEALTHY"
        assert capabilities[LINEAGE_CAPABILITY_ID] == "HEALTHY"
    finally:
        runtime.close()

    restarted = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "local-pillars",
        lineage_signing_key=TEST_SIGNING_KEY,
    )
    try:
        verified = restarted.execute_local_pillar(LINEAGE_CAPABILITY_ID, {"action": "verify"})
        assert verified.data["entries"] == 1
        assert verified.data["head_digest"] == appended.data["entry_digest"]
    finally:
        restarted.close()


def test_runtime_marks_p25_unhealthy_when_secret_is_missing(tmp_path: Path) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "local-pillars",
    )
    try:
        with pytest.raises(LocalPillarError) as unavailable:
            runtime.execute_local_pillar(LINEAGE_CAPABILITY_ID, {"action": "verify"})
        assert unavailable.value.code == "CAPABILITY_UNAVAILABLE"
        assert (
            runtime.capability_registry.lookup(LINEAGE_CAPABILITY_ID).health_status == "UNHEALTHY"
        )
    finally:
        runtime.close()


def test_lineage_secret_is_validated_and_redacted_by_core_config(tmp_path: Path) -> None:
    secret = "local-lineage-secret-with-32-characters"
    config = CoreConfig.from_env(
        {
            "JAYA_ENVIRONMENT": "test",
            "JAYA_CORE_DATA_DIR": str(tmp_path),
            "JAYA_LINEAGE_SIGNING_KEY": secret,
        },
        core_dir=ROOT,
    )

    assert config.lineage_signing_key.get_secret_value() == secret
    assert config.to_safe_dict()["lineage_signing_key_configured"] is True
    assert secret not in json.dumps(config.to_safe_dict())


def test_canonical_launcher_wires_configured_local_pillars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import run_jaya_core_server

    secret = "launcher-lineage-secret-with-32-characters"
    monkeypatch.delenv("JAYA_PILLAR_MANIFEST_PATHS", raising=False)
    monkeypatch.delenv("JAYA_PILLAR_REGISTRY_DB", raising=False)
    config = CoreConfig.from_env(
        {
            "JAYA_ENVIRONMENT": "test",
            "JAYA_CORE_DATA_DIR": str(tmp_path),
            "JAYA_NODE_ID": "local-pillar-launcher-test",
            "JAYA_LINEAGE_SIGNING_KEY": secret,
        },
        core_dir=ROOT,
    )

    runtime = run_jaya_core_server._build_runtime(config)
    try:
        result = runtime.execute_local_pillar(LINEAGE_CAPABILITY_ID, {"action": "verify"})
        snapshot = runtime.operational_snapshot()
        p25 = next(item for item in snapshot["pillars"]["pillars"] if item["pillar_id"] == "P025")

        assert result.data["entries"] == 0
        assert p25["runtime_available"] is True
        assert (
            runtime.capability_registry.lookup(BINARY_DOT_CAPABILITY_ID).health_status == "HEALTHY"
        )
    finally:
        runtime.close()
