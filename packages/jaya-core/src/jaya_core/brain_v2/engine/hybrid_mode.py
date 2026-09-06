"""Pillar 37 — Hybrid Consciousness.

JAYA must stay intelligently operational regardless of network
connectivity.  HybridRouter monitors online status and adjusts which
subsystems are available:

    ONLINE  → full feature set: AgenticSearch, Collective Pulse, web RAG
    OFFLINE → local-only: ternary model + local RAG + twin experiments

The router checks connectivity every ``check_interval`` seconds via a
lightweight DNS probe (no raw socket, no heavy library).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import socket
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("HybridMode")

# Hosts to probe for connectivity (DNS lookup only — no data sent)
_PROBE_HOSTS: List[str] = [
    "8.8.8.8",       # Google DNS
    "1.1.1.1",       # Cloudflare DNS
]
_PROBE_TIMEOUT = 2.0  # seconds


def _check_online() -> bool:
    """Return True if at least one probe host resolves in time."""
    for host in _PROBE_HOSTS:
        try:
            socket.setdefaulttimeout(_PROBE_TIMEOUT)
            socket.gethostbyaddr(host)
            return True
        except (socket.herror, socket.gaierror, socket.timeout, OSError):
            continue
    # Direct TCP check as fallback
    for host in _PROBE_HOSTS:
        try:
            with socket.create_connection((host, 53), timeout=_PROBE_TIMEOUT):
                return True
        except OSError:
            continue
    return False


class HybridRouter:
    """Online/offline feature router (Pillar 37).

    Parameters
    ----------
    check_interval:
        Seconds between connectivity probes.
    force_offline:
        Force offline mode regardless of actual connectivity (useful in
        air-gapped deployments or tests).
    storage_path:
        Optional file path for persisting routing metrics and mode transitions.
    """

    def __init__(
        self,
        check_interval: float = 30.0,
        force_offline: bool = False,
        storage_path: Optional[str | Path] = None,
    ):
        self.check_interval = max(0.5, float(check_interval))
        self.force_offline = bool(force_offline)
        self.storage_path = Path(storage_path).expanduser().resolve() if storage_path else None
        self._is_online: bool = False
        self._last_check: float = 0.0
        self._transitions: int = 0
        self._online_since: Optional[float] = None
        self._route_counts: Dict[str, int] = {}

        if self.storage_path:
            self._load_state()

        # Perform one immediate probe unless forced offline
        if not self.force_offline:
            self._probe()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_online(self) -> bool:
        """Return current connectivity status; probe if interval elapsed."""
        now = time.time()
        if not self.force_offline and (now - self._last_check >= self.check_interval):
            self._probe()
        return self._is_online

    def set_force_offline(self, force: bool) -> None:
        """Dynamically set force_offline state."""
        self.force_offline = bool(force)
        self._probe()

    def available_features(self) -> List[str]:
        """Return the list of feature flags active in the current mode."""
        base = [
            "ternary_model",      # Pillar 22 — always available
            "local_rag",          # Pillar 33 local tier
            "twin_experiments",   # Pillar 23
            "dreaming",           # Pillar 3
            "narrative",          # Pillar 31
        ]
        if self.is_online:
            base += [
                "agentic_search",     # Pillar 33 web tier
                "collective_pulse",   # Pillar 32
                "zk_proof",           # Pillar 32
                "twin_p2p_sync",      # Pillar 30
            ]
        return base

    def route(self, feature: str) -> bool:
        """Return True if *feature* is currently routable."""
        clean = str(feature or "").strip().lower()
        is_allowed = clean in self.available_features()
        self._route_counts[clean] = self._route_counts.get(clean, 0) + 1
        if self.storage_path:
            self.save_state()
        return is_allowed

    # ------------------------------------------------------------------
    # Internal Probing & State
    # ------------------------------------------------------------------

    def _probe(self) -> None:
        was_online = self._is_online
        self._is_online = _check_online() and not self.force_offline
        self._last_check = time.time()

        if self._is_online != was_online:
            self._transitions += 1
            if self._is_online:
                self._online_since = time.time()
                logger.info("[HybridMode] ONLINE — full feature set unlocked")
            else:
                self._online_since = None
                logger.warning("[HybridMode] OFFLINE — switching to local-only mode")
            if self.storage_path:
                self.save_state()

    def status(self) -> Dict[str, Any]:
        return {
            "available": True,
            "is_online": self.is_online,
            "force_offline": self.force_offline,
            "check_interval": self.check_interval,
            "transitions": self._transitions,
            "available_features": self.available_features(),
            "route_counts": dict(self._route_counts),
            "persisted": self.storage_path is not None and self.storage_path.exists(),
            "storage_path": str(self.storage_path) if self.storage_path else None,
        }

    def save_state(self) -> bool:
        if not self.storage_path:
            return False
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "transitions": self._transitions,
                "route_counts": self._route_counts,
                "last_check": self._last_check,
                "force_offline": self.force_offline,
            }
            tmp = self.storage_path.with_suffix(f"{self.storage_path.suffix}.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, self.storage_path)
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("[HybridMode] cannot save state to %s: %s", self.storage_path, exc)
            return False

    def _load_state(self) -> bool:
        if not self.storage_path or not self.storage_path.exists():
            return False
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            self._transitions = max(self._transitions, int(data.get("transitions", 0)))
            routes = data.get("route_counts", {})
            if isinstance(routes, dict):
                for k, v in routes.items():
                    self._route_counts[str(k)] = int(v)
            return True
        except Exception as exc:
            logger.warning("[HybridMode] cannot load state from %s: %s", self.storage_path, exc)
            return False
