
"""Explicit prototype artifact generator.

STATUS: PROTOTYPE
BELUM PRODUCTION

Generated weights are random training fixtures and are deliberately rejected by
the production artifact loader. The command requires explicit prototype opt-in,
an injected DNA secret, and an explicit output path.
"""

import argparse
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
from jaya_core.brain_v2.format.schema import JayaFlags, JayaHeader
from jaya_core.brain_v2.protection.hardware import get_system_uuid
from jaya_core.core_config import core_config
from jaya_core.pillars.manifest import load_manifest
from jaya_core.pillars.models import PillarStatus

# ── V18: NANO model configs ────────────────────────────────────────────────────────
# Experimental dimensions; no production resource or quality claim is implied.
JAYA_NANO_CONFIG     = dict(d_model=64,  n_layers=2, n_heads=4, vocab_size=512)
JAYA_STANDARD_CONFIG = dict(d_model=128, n_layers=4, n_heads=4, vocab_size=1000)

# V18 additional flags (OR-ed on top of 40-pillar flags)
def _v18_flags():
    return (
        JayaFlags.PACKED_WEIGHTS |
        JayaFlags.NANO_PROFILE
    )


_ACTIVE_PILLAR_STATES = frozenset(
    {
        PillarStatus.IMPLEMENTED_LOCAL,
        PillarStatus.INTEGRATED,
        PillarStatus.VERIFIED,
        PillarStatus.PRODUCTION,
    }
)


def _implemented_pillar_flags() -> tuple[JayaFlags, int]:
    manifest_path = Path(__file__).resolve().parents[1] / "contracts" / "40_pillars.yaml"
    flags = JayaFlags(0)
    count = 0
    for pillar in load_manifest(manifest_path):
        if pillar.initial_status not in _ACTIVE_PILLAR_STATES or pillar.source_flag is None:
            continue
        flag_name = pillar.source_flag.removeprefix("JayaFlags.")
        flag = getattr(JayaFlags, flag_name, None)
        if flag is None:
            raise RuntimeError(f"pillar manifest references unknown flag: {flag_name}")
        flags |= flag
        count += 1
    return flags, count


def ignite_genesis(
    output_path: str | Path,
    *,
    dna_secret: bytes | None = None,
    allow_prototype: bool = False,
) -> Path:
    """
    The Spark of Life.
    Creates JAYA_SOVEREIGN_V18 with NANO packed weights.
    V18: pure-Python path, 2-bit ternary packing, self-evolving.
    """
    if allow_prototype is not True:
        raise RuntimeError("prototype genesis requires explicit allow_prototype=True")
    injected_secret = dna_secret
    if injected_secret is None:
        injected_secret = os.getenv("JAYA_DNA_ANCHOR_SECRET", "").encode("utf-8")
    if not isinstance(injected_secret, bytes) or len(injected_secret) < 32:
        raise RuntimeError("JAYA_DNA_ANCHOR_SECRET must contain at least 32 bytes")
    target_path = Path(output_path).expanduser().resolve()
    if target_path.exists():
        raise FileExistsError("prototype genesis refuses to overwrite an existing artifact")
    target_path.parent.mkdir(parents=True, exist_ok=True)

    print("--- IGNITING EXPLICIT PROTOTYPE GENESIS ---")

    # 1. Hardware Binding (Pillar 14)
    print("[1/6] Extracting Hardware Identity...")
    hw_id = get_system_uuid()
    hw_preview = hw_id.hex() if isinstance(hw_id, (bytes, bytearray)) else str(hw_id)
    print(f"      Hardware Hash: {hw_preview[:16]}...")

    # 2. DNA Anchor (Pillar 11) — SHA3-256 bound to hardware UUID
    print("[2/6] Synthesizing DNA Anchor (SHA3-256 + hardware-bound)...")
    # hw_id may be bytes or str depending on compiled hardware.pyd version
    hw_bytes    = hw_id if isinstance(hw_id, (bytes, bytearray)) else hw_id.encode("utf-8")
    dna_hash    = hashlib.sha3_256(injected_secret + hw_bytes).digest()  # 32 bytes
    dna_checksum = dna_hash   # replaces old zlib.crc32 + zero-padding

    # 3. The Iron Body (V18 — NanoModel, 2-bit packed)
    print("[3/6] Forging Iron Body (V18 NanoModel — pure NumPy, 2-bit packed)...")
    USE_NANO = False
    try:
        from jaya_core.brain_v2.format.packer import pack_state_dict
        from jaya_core.brain_v2.model.nano_inference import NanoModel
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
        from jaya_core.brain_v2.format.serializer import JayaSerializer
        from jaya_core.brain_v2.model.architecture import JayaHybridModel
        model            = JayaHybridModel(d_model=128, n_layers=4, n_heads=4, vocab_size=1000)
        iron_body        = model.get_state_dict()
        iron_body_packed = None

    # 4. Model Config (V18)
    print("[4/6] Writing Model Configuration...")
    cfg = JAYA_NANO_CONFIG.copy()
    cfg.update({
        "parent_dna_hash":    dna_hash.hex(),
        "creation_timestamp": datetime.now().isoformat(),
        "packed":             True,
        "nano_profile":       True,
        "self_evolving":      False,
        "weight_origin":      "random_prototype",
    })
    model_config = cfg
    print(f"      Config: d={cfg['d_model']}, layers={cfg['n_layers']}, "
          f"heads={cfg['n_heads']}, vocab={cfg['vocab_size']} [NANO V18]")

    # 5. The header reflects the canonical registry instead of claiming all
    # declared pillars are active.
    print("[5/6] Stamping prototype header from canonical pillar registry...")
    implemented_flags, implemented_count = _implemented_pillar_flags()
    v16_flags = implemented_flags | _v18_flags()

    header = JayaHeader(
        flags=v16_flags,
        hardware_hash=hw_id,
        dna_summary_hash=dna_checksum
    )

    # 6. Serialization (The Soul)
    print("[6/6] Encrypting Soul & Saving to Disk...")

    # Initial Soul State (Empty Memory)
    soul_payload = {
        "state": "PROTOTYPE_GENESIS_EMPTY",
        "memories": [],
        "narrative": (
            "Explicit JAYA prototype artifact. Random weights are not a trained "
            "model and are rejected by the production readiness contract."
        ),
        "pillar_status": {
            "declared_enabled": implemented_count,
            "version":     "V18.0",
        },
        "creation_timestamp": datetime.now().isoformat()
    }

    # V18: use nano writer if possible, fall back to JayaSerializer
    if USE_NANO:
        try:
            _write_nano_jay(str(target_path), header, iron_body_packed, soul_payload, model_config)
        except Exception as exc:
            print(f"      [WARN] nano write failed ({exc}) — falling back to JayaSerializer")
            from jaya_core.brain_v2.format.serializer import JayaSerializer
            serializer = JayaSerializer(password=core_config.SOUL_PASSWORD, hardware_id=hw_id)
            serializer.save_model(str(target_path), header, iron_body, soul_payload, model_config)
    else:
        from jaya_core.brain_v2.format.serializer import JayaSerializer
        serializer = JayaSerializer(password=core_config.SOUL_PASSWORD, hardware_id=hw_id)
        serializer.save_model(str(target_path), header, iron_body, soul_payload, model_config)

    file_size = target_path.stat().st_size
    print("\n--- PROTOTYPE GENESIS COMPLETE ---")
    print(f"Artifact: {target_path} ({file_size:,} bytes / {file_size/1024:.1f} KB)")
    print("Format: .jay V18.0 prototype (registry-derived flags, packed random weights)")
    print("STATUS: PROTOTYPE — random weights, not production-ready.")
    return target_path

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
    parser = argparse.ArgumentParser(description="Create an explicit prototype .jay artifact")
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-prototype", action="store_true")
    cli_args = parser.parse_args()
    ignite_genesis(cli_args.output, allow_prototype=cli_args.allow_prototype)
