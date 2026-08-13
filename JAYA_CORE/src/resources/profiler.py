"""Truthful, cross-platform resource discovery for JAYA Core."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from src.identity.models import NodeClass

_POWER_MODES = frozenset({"NORMAL", "SAVER", "CRITICAL", "UNKNOWN"})


@dataclass
class ResourceProfile:
    node_class: NodeClass
    total_memory_mb: int | None
    available_memory_mb: int | None
    process_memory_mb: int | None
    cpu_count: int
    storage_free_mb: int | None
    network_available: bool | None = None
    power_mode: str = "UNKNOWN"
    cpu_usage_percent: float | None = None
    hostname: str = ""
    operating_system: str = ""
    os_release: str = ""
    architecture: str = ""
    process_id: int = 0
    accelerator_available: bool | None = None
    accelerator_name: str | None = None
    accelerator_total_memory_mb: int | None = None
    accelerator_free_memory_mb: int | None = None
    thermal_celsius: float | None = None
    battery_percent: float | None = None
    power_source: str = "UNKNOWN"
    collected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sources: Dict[str, str] = field(default_factory=dict)
    metric_ages_ms: Dict[str, float] = field(default_factory=dict)
    errors: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.total_memory_mb,
                self.available_memory_mb,
                self.process_memory_mb,
                self.storage_free_mb,
                self.network_available,
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["node_class"] = self.node_class.value
        result["complete"] = self.complete
        return result


class ResourceProfiler:
    """Discover resources without replacing missing metrics with invented data."""

    def __init__(
        self,
        central_memory_threshold_mb: int = 16_000,
        standard_memory_threshold_mb: int = 4_000,
        edge_memory_threshold_mb: int = 1_000,
        storage_path: Path | str = ".",
        slow_probe_interval_seconds: float = 5.0,
    ) -> None:
        thresholds = (
            central_memory_threshold_mb,
            standard_memory_threshold_mb,
            edge_memory_threshold_mb,
        )
        if any(value <= 0 for value in thresholds):
            raise ValueError("memory classification thresholds must be positive")
        if (
            not central_memory_threshold_mb
            > standard_memory_threshold_mb
            > edge_memory_threshold_mb
        ):
            raise ValueError("memory thresholds must be strictly descending")
        if not 0.1 <= slow_probe_interval_seconds <= 300:
            raise ValueError("slow_probe_interval_seconds must be between 0.1 and 300")
        self.central_threshold = central_memory_threshold_mb
        self.standard_threshold = standard_memory_threshold_mb
        self.edge_threshold = edge_memory_threshold_mb
        self.storage_path = Path(storage_path)
        self.slow_probe_interval_seconds = float(slow_probe_interval_seconds)
        self._slow_probe_lock = threading.RLock()
        self._accelerator_cache: dict[str, Any] | None = None
        self._accelerator_cached_at = 0.0

    def profile(
        self,
        override_total_mem_mb: int | None = None,
        override_available_mem_mb: int | None = None,
        network_available: bool | None = None,
        power_mode: str = "UNKNOWN",
        force_slow_probe: bool = False,
    ) -> ResourceProfile:
        self._validate_override("override_total_mem_mb", override_total_mem_mb)
        self._validate_override("override_available_mem_mb", override_available_mem_mb)
        normalized_power_mode = power_mode.strip().upper()
        if normalized_power_mode not in _POWER_MODES:
            raise ValueError(f"unsupported power mode: {power_mode!r}")

        cpu_count = os.cpu_count() or 1
        total_mem_mb = override_total_mem_mb
        available_mem_mb = override_available_mem_mb
        process_mem_mb: int | None = None
        storage_free_mb: int | None = None
        observed_network = network_available
        cpu_usage_percent: float | None = None
        thermal_celsius: float | None = None
        battery_percent: float | None = None
        power_source = "UNKNOWN"
        accelerator_available: bool | None = None
        accelerator_name: str | None = None
        accelerator_total_memory_mb: int | None = None
        accelerator_free_memory_mb: int | None = None
        sources: Dict[str, str] = {"cpu": "os.cpu_count"}
        metric_ages_ms: Dict[str, float] = {}
        errors: list[str] = []

        if override_total_mem_mb is not None:
            sources["total_memory"] = "explicit_override"
        if override_available_mem_mb is not None:
            sources["available_memory"] = "explicit_override"
        if network_available is not None:
            sources["network"] = "explicit_override"

        try:
            import psutil

            memory = psutil.virtual_memory()
            if total_mem_mb is None:
                total_mem_mb = int(memory.total // (1024 * 1024))
                sources["total_memory"] = "psutil.virtual_memory"
            if available_mem_mb is None:
                available_mem_mb = int(memory.available // (1024 * 1024))
                sources["available_memory"] = "psutil.virtual_memory"
            process_mem_mb = int(psutil.Process().memory_info().rss // (1024 * 1024))
            sources["process_memory"] = "psutil.Process"
            cpu_usage_percent = float(psutil.cpu_percent(interval=None))
            sources["cpu_usage"] = "psutil.cpu_percent"
            if observed_network is None:
                interface_stats = psutil.net_if_stats()
                observed_network = any(
                    stat.isup and not name.casefold().startswith("loopback")
                    for name, stat in interface_stats.items()
                )
                sources["network"] = "psutil.net_if_stats"
            battery = psutil.sensors_battery()
            if battery is not None:
                battery_percent = float(battery.percent)
                power_source = "AC" if battery.power_plugged else "BATTERY"
                sources["power"] = "psutil.sensors_battery"
                if normalized_power_mode == "UNKNOWN":
                    if battery.power_plugged:
                        normalized_power_mode = "NORMAL"
                    elif battery_percent <= 10:
                        normalized_power_mode = "CRITICAL"
                    else:
                        normalized_power_mode = "SAVER"
            temperature_reader = getattr(psutil, "sensors_temperatures", None)
            if callable(temperature_reader):
                readings = temperature_reader(fahrenheit=False)
                temperatures = [
                    float(item.current)
                    for group in readings.values()
                    for item in group
                    if item.current is not None
                ]
                if temperatures:
                    thermal_celsius = max(temperatures)
                    sources["thermal"] = "psutil.sensors_temperatures"
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            errors.append(f"psutil_unavailable:{type(exc).__name__}")

        accelerator, accelerator_age_ms = self._accelerator_snapshot(
            force_refresh=force_slow_probe
        )
        accelerator_available = accelerator["available"]
        accelerator_name = accelerator["name"]
        accelerator_total_memory_mb = accelerator["total_memory_mb"]
        accelerator_free_memory_mb = accelerator["free_memory_mb"]
        sources["accelerator"] = accelerator["source"]
        metric_ages_ms["accelerator"] = accelerator_age_ms
        errors.extend(accelerator["errors"])
        if thermal_celsius is None and accelerator["thermal_celsius"] is not None:
            thermal_celsius = accelerator["thermal_celsius"]
            sources["thermal"] = accelerator["source"]
            metric_ages_ms["thermal"] = accelerator_age_ms

        try:
            storage_free_mb = int(
                shutil.disk_usage(self.storage_path.resolve()).free // (1024 * 1024)
            )
            sources["storage"] = "shutil.disk_usage"
        except (OSError, ValueError) as exc:
            errors.append(f"storage_probe_failed:{type(exc).__name__}")

        node_class = self._classify(total_mem_mb, available_mem_mb)
        return ResourceProfile(
            node_class=node_class,
            total_memory_mb=total_mem_mb,
            available_memory_mb=available_mem_mb,
            process_memory_mb=process_mem_mb,
            cpu_count=cpu_count,
            storage_free_mb=storage_free_mb,
            network_available=observed_network,
            power_mode=normalized_power_mode,
            cpu_usage_percent=cpu_usage_percent,
            hostname=socket.gethostname(),
            operating_system=platform.system(),
            os_release=platform.release(),
            architecture=platform.machine(),
            process_id=os.getpid(),
            accelerator_available=accelerator_available,
            accelerator_name=accelerator_name,
            accelerator_total_memory_mb=accelerator_total_memory_mb,
            accelerator_free_memory_mb=accelerator_free_memory_mb,
            thermal_celsius=thermal_celsius,
            battery_percent=battery_percent,
            power_source=power_source,
            sources=sources,
            metric_ages_ms=metric_ages_ms,
            errors=tuple(errors),
        )

    def _accelerator_snapshot(
        self,
        *,
        force_refresh: bool,
    ) -> tuple[dict[str, Any], float]:
        """Return one bounded slow-hardware probe with explicit metric age."""

        with self._slow_probe_lock:
            now = time.monotonic()
            age_seconds = now - self._accelerator_cached_at
            if (
                not force_refresh
                and self._accelerator_cache is not None
                and age_seconds < self.slow_probe_interval_seconds
            ):
                return dict(self._accelerator_cache), round(age_seconds * 1_000, 3)

            snapshot: dict[str, Any] = {
                "available": None,
                "name": None,
                "total_memory_mb": None,
                "free_memory_mb": None,
                "thermal_celsius": None,
                "source": "nvidia-smi:not_found",
                "errors": (),
            }
            nvidia_smi = shutil.which("nvidia-smi")
            if nvidia_smi:
                snapshot["source"] = "nvidia-smi"
                try:
                    completed = subprocess.run(
                        [
                            nvidia_smi,
                            "--query-gpu=name,memory.total,memory.free,"
                            "temperature.gpu",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=2.0,
                        check=False,
                    )
                    if completed.returncode == 0 and completed.stdout.strip():
                        values = [
                            item.strip()
                            for item in completed.stdout.splitlines()[0].split(",")
                        ]
                        if len(values) == 4:
                            snapshot.update(
                                {
                                    "available": True,
                                    "name": values[0],
                                    "total_memory_mb": int(float(values[1])),
                                    "free_memory_mb": int(float(values[2])),
                                    "thermal_celsius": float(values[3]),
                                }
                            )
                        else:
                            snapshot["errors"] = (
                                "accelerator_probe_failed:invalid_output",
                            )
                    else:
                        snapshot["errors"] = ("accelerator_probe_failed:nonzero_exit",)
                except (OSError, subprocess.SubprocessError, ValueError) as exc:
                    snapshot["errors"] = (
                        f"accelerator_probe_failed:{type(exc).__name__}",
                    )
            self._accelerator_cache = snapshot
            self._accelerator_cached_at = time.monotonic()
            return dict(snapshot), 0.0

    def _classify(
        self,
        total_mem_mb: int | None,
        available_mem_mb: int | None,
    ) -> NodeClass:
        if total_mem_mb is None or available_mem_mb is None:
            return NodeClass.CONSTRAINED
        if total_mem_mb >= self.central_threshold:
            return NodeClass.CENTRAL
        if total_mem_mb >= self.standard_threshold:
            return NodeClass.STANDARD
        if total_mem_mb >= self.edge_threshold:
            return NodeClass.EDGE
        return NodeClass.CONSTRAINED

    @staticmethod
    def _validate_override(name: str, value: int | None) -> None:
        if value is not None and value < 0:
            raise ValueError(f"{name} must not be negative")


__all__ = ["ResourceProfile", "ResourceProfiler"]
