"""
profiler.py — Lightweight resource profiler for JAYA Core.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict

from src.identity.models import NodeClass


@dataclass
class ResourceProfile:
    node_class: NodeClass
    total_memory_mb: int
    available_memory_mb: int
    process_memory_mb: int
    cpu_count: int
    storage_free_mb: int
    network_available: bool = True
    power_mode: str = "NORMAL"  # "NORMAL", "SAVER", "CRITICAL"

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["node_class"] = self.node_class.value
        return res


class ResourceProfiler:
    """Lightweight system resource profiler with configurable node classification threshold."""

    def __init__(
        self,
        central_memory_threshold_mb: int = 16000,
        standard_memory_threshold_mb: int = 4000,
        edge_memory_threshold_mb: int = 1000,
    ) -> None:
        self.central_threshold = central_memory_threshold_mb
        self.standard_threshold = standard_memory_threshold_mb
        self.edge_threshold = edge_memory_threshold_mb

    def profile(
        self,
        override_total_mem_mb: int | None = None,
        override_available_mem_mb: int | None = None,
        network_available: bool = True,
        power_mode: str = "NORMAL",
    ) -> ResourceProfile:
        cpu_count = os.cpu_count() or 1

        # Determine RAM
        total_mem_mb = override_total_mem_mb
        available_mem_mb = override_available_mem_mb
        process_mem_mb = 50  # baseline estimate

        try:
            import psutil
            mem = psutil.virtual_memory()
            if total_mem_mb is None:
                total_mem_mb = mem.total // (1024 * 1024)
            if available_mem_mb is None:
                available_mem_mb = mem.available // (1024 * 1024)
            proc = psutil.Process()
            process_mem_mb = proc.memory_info().rss // (1024 * 1024)
        except Exception:
            # Fallback if psutil is unavailable or fails
            if total_mem_mb is None:
                total_mem_mb = 8000
            if available_mem_mb is None:
                available_mem_mb = 4000

        # Estimate free storage
        storage_free_mb = 10000
        try:
            if hasattr(os, "statvfs"):
                st = os.statvfs(".")
                storage_free_mb = (st.f_bavail * st.f_frsize) // (1024 * 1024)
        except Exception:
            pass

        # Classify node class
        node_class = self._classify(total_mem_mb or 8000, available_mem_mb or 4000)

        return ResourceProfile(
            node_class=node_class,
            total_memory_mb=total_mem_mb,
            available_memory_mb=available_mem_mb,
            process_memory_mb=process_mem_mb,
            cpu_count=cpu_count,
            storage_free_mb=storage_free_mb,
            network_available=network_available,
            power_mode=power_mode,
        )

    def _classify(self, total_mem_mb: int, available_mem_mb: int) -> NodeClass:
        if total_mem_mb >= self.central_threshold:
            return NodeClass.CENTRAL
        if total_mem_mb >= self.standard_threshold:
            return NodeClass.STANDARD
        if total_mem_mb >= self.edge_threshold:
            return NodeClass.EDGE
        return NodeClass.CONSTRAINED
