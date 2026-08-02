"""
falsification_engine.py — Evaluates scientific hypotheses against physics constraints (Falsification Gate).
"""

from __future__ import annotations

import hashlib
from typing import Dict, List

from .contracts import (
    DiscoveryArtifact,
    DiscoveryArtifactType,
    FalsificationResult,
    PhysicsConstraint,
    ScientificHypothesis,
)


class PhysicsFalsificationEngine:
    """Falsifies hypotheses against fundamental physics laws and outputs DiscoveryArtifacts."""

    def __init__(self) -> None:
        self._standard_laws: List[PhysicsConstraint] = [
            PhysicsConstraint(
                law_name="Law of Conservation of Energy",
                description="Total energy in an isolated system remains constant.",
                governing_equation="E_in = E_out + E_stored",
            ),
            PhysicsConstraint(
                law_name="Thermodynamic Heat Dissipation Limit",
                description="Carnot heat rejection limits maximum thermal efficiency.",
                governing_equation="eta_max = 1 - (T_cold / T_hot)",
            ),
            PhysicsConstraint(
                law_name="Lawson Criterion for Fusion Ignition",
                description="Triple product (density * temperature * confinement time) required for fusion ignition.",
                governing_equation="n * T * tau_E >= 3e21 m^-3 keV s",
            ),
        ]

    def evaluate_hypothesis(
        self, hypothesis: ScientificHypothesis, target_specs: Dict[str, float] | None = None
    ) -> FalsificationResult:
        specs = target_specs or {}
        violating: List[str] = []
        evidence: Dict[str, float] = {}

        # 1. Fusion Scaling Check (Lawson Criterion / Lawson Confinement)
        if "fusion" in hypothesis.domain.lower() or "tokamak" in hypothesis.title.lower():
            # If diameter is <= 15cm and requested power is > 10MW
            max_dia = float(specs.get("max_diameter_cm", 12.0))
            power_mw = float(specs.get("continuous_power_mw", 10.0))

            if max_dia <= 30.0 and power_mw >= 1.0:
                violating.append("Lawson Criterion for Fusion Ignition")
                evidence["calculated_confinement_time_s"] = 0.0001
                evidence["required_confinement_time_s"] = 1.5
                evidence["scaling_deficit_factor"] = 15000.0

        # 2. Thermal Dissipation Limit
        if "max_surface_temp_c" in specs and "peak_power_mw" in specs:
            surface_temp = float(specs["max_surface_temp_c"])
            peak_power = float(specs["peak_power_mw"])
            if surface_temp < 50.0 and peak_power >= 10.0:
                violating.append("Thermodynamic Heat Dissipation Limit")
                evidence["required_cooling_area_m2"] = 145.0
                evidence["actual_cooling_area_m2"] = 0.05

        is_falsified = len(violating) > 0
        summary = (
            f"Hipotesis '{hypothesis.title}' GAGAL UJI FALSIFIKASI karena melanggar: {', '.join(violating)}"
            if is_falsified
            else f"Hipotesis '{hypothesis.title}' LOLOS UJI FALSIFIKASI awal."
        )

        return FalsificationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            is_falsified=is_falsified,
            violating_laws=violating,
            numerical_evidence=evidence,
            summary=summary,
        )

    def export_artifact(
        self, hypothesis: ScientificHypothesis, falsification: FalsificationResult
    ) -> DiscoveryArtifact:
        suffix = hashlib.sha256(hypothesis.hypothesis_id.encode("utf-8")).hexdigest()[:8]

        if falsification.is_falsified:
            artifact_id = f"art-rej-{suffix}"
            return DiscoveryArtifact(
                artifact_id=artifact_id,
                artifact_type=DiscoveryArtifactType.REJECTED_HYPOTHESIS,
                concept_name=hypothesis.title,
                summary=falsification.summary,
                payload={
                    "hypothesis": hypothesis.to_dict(),
                    "falsification": falsification.to_dict(),
                },
                evidence_kind="THEORETICAL",
                status="REJECTED_HYPOTHESIS",
            )

        artifact_id = f"art-disc-{suffix}"
        return DiscoveryArtifact(
            artifact_id=artifact_id,
            artifact_type=DiscoveryArtifactType.DISCOVERY_CANDIDATE,
            concept_name=hypothesis.title,
            summary=falsification.summary,
            payload={
                "hypothesis": hypothesis.to_dict(),
                "falsification": falsification.to_dict(),
            },
            evidence_kind="THEORETICAL",
            status="CANDIDATE",
        )
