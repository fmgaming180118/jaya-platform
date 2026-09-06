"""Host energy measurement adapters with explicit availability failures."""

from __future__ import annotations

import json
import math
import platform
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_RAPL_PACKAGE_CHANNEL = re.compile(r"^RAPL_Package\d+_PKG$")
_PICOWATT_HOUR_TO_JOULE = 3.6e-9
_POWERSHELL_QUERY = (
    "Get-CimInstance -ClassName "
    "Win32_PerfFormattedData_PowerMeterCounter_EnergyMeter | "
    "Select-Object Name,Energy | ConvertTo-Json -Compress"
)


class EnergyMeterError(RuntimeError):
    """Stable energy meter failure without leaking subprocess output."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class EnergySample:
    captured_at: str
    monotonic_ns: int
    energy_picowatt_hours: int
    channels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnergyMeasurement:
    elapsed_seconds: float
    energy_picowatt_hours: int
    joules: float
    average_package_watts: float
    channels: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "MEASURED_HOST_PACKAGE",
            "provider": "WINDOWS_EMI_RAPL",
            "unit_source": "EMI_V1_PICOWATT_HOURS",
            "scope": "CPU_PACKAGE_HOST_TOTAL_NOT_PROCESS_ATTRIBUTED",
            "elapsed_seconds": self.elapsed_seconds,
            "energy_picowatt_hours": self.energy_picowatt_hours,
            "joules": self.joules,
            "average_package_watts": self.average_package_watts,
            "channels": list(self.channels),
        }


class WindowsEmiEnergyMeter:
    """Read package energy through Windows Energy Meter Interface counters."""

    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        if not 0.1 <= timeout_seconds <= 30.0:
            raise EnergyMeterError("INVALID_CONFIG", "energy meter timeout is out of range")
        self._timeout_seconds = timeout_seconds
        self._powershell = shutil.which("powershell") if platform.system() == "Windows" else None

    def sample(self) -> EnergySample:
        if self._powershell is None:
            raise EnergyMeterError(
                "ENERGY_COUNTER_UNAVAILABLE", "Windows EMI energy counters are unavailable"
            )
        try:
            completed = subprocess.run(
                [self._powershell, "-NoProfile", "-NonInteractive", "-Command", _POWERSHELL_QUERY],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise EnergyMeterError("ENERGY_COUNTER_TIMEOUT", "energy counter query timed out") from exc
        except (OSError, UnicodeError) as exc:
            raise EnergyMeterError(
                "ENERGY_COUNTER_UNAVAILABLE", "energy counter query could not run"
            ) from exc
        if completed.returncode != 0 or not completed.stdout.strip():
            raise EnergyMeterError(
                "ENERGY_COUNTER_UNAVAILABLE", "energy counter query returned no data"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise EnergyMeterError(
                "ENERGY_COUNTER_INVALID", "energy counter returned invalid data"
            ) from exc
        rows = payload if isinstance(payload, list) else [payload]
        package_rows: list[tuple[str, int]] = []
        for row in rows:
            if not isinstance(row, dict) or not _RAPL_PACKAGE_CHANNEL.fullmatch(
                str(row.get("Name", ""))
            ):
                continue
            energy = row.get("Energy")
            if isinstance(energy, bool) or not isinstance(energy, int) or energy < 0:
                raise EnergyMeterError(
                    "ENERGY_COUNTER_INVALID", "energy counter value is invalid"
                )
            package_rows.append((str(row["Name"]), energy))
        if not package_rows:
            raise EnergyMeterError(
                "ENERGY_COUNTER_UNAVAILABLE", "no CPU package energy channel is available"
            )
        package_rows.sort()
        return EnergySample(
            captured_at=datetime.now(UTC).isoformat(),
            monotonic_ns=time.perf_counter_ns(),
            energy_picowatt_hours=sum(energy for _, energy in package_rows),
            channels=tuple(name for name, _ in package_rows),
        )

    @staticmethod
    def measure(start: EnergySample, end: EnergySample) -> EnergyMeasurement:
        if start.channels != end.channels:
            raise EnergyMeterError(
                "ENERGY_COUNTER_CHANGED", "energy counter channels changed during measurement"
            )
        elapsed_seconds = (end.monotonic_ns - start.monotonic_ns) / 1_000_000_000.0
        energy_delta = end.energy_picowatt_hours - start.energy_picowatt_hours
        if elapsed_seconds <= 0 or energy_delta <= 0:
            raise EnergyMeterError(
                "ENERGY_COUNTER_INVALID", "energy counter did not advance during measurement"
            )
        joules = energy_delta * _PICOWATT_HOUR_TO_JOULE
        watts = joules / elapsed_seconds
        if not all(math.isfinite(value) and value > 0 for value in (joules, watts)):
            raise EnergyMeterError(
                "ENERGY_COUNTER_INVALID", "energy measurement is outside numeric bounds"
            )
        return EnergyMeasurement(
            elapsed_seconds=elapsed_seconds,
            energy_picowatt_hours=energy_delta,
            joules=joules,
            average_package_watts=watts,
            channels=start.channels,
        )


__all__ = [
    "EnergyMeasurement",
    "EnergyMeterError",
    "EnergySample",
    "WindowsEmiEnergyMeter",
]
