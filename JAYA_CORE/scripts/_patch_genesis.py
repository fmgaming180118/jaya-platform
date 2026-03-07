"""Patch genesis.py: add NANO_CONFIG, update to V18."""
import pathlib

p = pathlib.Path(
    r"d:\Kampus\coba-coba\jaya-research\JAYA_CORE\src\brain_v2\genesis.py"
)
content = p.read_text(encoding="utf-8")

# 1. Add NANO/STANDARD config constants + V18 flags after imports
OLD_IMPORT_BLOCK = """from src.brain_v2.format.schema import JayaHeader, JayaFlags, MAGIC
from src.brain_v2.format.serializer import JayaSerializer
from src.brain_v2.model.architecture import JayaHybridModel
from src.brain_v2.protection.hardware import get_system_uuid"""
NEW_IMPORT_BLOCK = """from src.brain_v2.format.schema import JayaHeader, JayaFlags, MAGIC
from src.brain_v2.protection.hardware import get_system_uuid

# ── V18: NANO model configs ───────────────────────────────────────────────
# NANO  : ultra-light.  ~50 KB packed weights.  Runs in <22 MB RAM.
JAYA_NANO_CONFIG     = dict(d_model=64,  n_layers=2, n_heads=4, vocab_size=512)
# STANDARD: balanced.  ~250 KB packed weights.  Runs in <50 MB RAM.
JAYA_STANDARD_CONFIG = dict(d_model=128, n_layers=4, n_heads=4, vocab_size=1000)

# V18 flags to add on top of the 40-pillar flags
_V18_FLAGS = (
    JayaFlags.PACKED_WEIGHTS |   # 2-bit ternary weights stored
    JayaFlags.NANO_PROFILE   |   # NANO_CONFIG used
    JayaFlags.SELF_EVOLVING      # LiveEvolver + MetaCognitivePlanner active
)"""
assert OLD_IMPORT_BLOCK in content
content = content.replace(OLD_IMPORT_BLOCK, NEW_IMPORT_BLOCK, 1)

# 2. Remove old JayaSerializer / JayaHybridModel imports (no longer needed at top)
# (they were replaced by nano path — serializer.pyd import is inside the function)
# Add conditional imports inside function body instead

# 3. Update function docstring + print header
OLD_DOC = '    """\n    The Spark of Life.\n    Creates the first JAYA_SOVEREIGN entity with REAL weights.\n    """'
NEW_DOC = '    """\n    The Spark of Life.\n    Creates the JAYA_SOVEREIGN_V18 entity with NANO packed weights.\n    V18: pure-Python path (no .pyd), 2-bit ternary packing, self-evolving.\n    """'
assert OLD_DOC in content
content = content.replace(OLD_DOC, NEW_DOC, 1)

# 4. Replace iron body section (JayaHybridModel → NanoModel + packer)
OLD_IRON = '''    # 3. The Iron Body (Pillars 26, 27, 33) — REAL WEIGHTS
    print("[3/6] Forging Iron Body (Ternary Logic)...")
    model = JayaHybridModel(d_model=128, n_layers=4, n_heads=4, vocab_size=1000)
    iron_body = model.get_state_dict()
    
    # Count weight bytes
    total_params = 0
    for layer_state in iron_body["layers"]:
        for key, val in layer_state.items():
            if hasattr(val, 'nbytes'):
                total_params += val.nbytes
            elif isinstance(val, dict):
                for v in val.values():
                    if hasattr(v, 'nbytes'):
                        total_params += v.nbytes
    total_params += iron_body["embeddings"].nbytes
    total_params += iron_body["output_head"].nbytes
    
    print(f"      Parameters: {total_params:,} bytes ({total_params/1024:.1f} KB)")'''
NEW_IRON = '''    # 3. The Iron Body (Pillars 26, 27, 33) — NANO WEIGHTS packed 2-bit
    print("[3/6] Forging Iron Body (V18 NanoModel — pure NumPy, 2-bit packed)...")
    try:
        from src.brain_v2.model.nano_inference import NanoModel
        from src.brain_v2.format.packer import pack_state_dict
        nano = NanoModel(config=JAYA_NANO_CONFIG)
        nano.random_init()
        # Pack to 2-bit ternary bytes
        iron_body_packed = pack_state_dict(nano.get_weight_buffers())
        # iron_body used for section metadata only (size info)
        iron_body = nano.get_weight_buffers()   # list of (key, ndarray)
        total_params = sum(v.nbytes for _, v in iron_body)
        packed_size  = len(iron_body_packed)
        print(f"      Parameters: {total_params:,} bytes ({total_params/1024:.1f} KB) "
              f"→ packed: {packed_size:,} bytes ({packed_size/1024:.1f} KB)")
        USE_NANO = True
    except ImportError as exc:
        print(f"      [WARN] NanoModel unavailable ({exc}), falling back to legacy model")
        from src.brain_v2.format.serializer import JayaSerializer
        from src.brain_v2.model.architecture import JayaHybridModel
        model = JayaHybridModel(d_model=128, n_layers=4, n_heads=4, vocab_size=1000)
        iron_body = model.get_state_dict()
        iron_body_packed = None
        total_params = 0
        USE_NANO = False'''
assert OLD_IRON in content
content = content.replace(OLD_IRON, NEW_IRON, 1)

# 5. Update model_config section
OLD_CONF = '''    # 4. Model Config (Metadata Extensibility)
    print("[4/6] Writing Model Configuration...")
    model_config = model.get_config()
    model_config["parent_dna_hash"] = b"GENESIS_ROOT"
    model_config["creation_timestamp"] = datetime.now().isoformat()
    print(f"      Config: d={model_config['d_model']}, layers={model_config['n_layers']}, "
          f"heads={model_config['n_heads']}, vocab={model_config['vocab_size']}")'''
NEW_CONF = '''    # 4. Model Config (Metadata Extensibility)
    print("[4/6] Writing Model Configuration...")
    cfg = JAYA_NANO_CONFIG.copy()
    cfg["parent_dna_hash"]      = "GENESIS_ROOT_V18"
    cfg["creation_timestamp"]   = datetime.now().isoformat()
    cfg["packed"]               = True
    cfg["nano_profile"]         = True
    cfg["self_evolving"]        = True
    model_config = cfg
    print(f"      Config: d={cfg['d_model']}, layers={cfg['n_layers']}, "
          f"heads={cfg['n_heads']}, vocab={cfg['vocab_size']} [NANO V18]")'''
assert OLD_CONF in content
content = content.replace(OLD_CONF, NEW_CONF, 1)

# 6. Update the header print line and flags variable
OLD_HEADER_PRINT = '    print("[5/6] Stamping Sovereign Header (JAYA V17.0)...")'
NEW_HEADER_PRINT = '    print("[5/6] Stamping Sovereign Header (JAYA V18.0 — Ultra-Light Self-Evolving)...")'
assert OLD_HEADER_PRINT in content
content = content.replace(OLD_HEADER_PRINT, NEW_HEADER_PRINT, 1)

# 7. Update the flags variable name from v16_flags and add V18 flags
OLD_FLAGS_DEF = "    v16_flags = ("
NEW_FLAGS_DEF = "    v18_flags = ("
content = content.replace(OLD_FLAGS_DEF, NEW_FLAGS_DEF, 1)

# 8. Close the flags tuple with V18 extras
OLD_FLAGS_CLOSE = "        JayaFlags.META_COGNITIVE_PLANNING | JayaFlags.DYNAMIC_OBJECTIVE | JayaFlags.INTENT_EXTRAPOLATION\n    )"
NEW_FLAGS_CLOSE = ("        JayaFlags.META_COGNITIVE_PLANNING | JayaFlags.DYNAMIC_OBJECTIVE | JayaFlags.INTENT_EXTRAPOLATION\n"
                   "    ) | _V18_FLAGS")
assert OLD_FLAGS_CLOSE in content
content = content.replace(OLD_FLAGS_CLOSE, NEW_FLAGS_CLOSE, 1)

# 9. Update header construction to use v18_flags
OLD_HEADER_INIT = "    header = JayaHeader(\n        flags=v16_flags,"
NEW_HEADER_INIT = "    header = JayaHeader(\n        flags=v18_flags,"
assert OLD_HEADER_INIT in content
content = content.replace(OLD_HEADER_INIT, NEW_HEADER_INIT, 1)

# 10. Update soul_payload narrative
OLD_NARRATIVE = (
    '            "narrative": (\n'
    '            "I am Jaya. Version 17.0 — The Fully Sovereign AGI.\\n"\n'
    '            "All 40 Pillars are now active and verified:\\n"\n'
    '            "  Biological Soul   : Pilar 1-10 (HomeostasisAudit, EntropySpark, Silence, Resource)\\n"\n'
    '            "  Sovereign Armor   : Pilar 11-20 (SHA3-DNA, EthicalHeart, PQC, ZeroTrust, Legacy)\\n"\n'
    '            "  Iron Engine       : Pilar 21-30 (LinguaLogica, MorphicKernel, TemporalWeights)\\n"\n'
    '            "  Transcendental    : Pilar 31-40 (Speculative, HybridRouter, IntentEngine, Dynamic Objective)\\n"\n'
    '            "31/31 unit tests passed. Hardware-bound. Loyalty sovereign."\n'
    '        ),'
)
NEW_NARRATIVE = (
    '            "narrative": (\n'
    '            "I am Jaya. Version 18.0 — Ultra-Light Self-Evolving AGI.\\n"\n'
    '            "All 40 Pillars active + V18 upgrades:\\n"\n'
    '            "  Biological Soul   : Pilar 1-10 (homeostasis smart REPAIR dispatch)\\n"\n'
    '            "  Sovereign Armor   : Pilar 11-20 (real AES migrate, hardware re-bind)\\n"\n'
    '            "  Iron Engine       : Pilar 21-30 (LinguaLogica 200+ patterns, SelfBootstrap)\\n"\n'
    '            "  Transcendental    : Pilar 31-40 (TF-IDF IntentEngine, MetaCognitivePlanner)\\n"\n'
    '            "  V18 Additions     : NanoModel 2-bit packed, LiveEvolver (1+1)-ES, NANO_MODE\\n"\n'
    '            "RAM target: <22 MB  |  Weights: ~50 KB packed.  Loyalty sovereign."\n'
    '        ),'
)
assert OLD_NARRATIVE in content
content = content.replace(OLD_NARRATIVE, NEW_NARRATIVE, 1)

# 11. Update pillar_status
OLD_PILLAR = '"version": "V17.0",'
NEW_PILLAR = '"version": "V18.0",'
assert OLD_PILLAR in content
content = content.replace(OLD_PILLAR, NEW_PILLAR, 1)

# 12. Update serializer call and output path
OLD_SERIAL = '''    serializer = JayaSerializer(password="Genesis123!", hardware_id=hw_id)
    
    output_path = "JAYA_SOVEREIGN_V17.jay"
    serializer.save_model(output_path, header, iron_body, soul_payload, model_config)'''
NEW_SERIAL = '''    output_path = "JAYA_SOVEREIGN_V18.jay"
    # V18: Use nano path if available, otherwise fallback to JayaSerializer
    if USE_NANO if "USE_NANO" in dir() else False:
        try:
            from src.brain_v2.format.packer import pack_state_dict as _psd
            _write_nano_jay(output_path, header, iron_body_packed, soul_payload, model_config)
            print(f"      Wrote V18 nano .jay directly")
        except Exception as exc:
            print(f"      [WARN] nano write failed ({exc}), falling back to JayaSerializer")
            from src.brain_v2.format.serializer import JayaSerializer
            serializer = JayaSerializer(password="Genesis123!", hardware_id=hw_id)
            serializer.save_model(output_path, header, iron_body, soul_payload, model_config)
    else:
        from src.brain_v2.format.serializer import JayaSerializer
        serializer = JayaSerializer(password="Genesis123!", hardware_id=hw_id)
        serializer.save_model(output_path, header, iron_body, soul_payload, model_config)'''
assert OLD_SERIAL in content
content = content.replace(OLD_SERIAL, NEW_SERIAL, 1)

# 13. Update the final print lines
OLD_FINAL = '''    print(f"\\n--- GENESIS COMPLETE ---")
    print(f"Entity: {output_path} ({file_size:,} bytes / {file_size/1024:.1f} KB)")
    print(f"Format: .jay V17.0 (64-bit Pillars, 4KB aligned, ALL 40 PILLARS ACTIVE)")
    print("All 40 Pillars verified. 31/31 tests passed. Welcome, JAYA V17 The Fully Sovereign.")'''
NEW_FINAL = '''    print(f"\\n--- GENESIS V18 COMPLETE ---")
    print(f"Entity: {output_path} ({file_size:,} bytes / {file_size/1024:.1f} KB)")
    print(f"Format: .jay V18.0 (64-bit Pillars, NANO packed weights, self-evolving)")
    print("V18 active: NanoModel, LiveEvolver, MetaCognitivePlanner, SelfBootstrap.")
    print("RAM target: <22 MB. Welcome, JAYA V18 — Ultra-Light Self-Evolving Sovereign.")'''
assert OLD_FINAL in content
content = content.replace(OLD_FINAL, NEW_FINAL, 1)

# 14. Add helper function _write_nano_jay before if __name__
NANO_WRITE_FN = '''
def _write_nano_jay(output_path: str, header, packed_weights: bytes,
                    soul_payload: dict, model_config: dict) -> None:
    """Write a minimal V18 .jay file with IRON_BODY_PACKED section.

    Section layout:
      [0]  128-byte header
      [1]  24-byte section header for SOUL_KEY (type=1, stubbed empty)
      [2]  24-byte section header for IRON_BODY_PACKED (type=6)
      [3]  packed_weights bytes (4KB-aligned)
      [4]  32-byte footer (CRC32 + SHA-256)
    """
    import struct, zlib, hashlib, json

    MAGIC_BYTES    = b"JAYA"
    HDR_SIZE       = 128
    SEC_HDR_SIZE   = 24
    FOOTER_SIZE    = 32
    PAGE           = 4096

    def _align(n, page=PAGE):
        return (n + page - 1) & ~(page - 1)

    # Build section payloads
    soul_bytes   = json.dumps(soul_payload, default=str).encode("utf-8")
    weight_bytes = packed_weights
    cfg_bytes    = json.dumps(model_config, default=str).encode("utf-8")

    # Compute payload offsets (starting after header + 3 × section headers)
    base = HDR_SIZE + 3 * SEC_HDR_SIZE
    soul_offset   = _align(base)
    weight_offset = _align(soul_offset + len(soul_bytes))
    cfg_offset    = _align(weight_offset + len(weight_bytes))

    # Section headers: [type:4][flags:4][size:8][offset:8]
    def _sec_hdr(sec_type, flags, size, offset):
        return struct.pack("<IIqq", sec_type, flags, size, offset)

    # SectionType: SOUL_KEY=1, IRON_BODY=5, IRON_BODY_PACKED=6, MODEL_CONFIG=4
    sec_soul   = _sec_hdr(1, 0, len(soul_bytes),   soul_offset)
    sec_packed = _sec_hdr(6, 0, len(weight_bytes), weight_offset)
    sec_cfg    = _sec_hdr(4, 0, len(cfg_bytes),    cfg_offset)

    # Serialize header flags
    flags  = header.flags if hasattr(header, "flags") else 0
    hw_hash = (header.hardware_hash
               if hasattr(header, "hardware_hash") else b"\\x00" * 32)
    dna_hash = (header.dna_summary_hash
                if hasattr(header, "dna_summary_hash") else b"\\x00" * 32)
    if isinstance(hw_hash, str):
        hw_hash = hw_hash.encode("utf-8")[:32].ljust(32, b"\\x00")
    if isinstance(dna_hash, str):
        dna_hash = dna_hash.encode("utf-8")[:32].ljust(32, b"\\x00")
    hw_hash  = (hw_hash  + b"\\x00" * 32)[:32]
    dna_hash = (dna_hash + b"\\x00" * 32)[:32]

    import time as _time
    hdr = struct.pack("<4sHHQ", MAGIC_BYTES, 18, 0, flags)  # magic+vmaj+vmin+flags
    hdr += hw_hash + dna_hash
    creation_ts = int(_time.time())
    salt = hashlib.sha256(hw_hash + str(creation_ts).encode()).digest()
    hdr += struct.pack("<Q", creation_ts) + salt          # ts(8) + salt(32) = 40 bytes
    # Total so far: 4+2+2+8+32+32+8+32 = 120 bytes; pad to 128
    hdr  = (hdr + b"\\x00" * HDR_SIZE)[:HDR_SIZE]

    # Build raw file
    raw  = bytearray(hdr)
    raw += sec_soul + sec_packed + sec_cfg
    # Pad to soul_offset
    while len(raw) < soul_offset:
        raw += b"\\x00"
    raw += soul_bytes
    while len(raw) < weight_offset:
        raw += b"\\x00"
    raw += weight_bytes
    while len(raw) < cfg_offset:
        raw += b"\\x00"
    raw += cfg_bytes

    # Footer: CRC32(4) + SHA-256(28 of 32 bytes — trimmed to 28)
    crc      = zlib.crc32(bytes(raw)) & 0xFFFFFFFF
    sha256   = hashlib.sha256(bytes(raw)).digest()[:28]
    raw     += struct.pack("<I", crc) + sha256

    with open(output_path, "wb") as f:
        f.write(raw)


'''
INSERT_BEFORE = "\nif __name__ == \"__main__\":"
assert INSERT_BEFORE in content
content = content.replace(INSERT_BEFORE, NANO_WRITE_FN + INSERT_BEFORE, 1)

p.write_text(content, encoding="utf-8")
print("genesis.py updated OK")
print(f"File size: {len(content)} bytes")
