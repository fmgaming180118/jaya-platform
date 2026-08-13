"""Explicit check-ID registry for functional canary runners."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import CanaryError, CanaryResult, CanaryRunner

_CHECK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class CanaryRegistry:
    """Map signed manifest check IDs to exact functional implementations."""

    def __init__(self) -> None:
        self._runners: dict[str, CanaryRunner] = {}

    @staticmethod
    def _check_id(value: str) -> str:
        if not isinstance(value, str) or not _CHECK_ID_RE.fullmatch(value):
            raise CanaryError("CHECK_ID_INVALID", "canary check ID is invalid")
        return value

    def register(self, runner: CanaryRunner) -> None:
        check_id = self._check_id(runner.check_id)
        if check_id in self._runners:
            raise CanaryError(
                "DUPLICATE_RUNNER",
                f"canary check {check_id!r} is already registered",
            )
        self._runners[check_id] = runner

    def get(self, check_id: str) -> CanaryRunner:
        normalized = self._check_id(check_id)
        runner = self._runners.get(normalized)
        if runner is None:
            raise CanaryError(
                "UNKNOWN_CHECK_ID",
                f"no canary runner is registered for check {normalized!r}",
            )
        return runner

    def has(self, check_id: str) -> bool:
        try:
            normalized = self._check_id(check_id)
        except CanaryError:
            return False
        return normalized in self._runners

    def list_check_ids(self) -> list[str]:
        return sorted(self._runners)


_global_registry = CanaryRegistry()


def get_canary_registry() -> CanaryRegistry:
    return _global_registry


def get_canary_runner(check_id: str) -> CanaryRunner:
    return _global_registry.get(check_id)


def register_canary_runner(runner: CanaryRunner) -> None:
    _global_registry.register(runner)


def _manifest_check_id(manifest: Any) -> str:
    check_id = getattr(manifest, "canary_check_id", None)
    if isinstance(check_id, str) and check_id:
        return check_id
    if isinstance(manifest, dict):
        install_plan = manifest.get("install_plan")
        if isinstance(install_plan, dict):
            canary = install_plan.get("canary")
            if isinstance(canary, dict):
                candidate = canary.get("check_id")
                if isinstance(candidate, str) and candidate:
                    return candidate
    raise CanaryError(
        "CHECK_ID_MISSING",
        "verified manifest does not provide an explicit canary check ID",
    )


class CompositeCanaryRunner:
    """Installer callback that dispatches only by the signed check ID."""

    def __init__(self, registry: CanaryRegistry | None = None) -> None:
        self._registry = registry or _global_registry

    def run(self, artifact_path: Path, manifest: Any) -> CanaryResult:
        check_id = _manifest_check_id(manifest)
        return self._registry.get(check_id).run(artifact_path, manifest)

    def __call__(self, artifact_path: Path, manifest: Any) -> dict[str, Any]:
        return self.run(artifact_path, manifest).to_dict()
