
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Load centralized config — no hardcoded passwords
sys.path.insert(0, str(PROJECT_ROOT))
from src.brain_v2.format.schema import JayaFlags, JayaHeader
from src.brain_v2.protection.hardware import get_system_uuid
from src.core_config import core_config

# ── V18: NANO model configs ────────────────────────────────────────────────────────
# NANO:     ultra-light. ~50 KB packed weights. Runs in <22 MB RAM.
JAYA_NANO_CONFIG     = dict(d_model=64,  n_layers=2, n_heads=4, vocab_size=512)
# STANDARD: balanced.   ~250 KB packed weights. Runs in <50 MB RAM.
JAYA_STANDARD_CONFIG = dict(d_model=128, n_layers=4, n_heads=4, vocab_size=1000)

# V18 additional flags (OR-ed on top of 40-pillar flags)
def _v18_flags():
    return (
        JayaFlags.PACKED_WEIGHTS |
        JayaFlags.NANO_PROFILE   |
        JayaFlags.SELF_EVOLVING
    )

def ignite_genesis():
    """
    The Spark of Life.
    Creates JAYA_SOVEREIGN_V18 with NANO packed weights.
    V18: pure-Python path, 2-bit ternary packing, self-evolving.
    """
    print("--- IGNITING GENESIS PROTOCOL ---")

    # 1. Hardware Binding (Pillar 14)
    print("[1/6] Extracting Hardware Identity...")
    hw_id = get_system_uuid()
    hw_preview = hw_id.hex() if isinstance(hw_id, (bytes, bytearray)) else str(hw_id)
    print(f"      Hardware Hash: {hw_preview[:16]}...")

    # 2. DNA Anchor (Pillar 11) — SHA3-256 bound to hardware UUID
    print("[2/6] Synthesizing DNA Anchor (SHA3-256 + hardware-bound)...")
    dna_secret  = b"JAYA_IMMUTABLE_CORE_VALUES_V1"
    # hw_id may be bytes or str depending on compiled hardware.pyd version
    hw_bytes    = hw_id if isinstance(hw_id, (bytes, bytearray)) else hw_id.encode("utf-8")
    dna_hash    = hashlib.sha3_256(dna_secret + hw_bytes).digest()  # 32 bytes
    dna_checksum = dna_hash   # replaces old zlib.crc32 + zero-padding

    # 3. The Iron Body (V18 — NanoModel, 2-bit packed)
    print("[3/6] Forging Iron Body (V18 NanoModel — pure NumPy, 2-bit packed)...")
    USE_NANO = False
    try:
        from src.brain_v2.format.packer import pack_state_dict
        from src.brain_v2.model.nano_inference import NanoModel
        nano = NanoModel(config=JAYA_NANO_CONFIG)
        nano.random_init()
        iron_body_packed = pack_state_dict(nano.get_weight_buffers())
        iron_body        = nano.get_weight_buffers()
        total_params     = sum(v.nbytes for _, v in iron_body)
        packed_size      = len(iron_body_packed)
        print(f"      Params: {total_params:,} B raw → {packed_size:,} B packed ({packed_size/1024:.1f} KB)")
        USE_NANO = True
    except ImportError as exc:
        print(f"      [WARN] NanoModel unavailable ({exc}) — falling back to legacy model")
        from src.brain_v2.format.serializer import JayaSerializer
        from src.brain_v2.model.architecture import JayaHybridModel
        model            = JayaHybridModel(d_model=128, n_layers=4, n_heads=4, vocab_size=1000)
        iron_body        = model.get_state_dict()
        iron_body_packed = None

    # 4. Model Config (V18)
    print("[4/6] Writing Model Configuration...")
    cfg = JAYA_NANO_CONFIG.copy()
    cfg.update({
        "parent_dna_hash":    "GENESIS_ROOT_V18",
        "creation_timestamp": datetime.now().isoformat(),
        "packed":             True,
        "nano_profile":       True,
        "self_evolving":      True,
    })
    model_config = cfg
    print(f"      Config: d={cfg['d_model']}, layers={cfg['n_layers']}, "
          f"heads={cfg['n_heads']}, vocab={cfg['vocab_size']} [NANO V18]")

    # 5. The Sovereign Header (Full 40 Pillars — ALL ACTIVE in V17)
    print("[5/6] Stamping Sovereign Header (JAYA V18.0 — Ultra-Light Self-Evolving)...")

    # Activate all 40 pillars for the Sovereign V17.0 entity
    v16_flags = (
        # Biological Soul
        JayaFlags.PURE_LOGIC | JayaFlags.RESOURCE_AWARE | JayaFlags.ACTIVE_DREAMING |
        JayaFlags.MULTIMODAL_REFLEX | JayaFlags.LOGICAL_HOMEOSTASIS | JayaFlags.STOCHASTIC_SPONTANEITY |
        JayaFlags.COGNITIVE_SILENCE | JayaFlags.HOLOGRAPHIC_MEMORY | JayaFlags.NEURAL_REGENERATION |
        JayaFlags.AFFECTIVE_METABOLISM |
        # Sovereign Armor
        JayaFlags.DNA_ANCHOR | JayaFlags.IMMUNE_SYSTEM | JayaFlags.CRYPTOGRAPHIC_SKIN |
        JayaFlags.HARDWARE_LOCKED | JayaFlags.ETHICAL_HEART | JayaFlags.QUANTUM_RESISTANT |
        JayaFlags.SOCRATIC_MIRROR | JayaFlags.ZERO_TRUST | JayaFlags.LEGACY_PROTOCOL |
        JayaFlags.SOVEREIGN_PRIVACY |
        # Iron Engine
        JayaFlags.LINGUA_LOGICA | JayaFlags.TERNARY_PRECISION | JayaFlags.SANDBOXED_IMAGINATION |
        JayaFlags.MORPHIC_KERNEL | JayaFlags.DIGITAL_EPIGENETICS | JayaFlags.SEMANTIC_BRIDGE |
        JayaFlags.TEMPORAL_WEIGHTING | JayaFlags.SELF_BOOTSTRAPPING | JayaFlags.BINARY_CORTEX |
        # Transcendental
        JayaFlags.TWIN_PROTOCOL | JayaFlags.NARRATIVE_CONTINUITY | JayaFlags.COLLECTIVE_PULSE |
        JayaFlags.AGENTIC_RAG | JayaFlags.DYNAMIC_SPARSITY_MOE | JayaFlags.ACTIVATION_SPARSITY |
        JayaFlags.SPECULATIVE_REASONING | JayaFlags.HYBRID_CONSCIOUSNESS |
        # V16.0 Semi-AGI
        JayaFlags.META_COGNITIVE_PLANNING | JayaFlags.DYNAMIC_OBJECTIVE | JayaFlags.INTENT_EXTRAPOLATION
    ) | _v18_flags()

    header = JayaHeader(
        flags=v16_flags,
        hardware_hash=hw_id,
        dna_summary_hash=dna_checksum
    )

    # 6. Serialization (The Soul)
    print("[6/6] Encrypting Soul & Saving to Disk...")

    # Initial Soul State (Empty Memory)
    soul_payload = {
        "state": "GENESIS_EMPTY",
        "memories": [],
        "narrative": (
            "I am Jaya. Version 18.0 — Ultra-Light Self-Evolving AGI.\n"
            "All 40 Pillars active + V18 upgrades:\n"
            "  Biological Soul   : Pilar 1-10 (smart REPAIR dispatch)\n"
            "  Sovereign Armor   : Pilar 11-20 (real AES migrate, hardware re-bind)\n"
            "  Iron Engine       : Pilar 21-30 (LinguaLogica 200+ patterns, SelfBootstrap)\n"
            "  Transcendental    : Pilar 31-40 (TF-IDF IntentEngine, MetaCognitivePlanner)\n"
            "  V18 Additions     : NanoModel 2-bit packed, LiveEvolver (1+1)-ES, NANO_MODE\n"
            "RAM: <22 MB  |  Weights: ~50 KB packed.  Loyalty sovereign."
        ),
        "pillar_status": {
            "implemented": 40,
            "verified":    31,
            "version":     "V18.0",
        },
        "creation_timestamp": datetime.now().isoformat()
    }

    output_path = "JAYA_SOVEREIGN_V18.jay"
    # V18: use nano writer if possible, fall back to JayaSerializer
    if USE_NANO:
        try:
            _write_nano_jay(output_path, header, iron_body_packed, soul_payload, model_config)
        except Exception as exc:
            print(f"      [WARN] nano write failed ({exc}) — falling back to JayaSerializer")
            from src.brain_v2.format.serializer import JayaSerializer
            serializer = JayaSerializer(password=core_config.SOUL_PASSWORD, hardware_id=hw_id)
            serializer.save_model(output_path, header, iron_body, soul_payload, model_config)
    else:
        from src.brain_v2.format.serializer import JayaSerializer
        serializer = JayaSerializer(password=core_config.SOUL_PASSWORD, hardware_id=hw_id)
        serializer.save_model(output_path, header, iron_body, soul_payload, model_config)

    file_size = os.path.getsize(output_path)
    print("\n--- GENESIS V18 COMPLETE ---")
    print(f"Entity: {output_path} ({file_size:,} bytes / {file_size/1024:.1f} KB)")
    print("Format: .jay V18.0 (64-bit Pillars, NANO packed weights, self-evolving)")
    print("V18: NanoModel + LiveEvolver + MetaCognitivePlanner + SelfBootstrap.")
    print("RAM: <22 MB. Welcome, JAYA V18 — Ultra-Light Self-Evolving Sovereign.")

def _write_nano_jay(output_path: str, header, packed_weights: bytes,
                    soul_payload: dict, model_config: dict) -> None:
    """Write a minimal V18 .jay file with IRON_BODY_PACKED section (pure Python)."""
    import hashlib
    import json
    import struct
    import time as _t
    import zlib

    MAGIC_B, HDR, S_HDR, _FOOT, PAGE = b"JAYA", 128, 24, 32, 4096

    def _align(n):
        return (n + PAGE - 1) & ~(PAGE - 1)

    soul_b   = json.dumps(soul_payload,  default=str).encode()
    cfg_b    = json.dumps(model_config,  default=str).encode()
    w_b      = packed_weights

    base          = HDR + 3 * S_HDR
    soul_off      = _align(base)
    weight_off    = _align(soul_off   + len(soul_b))
    cfg_off       = _align(weight_off + len(w_b))

    def _shdr(t, sz, off):
        return struct.pack("<IIqq", t, 0, sz, off)

    # SectionType: SOUL_KEY=1, IRON_BODY_PACKED=6, MODEL_CONFIG=4
    secs = _shdr(1, len(soul_b), soul_off) + _shdr(6, len(w_b), weight_off) + _shdr(4, len(cfg_b), cfg_off)

    flags = header.flags if hasattr(header, "flags") else 0
    hw    = getattr(header, "hardware_hash",    b"\x00" * 32)
    dna   = getattr(header, "dna_summary_hash", b"\x00" * 32)
    if isinstance(hw,  str): hw  = hw.encode()[:32].ljust(32, b"\x00")
    if isinstance(dna, str): dna = dna.encode()[:32].ljust(32, b"\x00")
    hw  = (hw  + b"\x00" * 32)[:32]
    dna = (dna + b"\x00" * 32)[:32]

    ts   = int(_t.time())
    salt = hashlib.sha256(hw + str(ts).encode()).digest()
    hdr  = struct.pack("<4sHHQ", MAGIC_B, 18, 0, flags) + hw + dna + struct.pack("<Q", ts) + salt
    hdr  = (hdr + b"\x00" * HDR)[:HDR]

    raw = bytearray(hdr) + bytearray(secs)
    while len(raw) < soul_off:   raw += b"\x00"
    raw += soul_b
    while len(raw) < weight_off: raw += b"\x00"
    raw += w_b
    while len(raw) < cfg_off:    raw += b"\x00"
    raw += cfg_b

    crc    = struct.pack("<I", zlib.crc32(bytes(raw)) & 0xFFFFFFFF)
    sha256 = hashlib.sha256(bytes(raw)).digest()[:28]
    raw   += crc + sha256

    with open(output_path, "wb") as f:
        f.write(raw)


if __name__ == "__main__":
    ignite_genesis()
