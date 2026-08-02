"""
openusd.py — OpenUSD Parametric 3D Geometry Adapter.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from .base import SolverAdapter, SolverInput, SolverOutput


class OpenUSDGeometryAdapter(SolverAdapter):
    """Generates parametric OpenUSD USDA stage specifications for 3D designs."""

    @property
    def solver_name(self) -> str:
        return "OpenUSDGeometryAdapter"

    @property
    def domain(self) -> str:
        return "cad.parametric_3d"

    def generate_usda_script(self, concept_name: str, params: Dict[str, Any]) -> str:
        height = params.get("height_cm", 15.0)
        radius = params.get("radius_cm", 6.0)

        usda_content = f"""#usda 1.0
(
    defaultPrim = "Root"
    upAxis = "Y"
)

def Xform "Root"
{{
    def Cube "{concept_name.replace(' ', '_')}_Body"
    {{
        double size = {height}
        float3[] extent = [(-{radius}, -{radius}, -{radius}), ({radius}, {radius}, {radius})]
    }}
}}
"""
        return usda_content

    def solve(self, solver_input: SolverInput) -> SolverOutput:
        concept = solver_input.parameters.get("concept_name", "ParametricObject")
        usda = self.generate_usda_script(concept, solver_input.parameters)

        return SolverOutput(
            solver_name=self.solver_name,
            status="SUCCESS",
            metrics={
                "prim_count": 2,
                "format": "OpenUSD_ASCII",
                "content_length_bytes": len(usda),
            },
            output_files=[f"{concept.lower().replace(' ', '_')}.usda"],
        )
