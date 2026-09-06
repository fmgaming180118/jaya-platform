"""Pillar 2 — Resource Aware (upgrade).

Monitors CPU%, RAM, and battery level at configurable intervals.
Callbacks notify the IronEngine to auto-adjust ``AgiConfig.topk_ratio``
and trigger ``enter_silence()`` under high-load conditions.

Falls back gracefully if ``psutil`` is not installed.
"""

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from jaya_core.brain_v2.engine.runtime import IronEngine

logger = logging.getLogger("ResourceMonitor")

_psutil_ok: bool = False
_psutil_mod: Any = None
try:
    import psutil as _psutil_mod  # type: ignore[import]
    _psutil_ok = True
except ImportError:
    logger.warning("[ResourceMonitor] psutil not available — using stub readings")


def get_readings() -> Dict[str, float]:
    """Return current resource readings."""
    if _psutil_ok and _psutil_mod is not None:
        cpu   = float(_psutil_mod.cpu_percent(interval=None))
        mem   = float(_psutil_mod.virtual_memory().percent)
        bat   = -1.0
        battery = _psutil_mod.sensors_battery()
        if battery is not None:
            bat = float(battery.percent)
        return {"cpu_pct": cpu, "mem_pct": mem, "battery_pct": bat}
    # Stub values when psutil is absent
    return {"cpu_pct": 0.0, "mem_pct": 30.0, "battery_pct": -1.0}


class ResourceMonitor:
    """Background resource watcher (Pillar 2).

    Parameters
    ----------
    check_interval:
        Seconds between readings.
    high_cpu_threshold:
        CPU% above which ``enter_silence()`` is called on the engine.
    low_cpu_threshold:
        CPU% below which normal operation is restored.
    callbacks:
        List of ``(condition_fn, action_fn)`` pairs.  ``condition_fn``
        receives a readings dict; ``action_fn`` receives the readings
        dict and the engine.
    """

    def __init__(self,
                 check_interval: float = 5.0,
                 high_cpu_threshold: float = 85.0,
                 low_cpu_threshold: float = 40.0,
                 high_memory_threshold: float = 90.0,
                 recovery_memory_threshold: float = 70.0,
                 low_battery_threshold: float = 10.0,
                 recovery_battery_threshold: float = 20.0,
                 callbacks: Optional[List[Any]] = None):
        if check_interval <= 0:
            raise ValueError("check_interval must be positive")
        if not 0 <= low_cpu_threshold < high_cpu_threshold <= 100:
            raise ValueError("CPU thresholds are invalid")
        if not 0 <= recovery_memory_threshold < high_memory_threshold <= 100:
            raise ValueError("memory thresholds are invalid")
        if not 0 <= low_battery_threshold < recovery_battery_threshold <= 100:
            raise ValueError("battery thresholds are invalid")
        self.check_interval      = check_interval
        self.high_cpu_threshold  = high_cpu_threshold
        self.low_cpu_threshold   = low_cpu_threshold
        self.high_memory_threshold = high_memory_threshold
        self.recovery_memory_threshold = recovery_memory_threshold
        self.low_battery_threshold = low_battery_threshold
        self.recovery_battery_threshold = recovery_battery_threshold
        self._callbacks: List[Any]    = callbacks or []
        self._engine: Optional["IronEngine"] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_readings: Dict[str, float] = {}
        self._silence_active = False
        self._reading_count  = 0

    # ------------------------------------------------------------------

    def attach(self, engine: "IronEngine") -> None:
        """Attach to *engine* and start the monitoring thread."""
        self._engine = engine
        self.start()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="ResourceMonitor", daemon=True
        )
        self._thread.start()
        logger.info("[ResourceMonitor] started (interval=%.1fs)", self.check_interval)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=self.check_interval * 2)
        logger.info("[ResourceMonitor] stopped")

    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error("[ResourceMonitor] tick error: %s", exc)
            time.sleep(self.check_interval)

    def _tick(self) -> None:
        readings = get_readings()
        self._last_readings = readings
        self._reading_count += 1

        cpu = readings["cpu_pct"]
        memory = readings["mem_pct"]
        battery = readings["battery_pct"]
        engine = self._engine

        if engine is not None:
            pressure_reasons: List[str] = []
            if cpu >= self.high_cpu_threshold:
                pressure_reasons.append("cpu")
            if memory >= self.high_memory_threshold:
                pressure_reasons.append("memory")
            if 0 <= battery <= self.low_battery_threshold:
                pressure_reasons.append("battery")

            battery_recovered = (
                battery < 0 or battery >= self.recovery_battery_threshold
            )
            resources_recovered = (
                cpu <= self.low_cpu_threshold
                and memory <= self.recovery_memory_threshold
                and battery_recovered
            )

            if pressure_reasons and not self._silence_active:
                logger.warning(
                    "[ResourceMonitor] pressure=%s — entering silence",
                    ",".join(pressure_reasons),
                )
                if hasattr(engine, "enter_silence"):
                    result = engine.enter_silence("RESOURCE_PRESSURE")
                    self._silence_active = bool(
                        isinstance(result, dict) and result.get("ok")
                    )

            elif resources_recovered and self._silence_active:
                logger.info("[ResourceMonitor] pressure cleared — exiting silence")
                if hasattr(engine, "exit_silence"):
                    result = engine.exit_silence("RESOURCE_RECOVERED")
                    if isinstance(result, dict) and result.get("ok"):
                        self._silence_active = bool(result.get("active"))

            # Adjust topk_ratio dynamically
            if cpu < 30.0:
                target_topk = 0.10   # full capacity
            elif cpu < 60.0:
                target_topk = 0.07
            elif cpu < 80.0:
                target_topk = 0.04
            else:
                target_topk = 0.02   # minimal firing

            if abs(engine.config.topk_ratio - target_topk) > 0.01:
                engine.config.topk_ratio = target_topk
                logger.debug("[ResourceMonitor] topk_ratio → %.2f (cpu=%.1f%%)",
                             target_topk, cpu)

        # User-registered callbacks
        for condition_fn, action_fn in self._callbacks:
            try:
                if condition_fn(readings):
                    action_fn(readings, engine)
            except Exception as exc:
                logger.warning("[ResourceMonitor] callback error: %s", exc)

    # ------------------------------------------------------------------

    def readings(self) -> Dict[str, float]:
        """Return the most recent resource snapshot."""
        return dict(self._last_readings)

    def status(self) -> Dict[str, Any]:
        return {
            "available": True,
            "running":       self._running,
            "psutil":        _psutil_ok,
            "readings":      self._last_readings,
            "reading_count": self._reading_count,
            "silence_active": self._silence_active,
            "check_interval": self.check_interval,
            "thresholds": {
                "high_cpu_pct": self.high_cpu_threshold,
                "recovery_cpu_pct": self.low_cpu_threshold,
                "high_memory_pct": self.high_memory_threshold,
                "recovery_memory_pct": self.recovery_memory_threshold,
                "low_battery_pct": self.low_battery_threshold,
                "recovery_battery_pct": self.recovery_battery_threshold,
            },
        }
