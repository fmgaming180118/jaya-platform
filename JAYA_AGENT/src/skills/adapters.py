"""Public adapter contracts for JAYA Agent skills."""

from __future__ import annotations

from typing import Any, Protocol

from security.capability_sandbox import CapabilityDenied


class SkillAdapterUnavailable(CapabilityDenied):
    """Stable fail-closed error for a missing public skill adapter."""

    def __init__(self, adapter_name: str) -> None:
        super().__init__(
            "ADAPTER_UNAVAILABLE",
            f"Required public adapter is unavailable: {adapter_name}",
        )


class WebResearchAdapter(Protocol):
    """Search adapter configured outside the Agent implementation."""

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Return bounded, structured results."""
        ...


class MemoryMaintenanceAdapter(Protocol):
    """Adapter for maintenance of Agent-owned installed memory state."""

    def optimize_sqlite_database(self) -> Any:
        """Run bounded SQLite maintenance and return a result or receipt."""
        ...

    def enforce_memory_cap(self, max_ram_mb: int) -> dict[str, Any]:
        """Return measured memory information."""
        ...
