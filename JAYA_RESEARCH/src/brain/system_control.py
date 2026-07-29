"""Read-only system telemetry plus an injected capability boundary."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import psutil
from src.capability_boundary import (
    ArbitraryExecutionRejected,
    CapabilityGateway,
    InvalidCapabilityRequest,
    request_capability,
    require_profile,
)


class SystemController:
    """Expose telemetry locally and route effects through an authorized gateway."""

    def __init__(self, capability_gateway: CapabilityGateway | None = None) -> None:
        self._capability_gateway = capability_gateway

    def run_command(self, command: str) -> str:
        """Reject legacy raw shell input regardless of caller or platform."""
        del command
        raise ArbitraryExecutionRejected(
            "raw shell commands are not a supported Research capability"
        )

    def run_profile(
        self,
        profile: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Request a pre-registered execution profile through the public gateway."""
        safe_profile = require_profile(profile)
        return request_capability(
            self._capability_gateway,
            action="process.profile.run",
            arguments={
                "profile": safe_profile,
                "arguments": dict(arguments or {}),
            },
        )

    def open_app(self, app_name: str) -> Mapping[str, Any]:
        """Request an application launch without constructing a shell command."""
        application = str(app_name or "").strip()
        if not application or len(application) > 128:
            raise InvalidCapabilityRequest("invalid application identifier")
        return request_capability(
            self._capability_gateway,
            action="application.open",
            arguments={"application": application},
        )

    def close_app(self, app_name: str) -> Mapping[str, Any]:
        """Request an application close through the injected gateway."""
        application = str(app_name or "").strip()
        if not application or len(application) > 128:
            raise InvalidCapabilityRequest("invalid application identifier")
        return request_capability(
            self._capability_gateway,
            action="application.close",
            arguments={"application": application},
        )

    def open_folder(self, path: str | Path) -> Mapping[str, Any]:
        """Request a folder launch while leaving authorization to the gateway."""
        value = str(path or "").strip()
        if not value or len(value) > 4096:
            raise InvalidCapabilityRequest("invalid folder path")
        return request_capability(
            self._capability_gateway,
            action="folder.open",
            arguments={"path": value},
        )

    @staticmethod
    def get_system_status() -> str:
        """Return read-only CPU, memory, and network telemetry."""
        cpu_usage = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        network = psutil.net_io_counters()
        return (
            f"CPU Usage: {cpu_usage}%\n"
            f"Memory: {memory.percent}% used "
            f"({round(memory.used / 1e9, 2)} GB / "
            f"{round(memory.total / 1e9, 2)} GB)\n"
            f"Network Sent: {round(network.bytes_sent / 1e6, 2)} MB\n"
            f"Network Recv: {round(network.bytes_recv / 1e6, 2)} MB"
        )

    @staticmethod
    def get_running_apps(limit: int = 5) -> str:
        """Return a bounded read-only process summary."""
        bounded_limit = max(1, min(int(limit), 50))
        processes: list[dict[str, Any]] = []
        for process in psutil.process_iter(["pid", "name", "memory_percent"]):
            try:
                processes.append(process.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        processes.sort(
            key=lambda item: item.get("memory_percent") or 0,
            reverse=True,
        )
        lines = ["Top Apps by Memory:"]
        lines.extend(
            f"- {item.get('name') or 'unknown'} "
            f"({round(item.get('memory_percent') or 0, 1)}%)"
            for item in processes[:bounded_limit]
        )
        return "\n".join(lines)


if __name__ == "__main__":
    controller = SystemController()
    print(controller.get_system_status())
    print(controller.get_running_apps())
