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
* **NarrativeContinuity** (Pillar 31): keeps bounded autobiographical
    context across turns for coherent follow-up behaviour.
* **TwinProtocol** (Pillar 30): signed deterministic handshake and sync
    packets for trusted twin-to-twin coordination.
* **CollectivePulse** (Pillar 32): aggregates collective trust/cohesion
    signals for online-offline coordination.
* **AgenticRAG** (Pillar 33): local procedural retrieval and feedback loop
    for autonomous task guidance without heavy dependencies.
* **DynamicSparsityMoE** (Pillar 34): routes each request to a sparse
    expert subset under resource-aware constraints.
* **ActivationSparsity** (Pillar 35): adapts active-neuron budget per
    turn based on intent complexity and resource pressure.
* **MetaCognitivePlanner** (Pillar 38): reflects every 600 s on weak tasks,
  triggers MorphicKernel patches + LiveEvolver runs.
* **SelfBootstrap** (Pillar 28): detects idle > 300 s and injects
  self-study curriculum tasks.
* **LiveEvolver**: (1+1)-ES micro-evolution wired to live NanoModel weights.
"""

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast

logger = logging.getLogger("IronEngine")

JAYA_IR_CACHE_SIZE = 768
JAYA_IR_TTL_S = 600.0

_AGENTIC_ALLOWED_OPERATIONS: set[str] = {
    "facts",
    "procedures",
    "graph",
    "feedback",
}

_AGENTIC_DEFAULT_SOURCE_POLICY: Dict[str, Any] = {
    "require_trusted_source": True,
    "allow_facts": True,
    "allow_procedures": False,
    "allow_graph": False,
    "allow_feedback": False,
    "max_limit": 2,
    "allowed_operations": ["facts"],
}


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
        self._twin_protocol:   Optional[Any] = None   # Pillar 30
        self._hybrid:          Optional[Any] = None   # Pillar 37
        self._narrative:       Optional[Any] = None   # Pillar 31
        self._collective_pulse: Optional[Any] = None  # Pillar 32
        self._agentic_rag:     Optional[Any] = None   # Pillar 33
        self._dynamic_moe:     Optional[Any] = None   # Pillar 34
        self._activation_sparsity: Optional[Any] = None  # Pillar 35
        self._speculative:     Optional[Any] = None   # Pillar 36
        self._intent:          Optional[Any] = None   # Pillar 40
        self._lingua:          Optional[Any] = None   # Pillar 21
        self._jaya_ir_exec:    Optional[Any] = None   # Phase 1 JayaIR executor
        self._evolution_gate:  Optional[Any] = None   # Phase 2 evolution gate
        self._morphic:         Optional[Any] = None   # Pillar 24
        self._resource_mon:    Optional[Any] = None   # Pillar 2
        # V18 additions
        self.nano_mode:         bool          = False   # True when pure-NumPy path
        self._nano_model:      Optional[Any] = None   # NanoModel instance
        self._meta_cognitive:  Optional[Any] = None   # Pillar 38 MetaCognitivePlanner
        self._self_bootstrap:  Optional[Any] = None   # Pillar 28 SelfBootstrap
        self._live_evolver:    Optional[Any] = None   # LiveEvolver for micro-evolution
        self._agentic_source_policy: Dict[str, Dict[str, Any]] = {
            "local_rag": {
                "require_trusted_source": False,
                "allow_facts": True,
                "allow_procedures": True,
                "allow_graph": True,
                "allow_feedback": True,
                "max_limit": 8,
                "allowed_operations": ["facts", "procedures", "graph", "feedback"],
            },
            "user_direct": {
                "require_trusted_source": True,
                "allow_facts": True,
                "allow_procedures": True,
                "allow_graph": True,
                "allow_feedback": True,
                "max_limit": 8,
                "allowed_operations": ["facts", "procedures", "graph", "feedback"],
            },
            "remote_api_readonly": {
                "require_trusted_source": True,
                "allow_facts": True,
                "allow_procedures": False,
                "allow_graph": False,
                "allow_feedback": False,
                "max_limit": 3,
                "allowed_operations": ["facts"],
            },
            "remote_api_privileged": {
                "require_trusted_source": True,
                "allow_facts": True,
                "allow_procedures": True,
                "allow_graph": True,
                "allow_feedback": True,
                "max_limit": 5,
                "allowed_operations": ["facts", "procedures", "graph", "feedback"],
            },
        }

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
        """Initialise intelligence subsystems (Pillars 21, 30, 31, 32, 33, 34, 35, 36, 37, 40, 24)."""
        try:
            from src.brain_v2.soul.lingua_logica import LinguaLogica
            self._lingua = LinguaLogica()
            logger.info("[Pillar 21] LinguaLogica ready")
        except ImportError as exc:
            logger.warning("LinguaLogica unavailable: %s", exc)

        try:
            from src.brain_v2.extensions.twin.twin_protocol import TwinProtocol

            shared_secret = os.getenv("JAYA_TWIN_SHARED_SECRET")
            if not shared_secret:
                shared_secret = TwinProtocol.derive_secret(
                    password=self.password,
                    model_ref=os.path.basename(self.model_path),
                )

            node_seed = os.getenv("JAYA_NODE_ID")
            if node_seed:
                node_id = str(node_seed)
            else:
                node_id = hashlib.sha256(
                    f"{self.model_path}|{self.password}".encode("utf-8")
                ).hexdigest()[:16]

            self._twin_protocol = TwinProtocol(
                node_id=node_id,
                shared_secret=shared_secret,
            )
            logger.info("[Pillar 30] TwinProtocol ready node=%s", node_id)
        except ImportError as exc:
            logger.warning("TwinProtocol unavailable: %s", exc)

        try:
            from src.brain_v2.engine.dynamic_moe import DynamicMoERouter

            self._dynamic_moe = DynamicMoERouter(max_active_experts=2)
            logger.info("[Pillar 34] DynamicMoERouter ready")
        except ImportError as exc:
            logger.warning("DynamicMoERouter unavailable: %s", exc)

        try:
            from src.brain_v2.engine.activation_sparsity import ActivationSparsityController

            self._activation_sparsity = ActivationSparsityController(
                default_topk=self.config.topk_ratio,
            )
            logger.info("[Pillar 35] ActivationSparsityController ready")
        except ImportError as exc:
            logger.warning("ActivationSparsityController unavailable: %s", exc)

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
            from src.brain_v2.engine.narrative_continuity import NarrativeContinuity

            persist_path = os.getenv("JAYA_NARRATIVE_PATH")
            self._narrative = NarrativeContinuity(persist_path=persist_path)
            logger.info(
                "[Pillar 31] NarrativeContinuity ready (persist=%s)",
                bool(persist_path),
            )
        except ImportError as exc:
            logger.warning("NarrativeContinuity unavailable: %s", exc)

        try:
            from src.brain_v2.engine.collective_pulse import CollectivePulse

            self._collective_pulse = CollectivePulse(max_events=160, history_window=16)
            logger.info("[Pillar 32] CollectivePulse ready")
        except ImportError as exc:
            logger.warning("CollectivePulse unavailable: %s", exc)

        try:
            from src.brain_v2.soul.agentic_rag import AgenticRAG

            rag_path_env = os.getenv("JAYA_AGENTIC_RAG_PATH")
            if rag_path_env:
                rag_db_path = str(Path(rag_path_env))
            else:
                rag_db_path = str(
                    Path(__file__).resolve().parents[3] / "data" / "rag_runtime.db"
                )

            self._agentic_rag = AgenticRAG(db_path=rag_db_path)
            logger.info("[Pillar 33] AgenticRAG ready db=%s", rag_db_path)
        except ImportError as exc:
            logger.warning("AgenticRAG unavailable: %s", exc)

        try:
            from src.brain_v2.engine.intent_engine import IntentEngine
            self._intent = IntentEngine()
            logger.info("[Pillar 40] IntentEngine ready")
        except ImportError as exc:
            logger.warning("IntentEngine unavailable: %s", exc)

        self._ensure_jaya_ir_executor(log_on_ready=True)

        try:
            from src.brain_v2.engine.morphic import MorphicKernel
            self._morphic = MorphicKernel(
                ethical_heart=self._ethical_heart,
            )
            logger.info("[Pillar 24] MorphicKernel ready")
        except ImportError as exc:
            logger.warning("MorphicKernel unavailable: %s", exc)

        try:
            from src.brain_v2.engine.evolution_gate import EvolutionGate
            self._evolution_gate = EvolutionGate(
                ethical_heart=self._ethical_heart,
                zero_trust=self._zero_trust,
            )
            logger.info("[Phase 2] EvolutionGate ready")
        except ImportError as exc:
            logger.warning("EvolutionGate unavailable: %s", exc)

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
        cfg_update = result.get("config_update", {})
        if cfg_update.get("invalidate_ir_cache") and self._jaya_ir_exec:
            self._jaya_ir_exec.clear_cache()
            logger.info("[Phase 1] JayaIR cache invalidated from feedback")
        # Teach IntentEngine from task labels (Pillar 40)
        if self._intent and result.get("task"):
            self._intent.learn(str(result["task"]))
        # V18: signal real activity to prevent idle curriculum spam
        if self._self_bootstrap:
            self._self_bootstrap.signal_activity()
        if self._narrative:
            try:
                score = result.get("result", {}).get("score")
                self._narrative.remember_feedback(
                    task=str(result.get("task") or "unknown_task"),
                    score=score,
                )
            except Exception as exc:
                logger.debug("NarrativeContinuity feedback trace failed: %s", exc)
        if self._collective_pulse:
            try:
                score = result.get("result", {}).get("score")
                online = bool(self._hybrid.is_online) if self._hybrid else False
                self._collective_pulse.ingest_feedback(
                    task=str(result.get("task") or "unknown_task"),
                    score=score,
                    is_online=online,
                )
            except Exception as exc:
                logger.debug("CollectivePulse feedback ingest failed: %s", exc)

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

    def _ensure_jaya_ir_executor(self, log_on_ready: bool = False) -> bool:
        """Create JayaIR executor lazily through a single runtime factory."""
        if self._jaya_ir_exec is not None:
            return True
        try:
            from src.brain_v2.engine.jaya_ir_exec import JayaIRExecutor
            self._jaya_ir_exec = JayaIRExecutor(
                cache_size=JAYA_IR_CACHE_SIZE,
                ttl_s=JAYA_IR_TTL_S,
            )
            if log_on_ready:
                logger.info(
                    "[Phase 1] JayaIRExecutor ready (cache=%d ttl=%.1fs)",
                    JAYA_IR_CACHE_SIZE,
                    JAYA_IR_TTL_S,
                )
            return True
        except ImportError as exc:
            logger.warning("JayaIRExecutor unavailable: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Phase 1 — JayaIR execution path
    # ------------------------------------------------------------------

    def execute_intent(self, text: str) -> Dict[str, Any]:
        """Run one natural-language intent through Lingua -> JayaIR."""
        if not self._lingua:
            from src.brain_v2.soul.lingua_logica import LinguaLogica
            self._lingua = LinguaLogica()
        if not self._ensure_jaya_ir_executor(log_on_ready=True):
            return {
                "ok": False,
                "error": "jaya_ir_executor_unavailable",
                "intent": text,
            }
        executor = self._jaya_ir_exec
        if executor is None:
            return {
                "ok": False,
                "error": "jaya_ir_executor_unavailable",
                "intent": text,
            }

        expr = self._lingua.encode(text)

        readings: Dict[str, Any] = {}
        if self._resource_mon:
            try:
                readings = self._resource_mon.readings()
            except Exception:
                readings = {}

        moe_route: Optional[Dict[str, Any]] = None
        if self._dynamic_moe:
            try:
                moe_route = self._dynamic_moe.route(
                    text=text,
                    logic_expr=expr,
                    cpu_pct=readings.get("cpu_pct"),
                    mem_pct=readings.get("mem_pct"),
                )
            except Exception as exc:
                logger.debug("DynamicMoE route failed: %s", exc)

        if self._activation_sparsity:
            try:
                decision = self._activation_sparsity.decide(
                    text=text,
                    logic_expr=expr,
                    base_topk=self.config.topk_ratio,
                    cpu_pct=readings.get("cpu_pct"),
                    mem_pct=readings.get("mem_pct"),
                    is_silent=self._silent,
                )
                target_topk = float(decision["target_topk"])
                self.config.topk_ratio = target_topk

                if self._nano_model is not None:
                    self._nano_model.topk_ratio = target_topk
            except Exception as exc:
                logger.debug("ActivationSparsity decision failed: %s", exc)

        out = executor.execute_logic_expr(expr)
        out["intent"] = text
        out["logic_expr"] = expr
        out["activation_topk"] = self.config.topk_ratio
        if moe_route is not None:
            out["moe_route"] = moe_route
            out["moe_primary_expert"] = moe_route.get("primary_expert")

        if self._collective_pulse:
            try:
                online = bool(self._hybrid.is_online) if self._hybrid else False
                self._collective_pulse.ingest_turn(
                    text=text,
                    activation_topk=self.config.topk_ratio,
                    primary_expert=str(out.get("moe_primary_expert") or "logic"),
                    is_online=online,
                )
                out["collective_pulse"] = self._collective_pulse.pulse()
            except Exception as exc:
                logger.debug("CollectivePulse turn ingest failed: %s", exc)

        if self._narrative:
            try:
                self._narrative.remember_turn(
                    user_text=text,
                    logic_expr=expr,
                    runtime_result=out,
                )
            except Exception as exc:
                logger.debug("NarrativeContinuity turn trace failed: %s", exc)

        if self._agentic_rag:
            try:
                procedures = self._agentic_rag.recall_procedure(
                    text,
                    language="id",
                    limit=1,
                )
                if procedures:
                    top_raw = procedures[0]
                    top = cast(Dict[str, Any], top_raw) if isinstance(top_raw, dict) else {}
                    steps_raw = top.get("steps", [])
                    step_seq = cast(list[Any], steps_raw) if isinstance(steps_raw, list) else []
                    steps = [
                        str(item) for item in step_seq
                        if isinstance(item, str) and item.strip()
                    ]
                    out["agentic_hint"] = {
                        "trigger": str(top.get("trigger") or ""),
                        "score": float(top.get("score") or 0.0),
                        "steps": steps[:4],
                    }
            except Exception as exc:
                logger.debug("AgenticRAG hint generation failed: %s", exc)
        return out

    def narrative_context(self, limit: int = 5, max_chars: int = 600) -> Dict[str, Any]:
        """Return bounded autobiographical context (Pillar 31)."""
        if not self._narrative:
            return {
                "ok": False,
                "error": "narrative_continuity_unavailable",
                "summary": "",
                "recent": [],
                "context": "",
            }

        try:
            snap = self._narrative.snapshot(limit=limit, max_chars=max_chars)
            snap["ok"] = True
            return snap
        except Exception as exc:
            return {
                "ok": False,
                "error": f"narrative_context_failed:{exc}",
                "summary": "",
                "recent": [],
                "context": "",
            }

    # ------------------------------------------------------------------
    # Pillar 33 — Agentic RAG
    # ------------------------------------------------------------------

    def memorize_agentic_procedure(
        self,
        trigger: str,
        steps: list[str],
        language: str = "id",
        source: str = "runtime",
        confidence: float = 0.80,
    ) -> Dict[str, Any]:
        if not self._agentic_rag:
            return {"ok": False, "error": "agentic_rag_unavailable"}

        stored = self._agentic_rag.memorize_procedure(
            trigger=trigger,
            steps=steps,
            language=language,
            source=source,
            confidence=confidence,
        )
        return {
            "ok": bool(stored),
            "trigger": str(trigger or "").strip().lower(),
            "language": str(language or "id").strip().lower(),
        }

    def set_agentic_source_policy(self, source: str, policy: Dict[str, Any]) -> Dict[str, Any]:
        safe_source = str(source or "").strip()
        if not safe_source:
            return {"ok": False, "error": "invalid_source"}

        current = self._resolve_agentic_source_policy(safe_source)
        merged = dict(current)
        merged.update(dict(policy or {}))
        if "allowed_operations" not in dict(policy or {}):
            merged.pop("allowed_operations", None)
        safe_policy = self._sanitize_agentic_source_policy(merged)
        self._agentic_source_policy[safe_source] = safe_policy
        return {
            "ok": True,
            "source": safe_source,
            "policy": dict(safe_policy),
        }

    def _sanitize_agentic_source_policy(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        operations_obj = policy.get("allowed_operations")
        merged = dict(_AGENTIC_DEFAULT_SOURCE_POLICY)
        merged.update(dict(policy or {}))

        try:
            max_limit_raw = int(merged.get("max_limit", _AGENTIC_DEFAULT_SOURCE_POLICY["max_limit"]))
        except (TypeError, ValueError):
            max_limit_raw = int(_AGENTIC_DEFAULT_SOURCE_POLICY["max_limit"])

        safe_policy: Dict[str, Any] = {
            "require_trusted_source": bool(merged.get("require_trusted_source", True)),
            "allow_facts": bool(merged.get("allow_facts", True)),
            "allow_procedures": bool(merged.get("allow_procedures", False)),
            "allow_graph": bool(merged.get("allow_graph", False)),
            "allow_feedback": bool(merged.get("allow_feedback", False)),
            "max_limit": max(1, min(max_limit_raw, 16)),
        }
        safe_policy["allowed_operations"] = self._normalize_agentic_operations(
            operations=operations_obj,
            fallback_policy=safe_policy,
        )
        return safe_policy

    def _normalize_agentic_operations(self, operations: Any, fallback_policy: Dict[str, Any]) -> list[str]:
        allowed_ops: list[str] = []
        if isinstance(operations, list):
            raw_ops = cast(list[Any], operations)
            for raw in raw_ops:
                op = str(raw or "").strip().lower()
                if op in _AGENTIC_ALLOWED_OPERATIONS and op not in allowed_ops:
                    allowed_ops.append(op)

        if not allowed_ops:
            if bool(fallback_policy.get("allow_facts", False)):
                allowed_ops.append("facts")
            if bool(fallback_policy.get("allow_procedures", False)):
                allowed_ops.append("procedures")
            if bool(fallback_policy.get("allow_graph", False)):
                allowed_ops.append("graph")
            if bool(fallback_policy.get("allow_feedback", False)):
                allowed_ops.append("feedback")

        if not allowed_ops:
            allowed_ops.append("facts")
        return allowed_ops

    def _agentic_policy_allows(self, policy: Dict[str, Any], operation: str) -> bool:
        operation_map = {
            "facts": "allow_facts",
            "procedures": "allow_procedures",
            "graph": "allow_graph",
            "feedback": "allow_feedback",
        }
        op = str(operation or "").strip().lower()
        gate_field = operation_map.get(op)
        if gate_field is None:
            return False

        if not bool(policy.get(gate_field, False)):
            return False

        raw_operations_obj = policy.get("allowed_operations", [])
        if not isinstance(raw_operations_obj, list):
            return False

        raw_operations = cast(list[Any], raw_operations_obj)
        normalized_ops = {
            str(item or "").strip().lower()
            for item in raw_operations
            if str(item or "").strip().lower() in _AGENTIC_ALLOWED_OPERATIONS
        }
        return op in normalized_ops

    def _resolve_agentic_source_policy(self, source: str) -> Dict[str, Any]:
        safe_source = str(source or "").strip() or "unknown"
        policy = self._agentic_source_policy.get(safe_source)
        if isinstance(policy, dict):
            return self._sanitize_agentic_source_policy(dict(policy))
        return self._sanitize_agentic_source_policy({})

    def query_agentic_rag(
        self,
        query: str,
        language: Optional[str] = "id",
        limit: int = 3,
        source: str = "local_rag",
    ) -> Dict[str, Any]:
        if not self._agentic_rag:
            return {
                "ok": False,
                "error": "agentic_rag_unavailable",
                "query": query,
            }

        safe_query = str(query or "").strip()
        if not safe_query:
            return {
                "ok": False,
                "error": "invalid_query",
                "query": safe_query,
            }

        safe_source = str(source or "local_rag").strip() or "local_rag"
        source_policy = self._resolve_agentic_source_policy(safe_source)
        require_trusted = bool(source_policy.get("require_trusted_source", True))
        allow_facts = self._agentic_policy_allows(source_policy, "facts")
        allow_procedures = self._agentic_policy_allows(source_policy, "procedures")
        allow_graph = self._agentic_policy_allows(source_policy, "graph")
        max_limit = max(1, min(int(source_policy.get("max_limit", 2)), 16))

        if require_trusted:
            if not self._zero_trust:
                return {
                    "ok": False,
                    "error": "zero_trust_unavailable",
                    "reason": "trusted_source_required",
                    "query": safe_query,
                    "source": safe_source,
                }

            trusted_sources_fallback: set[str] = set()
            trusted_sources_obj = getattr(
                self._zero_trust,
                "trusted_sources",
                trusted_sources_fallback,
            )
            trusted_sources = (
                cast(set[str], trusted_sources_obj)
                if isinstance(trusted_sources_obj, set)
                else trusted_sources_fallback
            )
            if safe_source not in trusted_sources:
                return {
                    "ok": False,
                    "error": "zero_trust_blocked",
                    "reason": f"source_not_trusted:{safe_source}",
                    "query": safe_query,
                    "source": safe_source,
                }

            trust_ok, trust_reason = self._zero_trust.validate(
                source=safe_source,
                payload=safe_query,
                force_scan=True,
            )
            if not trust_ok:
                return {
                    "ok": False,
                    "error": "zero_trust_blocked",
                    "reason": trust_reason,
                    "query": safe_query,
                    "source": safe_source,
                }

        safe_limit = max(1, min(int(limit), max_limit))

        procedures: list[Dict[str, Any]] = []
        if allow_procedures:
            procedures_raw = self._agentic_rag.recall_procedure(
                safe_query,
                language=language,
                limit=safe_limit,
            )
            procedures = cast(list[Dict[str, Any]], procedures_raw) if isinstance(procedures_raw, list) else []

        facts: list[Dict[str, Any]] = []
        if allow_facts:
            facts_raw = self._agentic_rag.recall(safe_query, limit=safe_limit)
            facts = cast(list[Dict[str, Any]], facts_raw) if isinstance(facts_raw, list) else []

        graph_context: list[str] = []
        if allow_graph:
            try:
                graph_bundle = self._agentic_rag.recall_with_graph(
                    safe_query,
                    limit=safe_limit,
                    graph_hop=1,
                )
                if isinstance(graph_bundle, dict):
                    graph_map = cast(Dict[str, Any], graph_bundle)
                    graph_raw_obj = graph_map.get("graph_context", [])
                    if isinstance(graph_raw_obj, list):
                        graph_raw = cast(list[Any], graph_raw_obj)
                        graph_context = [str(item) for item in graph_raw[:safe_limit]]
            except Exception:
                graph_context = []

        plan: list[str] = []
        plan_source = "none"
        confidence = 0.0

        if procedures:
            plan_source = "procedure"
            top = procedures[0]
            steps_raw = top.get("steps", [])
            step_seq = cast(list[Any], steps_raw) if isinstance(steps_raw, list) else []
            if isinstance(steps_raw, list):
                plan = [
                    str(item) for item in step_seq
                    if isinstance(item, str) and item.strip()
                ][:8]
            try:
                confidence = float(top.get("score") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
        elif facts:
            plan_source = "facts"
            fact_rows = facts
            for item in fact_rows[:safe_limit]:
                topic = str(item.get("topic") or "").strip()
                content = str(item.get("content") or "").strip()
                if topic and content:
                    plan.append(f"Review {topic}: {content[:120]}")
                elif content:
                    plan.append(f"Review: {content[:120]}")
            confidence = 0.35 if plan else 0.0

        if not plan:
            if allow_procedures or allow_facts:
                plan = [
                    "No local procedural memory found.",
                    "Ask one clarifying question before executing risky actions.",
                ]
            else:
                plan = [
                    "Source policy does not allow memory retrieval.",
                    "Use trusted source or update agentic source policy.",
                ]

        clarify_threshold_raw = os.getenv("JAYA_CLARIFY_THRESHOLD", "0.62")
        try:
            clarify_threshold = float(clarify_threshold_raw)
        except (TypeError, ValueError):
            clarify_threshold = 0.62

        return {
            "ok": True,
            "query": safe_query,
            "source_input": safe_source,
            "source": plan_source,
            "source_policy": source_policy,
            "confidence": max(0.0, min(1.0, confidence)),
            "should_clarify": confidence < clarify_threshold,
            "plan": plan,
            "procedures": procedures,
            "facts": facts,
            "graph_context": graph_context,
        }

    def apply_agentic_feedback(
        self,
        query: str,
        success: bool = True,
        language: Optional[str] = "id",
        source: str = "local_rag",
    ) -> Dict[str, Any]:
        if not self._agentic_rag:
            return {
                "ok": False,
                "error": "agentic_rag_unavailable",
                "query": query,
                "success": bool(success),
            }

        safe_query = str(query or "").strip()
        safe_source = str(source or "local_rag").strip() or "local_rag"
        source_policy = self._resolve_agentic_source_policy(safe_source)
        if not self._agentic_policy_allows(source_policy, "feedback"):
            return {
                "ok": False,
                "error": "feedback_not_allowed_for_source",
                "query": safe_query,
                "source": safe_source,
                "source_policy": source_policy,
            }

        require_trusted = bool(source_policy.get("require_trusted_source", True))
        if require_trusted:
            if not self._zero_trust:
                return {
                    "ok": False,
                    "error": "zero_trust_unavailable",
                    "reason": "trusted_source_required",
                    "query": safe_query,
                    "source": safe_source,
                }

            trusted_sources_fallback: set[str] = set()
            trusted_sources_obj = getattr(
                self._zero_trust,
                "trusted_sources",
                trusted_sources_fallback,
            )
            trusted_sources = (
                cast(set[str], trusted_sources_obj)
                if isinstance(trusted_sources_obj, set)
                else trusted_sources_fallback
            )
            if safe_source not in trusted_sources:
                return {
                    "ok": False,
                    "error": "zero_trust_blocked",
                    "reason": f"source_not_trusted:{safe_source}",
                    "query": safe_query,
                    "source": safe_source,
                }

        if self._zero_trust and safe_source != "local_rag":
            trust_ok, trust_reason = self._zero_trust.validate(
                source=safe_source,
                payload=safe_query,
                force_scan=True,
            )
            if not trust_ok:
                return {
                    "ok": False,
                    "error": "zero_trust_blocked",
                    "reason": trust_reason,
                    "query": safe_query,
                    "source": safe_source,
                }

        result = self._agentic_rag.apply_procedure_feedback(
            query=safe_query,
            success=success,
            language=language,
        )
        if isinstance(result, dict):
            payload = cast(Dict[str, Any], result)
            if bool(payload.get("ok")):
                base_weights_raw = self.config.objective_weights or {}
                base_weights = dict(base_weights_raw)
                objective = {
                    "accuracy": float(base_weights.get("accuracy", 0.4)),
                    "efficiency": float(base_weights.get("efficiency", 0.3)),
                    "safety": float(base_weights.get("safety", 0.2)),
                    "creativity": float(base_weights.get("creativity", 0.1)),
                }

                if success:
                    loyalty_delta = 0.02
                    objective["accuracy"] += 0.03
                    objective["efficiency"] += 0.02
                    objective["safety"] -= 0.02
                    objective["creativity"] -= 0.01
                else:
                    loyalty_delta = -0.06
                    objective["accuracy"] -= 0.03
                    objective["efficiency"] -= 0.03
                    objective["safety"] += 0.08
                    objective["creativity"] -= 0.02

                min_w = 0.05
                for key in list(objective.keys()):
                    objective[key] = max(min_w, float(objective[key]))

                total = sum(objective.values())
                if total <= 0:
                    total = 1.0

                normalized = {
                    "accuracy": objective["accuracy"] / total,
                    "efficiency": objective["efficiency"] / total,
                    "safety": objective["safety"] / total,
                    "creativity": objective["creativity"] / total,
                }

                self.config.apply_feedback(
                    {
                        "loyalty_delta": loyalty_delta,
                        "objective_weights": normalized,
                    }
                )

                clarify_raw = os.getenv("JAYA_CLARIFY_THRESHOLD", "0.62")
                decay_raw = os.getenv("JAYA_PROCEDURE_DECAY_HOURS", "120")
                try:
                    clarify_value = float(clarify_raw)
                except (TypeError, ValueError):
                    clarify_value = 0.62
                try:
                    decay_value = float(decay_raw)
                except (TypeError, ValueError):
                    decay_value = 120.0

                history_written = False
                try:
                    history_written = bool(
                        self._agentic_rag.log_policy_decision(
                            {
                                "base_clarify_threshold": clarify_value,
                                "base_decay_hours": decay_value,
                                "recommended_clarify_threshold": clarify_value,
                                "recommended_decay_hours": decay_value,
                                "clarify_mode": "agentic_feedback_success" if success else "agentic_feedback_failure",
                                "decay_mode": "stable",
                                "reasons": ["agentic_feedback", "objective_shift"],
                                "snapshot": {
                                    "query": safe_query,
                                    "source": safe_source,
                                    "success": bool(success),
                                    "objective_weights": dict(self.config.objective_weights or normalized),
                                    "loyalty_score": float(self.config.loyalty_score),
                                },
                            },
                            source=f"agentic_feedback:{safe_source}",
                        )
                    )
                except Exception as exc:
                    logger.debug("AgenticRAG policy history log failed: %s", exc)

                evolution_audit_logged = self._record_evolution_runtime_event(
                    event_type="agentic_objective_update",
                    payload={
                        "source": safe_source,
                        "success": bool(success),
                        "loyalty_delta": loyalty_delta,
                        "loyalty_score": float(self.config.loyalty_score),
                        "query": safe_query,
                    },
                )

                payload["objective_update"] = {
                    "applied": True,
                    "loyalty_delta": loyalty_delta,
                    "loyalty_score": float(self.config.loyalty_score),
                    "objective_weights": dict(self.config.objective_weights or normalized),
                    "policy_history_written": history_written,
                    "evolution_audit_logged": evolution_audit_logged,
                }
            else:
                payload["objective_update"] = {
                    "applied": False,
                    "reason": "feedback_not_applied",
                }
            payload["source_policy"] = source_policy
            return payload
        return {
            "ok": False,
            "error": "invalid_feedback_result",
        }

    # ------------------------------------------------------------------
    # Pillar 30 — Twin Protocol sync
    # ------------------------------------------------------------------

    def twin_handshake(
        self,
        peer_id: str,
        capabilities: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._twin_protocol:
            return {"ok": False, "error": "twin_protocol_unavailable"}

        caps = capabilities or {
            "collective_pulse": self._collective_pulse is not None,
            "agentic_rag": self._agentic_rag is not None,
            "dynamic_moe": self._dynamic_moe is not None,
            "activation_sparsity": self._activation_sparsity is not None,
            "narrative": self._narrative is not None,
        }
        payload = self._twin_protocol.create_handshake(peer_id=peer_id, capabilities=caps)
        return {"ok": True, "handshake": payload}

    def verify_twin_handshake(
        self,
        handshake: Dict[str, Any],
        expected_sender: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self._twin_protocol:
            return {
                "ok": False,
                "error": "twin_protocol_unavailable",
                "reason": "unavailable",
            }

        ok, reason = self._twin_protocol.verify_handshake(
            payload=handshake,
            expected_peer_id=self._twin_protocol.node_id,
            expected_sender=expected_sender,
        )
        return {"ok": ok, "reason": reason}

    def create_twin_sync_packet(
        self,
        peer_id: str,
        state_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._twin_protocol:
            return {"ok": False, "error": "twin_protocol_unavailable"}

        if state_override is not None:
            state: Dict[str, Any] = dict(state_override)
        else:
            pulse = self._collective_pulse.pulse() if self._collective_pulse else None
            moe_status: Dict[str, Any] = self._dynamic_moe.status() if self._dynamic_moe else {}
            last_route_raw = moe_status.get("last_route")
            last_route: Dict[str, Any] = cast(Dict[str, Any], last_route_raw) if isinstance(last_route_raw, dict) else {}

            state = {
                "is_silent": bool(self._silent),
                "topk_ratio": float(self.config.topk_ratio),
                "loyalty_score": float(self.config.loyalty_score),
                "moe_primary_expert": last_route.get("primary_expert"),
                "collective_pulse": pulse,
                "timestamp": round(time.time(), 3),
            }
        packet = self._twin_protocol.create_sync_packet(peer_id=peer_id, state=state)
        return {"ok": True, "packet": packet}

    def ingest_twin_sync_packet(
        self,
        packet: Dict[str, Any],
        expected_sender: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self._twin_protocol:
            return {
                "ok": False,
                "error": "twin_protocol_unavailable",
                "reason": "unavailable",
            }

        ok, reason, state = self._twin_protocol.verify_sync_packet(
            payload=packet,
            expected_peer_id=self._twin_protocol.node_id,
            expected_sender=expected_sender,
        )
        if not ok:
            return {"ok": False, "reason": reason, "applied": {}}

        if self._zero_trust:
            safe_ok, safe_reason, safe_state = self._zero_trust.validate_twin_sync_state(state)
            if not safe_ok:
                return {
                    "ok": False,
                    "reason": f"zero_trust:{safe_reason}",
                    "applied": {},
                }
            state = safe_state

        applied: Dict[str, Any] = {}
        if self._collective_pulse and isinstance(state.get("collective_pulse"), dict):
            try:
                pulse = state["collective_pulse"]
                trust = float(pulse.get("avg_trust", 0.5))
                novelty = float(pulse.get("avg_novelty", 0.4))
                cohesion = float(pulse.get("avg_cohesion", 0.6))
                sender_id = str(packet.get("node_id") or "peer")
                online = bool(self._hybrid.is_online) if self._hybrid else False
                self._collective_pulse.ingest_peer_signal(
                    peer_id=sender_id,
                    trust=trust,
                    novelty=novelty,
                    cohesion=cohesion,
                    is_online=online,
                )
                applied["collective_peer_signal"] = True
            except Exception as exc:
                applied["collective_peer_signal"] = f"error:{exc}"

        return {"ok": True, "reason": reason, "applied": applied, "state": state}

    # ------------------------------------------------------------------
    # Phase 2 — Safe evolution gate
    # ------------------------------------------------------------------

    def _record_evolution_runtime_event(self, event_type: str, payload: Dict[str, Any]) -> bool:
        if self._evolution_gate is None:
            return False

        public_record_fn = getattr(self._evolution_gate, "record_runtime_event", None)
        if callable(public_record_fn):
            try:
                public_record = cast(Callable[[str, Dict[str, Any]], bool], public_record_fn)
                return bool(
                    public_record(
                        event_type,
                        dict(payload or {}),
                    )
                )
            except Exception as exc:
                logger.debug("EvolutionGate public runtime event logging failed: %s", exc)

        legacy_record_fn = getattr(self._evolution_gate, "_record_event", None)
        if callable(legacy_record_fn):
            try:
                legacy_record = cast(Callable[[str, Dict[str, Any]], None], legacy_record_fn)
                legacy_record(event_type, dict(payload or {}))
                return True
            except Exception as exc:
                logger.debug("EvolutionGate legacy runtime event logging failed: %s", exc)

        return False

    def register_stable_state(self, label: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        if not self._evolution_gate:
            return {"ok": False, "error": "evolution_gate_unavailable"}
        self._evolution_gate.register_stable_snapshot(label, snapshot)
        return {"ok": True, "label": label}

    def evaluate_evolution_candidate(
        self,
        candidate: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self._evolution_gate:
            return {"ok": False, "error": "evolution_gate_unavailable"}

        from src.brain_v2.engine.evolution_gate import CandidateEvidence, EvolutionCandidate

        cand = EvolutionCandidate.from_dict(candidate)
        ev = CandidateEvidence.from_dict(evidence)
        decision = self._evolution_gate.evaluate(cand, ev)
        return {"ok": True, "decision": decision.to_dict()}

    def sign_evolution_candidate(self, candidate: Dict[str, Any], key_id: str = "local") -> Dict[str, Any]:
        if not self._evolution_gate:
            return {"ok": False, "error": "evolution_gate_unavailable"}

        from src.brain_v2.engine.evolution_gate import EvolutionCandidate

        cand = EvolutionCandidate.from_dict(candidate)
        signature = self._evolution_gate.sign_candidate(cand, key_id=key_id)
        payload = cand.to_dict()
        payload["signature"] = signature
        return {"ok": True, "candidate": payload}

    def rollback_stable_state(self, target_label: Optional[str] = None) -> Dict[str, Any]:
        if not self._evolution_gate:
            return {"ok": False, "error": "evolution_gate_unavailable"}
        ok, payload = self._evolution_gate.rollback(target_label)
        payload["ok"] = ok
        return payload

    def evolution_audit_log(self, limit: int = 200) -> Dict[str, Any]:
        if not self._evolution_gate:
            return {"ok": False, "error": "evolution_gate_unavailable", "events": []}
        return {"ok": True, "events": self._evolution_gate.export_audit_log(limit=limit)}

    def create_evolution_manifest(
        self,
        candidate: Dict[str, Any],
        baseline_ref: str,
        out_path: Optional[str] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        if not self._evolution_gate:
            return {"ok": False, "error": "evolution_gate_unavailable"}

        from src.brain_v2.engine.evolution_gate import EvolutionCandidate
        from src.brain_v2.engine.evolution_manifest import build_signed_manifest, save_manifest

        cand = EvolutionCandidate.from_dict(candidate)
        manifest = build_signed_manifest(
            candidate=cand,
            gate=self._evolution_gate,
            baseline_ref=baseline_ref,
            notes=notes,
        )
        result: Dict[str, Any] = {"ok": True, "manifest": manifest}
        if out_path:
            result["manifest_path"] = save_manifest(manifest, out_path)
        return result

    def verify_evolution_manifest(self, manifest_path: str) -> Dict[str, Any]:
        if not self._evolution_gate:
            return {"ok": False, "error": "evolution_gate_unavailable"}

        from src.brain_v2.engine.evolution_manifest import load_manifest, verify_manifest

        manifest = load_manifest(manifest_path)
        valid, reason = verify_manifest(manifest, self._evolution_gate)
        return {
            "ok": valid,
            "reason": reason,
            "manifest": manifest,
        }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        twin_status: Optional[Dict[str, Any]] = (
            self.twin.status() if self.twin is not None else None
        )
        agentic_status: Optional[Dict[str, Any]] = None
        if self._agentic_rag is not None:
            try:
                agentic_status = {
                    "available": True,
                    "db_path": str(getattr(self._agentic_rag, "db_path", "")),
                    "procedural": self._agentic_rag.procedural_stats_snapshot(top_n=3),
                    "source_policies": dict(self._agentic_source_policy),
                    "policy_history": self._agentic_rag.policy_history_summary(window=8),
                }
            except Exception as exc:
                agentic_status = {
                    "available": True,
                    "db_path": str(getattr(self._agentic_rag, "db_path", "")),
                    "error": str(exc),
                }
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
            "twin_protocol": self._twin_protocol.status() if self._twin_protocol else None,
            "narrative":     self._narrative.status()     if self._narrative     else None,
            "collective_pulse": (
                self._collective_pulse.status()
                if self._collective_pulse is not None else None
            ),
            "agentic_rag":  agentic_status,
            "dynamic_moe":   self._dynamic_moe.status()   if self._dynamic_moe   else None,
            "activation_sparsity": (
                self._activation_sparsity.status()
                if self._activation_sparsity is not None else None
            ),
            "lingua":        self._lingua.status()        if self._lingua        else None,
            "jaya_ir":       self._jaya_ir_exec.status()  if self._jaya_ir_exec  else None,
            "evolution_gate": self._evolution_gate.status() if self._evolution_gate else None,
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
