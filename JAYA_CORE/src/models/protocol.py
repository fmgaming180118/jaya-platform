"""
protocol.py — Protocol for Cognitive Models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, runtime_checkable


@dataclass
class ModelRequest:
    prompt: str
    context: Dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 512
    temperature: float = 0.0


@dataclass
class ModelCost:
    estimated_memory_mb: int = 128
    estimated_latency_ms: float = 50.0
    requires_network: bool = False


@dataclass
class ModelResponse:
    text: str
    model_id: str
    finish_reason: str = "stop"
    raw_output: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CognitiveModel(Protocol):
    """Protocol for models used by JAYA Core."""

    model_id: str

    def is_ready(self) -> bool: ...
    def estimate_cost(self, request: ModelRequest) -> ModelCost: ...
    def generate(self, request: ModelRequest) -> ModelResponse: ...
