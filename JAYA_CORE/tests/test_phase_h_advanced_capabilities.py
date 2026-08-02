"""
test_phase_h_advanced_capabilities.py — Unit tests for Phase H: Advanced Capabilities.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

from src.capabilities.benchmark import CapabilityPackBenchmarkEngine
from src.capabilities.pack_manager import DynamicCapabilityPackManager
from src.capabilities.packs.cad_basic_pack import CadBasicCapabilityPack
from src.capabilities.registry import CapabilityRegistry
from src.cognitive.domain_validator import DomainBoundaryValidator


class TestDomainBoundaryValidator:
    def test_cognitive_kernel_is_domain_neutral(self):
        validator = DomainBoundaryValidator()
        report = validator.validate_cognitive_kernel()
        assert report.is_domain_neutral is True
        assert report.violations_count == 0
        assert report.scanned_files_count > 0


class TestCadBasicCapabilityPack:
    def test_cad_basic_primitives_generation(self):
        pack = CadBasicCapabilityPack()
        assert pack.pack_id == "cad.basic"
        assert len(pack.get_manifests()) == 4

        # Test cube
        res_cube = pack.execute_capability("cad.basic.create_cube", {"size": 3.0})
        assert res_cube["status"] == "SUCCESS"
        assert "#usda 1.0" in res_cube["usda_content"]
        assert "double size = 3.0" in res_cube["usda_content"]

        # Test box
        res_box = pack.execute_capability(
            "cad.basic.create_box", {"width": 5.0, "height": 2.0, "depth": 10.0}
        )
        assert res_box["status"] == "SUCCESS"
        assert "ParametricBox" in res_box["usda_content"]


class TestDynamicCapabilityPackManager:
    def test_live_pack_installation_execution_and_uninstallation(self):
        registry = CapabilityRegistry()
        manager = DynamicCapabilityPackManager(registry)
        pack = CadBasicCapabilityPack()

        # Live install
        installed = manager.install_pack(pack)
        assert installed is True
        assert len(manager.list_installed_packs()) == 1

        # Check registry manifests
        manifest = registry.lookup("cad.basic.create_cube")
        assert manifest is not None
        assert manifest.capability_id == "cad.basic.create_cube"

        # Execute pack capability via manager
        output = manager.execute_pack_capability(
            "cad.basic", "cad.basic.create_sphere", {"radius": 2.5}
        )
        assert output["status"] == "SUCCESS"
        assert "double radius = 2.5" in output["usda_content"]

        # Live uninstall
        uninstalled = manager.uninstall_pack("cad.basic")
        assert uninstalled is True
        assert len(manager.list_installed_packs()) == 0
        assert registry.lookup("cad.basic.create_cube") is None


class TestCapabilityPackBenchmarkEngine:
    def test_benchmark_capability_resources(self):
        pack = CadBasicCapabilityPack()
        engine = CapabilityPackBenchmarkEngine()

        report = engine.benchmark_capability(pack, "cad.basic.create_cube", {"size": 2.0})
        assert report.status == "BENCHMARK_PASSED"
        assert report.ram_delta_mb <= 30.0
        assert report.execution_latency_ms >= 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
