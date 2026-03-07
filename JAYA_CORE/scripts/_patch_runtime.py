"""Patch runtime.py: add NANO load path, wire MetaCognitivePlanner, SelfBootstrap, LiveEvolver."""
import pathlib

p = pathlib.Path(
    r"d:\Kampus\coba-coba\jaya-research\JAYA_CORE\src\brain_v2\engine\runtime.py"
)
content = p.read_text(encoding="utf-8")

# 1. Update module docstring
OLD_DOC_END = "The class intentionally stays lightweight: no heavy ML libraries are\n        imported at module level.  Features load lazily, keeping startup fast and\n        allowing JAYA to \"run in any condition.\"\n\"\"\""
NEW_DOC_END = """The class intentionally stays lightweight: no heavy ML libraries are
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
\"\"\""""
assert OLD_DOC_END in content
content = content.replace(OLD_DOC_END, NEW_DOC_END, 1)

# 2. Add NANO_MODE flag + new subsystem attributes to __init__
OLD_INIT_END = """        # Subsystems initialised during ignite()
        self._ethical_heart: Optional[Any] = None   # Pillar 15
        self._zero_trust:    Optional[Any] = None   # Pillar 18
        self._legacy:        Optional[Any] = None   # Pillar 19
        self._hybrid:        Optional[Any] = None   # Pillar 37
        self._speculative:   Optional[Any] = None   # Pillar 36
        self._intent:        Optional[Any] = None   # Pillar 40
        self._lingua:        Optional[Any] = None   # Pillar 21
        self._morphic:       Optional[Any] = None   # Pillar 24
        self._resource_mon:  Optional[Any] = None   # Pillar 2"""
NEW_INIT_END = """        # Subsystems initialised during ignite()
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
        self.NANO_MODE:        bool          = False   # True when pure-NumPy path
        self._nano_model:      Optional[Any] = None   # NanoModel instance
        self._meta_cognitive:  Optional[Any] = None   # Pillar 38 MetaCognitivePlanner
        self._self_bootstrap:  Optional[Any] = None   # Pillar 28 SelfBootstrap
        self._live_evolver:    Optional[Any] = None   # LiveEvolver for micro-evolution"""
assert OLD_INIT_END in content
content = content.replace(OLD_INIT_END, NEW_INIT_END, 1)

# 3. Add NANO model loading inside ignite() after is_awake = True
OLD_IGNITE_CHECK = """        # -- Model loading (stubbed; replace with real deserializer) --
        if os.path.exists(self.model_path):
            logger.info("Model file found: %s", self.model_path)
        else:
            logger.warning("Model file not found (%s) — proceeding in stub mode",
                           self.model_path)

        self.is_awake = True"""
NEW_IGNITE_CHECK = """        # -- Model loading: NANO path (V18) or stub --
        if os.path.exists(self.model_path):
            logger.info("Model file found: %s", self.model_path)
            self._try_load_nano_model()
        else:
            logger.warning("Model file not found (%s) — proceeding in stub mode",
                           self.model_path)

        self.is_awake = True"""
assert OLD_IGNITE_CHECK in content
content = content.replace(OLD_IGNITE_CHECK, NEW_IGNITE_CHECK, 1)

# 4. Add _try_load_nano_model method after _init_twin
NANO_LOAD_METHOD = '''
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
                logger.info("[V18] PACKED_WEIGHTS flag not set — using legacy model path")
                return

            from src.brain_v2.model.nano_inference import NanoModel, NANO_CONFIG, STANDARD_CONFIG
            from src.brain_v2.format.packer import unpack_state_dict
            NANO_PROFILE_BIT = 1 << 43

            cfg = NANO_CONFIG if (flags & NANO_PROFILE_BIT) else STANDARD_CONFIG
            model = NanoModel(config=cfg)

            # Find IRON_BODY_PACKED section (type = 6) and unpack
            try:
                section_offset = 128
                SECTION_HDR = 24
                FOOTER_SIZE = 32

                file_size = os.path.getsize(self.model_path)
                with open(self.model_path, "rb") as f:
                    raw = f.read()

                while section_offset + SECTION_HDR <= file_size - FOOTER_SIZE:
                    sec_type   = struct.unpack_from("<I", raw, section_offset)[0]
                    sec_size   = struct.unpack_from("<Q", raw, section_offset + 8)[0]
                    sec_off_pl = struct.unpack_from("<Q", raw, section_offset + 16)[0]
                    if sec_type == 6 and sec_size > 0:
                        payload = raw[sec_off_pl : sec_off_pl + sec_size]
                        state_dict = unpack_state_dict(payload)
                        model.set_state_dict(state_dict)
                        logger.info("[V18] NanoModel loaded from IRON_BODY_PACKED (%d bytes packed)", sec_size)
                        break
                    section_offset += SECTION_HDR
                else:
                    logger.info("[V18] IRON_BODY_PACKED section not found — using random-init NanoModel")
                    model.random_init()

            except Exception as exc:
                logger.warning("[V18] weight unpack failed (%s) — using random-init NanoModel", exc)
                model.random_init()

            self._nano_model = model
            self.NANO_MODE   = True
            logger.info("[V18] NANO_MODE=True | config=%s", cfg)

        except Exception as exc:
            logger.warning("[V18] NanoModel load failed (%s) — using legacy path", exc)

'''
assert "    def _init_twin(self):" in content
content = content.replace("    def _init_twin(self):", NANO_LOAD_METHOD + "    def _init_twin(self):", 1)

# 5. Wire MetaCognitivePlanner, SelfBootstrap, LiveEvolver in _init_intelligence
OLD_INIT_INTEL_END = """        try:
            from src.brain_v2.engine.morphic import MorphicKernel
            self._morphic = MorphicKernel(
                ethical_heart=self._ethical_heart,
            )
            logger.info("[Pillar 24] MorphicKernel ready")
        except ImportError as exc:
            logger.warning("MorphicKernel unavailable: %s", exc)"""
NEW_INIT_INTEL_END = """        try:
            from src.brain_v2.engine.morphic import MorphicKernel
            self._morphic = MorphicKernel(
                ethical_heart=self._ethical_heart,
            )
            logger.info("[Pillar 24] MorphicKernel ready")
        except ImportError as exc:
            logger.warning("MorphicKernel unavailable: %s", exc)

        # V18: MetaCognitivePlanner (Pillar 38) ─────────────────────────────
        try:
            from src.brain_v2.engine.meta_cognitive import MetaCognitivePlanner
            self._meta_cognitive = MetaCognitivePlanner(
                engine=self,
                morphic=self._morphic,
            )
            logger.info("[Pillar 38] MetaCognitivePlanner ready")
        except ImportError as exc:
            logger.warning("MetaCognitivePlanner unavailable: %s", exc)

        # V18: SelfBootstrap (Pillar 28) ────────────────────────────────────
        try:
            from src.brain_v2.engine.self_bootstrap import SelfBootstrap
            self._self_bootstrap = SelfBootstrap()
            logger.info("[Pillar 28] SelfBootstrap ready")
        except ImportError as exc:
            logger.warning("SelfBootstrap unavailable: %s", exc)

        # V18: LiveEvolver ───────────────────────────────────────────────────
        try:
            from src.brain_v2.education.live_evolver import LiveEvolver
            if self._nano_model is not None:
                self._live_evolver = LiveEvolver(engine=self, max_steps=200)
                logger.info("[V18] LiveEvolver ready (NANO_MODE=%s)", self.NANO_MODE)
        except ImportError as exc:
            logger.warning("LiveEvolver unavailable: %s", exc)"""
assert OLD_INIT_INTEL_END in content
content = content.replace(OLD_INIT_INTEL_END, NEW_INIT_INTEL_END, 1)

# 6. Wire meta_cognitive and self_bootstrap ticks in Magnum Cycle
OLD_CYCLE_LOOP = """                now = time.time()
                if (not self._silent
                        and now - last_dream >= self.config.dream_interval):
                    self.dream()
                    last_dream = now
                await asyncio.sleep(1.0)"""
NEW_CYCLE_LOOP = """                now = time.time()
                if (not self._silent
                        and now - last_dream >= self.config.dream_interval):
                    self.dream()
                    last_dream = now
                # V18: tick self-evolution subsystems every second
                if self.twin:
                    if self._meta_cognitive:
                        self._meta_cognitive.tick(self.twin)
                    if self._self_bootstrap:
                        self._self_bootstrap.tick(self.twin)
                await asyncio.sleep(1.0)"""
assert OLD_CYCLE_LOOP in content
content = content.replace(OLD_CYCLE_LOOP, NEW_CYCLE_LOOP, 1)

# 7. Signal activity to SelfBootstrap on real feedback
OLD_FEEDBACK_END = """        if self._intent and result.get("task"):
            self._intent.learn(str(result["task"]))"""
NEW_FEEDBACK_END = """        if self._intent and result.get("task"):
            self._intent.learn(str(result["task"]))
        # V18: signal real activity to prevent idle curriculum spam
        if self._self_bootstrap:
            self._self_bootstrap.signal_activity()"""
assert OLD_FEEDBACK_END in content
content = content.replace(OLD_FEEDBACK_END, NEW_FEEDBACK_END, 1)

# 8. Update status() to include V18 subsystems
OLD_STATUS_RETURN = """            "resource_mon":  self._resource_mon.status()  if self._resource_mon  else None,
        }"""
NEW_STATUS_RETURN = """            "resource_mon":   self._resource_mon.status()    if self._resource_mon    else None,
            # V18 additions
            "nano_mode":      self.NANO_MODE,
            "meta_cognitive": (self._meta_cognitive.status()
                               if hasattr(self._meta_cognitive, "status") else None),
            "self_bootstrap": (self._self_bootstrap.status()
                               if hasattr(self._self_bootstrap, "status") else None),
            "live_evolver":   (self._live_evolver.status()
                               if hasattr(self._live_evolver, "status") else None),
        }"""
assert OLD_STATUS_RETURN in content
content = content.replace(OLD_STATUS_RETURN, NEW_STATUS_RETURN, 1)

p.write_text(content, encoding="utf-8")
print("runtime.py updated OK")
print(f"File size: {len(content)} bytes")
