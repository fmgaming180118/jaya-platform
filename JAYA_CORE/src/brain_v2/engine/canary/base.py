"""Fail-closed canary runner contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CanaryError(RuntimeError):
    """Typed, client-safe canary rejection."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CanaryResult:
    """Result returned by an explicit functional canary check."""

    passed: bool
    details: Mapping[str, Any]
    metrics: Mapping[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "passed": self.passed,
            "details": dict(self.details),
        }
        if self.metrics is not None:
            result["metrics"] = dict(self.metrics)
        return result


class CanaryRunner(ABC):
    """One functional probe registered under an explicit signed check ID."""

    @property
    @abstractmethod
    def check_id(self) -> str:
        """Return the exact manifest check ID implemented by this runner."""

    @abstractmethod
    def run(self, artifact_path: Path, manifest: Any) -> CanaryResult:
        """Run a non-mutating functional check against the installed artifact."""

    def validate_environment(self) -> tuple[bool, str]:
        return True, ""


def create_canary_result(
    passed: bool,
    details: Mapping[str, Any] | None = None,
    metrics: Mapping[str, float] | None = None,
) -> CanaryResult:
    return CanaryResult(
        passed=passed,
        details=details or {},
        metrics=metrics,
    )
