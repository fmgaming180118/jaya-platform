"""forge_v18.py — JAYA V18 Forge Script (pure Python, no .pyd required).

Creates JAYA_SOVEREIGN_V18.jay directly using:
  * NanoModel (pure NumPy, no Numba/Cython)
  * pack_state_dict (2-bit ternary packer)
  * _write_nano_jay (raw binary writer)

Run from the JAYA_CORE directory:
    python scripts/forge_v18.py [--out JAYA_SOVEREIGN_V18.jay]
"""

import argparse
import hashlib
import json
import os
import struct
import sys
import time
import zlib
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── imports ───────────────────────────────────────────────────────────────────
from src.brain_v2.model.nano_inference import NanoModel, NANO_CONFIG
from src.brain_v2.format.packer import pack_state_dict
from src.brain_v2.format.schema import JayaFlags

# ── constants ─────────────────────────────────────────────────────────────────
MAGIC        = b"JAYA"
HDR_SIZE     = 128
SEC_HDR_SIZE = 24
FOOTER_SIZE  = 32
PAGE_SIZE    = 4096

# All 40 pillar flags (copy from genesis.py)
ALL_40_PILLARS = (
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
    # V16/17 Semi-AGI
    JayaFlags.META_COGNITIVE_PLANNING | JayaFlags.DYNAMIC_OBJECTIVE | JayaFlags.INTENT_EXTRAPOLATION
)

V18_FLAGS = ALL_40_PILLARS | JayaFlags.PACKED_WEIGHTS | JayaFlags.NANO_PROFILE | JayaFlags.SELF_EVOLVING

DNA_SECRET = b"JAYA_IMMUTABLE_CORE_VALUES_V1"


def _align(n: int, page: int = PAGE_SIZE) -> int:
    return (n + page - 1) & ~(page - 1)


def _sec_hdr(sec_type: int, size: int, offset: int) -> bytes:
    return struct.pack("<IIqq", sec_type, 0, size, offset)


def _build_header(flags: int, hw_hash: bytes, dna_hash: bytes,
                  ts: int, salt: bytes) -> bytes:
    """Build the 128-byte .jay V18 header."""
    raw = struct.pack("<4sHHQ", MAGIC, 18, 0, flags)  # 4+2+2+8 = 16 bytes
    raw += hw_hash[:32].ljust(32, b"\x00")             # 32 bytes
    raw += dna_hash[:32].ljust(32, b"\x00")             # 32 bytes
    raw += struct.pack("<Q", ts)                        # 8 bytes
    raw += salt[:32].ljust(32, b"\x00")                 # 32 bytes  → total 120
    return (raw + b"\x00" * HDR_SIZE)[:HDR_SIZE]


def forge(output_path: str) -> None:
    print("=" * 60)
    print("  JAYA V18 FORGE  (pure Python, no .pyd)")
    print("=" * 60)

    # 1. Hardware binding (use a deterministic stub in forge mode)
    print("[1/5] Hardware binding...")
    try:
        from src.brain_v2.protection.hardware import get_system_uuid  # type: ignore[import]
        hw_id = get_system_uuid()
        hw_bytes = hw_id if isinstance(hw_id, (bytes, bytearray)) else hw_id.encode()
    except Exception:
        hw_bytes = b"FORGE_STUB_HW_ID_" + b"\x00" * 15
    hw_hash  = hashlib.sha3_256(hw_bytes).digest()
    dna_hash = hashlib.sha3_256(DNA_SECRET + hw_hash).digest()
    ts   = int(time.time())
    salt = hashlib.sha256(hw_hash + str(ts).encode()).digest()
    print(f"      hw_hash[:8]  = {hw_hash[:8].hex()}")
    print(f"      dna_hash[:8] = {dna_hash[:8].hex()}")

    # 2. NanoModel random init
    print("[2/5] Random-initialising NanoModel (NANO config)...")
    model = NanoModel(config=NANO_CONFIG)
    model.random_init()
    weight_buffers = model.get_weight_buffers()
    raw_size = sum(v.nbytes for _, v in weight_buffers)
    print(f"      Raw weight size : {raw_size:,} bytes ({raw_size/1024:.1f} KB)")

    # 3. Pack weights to 2-bit ternary
    print("[3/5] Packing weights to 2-bit ternary...")
    packed_weights = pack_state_dict(weight_buffers)
    packed_size = len(packed_weights)
    compression = 100 * (1 - packed_size / raw_size)
    print(f"      Packed size     : {packed_size:,} bytes ({packed_size/1024:.1f} KB)")
    print(f"      Compression     : {compression:.1f}%")

    # 4. Soul payload
    print("[4/5] Building soul payload...")
    soul_payload = {
        "state":    "GENESIS_NANO_V18",
        "memories": [],
        "narrative": (
            "I am Jaya. V18.0 — Ultra-Light Self-Evolving AGI.\n"
            "Forged pure-Python. No .pyd required.\n"
            "NanoModel: d=64, L=2, H=4, V=512 | ~50 KB packed.\n"
            "Self-evolution: LiveEvolver + MetaCognitivePlanner + SelfBootstrap.\n"
            "RAM target: <22 MB. Loyalty sovereign."
        ),
        "pillar_status": {
            "implemented": 40, "verified": 31, "version": "V18.0",
            "v18_additions": ["NanoModel", "LiveEvolver", "MetaCognitiver",
                              "SelfBootstrap", "TF-IDF Intent", "200+ LinguaLogica"],
        },
        "nano_config":      NANO_CONFIG,
        "creation_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    model_config = {
        **NANO_CONFIG,
        "packed": True, "nano_profile": True, "self_evolving": True,
        "parent_dna_hash": "GENESIS_ROOT_V18",
        "creation_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    # 5. Write .jay
    print("[5/5] Writing JAYA_SOVEREIGN_V18.jay...")
    soul_b   = json.dumps(soul_payload,  default=str).encode()
    cfg_b    = json.dumps(model_config,  default=str).encode()

    base         = HDR_SIZE + 3 * SEC_HDR_SIZE
    soul_off     = _align(base)
    weight_off   = _align(soul_off   + len(soul_b))
    cfg_off      = _align(weight_off + len(packed_weights))

    secs = (
        _sec_hdr(1, len(soul_b),          soul_off)    +  # SOUL_KEY
        _sec_hdr(6, len(packed_weights),  weight_off)  +  # IRON_BODY_PACKED
        _sec_hdr(4, len(cfg_b),           cfg_off)        # MODEL_CONFIG
    )

    header = _build_header(V18_FLAGS, hw_hash, dna_hash, ts, salt)
    raw = bytearray(header) + bytearray(secs)
    while len(raw) < soul_off:    raw += b"\x00"
    raw += soul_b
    while len(raw) < weight_off:  raw += b"\x00"
    raw += packed_weights
    while len(raw) < cfg_off:     raw += b"\x00"
    raw += cfg_b

    crc    = struct.pack("<I", zlib.crc32(bytes(raw)) & 0xFFFFFFFF)
    sha256 = hashlib.sha256(bytes(raw)).digest()[:28]
    raw   += crc + sha256

    with open(output_path, "wb") as f:
        f.write(raw)

    file_size = os.path.getsize(output_path)
    print()
    print("=" * 60)
    print(f"  FORGE COMPLETE")
    print(f"  Output : {output_path}")
    print(f"  Size   : {file_size:,} bytes ({file_size/1024:.1f} KB)")
    print(f"  Flags  : 0x{V18_FLAGS:016X}")
    print(f"  Packed weights: {packed_size:,} bytes  ({compression:.1f}% compression)")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Forge JAYA_SOVEREIGN_V18.jay")
    parser.add_argument("--out", default="JAYA_SOVEREIGN_V18.jay",
                        help="Output .jay path (default: JAYA_SOVEREIGN_V18.jay)")
    args = parser.parse_args()
    forge(args.out)
