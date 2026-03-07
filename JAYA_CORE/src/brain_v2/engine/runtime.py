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

V18 additions
-------------
* **NANO_MODE**: if the .jay has PACKED_WEIGHTS flag, unpacks the 2-bit
  weights and loads a pure-NumPy NanoModel (no .pyd required).
* **MetaCognitivePlanner** (Pillar 38): reflects every 600 s on weak tasks,
  triggers MorphicKernel patches + LiveEvolver runs.
* **SelfBootstrap** (Pillar 28): detects idle > 300 s and injects
  self-study curriculum tasks.
* **LiveEvolver**: (1+1)-ES micro-evolution wired to live NanoModel weights.
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

    # Pillar 39 — Dynamic Objective Function
    loyalty_score: float = 1.0          # 0–1; drops on boss-adverse outcomes
    objective_weights: Optional[Dict[str, float]] = None

    def __post_init__(self) -> None:
        if self.objective_weights is None:
            self.objective_weights = {
                "accuracy":   0.4,
                "efficiency": 0.3,
                "safety":     0.2,
                "creativity": 0.1,
            }

    def apply_feedback(self, feedback: Dict[str, Any]):
        """Merge numeric feedback keys into this config.

        Pillar 39: also adjusts ``loyalty_score`` if a 'loyalty_delta'
        key is present, and rebalances ``objective_weights``.
        """
        for key, val in feedback.items():
            if key == "loyalty_delta":
                self.loyalty_score = max(0.0, min(1.0,
                    self.loyalty_score + float(val)))
                self.version += 1
                logger.info("AgiConfig.loyalty_score → %.3f  (v%d)",
                            self.loyalty_score, self.version)
                continue
            if key == "objective_weights" and isinstance(val, dict):
                for obj_k, obj_v in val.items():  # type: ignore[union-attr]
                    self.objective_weights[str(obj_k)] = float(obj_v)  # type: ignore[index]
                self.version += 1
                logger.info("AgiConfig.objective_weights updated  (v%d)",
                            self.version)
                continue
            if hasattr(self, key):
                try:
                    setattr(self, key, type(getattr(self, key))(val))
                    self.version += 1
                    logger.info("AgiConfig.%s → %s  (v%d)", key, val, self.version)
                except (TypeError, ValueError):
                    pass

        # Loyalty gate: if loyalty low, shift objectives toward safety
        if self.loyalty_score < 0.5 and self.objective_weights is not None:
            self.objective_weights["safety"] = min(
                1.0, self.objective_weights.get("safety", 0.2) + 0.1
            )
            logger.warning("AgiConfig: low loyalty (%.2f) — safety weight bumped",
                           self.loyalty_score)

    def snapshot(self) -> Dict[str, Any]:
        d = asdict(self)  # type: ignore[return-value]
        return d


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
        self._start_time: float  = 0.0

        # Pillar 7 — Cognitive Silence
        self._silent: bool = False

        # Subsystems initialised during ignite()
        self._ethical_heart:   Optional[Any] = None   # Pillar 15
        self._zero_trust:      Optional[Any] = None   # Pillar 18
        self._legacy:          Optional[Any] = None   # Pillar 19
        self._hybrid:          Optional[Any] = None   # Pillar 37
        self._speculative:     Optional[Any] = None   # Pillar 36
        self._intent:          Optional[Any] = None   # Pillar 40
        self._lingua:          Optional[Any] = None   # Pillar 21
        self._morphic:         Optional[Any] = None   # Pillar 24
        self._resource_mon:    Optional[Any] = None   # Pillar 2
        # V18 additions
        self.nano_mode:         bool          = False   # True when pure-NumPy path
        self._nano_model:      Optional[Any] = None   # NanoModel instance
        self._meta_cognitive:  Optional[Any] = None   # Pillar 38 MetaCognitivePlanner
        self._self_bootstrap:  Optional[Any] = None   # Pillar 28 SelfBootstrap
        self._live_evolver:    Optional[Any] = None   # LiveEvolver for micro-evolution

    # ------------------------------------------------------------------
    # Ignition
    # ------------------------------------------------------------------

    def ignite(self):
        """Bring the engine online: load the model, start the twin."""
        self._start_time = time.time()
        logger.info("Igniting IronEngine | model=%s twin=%s omniverse=%s",
                    os.path.basename(self.model_path),
                    self.enable_twin, self.omniverse_requested)

        # -- Model loading: NANO path (V18) or stub --
        if os.path.exists(self.model_path):
            logger.info("Model file found: %s", self.model_path)
            self._try_load_nano_model()
        else:
            logger.warning("Model file not found (%s) — proceeding in stub mode",
                           self.model_path)

        self.is_awake = True

        # -- Sovereign / security subsystems --
        self._init_security()

        # -- Intelligence subsystems --
        self._init_intelligence()

        # -- Twin subsystem --
        if self.enable_twin:
            self._init_twin()

        # -- Resource monitor (starts background thread) --
        self._init_resource_monitor()

    def _try_load_nano_model(self) -> None:
        """V18: attempt to load NanoModel from IRON_BODY_PACKED section.

        Reads the first 128 bytes of the .jay header and checks for the
        PACKED_WEIGHTS flag (bit 42).  If present, unpacks 2-bit weights
        into a NanoModel (pure NumPy, zero Numba dependency).
        """
        import struct
        PACKED_WEIGHTS_BIT = 1 << 42
        try:
            with open(self.model_path, "rb") as f:
                header = f.read(128)
            if len(header) < 16:
                return
            flags = struct.unpack_from("<Q", header, 8)[0]
            if not (flags & PACKED_WEIGHTS_BIT):
                logger.info("[V18] PACKED_WEIGHTS flag not set — legacy model path")
                return

            from src.brain_v2.model.nano_inference import NanoModel, NANO_CONFIG, STANDARD_CONFIG
            from src.brain_v2.format.packer import unpack_state_dict
            # unpack_state_dict returns dict[str, Any] after our update
            NANO_PROFILE_BIT = 1 << 43
            cfg = NANO_CONFIG if (flags & NANO_PROFILE_BIT) else STANDARD_CONFIG
            model = NanoModel(config=cfg)

            try:
                section_offset = 128
                SECTION_HDR = 24
                FOOTER_SIZE = 32
                file_size = os.path.getsize(self.model_path)
                with open(self.model_path, "rb") as f:
                    raw = f.read()
                while section_offset + SECTION_HDR <= file_size - FOOTER_SIZE:
                    sec_type   = struct.unpack_from("<I", raw, section_offset)[0]
                    sec_size   = struct.unpack_from("<q", raw, section_offset + 8)[0]
                    sec_off_pl = struct.unpack_from("<q", raw, section_offset + 16)[0]
                    if sec_type == 6 and sec_size > 0:
                        payload = raw[sec_off_pl : sec_off_pl + sec_size]
                        # type hints help static analysers understand the mapping
                        state_dict: dict[str, Any] = unpack_state_dict(payload)
                        model.load_state_dict(state_dict)
                        logger.info("[V18] NanoModel loaded from IRON_BODY_PACKED (%d B packed)", sec_size)
                        break
                    section_offset += SECTION_HDR
                else:
                    model.random_init()
                    logger.info("[V18] IRON_BODY_PACKED not found — random-init NanoModel")
            except Exception as exc:
                model.random_init()
                logger.warning("[V18] weight unpack failed (%s) — random-init NanoModel", exc)

            self._nano_model = model
            self.nano_mode   = True
            logger.info("[V18] NANO_MODE=True | config=%s", cfg)

        except Exception as exc:
            logger.warning("[V18] NanoModel load failed (%s) — legacy path", exc)

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

    def _init_security(self) -> None:
        """Initialise sovereign-armor subsystems (Pillars 15, 18, 19, 16)."""
        try:
            from src.brain_v2.soul.ethical_heart import EthicalHeart
            self._ethical_heart = EthicalHeart(strict=False)
            logger.info("[Pillar 15] EthicalHeart ready")
        except ImportError as exc:
            logger.warning("EthicalHeart unavailable: %s", exc)

        try:
            from src.brain_v2.protection.zero_trust import ZeroTrustFilter
            self._zero_trust = ZeroTrustFilter()
            logger.info("[Pillar 18] ZeroTrustFilter ready")
        except ImportError as exc:
            logger.warning("ZeroTrustFilter unavailable: %s", exc)

        try:
            from src.brain_v2.engine.legacy_protocol import LegacyProtocol
            self._legacy = LegacyProtocol(jay_path=self.model_path)
            logger.info("[Pillar 19] LegacyProtocol ready")
        except ImportError as exc:
            logger.warning("LegacyProtocol unavailable: %s", exc)

        try:
            from src.brain_v2.protection.pqc import PQCWrapper
            pqc = PQCWrapper()
            logger.info("[Pillar 16] PQC backend: %s", pqc.algorithm)
        except ImportError as exc:
            logger.warning("PQC unavailable: %s", exc)

    def _init_intelligence(self) -> None:
        """Initialise intelligence subsystems (Pillars 21, 36, 37, 40, 24)."""
        try:
            from src.brain_v2.soul.lingua_logica import LinguaLogica
            self._lingua = LinguaLogica()
            logger.info("[Pillar 21] LinguaLogica ready")
        except ImportError as exc:
            logger.warning("LinguaLogica unavailable: %s", exc)

        try:
            from src.brain_v2.engine.speculative import SpeculativeEngine
            self._speculative = SpeculativeEngine(
                n_paths=3, timeout=4.0
            )
            logger.info("[Pillar 36] SpeculativeEngine ready")
        except ImportError as exc:
            logger.warning("SpeculativeEngine unavailable: %s", exc)

        try:
            from src.brain_v2.engine.hybrid_mode import HybridRouter
            self._hybrid = HybridRouter(
                check_interval=30.0,
                force_offline=False,
            )
            logger.info("[Pillar 37] HybridRouter online=%s",
                        self._hybrid.is_online)  # type: ignore[union-attr]
        except ImportError as exc:
            logger.warning("HybridRouter unavailable: %s", exc)

        try:
            from src.brain_v2.engine.intent_engine import IntentEngine
            self._intent = IntentEngine()
            logger.info("[Pillar 40] IntentEngine ready")
        except ImportError as exc:
            logger.warning("IntentEngine unavailable: %s", exc)

        try:
            from src.brain_v2.engine.morphic import MorphicKernel
            self._morphic = MorphicKernel(
                ethical_heart=self._ethical_heart,
            )
            logger.info("[Pillar 24] MorphicKernel ready")
        except ImportError as exc:
            logger.warning("MorphicKernel unavailable: %s", exc)

        # V18: MetaCognitivePlanner (Pillar 38)
        try:
            from src.brain_v2.engine.meta_cognitive import MetaCognitivePlanner
            self._meta_cognitive = MetaCognitivePlanner()
            logger.info("[Pillar 38] MetaCognitivePlanner ready")
        except ImportError as exc:
            logger.warning("MetaCognitivePlanner unavailable: %s", exc)

        # V18: SelfBootstrap (Pillar 28)
        try:
            from src.brain_v2.engine.self_bootstrap import SelfBootstrap
            self._self_bootstrap = SelfBootstrap()
            logger.info("[Pillar 28] SelfBootstrap ready")
        except ImportError as exc:
            logger.warning("SelfBootstrap unavailable: %s", exc)

        # V18: LiveEvolver
        try:
            from src.brain_v2.education.live_evolver import LiveEvolver
            if self._nano_model is not None:
                self._live_evolver = LiveEvolver(engine=self, max_steps=200)
                logger.info("[V18] LiveEvolver ready (NANO_MODE=%s)", self.nano_mode)
        except ImportError as exc:
            logger.warning("LiveEvolver unavailable: %s", exc)

    def _init_resource_monitor(self) -> None:
        """Start background resource watcher (Pillar 2)."""
        try:
            from src.brain_v2.organism.resource_monitor import ResourceMonitor
            self._resource_mon = ResourceMonitor(check_interval=5.0)
            self._resource_mon.attach(self)   # type: ignore[union-attr]
            logger.info("[Pillar 2] ResourceMonitor started")
        except ImportError as exc:
            logger.warning("ResourceMonitor unavailable: %s", exc)

    # ------------------------------------------------------------------
    # Dreaming (internal memory consolidation)
    # ------------------------------------------------------------------

    def dream(self):
        """Single dreaming tick — consolidates recent experience."""
        if self._silent:
            logger.debug("[Dream] suppressed — Cognitive Silence active")
            return
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
        """Async version of the main run loop."""
        logger.info("Magnum Cycle STARTING  (dream every %.0fs)",
                    self.config.dream_interval)

        if self.twin:
            await self.twin.start()

        last_dream = time.time()
        try:
            while True:
                now = time.time()
                if (not self._silent
                        and now - last_dream >= self.config.dream_interval):
                    self.dream()
                    last_dream = now
                # V18: tick self-evolution subsystems
                if self.twin:
                    if self._meta_cognitive:
                        self._meta_cognitive.tick(self.twin)
                    if self._self_bootstrap:
                        self._self_bootstrap.tick(self.twin)
                await asyncio.sleep(1.0)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            if self.twin:
                await self.twin.stop()
            if self._resource_mon:
                self._resource_mon.stop()
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
        """Process experiment results from the twin."""
        self._feedback_count += 1
        logger.info("[Feedback #%d] task=%r score=%s",
                    self._feedback_count,
                    result.get("task"), result.get("result", {}).get("score"))
        self.config.apply_feedback(result.get("config_update", {}))
        # Teach IntentEngine from task labels (Pillar 40)
        if self._intent and result.get("task"):
            self._intent.learn(str(result["task"]))
        # V18: signal real activity to prevent idle curriculum spam
        if self._self_bootstrap:
            self._self_bootstrap.signal_activity()

    # ------------------------------------------------------------------
    # Pillar 7 — Cognitive Silence
    # ------------------------------------------------------------------

    def enter_silence(self) -> None:
        """Suspend non-essential processing to conserve resources."""
        if self._silent:
            return
        self._silent = True
        if self.twin:
            # Don't await here — fire-and-forget via thread-safe flag
            self.twin.running = False
        self.config.topk_ratio = 0.02
        logger.info("[Pillar 7] Cognitive Silence ACTIVATED — topk=0.02")

    def exit_silence(self) -> None:
        """Resume full operation after a silence period."""
        if not self._silent:
            return
        self._silent = False
        self.config.topk_ratio = 0.10
        logger.info("[Pillar 7] Cognitive Silence DEACTIVATED — topk=0.10")

    @property
    def is_silent(self) -> bool:
        return self._silent

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        twin_status: Optional[Dict[str, Any]] = (
            self.twin.status() if self.twin is not None else None
        )
        return {
            "is_awake":     self.is_awake,
            "is_silent":    self._silent,
            "uptime":       round(time.time() - self._start_time, 1),
            "dreams":       self._dream_count,
            "feedbacks":    self._feedback_count,
            "config":       self.config.snapshot(),
            "twin":         twin_status,
            "hybrid_online": self._hybrid.is_online if self._hybrid else None,
            "ethical_heart": self._ethical_heart.status() if self._ethical_heart else None,
            "zero_trust":    self._zero_trust.status()    if self._zero_trust    else None,
            "speculative":   self._speculative.status()   if self._speculative   else None,
            "intent":        self._intent.status()        if self._intent        else None,
            "lingua":        self._lingua.status()        if self._lingua        else None,
            "morphic":       self._morphic.status()       if self._morphic       else None,
            "resource_mon":   self._resource_mon.status()    if self._resource_mon    else None,
            # V18 additions
            "nano_mode":      self.nano_mode,
            "meta_cognitive": (self._meta_cognitive.status()
                               if self._meta_cognitive is not None else None),
            "self_bootstrap": (self._self_bootstrap.status()
                               if self._self_bootstrap is not None else None),
            "live_evolver":   (self._live_evolver.status()
                               if self._live_evolver is not None else None),
        }
