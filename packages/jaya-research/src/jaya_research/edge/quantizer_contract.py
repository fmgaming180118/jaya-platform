"""
quantizer_contract.py — Contract & Gate for GGUF Q4 Edge Model Quantization Metrics.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ModelQuantizationMetrics:
    model_id: str
    quant_type: str  # "Q4_0", "Q4_K_M", "Q5_K_M"
    size_mb: float
    ram_usage_mb: float
    avg_latency_ms: float
    peak_surface_temp_c: float
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuantizationValidationResult:
    model_id: str
    is_compliant: bool
    violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GGUFQuantizationContract:
    """Enforces size, RAM, latency, and thermal target bounds for quantized Edge models."""

    def __init__(
        self,
        max_size_mb: float = 300.0,
        max_ram_mb: float = 512.0,
        max_latency_ms: float = 500.0,
        max_temp_c: float = 45.0,
    ) -> None:
        self.max_size_mb = max_size_mb
        self.max_ram_mb = max_ram_mb
        self.max_latency_ms = max_latency_ms
        self.max_temp_c = max_temp_c

    def evaluate(self, metrics: ModelQuantizationMetrics) -> QuantizationValidationResult:
        violations = []

        if metrics.size_mb > self.max_size_mb:
            violations.append(
                f"Model size {metrics.size_mb:.1f} MB exceeds max target limit of {self.max_size_mb:.1f} MB"
            )

        if metrics.ram_usage_mb > self.max_ram_mb:
            violations.append(
                f"RAM usage {metrics.ram_usage_mb:.1f} MB exceeds target limit of {self.max_ram_mb:.1f} MB"
            )

        if metrics.avg_latency_ms > self.max_latency_ms:
            violations.append(
                f"Average latency {metrics.avg_latency_ms:.1f} ms exceeds max limit of {self.max_latency_ms:.1f} ms"
            )

        if metrics.peak_surface_temp_c > self.max_temp_c:
            violations.append(
                f"Peak thermal temp {metrics.peak_surface_temp_c:.1f} °C exceeds limit of {self.max_temp_c:.1f} °C"
            )

        is_compliant = len(violations) == 0
        if not is_compliant:
            logger.warning("Quantization metrics for %s violated contract: %s", metrics.model_id, violations)

        return QuantizationValidationResult(
            model_id=metrics.model_id,
            is_compliant=is_compliant,
            violations=violations,
        )
