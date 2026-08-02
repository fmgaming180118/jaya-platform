"""
requirement_engine.py — Translates fictional or abstract concepts into measurable engineering requirements.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from .contracts import DiscoveryRequirement, FeasibilityStatus


class FictionToRequirementTranslator:
    """Translates abstract / fictional concepts into measurable engineering requirements & subproblems."""

    def translate(self, concept_name: str, description: str) -> DiscoveryRequirement:
        c_lower = concept_name.lower().strip()
        d_lower = description.lower().strip()

        suffix = hashlib.sha256(f"{concept_name}:{description}".encode("utf-8")).hexdigest()[:8]
        req_id = f"req-disc-{suffix}"

        if "arc reactor" in c_lower or "arc reactor" in d_lower or ("reaktor" in d_lower and "portabel" in d_lower):
            return DiscoveryRequirement(
                requirement_id=req_id,
                concept_name=concept_name,
                translated_goal="Sumber energi portabel berdaya tinggi (10-100 MW) ber-kepadatan daya tinggi",
                target_specifications={
                    "max_diameter_cm": 12.0,
                    "max_depth_cm": 15.0,
                    "max_mass_kg": 3.0,
                    "continuous_power_mw": 10.0,
                    "peak_power_mw": 100.0,
                    "max_surface_temp_c": 45.0,
                    "radiation_shielding": "zero_external_leakage",
                },
                feasibility_status=FeasibilityStatus.UNFEASIBLE_WITH_KNOWN_PHYSICS,
                primary_blockers=[
                    "Batas scaling law confinement magnetik plasma (membutuhkan volume plasma besar seperti Tokamak/ITER)",
                    "Batas pendinginan mikrokanal untuk disipasi panas buangan 100 MW pada skala 12cm",
                    "Kerusakan neutron terhadap magnet superkonduktor kompak",
                    "Efisiensi konversi energi langsung (MHD/radiasi)",
                ],
                researchable_subproblems=[
                    "Geometri magnet superkonduktor HTS (High-Temperature Superconductor) medan tinggi portabel",
                    "Material komposit matriks keramik tahan radiasi neutron",
                    "Konversi energi magnetohidrodinamik (MHD) mikro-gap",
                    "Permodelan stabilitas plasma dengan Physics-Informed Neural Networks (PINN)",
                ],
            )

        if "propulsi" in c_lower or "drive" in c_lower or "engine" in d_lower:
            return DiscoveryRequirement(
                requirement_id=req_id,
                concept_name=concept_name,
                translated_goal="Sistem propulsi efisiensi tinggi dengan impuls spesifik (Isp) tinggi",
                target_specifications={
                    "target_thrust_n": 1000.0,
                    "target_isp_seconds": 3000.0,
                    "power_consumption_kw": 50.0,
                },
                feasibility_status=FeasibilityStatus.REQUIRES_FURTHER_SIMULATION,
                primary_blockers=[
                    "Erosi katoda pada pendorong ion/plasma",
                    "Disipasi panas elektroda tinggi",
                ],
                researchable_subproblems=[
                    "Desain nosel magnetik berbasis HTS",
                    "Optimasi fluida kerja berbasis gas mulia",
                ],
            )

        # Default generic translation
        return DiscoveryRequirement(
            requirement_id=req_id,
            concept_name=concept_name,
            translated_goal=f"Formulasi spesifikasi teknis terukur untuk {concept_name}",
            target_specifications={
                "input_description": description,
                "domain": "general_engineering",
            },
            feasibility_status=FeasibilityStatus.REQUIRES_FURTHER_SIMULATION,
            primary_blockers=["Perlu permodelan persamaan fisika awal"],
            researchable_subproblems=["Formulasi hipotesis kerja fisika"],
        )
