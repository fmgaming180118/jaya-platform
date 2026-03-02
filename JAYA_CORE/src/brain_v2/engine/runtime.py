"""IronEngine — JAYA_CORE Semi-AGI Brain Runtime.

Responsibilities
================
* Load (or stub-load) the ``JAYA_SOVEREIGN_V*.jay`` model file.
* Manage the digital twin (``CoreTwin``) lifecycle.
* Provide an async *Magnum Cycle* that keeps the engine and twin running
  indefinitely, with graceful shutdown on SIGINT / SIGTERM.
* Apply experiment feedback from the twin back to the engine configuration
  (the ``AgiConfig``), creating a simple but real self-improvement loop.

The class intentionally stays lightweight: no heavy ML libraries are
imported at module level.  Features load lazily, keeping startup fast and
allowing JAYA to "run in any condition."
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

logger = logging.getLogger("IronEngine")


# ---------------------------------------------------------------------------
# AGI Configuration
# ---------------------------------------------------------------------------

@dataclass
class AgiConfig:
    """Mutable configuration that controls the brain's behaviour.

    All fields can be updated at runtime by twin feedback.
    """
    # Sparse gating: how many neurons fire per token
    topk_ratio: float = 0.10          # 10 % active neurons
    # Dreaming (internal consolidation) interval in seconds
    dream_interval: float = 300.0
    # Confidence threshold below which the engine asks the twin for help
    uncertainty_threshold: float = 0.40
    # Maximum tokens generated per response (stub field)
    max_tokens: int = 512
    # Twin reflection interval forwarded on creation
    twin_reflection_interval: float = 30.0
    # Version tag for this config snapshot
    version: int = 0

    def apply_feedback(self, feedback: Dict[str, Any]):
        """Merge numeric feedback keys into this config."""
        for key, val in feedback.items():
            if hasattr(self, key):
                try:
                    setattr(self, key, type(getattr(self, key))(val))
                    self.version += 1
                    logger.info("AgiConfig.%s → %s  (v%d)", key, val, self.version)
                except (TypeError, ValueError):
                    pass

    def snapshot(self) -> Dict[str, Any]:
        return asdict(self)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# IronEngine
# ---------------------------------------------------------------------------

class IronEngine:
    """Core runtime for the JAYA semi-AGI system.

    Parameters
    ----------
    model_path:
        Path to the ``.jay`` model file.
    password:
        Decryption password for the model file.
    enable_voice:
        Whether to load voice I/O subsystems.
    enable_twin:
        Whether to start the digital twin background process.
    omniverse_requested:
        Whether the user wants to attempt Omniverse SDK init.
    """

    def __init__(self,
                 model_path: str,
                 password: str,
                 enable_voice: bool = False,
                 enable_twin: bool = False,
                 omniverse_requested: bool = False):
        self.model_path          = model_path
        self.password            = password
        self.enable_voice        = enable_voice
        self.enable_twin         = enable_twin
        self.omniverse_requested = omniverse_requested

        self.is_awake = False
        self.twin: Optional[Any] = None
        self.config   = AgiConfig()

        # Runtime statistics
        self._dream_count    = 0
        self._feedback_count = 0
        self._start_time: float = 0.0

    # ------------------------------------------------------------------
    # Ignition
    # ------------------------------------------------------------------

    def ignite(self):
        """Bring the engine online: load the model, start the twin."""
        self._start_time = time.time()
        logger.info("Igniting IronEngine | model=%s twin=%s omniverse=%s",
                    os.path.basename(self.model_path),
                    self.enable_twin, self.omniverse_requested)

        # -- Model loading (stubbed; replace with real deserializer) --
        if os.path.exists(self.model_path):
            logger.info("Model file found: %s", self.model_path)
        else:
            logger.warning("Model file not found (%s) — proceeding in stub mode",
                           self.model_path)

        self.is_awake = True

        # -- Twin subsystem --
        if self.enable_twin:
            self._init_twin()

    def _init_twin(self):
        try:
            from src.brain_v2.extensions.twin.core_twin import CoreTwin
            from src.brain_v2.extensions.twin import omniverse as ov_module

            if self.omniverse_requested:
                ov_module.initialize_sdk()

            self.twin = CoreTwin(
                engine=self,
                omniverse_enabled=ov_module.is_available(),
                reflection_interval=self.config.twin_reflection_interval,
            )
            logger.info("CoreTwin ready (omniverse=%s)", ov_module.is_available())
        except ImportError as exc:
            logger.warning("CoreTwin unavailable: %s — twin disabled", exc)

    # ------------------------------------------------------------------
    # Dreaming (internal memory consolidation)
    # ------------------------------------------------------------------

    def dream(self):
        """Single dreaming tick — consolidates recent experience."""
        self._dream_count += 1
        logger.info("[Dream #%d] consolidating sparse pathways...",
                    self._dream_count)
        # If twin is present, queue a self-reflection task
        if self.twin and hasattr(self.twin, "queue_task"):
            self.twin.queue_task(
                code="# dream consolidation\npass",
                label="OPTIMIZE",
            )

    # ------------------------------------------------------------------
    # Magnum Cycle (main async loop)
    # ------------------------------------------------------------------

    async def run_magnum_cycle_async(self):
        """Async version of the main run loop.

        Starts the twin (if available), then ticks every second until
        interrupted.  Dreaming occurs at ``config.dream_interval``.
        """
        logger.info("Magnum Cycle STARTING  (dream every %.0fs)",
                    self.config.dream_interval)

        # start twin background task
        if self.twin:
            await self.twin.start()

        last_dream = time.time()
        try:
            while True:
                now = time.time()
                if now - last_dream >= self.config.dream_interval:
                    self.dream()
                    last_dream = now
                await asyncio.sleep(1.0)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            if self.twin:
                await self.twin.stop()
            logger.info("Magnum Cycle STOPPED | uptime=%.1fs dreams=%d feedback=%d",
                        time.time() - self._start_time,
                        self._dream_count, self._feedback_count)

    def run_magnum_cycle(self):
        """Synchronous entry-point — runs ``run_magnum_cycle_async``."""
        asyncio.run(self.run_magnum_cycle_async())

    # ------------------------------------------------------------------
    # Twin interaction
    # ------------------------------------------------------------------

    def request_twin_action(self, config: Dict[str, Any]) -> None:
        """Queue an experiment in the twin from synchronous context."""
        if not self.twin:
            return
        code: str = str(config.get("code") or "")
        if code:
            self.twin.queue_task(code,
                                 label=str(config.get("label") or "OPTIMIZE"))

    def receive_twin_feedback(self, result: Dict[str, Any]):
        """Process experiment results from the twin.

        Feedback keys that match ``AgiConfig`` fields are applied.
        """
        self._feedback_count += 1
        logger.info("[Feedback #%d] task=%r score=%s",
                    self._feedback_count,
                    result.get("task"), result.get("result", {}).get("score"))
        # Apply any config-level suggestions carried in the result
        self.config.apply_feedback(result.get("config_update", {}))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        twin_status: Optional[Dict[str, Any]] = (
            self.twin.status() if self.twin is not None else None
        )
        return {
            "is_awake":   self.is_awake,
            "uptime":     round(time.time() - self._start_time, 1),
            "dreams":     self._dream_count,
            "feedbacks":  self._feedback_count,
            "config":     self.config.snapshot(),
            "twin":       twin_status,
        }
