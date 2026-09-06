"""
rule_based.py — Rule-based deterministic cognitive model for offline & test modes.
"""

from __future__ import annotations

from .protocol import CognitiveModel, ModelCost, ModelRequest, ModelResponse


class RuleBasedCognitiveModel:
    """Offline, zero-dependency, deterministic rule-based cognitive model."""

    model_id = "rule-based-v1"

    def __init__(self, ready: bool = True) -> None:
        self._ready = ready

    def is_ready(self) -> bool:
        return self._ready

    def estimate_cost(self, request: ModelRequest) -> ModelCost:
        return ModelCost(
            estimated_memory_mb=16,
            estimated_latency_ms=1.0,
            requires_network=False,
        )

    def generate(self, request: ModelRequest) -> ModelResponse:
        prompt_lower = request.prompt.lower()
        if "casing" in prompt_lower or "3d" in prompt_lower or "cad" in prompt_lower:
            ans = "Perencana merencanakan desain 3D parametrik untuk objek yang diminta."
        elif "rapikan" in prompt_lower or "file" in prompt_lower:
            ans = "Perencana menyusun langkah pembersihan dan pengorganisasian file."
        elif "ingat" in prompt_lower or "remind" in prompt_lower:
            ans = "JAYA mengatur pengingat sesuai instruksi pengguna."
        else:
            ans = f"Diproses secara deterministik untuk permintaan: {request.prompt[:50]}"

        return ModelResponse(
            text=ans,
            model_id=self.model_id,
            finish_reason="stop",
            raw_output={"rule": "deterministic_fallback"},
        )
