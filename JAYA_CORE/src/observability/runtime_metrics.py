"""Thread-safe operational metrics for the canonical JAYA Core service."""

from __future__ import annotations

import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    collected_at: str
    uptime_seconds: float
    requests_total: int
    errors_total: int
    latency_ms_total: float
    latency_ms_max: float
    paths: dict[str, int]
    statuses: dict[str, int]
    logic_results: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        average = (
            self.latency_ms_total / self.requests_total if self.requests_total else 0.0
        )
        return {
            "collected_at": self.collected_at,
            "uptime_seconds": self.uptime_seconds,
            "requests_total": self.requests_total,
            "errors_total": self.errors_total,
            "error_rate": (
                self.errors_total / self.requests_total if self.requests_total else 0.0
            ),
            "latency_ms_average": round(average, 6),
            "latency_ms_max": round(self.latency_ms_max, 6),
            "paths": dict(self.paths),
            "statuses": dict(self.statuses),
            "logic_results": dict(self.logic_results),
        }


class RuntimeMetrics:
    """Collect sanitized counters without storing request bodies or secrets."""

    def __init__(self) -> None:
        self._started = time.monotonic()
        self._requests_total = 0
        self._errors_total = 0
        self._latency_ms_total = 0.0
        self._latency_ms_max = 0.0
        self._paths: Counter[str] = Counter()
        self._statuses: Counter[str] = Counter()
        self._logic_results: Counter[str] = Counter()
        self._lock = threading.RLock()

    def observe_http(self, path: str, status_code: int, elapsed_ms: float) -> None:
        safe_path = (
            path
            if path
            in {
                "/healthz",
                "/readyz",
                "/v1/chat",
                "/v1/logic/evaluate",
                "/v1/metrics",
            }
            else "other"
        )
        with self._lock:
            self._requests_total += 1
            if status_code >= 400:
                self._errors_total += 1
            self._latency_ms_total += max(0.0, elapsed_ms)
            self._latency_ms_max = max(self._latency_ms_max, elapsed_ms)
            self._paths[safe_path] += 1
            self._statuses[str(status_code)] += 1

    def observe_logic(self, status: str) -> None:
        with self._lock:
            self._logic_results[status] += 1

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                collected_at=datetime.now(timezone.utc).isoformat(),
                uptime_seconds=round(time.monotonic() - self._started, 6),
                requests_total=self._requests_total,
                errors_total=self._errors_total,
                latency_ms_total=self._latency_ms_total,
                latency_ms_max=self._latency_ms_max,
                paths=dict(self._paths),
                statuses=dict(self._statuses),
                logic_results=dict(self._logic_results),
            )


__all__ = ["MetricsSnapshot", "RuntimeMetrics"]
