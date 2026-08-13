"""
digital_twin.py — Digital Twin Assembly Engine (OpenUSD + Solver Data Overlay).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from .contracts import DiscoveryArtifact, DiscoveryArtifactType


@dataclass
class DigitalTwinBundle:
    twin_id: str
    concept_name: str
    usda_script: str
    solver_results: Dict[str, Any]
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DigitalTwinBuilder:
    """Builds unified DigitalTwin bundles combining OpenUSD geometry and solver overlay data."""

    def assemble(
        self, concept_name: str, usda_script: str, solver_metrics: Dict[str, Any]
    ) -> DiscoveryArtifact:
        suffix = hashlib.sha256(f"{concept_name}:{usda_script}".encode("utf-8")).hexdigest()[:8]
        twin_id = f"dt-{suffix}"

        bundle = DigitalTwinBundle(
            twin_id=twin_id,
            concept_name=concept_name,
            usda_script=usda_script,
            solver_results=solver_metrics,
        )

        return DiscoveryArtifact(
            artifact_id=f"art-dt-{suffix}",
            artifact_type=DiscoveryArtifactType.DIGITAL_TWIN,
            concept_name=concept_name,
            summary=f"Digital Twin terpadu untuk {concept_name} (OpenUSD + Solver Overlay)",
            payload=bundle.to_dict(),
            evidence_kind="SIMULATION",
            status="CANDIDATE",
        )
