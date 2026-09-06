from pathlib import Path

from jaya_core.capabilities.manifest import CapabilityManifest
from jaya_core.capabilities.registry import CapabilityRegistry
from jaya_core.pillars import DynamicPillarRegistry, PillarRuntimeView

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


def test_runtime_view_only_marks_real_healthy_bindings_available(tmp_path: Path) -> None:
    registry = DynamicPillarRegistry(
        database_path=tmp_path / "pillars.db",
        manifest_paths=(BASELINE,),
    )
    capabilities = CapabilityRegistry()
    capabilities.register(
        CapabilityManifest(
            capability_id="core.logic.evaluate",
            version="1.0.0",
            provider="pure_logic_solver",
            execution_location="local",
            health_status="HEALTHY",
        )
    )

    snapshot = PillarRuntimeView(registry, capabilities).snapshot()
    pure_logic = next(item for item in snapshot["pillars"] if item["pillar_id"] == "P001")
    active_dreaming = next(item for item in snapshot["pillars"] if item["pillar_id"] == "P003")

    assert snapshot["total"] == 40
    assert pure_logic["runtime_available"] is True
    assert pure_logic["runtime_code"] == "AVAILABLE"
    assert active_dreaming["runtime_available"] is False
    assert active_dreaming["runtime_code"] == "CAPABILITY_NOT_REGISTERED"


def test_registered_but_unverified_capability_is_not_available(tmp_path: Path) -> None:
    registry = DynamicPillarRegistry(
        database_path=tmp_path / "pillars.db",
        manifest_paths=(BASELINE,),
    )
    capabilities = CapabilityRegistry()
    capabilities.register(
        CapabilityManifest(
            capability_id="core.logic.evaluate",
            version="1.0.0",
            provider="pure_logic_solver",
            execution_location="local",
        )
    )

    snapshot = PillarRuntimeView(registry, capabilities).snapshot()
    pure_logic = next(item for item in snapshot["pillars"] if item["pillar_id"] == "P001")

    assert pure_logic["runtime_available"] is False
    assert pure_logic["runtime_code"] == "REGISTERED_UNVERIFIED"


def test_production_launcher_injects_the_registry_into_core_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from scripts import run_jaya_core_server

    run_jaya_core_server._canonical_components()
    from jaya_core.core_config import CoreConfig

    monkeypatch.delenv("JAYA_PILLAR_MANIFEST_PATHS", raising=False)
    monkeypatch.delenv("JAYA_PILLAR_REGISTRY_DB", raising=False)
    config = CoreConfig.from_env(
        {
            "JAYA_ENVIRONMENT": "test",
            "JAYA_CORE_DATA_DIR": str(tmp_path),
            "JAYA_NODE_ID": "pillar-integration-node",
        },
        core_dir=ROOT,
    )
    runtime = run_jaya_core_server._build_runtime(config)
    try:
        snapshot = runtime.operational_snapshot()
        pure_logic = next(
            item
            for item in snapshot["pillars"]["pillars"]
            if item["pillar_id"] == "P001"
        )

        assert runtime.pillar_registry.health_check()
        assert snapshot["pillars"]["total"] == 40
        assert pure_logic["runtime_available"] is True
        assert pure_logic["runtime_code"] == "AVAILABLE"
    finally:
        runtime.close()
