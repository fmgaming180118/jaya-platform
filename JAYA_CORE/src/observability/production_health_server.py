"""
production_health_server.py — Production Health & Observability Metrics Server.

STATUS: PROTOTYPE / BASIC HTTP SERVER ONLY

This module is a PROTOTYPE/SCAFFOLD only. It does NOT:
- Perform real health checks against actual components
- Verify cognitive kernel readiness
- Verify capability sandbox status
- Monitor real system health

Current implementation:
- Returns hardcoded "READY"/"ACTIVE" status for all checks
- Only measures current process metrics (RAM, CPU)
- Does NOT probe actual kernel or sandbox

MUST NOT be claimed as "production health monitoring" or "production observability".
"""

from __future__ import annotations

import json
import logging
import os
import psutil
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Dict, Any, Optional

logger = logging.getLogger("ProductionHealthServer")

_START_TIME = time.time()
_ERROR_COUNT = 0
_REQUEST_COUNT = 0


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Production Observability - PROTOTYPE."""

    def _send_json(self, code: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        global _REQUEST_COUNT, _ERROR_COUNT
        _REQUEST_COUNT += 1

        path = self.path.split("?")[0]
        process = psutil.Process(os.getpid())
        mem_rss_mb = process.memory_info().rss / (1024 * 1024)

        if path in ("/health", "/readiness"):
            payload = {
                "status": "PROTOTYPE",
                "stage": "PROTOTYPE_LABEL_ONLY",
                "timestamp": time.time(),
                "uptime_seconds": round(time.time() - _START_TIME, 2),
                "checks": {
                    "cognitive_kernel": "PROTOTYPE_READY (hardcoded)",
                    "capability_sandbox": "PROTOTYPE_ACTIVE (hardcoded)",
                    "memory_footprint_mb": round(mem_rss_mb, 2),
                    "warning": "HARDCODED STATUS - NO REAL HEALTH CHECKS PERFORMED",
                },
            }
            self._send_json(200, payload)

        elif path == "/metrics":
            payload = {
                "stage": "PROTOTYPE_LABEL_ONLY",
                "process_id": os.getpid(),
                "uptime_seconds": round(time.time() - _START_TIME, 2),
                "requests_total": _REQUEST_COUNT,
                "errors_total": _ERROR_COUNT,
                "ram_rss_mb": round(mem_rss_mb, 2),
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "warning": "BASIC PROCESS METRICS ONLY - NO COMPONENT HEALTH",
            }
            self._send_json(200, payload)

        else:
            _ERROR_COUNT += 1
            self._send_json(404, {"error": "Endpoint not found", "path": path})

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy HTTP logging in test runs
        pass


class ProductionHealthServer:
    """Manages the background HTTP health monitoring server - PROTOTYPE."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8088):
        self.host = host
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[Thread] = None

    def start(self) -> None:
        self._server = HTTPServer((self.host, self.port), HealthCheckHandler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.warning("ProductionHealthServer started at http://%s:%d - PROTOTYPE: hardcoded responses only", self.host, self.port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            logger.info("Production Health Server stopped.")

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
