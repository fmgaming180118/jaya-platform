"""Shared result and failure contracts for production-local pillar services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


class LocalPillarError(RuntimeError):
    """Stable, non-secret-bearing failure raised by local pillar services."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        """Return a sanitized error payload for runtime boundaries."""

        return {"status": "FAILED", "code": self.code, "message": str(self)}


@dataclass(frozen=True, slots=True)
class LocalPillarResult:
    """Result envelope for a capability invoked through the canonical runtime."""

    pillar_id: str
    code: str
    data: Mapping[str, Any]
    status: str = "INTEGRATED"

    def to_dict(self) -> dict[str, Any]:
        """Serialize this immutable result without exposing implementation state."""

        return asdict(self)
