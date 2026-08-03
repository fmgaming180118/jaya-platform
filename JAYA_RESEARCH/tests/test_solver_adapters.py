"""
test_solver_adapters.py — Unit tests for OpenUSD & Physics Solver Adapters & Digital Twin Builder.

STATUS: PhysX test updated to verify PROTOTYPE behavior (mock arithmetic only).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_RESEARCH"))

from src.discovery.contracts import DiscoveryArtifactType
from src.discovery.digital_twin import DigitalTwinBuilder
from src.discovery.solver_adapters.base import SolverInput
from src.discovery.solver_adapters.openusd import OpenUSDGeometryAdapter
from src.discovery.solver_adapters.physx import PhysXSolverAdapter


class TestSolverAdapters:
    def test_openusd_geometry_adapter(self):
        adapter = OpenUSDGeometryAdapter()
        inp = SolverInput(
            solver_name="OpenUSDGeometryAdapter",
            domain="cad.parametric_3d",
            parameters={"concept_name": "MiniPC_Case", "height_cm": 20.0, "radius_cm": 8.0},
        )
        out = adapter.solve(inp)

        assert out.status == "SUCCESS"
        assert out.metrics["format"] == "OpenUSD_ASCII"
        assert len(out.output_files) == 1
        assert "minipc_case.usda" in out.output_files[0]

    def test_physx_solver_adapter_prototype(self):
        """Verify PhysXSolverAdapter returns PROTOTYPE_MOCK status (not SUCCESS)."""
        adapter = PhysXSolverAdapter()
        inp = SolverInput(
            solver_name="PhysXSolverAdapter",
            domain="physics.multiphysics.prototype",
            parameters={"mass_kg": 10.0, "applied_force_n": 500.0},
        )
        out = adapter.solve(inp)

        # PROTOTYPE: Should return PROTOTYPE_MOCK, not SUCCESS
        assert out.status == "PROTOTYPE_MOCK"
        assert out.metrics["calculated_acceleration_m_s2"] == 50.0
        assert "estimated_max_stress_mpa" in out.metrics
        assert "warning" in out.metrics
        assert "MOCK CALCULATIONS ONLY" in out.metrics["warning"]

    def test_digital_twin_builder(self):
        openusd = OpenUSDGeometryAdapter()
        physx = PhysXSolverAdapter()

        inp_usd = SolverInput(
            solver_name="OpenUSDGeometryAdapter",
            domain="cad.parametric_3d",
            parameters={"concept_name": "HTS_Coil", "height_cm": 10.0},
        )
        out_usd = openusd.solve(inp_usd)
        usda_script = openusd.generate_usda_script("HTS_Coil", inp_usd.parameters)

        inp_phys = SolverInput(
            solver_name="PhysXSolverAdapter",
            domain="physics.multiphysics.prototype",
            parameters={"mass_kg": 2.0, "applied_force_n": 50.0},
        )
        out_phys = physx.solve(inp_phys)

        builder = DigitalTwinBuilder()
        dt_artifact = builder.assemble("HTS_Coil", usda_script, out_phys.metrics)

        assert dt_artifact.artifact_type == DiscoveryArtifactType.DIGITAL_TWIN
        assert dt_artifact.status == "CANDIDATE"
        assert "usda_script" in dt_artifact.payload
        assert "solver_results" in dt_artifact.payload


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
