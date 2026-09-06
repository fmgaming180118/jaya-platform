"""Truthful mapping from architecture pillars to real runtime capabilities."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import PillarStatus
from .registry import DynamicPillarRegistry

_IMPLEMENTED_STATUSES = frozenset(
    {
        PillarStatus.IMPLEMENTED_LOCAL,
        PillarStatus.INTEGRATED,
        PillarStatus.VERIFIED,
        PillarStatus.PRODUCTION,
    }
)


class PillarRuntimeView:
    """Read-only runtime projection; registration never activates code."""

    def __init__(self, registry: DynamicPillarRegistry, capability_registry: object) -> None:
        self.registry = registry
        self.capability_registry = capability_registry

    def _capability_health(self, capability_id: str | None) -> tuple[bool, str]:
        if not capability_id:
            return False, "CAPABILITY_NOT_BOUND"
        lookup = getattr(self.capability_registry, "lookup", None)
        if not callable(lookup):
            return False, "CAPABILITY_REGISTRY_UNAVAILABLE"
        capability = lookup(capability_id)
        if capability is None:
            return False, "CAPABILITY_NOT_REGISTERED"
        health_status = str(getattr(capability, "health_status", "REGISTERED_UNVERIFIED"))
        return health_status == "HEALTHY", health_status

    def snapshot(self) -> dict[str, Any]:
        records = self.registry.list()
        by_id = {record.definition.pillar_id: record for record in records}
        items: list[dict[str, Any]] = []
        reasons: Counter[str] = Counter()
        available_count = 0
        for record in records:
            dependencies_ready = all(
                dependency in by_id and by_id[dependency].status in _IMPLEMENTED_STATUSES
                for dependency in record.definition.dependencies
            )
            capability_ready, capability_code = self._capability_health(
                record.definition.capability_id
            )
            if record.status not in _IMPLEMENTED_STATUSES:
                available = False
                reason = f"STATUS_{record.status.value}"
            elif not dependencies_ready:
                available = False
                reason = "DEPENDENCY_UNAVAILABLE"
            elif not capability_ready:
                available = False
                reason = capability_code
            else:
                available = True
                reason = "AVAILABLE"
                available_count += 1
            reasons[reason] += 1
            items.append(
                {
                    "pillar_id": record.definition.pillar_id,
                    "name": record.definition.name,
                    "status": record.status.value,
                    "capability_id": record.definition.capability_id,
                    "runtime_available": available,
                    "runtime_code": reason,
                }
            )
        return {
            "ready": self.registry.health_check(),
            "total": len(records),
            "runtime_available": available_count,
            "runtime_unavailable": len(records) - available_count,
            "reason_counts": dict(sorted(reasons.items())),
            "pillars": items,
        }
