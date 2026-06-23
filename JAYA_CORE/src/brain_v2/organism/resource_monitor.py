"""Pillar 2 — Resource Aware (upgrade).

Monitors CPU%, RAM, and battery level at configurable intervals.
Callbacks notify the IronEngine to auto-adjust ``AgiConfig.topk_ratio``
and trigger ``enter_silence()`` under high-load conditions.

Falls back gracefully if ``psutil`` is not installed.
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.brain_v2.engine.runtime import IronEngine

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
                 callbacks: Optional[List[Any]] = None):
        self.check_interval      = check_interval
        self.high_cpu_threshold  = high_cpu_threshold
        self.low_cpu_threshold   = low_cpu_threshold
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
        engine = self._engine

        if engine is not None:
            if cpu >= self.high_cpu_threshold and not self._silence_active:
                logger.warning("[ResourceMonitor] CPU=%.1f%% — entering silence",
                               cpu)
                if hasattr(engine, "enter_silence"):
                    engine.enter_silence()
                self._silence_active = True

            elif cpu <= self.low_cpu_threshold and self._silence_active:
                logger.info("[ResourceMonitor] CPU=%.1f%% — exiting silence",
                            cpu)
                if hasattr(engine, "exit_silence"):
                    engine.exit_silence()
                self._silence_active = False

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
        }
