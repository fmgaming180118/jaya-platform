"""Pillar 37 — Hybrid Consciousness.

JAYA must stay intelligently operational regardless of network
connectivity.  HybridRouter monitors online status and adjusts which
subsystems are available:

    ONLINE  → full feature set: AgenticSearch, Collective Pulse, web RAG
    OFFLINE → local-only: ternary model + local RAG + twin experiments

The router checks connectivity every ``check_interval`` seconds via a
lightweight DNS probe (no raw socket, no heavy library).
"""

import logging
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
    """

    def __init__(self,
                 check_interval: float = 30.0,
                 force_offline: bool = False):
        self.check_interval = check_interval
        self.force_offline  = force_offline
        self._is_online:    bool  = False
        self._last_check:   float = 0.0
        self._transitions:  int   = 0
        self._online_since: Optional[float] = None

        # Perform one immediate probe unless forced offline
        if not force_offline:
            self._probe()

    # ------------------------------------------------------------------

    @property
    def is_online(self) -> bool:
        """Return current connectivity status; probe if interval elapsed."""
        now = time.time()
        if not self.force_offline and (now - self._last_check >= self.check_interval):
            self._probe()
        return self._is_online

    # ------------------------------------------------------------------

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
        return feature in self.available_features()

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

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "is_online":        self.is_online,
            "force_offline":    self.force_offline,
            "check_interval":   self.check_interval,
            "transitions":      self._transitions,
            "available":        self.available_features(),
        }
