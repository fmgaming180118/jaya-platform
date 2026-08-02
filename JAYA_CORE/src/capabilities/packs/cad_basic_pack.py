"""
cad_basic_pack.py — CAD Basic Capability Pack (`cad.basic`).

Implements 3D primitive geometry generation (cube, sphere, cylinder, parametric box)
in OpenUSD (.usda) format. Hot-pluggable without touching Cognitive Kernel source.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from src.capabilities.manifest import CapabilityManifest
from src.capabilities.pack_manager import CapabilityPack
from src.capabilities.registry import CapabilityRegistry

logger = logging.getLogger(__name__)


class CadBasicCapabilityPack(CapabilityPack):
    """Capability Pack providing basic 3D CAD geometry generation in OpenUSD (.usda) format."""

    def __init__(self) -> None:
        super().__init__(
            pack_id="cad.basic",
            version="1.0.0",
            description="Basic 3D CAD primitive geometry generation in OpenUSD USDA format",
        )

    def get_manifests(self) -> List[CapabilityManifest]:
        return [
            CapabilityManifest(
                capability_id="cad.basic.create_cube",
                version="1.0.0",
                provider="cad_basic_pack",
                execution_location="local",
                min_memory_mb=64,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="cad.basic.create_sphere",
                version="1.0.0",
                provider="cad_basic_pack",
                execution_location="local",
                min_memory_mb=64,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="cad.basic.create_cylinder",
                version="1.0.0",
                provider="cad_basic_pack",
                execution_location="local",
                min_memory_mb=64,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="cad.basic.create_box",
                version="1.0.0",
                provider="cad_basic_pack",
                execution_location="local",
                min_memory_mb=64,
                offline_available=True,
            ),
        ]

    def install(self, registry: CapabilityRegistry) -> bool:
        for manifest in self.get_manifests():
            registry.register(manifest)
        return True

    def uninstall(self, registry: CapabilityRegistry) -> bool:
        for manifest in self.get_manifests():
            registry.unregister(manifest.capability_id)
        return True

    def execute_capability(self, capability_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        if capability_id == "cad.basic.create_cube":
            size = float(inputs.get("size", 2.0))
            usda_text = self._generate_usda_cube(size)
            return {"status": "SUCCESS", "format": "usda", "shape": "cube", "size": size, "usda_content": usda_text}

        elif capability_id == "cad.basic.create_sphere":
            radius = float(inputs.get("radius", 1.0))
            usda_text = self._generate_usda_sphere(radius)
            return {"status": "SUCCESS", "format": "usda", "shape": "sphere", "radius": radius, "usda_content": usda_text}

        elif capability_id == "cad.basic.create_cylinder":
            radius = float(inputs.get("radius", 1.0))
            height = float(inputs.get("height", 3.0))
            usda_text = self._generate_usda_cylinder(radius, height)
            return {"status": "SUCCESS", "format": "usda", "shape": "cylinder", "radius": radius, "height": height, "usda_content": usda_text}

        elif capability_id == "cad.basic.create_box":
            width = float(inputs.get("width", 2.0))
            height = float(inputs.get("height", 3.0))
            depth = float(inputs.get("depth", 4.0))
            usda_text = self._generate_usda_box(width, height, depth)
            return {
                "status": "SUCCESS",
                "format": "usda",
                "shape": "box",
                "dimensions": {"width": width, "height": height, "depth": depth},
                "usda_content": usda_text,
            }

        else:
            raise KeyError(f"[CADError] Capability '{capability_id}' not recognized by CadBasicCapabilityPack")

    def _generate_usda_cube(self, size: float) -> str:
        return f"""#usda 1.0
(
    defaultPrim = "CubePrim"
    upAxis = "Y"
)

def Cube "CubePrim"
{{
    double size = {size}
    uniform token axis = "Y"
}}
"""

    def _generate_usda_sphere(self, radius: float) -> str:
        return f"""#usda 1.0
(
    defaultPrim = "SpherePrim"
    upAxis = "Y"
)

def Sphere "SpherePrim"
{{
    double radius = {radius}
}}
"""

    def _generate_usda_cylinder(self, radius: float, height: float) -> str:
        return f"""#usda 1.0
(
    defaultPrim = "CylinderPrim"
    upAxis = "Y"
)

def Cylinder "CylinderPrim"
{{
    double radius = {radius}
    double height = {height}
    uniform token axis = "Y"
}}
"""

    def _generate_usda_box(self, width: float, height: float, depth: float) -> str:
        return f"""#usda 1.0
(
    defaultPrim = "ParametricBox"
    upAxis = "Y"
)

def Xform "ParametricBox"
{{
    def Cube "BoxMesh"
    {{
        double size = 1.0
        double3 xformOp:scale = ({width}, {height}, {depth})
        uniform token[] xformOpOrder = ["xformOp:scale"]
    }}
}}
"""
