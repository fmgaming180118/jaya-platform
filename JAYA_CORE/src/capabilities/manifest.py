"""
manifest.py — CapabilityManifest model definition.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class CapabilityManifest:
    capability_id: str
    version: str
    provider: str  # e.g. "built_in", "mcp_cad", "local_rule"
    execution_location: str  # "local" or "remote"
    min_memory_mb: int = 64
    permissions_required: List[str] = field(default_factory=list)
    offline_available: bool = True
    health_status: str = "HEALTHY"  # "HEALTHY", "UNHEALTHY", "DEGRADED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
