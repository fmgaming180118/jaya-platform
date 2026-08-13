"""Fail-closed canary framework for evolution installs."""

from __future__ import annotations

from .base import CanaryError, CanaryResult, CanaryRunner, create_canary_result
from .registry import (
    CanaryRegistry,
    CompositeCanaryRunner,
    get_canary_registry,
    get_canary_runner,
    register_canary_runner,
)
from .runners import GenericCanary, InferenceProbe, QLoRAAdapterCanary

# The built-in runner remains unavailable until application composition injects
# a real inference probe. This is intentionally fail-closed.
register_canary_runner(QLoRAAdapterCanary())


def create_canary_registry(
    *,
    qlora_inference_probe: InferenceProbe | None = None,
) -> CanaryRegistry:
    registry = CanaryRegistry()
    registry.register(QLoRAAdapterCanary(qlora_inference_probe))
    return registry


__all__ = [
    "CanaryRunner",
    "CanaryResult",
    "CanaryError",
    "create_canary_result",
    "CanaryRegistry",
    "get_canary_runner",
    "get_canary_registry",
    "register_canary_runner",
    "CompositeCanaryRunner",
    "QLoRAAdapterCanary",
    "GenericCanary",
    "InferenceProbe",
    "create_canary_registry",
]
