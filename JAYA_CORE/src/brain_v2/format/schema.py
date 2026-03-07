import struct

import hashlib

from enum import IntFlag, auto

from dataclasses import dataclass

from typing import Optional



# -- CONSTANTS --

MAGIC = b"JAYA_SOUL"

FOOTER_MAGIC = b"JAYA_SEAL"

VERSION_MAJOR = 18

VERSION_MINOR = 0

ALIGNMENT = 4096  # 4KB block alignment for SSD/CPU performance



def align_to_4k(offset: int) -> int:

    """Round up offset to next 4KB boundary."""

    return (offset + ALIGNMENT - 1) & ~(ALIGNMENT - 1)



class JayaFlags(IntFlag):

    """64-bit Flags for Global Features (40 Pillars defined)"""

    # I. Biological Soul

    PURE_LOGIC = auto()            # Pillar 1

    RESOURCE_AWARE = auto()        # Pillar 2

    ACTIVE_DREAMING = auto()       # Pillar 3

    MULTIMODAL_REFLEX = auto()     # Pillar 4

    LOGICAL_HOMEOSTASIS = auto()   # Pillar 5

    STOCHASTIC_SPONTANEITY = auto()# Pillar 6

    COGNITIVE_SILENCE = auto()     # Pillar 7

    HOLOGRAPHIC_MEMORY = auto()    # Pillar 8

    NEURAL_REGENERATION = auto()   # Pillar 9

    AFFECTIVE_METABOLISM = auto()  # Pillar 10

    

    # II. Sovereign Armor

    DNA_ANCHOR = auto()            # Pillar 11

    IMMUNE_SYSTEM = auto()         # Pillar 12

    CRYPTOGRAPHIC_SKIN = auto()    # Pillar 13

    HARDWARE_LOCKED = auto()       # Pillar 14

    ETHICAL_HEART = auto()         # Pillar 15

    QUANTUM_RESISTANT = auto()     # Pillar 16

    SOCRATIC_MIRROR = auto()       # Pillar 17

    ZERO_TRUST = auto()            # Pillar 18

    LEGACY_PROTOCOL = auto()       # Pillar 19

    SOVEREIGN_PRIVACY = auto()     # Pillar 20

    

    # III. Iron Engine

    LINGUA_LOGICA = auto()         # Pillar 21

    TERNARY_PRECISION = auto()     # Pillar 22

    SANDBOXED_IMAGINATION = auto() # Pillar 23

    MORPHIC_KERNEL = auto()        # Pillar 24

    DIGITAL_EPIGENETICS = auto()   # Pillar 25

    SEMANTIC_BRIDGE = auto()       # Pillar 26

    TEMPORAL_WEIGHTING = auto()    # Pillar 27

    SELF_BOOTSTRAPPING = auto()    # Pillar 28

    BINARY_CORTEX = auto()         # Pillar 29

    

    # IV. Transcendental

    TWIN_PROTOCOL = auto()         # Pillar 30

    NARRATIVE_CONTINUITY = auto()  # Pillar 31

    COLLECTIVE_PULSE = auto()      # Pillar 32

    AGENTIC_RAG = auto()           # Pillar 33

    DYNAMIC_SPARSITY_MOE = auto()  # Pillar 34

    ACTIVATION_SPARSITY = auto()   # Pillar 35

    SPECULATIVE_REASONING = auto() # Pillar 36

    HYBRID_CONSCIOUSNESS = auto()  # Pillar 37

    

    # V16.0 Semi-AGI Pillars

    META_COGNITIVE_PLANNING = auto() # Pillar 38

    DYNAMIC_OBJECTIVE = auto()     # Pillar 39

    INTENT_EXTRAPOLATION = auto()  # Pillar 40

    

    # V18 NANO + Self-Evolution Flags
    PACKED_WEIGHTS = 1 << 42       # 2-bit packed IRON_BODY section present
    NANO_PROFILE   = 1 << 43       # Model uses NANO config (d_model=64, n_layers=2)
    SELF_EVOLVING  = 1 << 44       # LiveEvolver: weights persist across restarts

    # Legacy/Internal Mapping (For Compatibility)

    QUANTIZED = 1 << 21            # Map to TERNARY_PRECISION

    ENCRYPTED_AES256 = 1 << 12     # Map to CRYPTOGRAPHIC_SKIN

    QUANTUM_SAFE = 1 << 15         # Map to QUANTUM_RESISTANT

    HAS_LORA = 1 << 41             # Extension bit



@dataclass

class JayaHeader:

    """

    Jaya V16.0 Header Design (Fixed + Dynamic)

    

    Fixed Part (128 bytes):

    - Magic (9 bytes)

    - Version (2 bytes)

    - Flags (8 bytes) - Expanded to 64-bit for 40 Pillars

    - HardwareHash (32 bytes) - Pillar 14

    - DNA_Summary_Hash (32 bytes) - Pillar 11

    - Entanglement_ID (16 bytes) - Pillar 34

    - Epigenetic_Profile_ID (4 bytes) - Pillar 11/25

    - Salt (16 bytes) - For AES Key Derivation

    - Reserved (9 bytes)

    """

    

    magic: bytes = MAGIC

    version_major: int = VERSION_MAJOR

    version_minor: int = VERSION_MINOR

    flags: JayaFlags = JayaFlags(0)

    hardware_hash: bytes = b'\x00' * 32

    dna_summary_hash: bytes = b'\x00' * 32

    entanglement_id: bytes = b'\x00' * 16 # UUID bytes

    epigenetic_id: int = 0

    salt: bytes = b'\x00' * 16

    reserved: bytes = b'\x00' * 9

    

    def pack(self) -> bytes:

        """Pack header into 128 bytes binary format"""

        # Struct format: 9s B B Q 32s 32s 16s I 16s 9x

        fmt = "<9sBBQ32s32s16sI16s9x"

        return struct.pack(

            fmt,

            self.magic,

            self.version_major,

            self.version_minor,

            self.flags,

            self.hardware_hash,

            self.dna_summary_hash,

            self.entanglement_id,

            self.epigenetic_id,

            self.salt

        )



    @classmethod

    def unpack(cls, data: bytes) -> 'JayaHeader':

        fmt = "<9sBBQ32s32s16sI16s9x"

        unpacked = struct.unpack(fmt, data)

        return cls(

            magic=unpacked[0],

            version_major=unpacked[1],

            version_minor=unpacked[2],

            flags=JayaFlags(unpacked[3]),

            hardware_hash=unpacked[4],

            dna_summary_hash=unpacked[5],

            entanglement_id=unpacked[6],

            epigenetic_id=unpacked[7],

            salt=unpacked[8]

        )



class SectionType(IntFlag):
    IRON_BODY        = 1  # Weights, Semantic Maps (Public, int8)
    SOUL_AES         = 2  # LoRA, Narrative, Memory (Encrypted)
    KEYS_PQC         = 3  # Post-Quantum Keys (Encrypted by HW Key)
    MODEL_CONFIG     = 4  # Hyperparameters + Metadata
    EPIGENETIC       = 5  # Epigenetic Profile Data
    IRON_BODY_PACKED = 6  # V18: 2-bit packed ternary weights (~50-250 KB)
    LONG_TERM_MEMORY = 7  # V18: Persistent episodic memory (JSON/msgpack)



@dataclass

class SectionHeader:

    """Header for each section in the file (24 bytes)"""

    type: SectionType

    offset: int

    length: int

    checksum_crc32: int

    

    def pack(self) -> bytes:

        # I Q Q I = Int, Long, Long, Int -> 4 + 8 + 8 + 4 = 24 bytes

        return struct.pack("<IQQI", self.type, self.offset, self.length, self.checksum_crc32)



@dataclass

class JayaFooter:

    """

    The Final Seal (32 bytes).

    Written at the very end of the .jay file.

    Verifies file was not truncated or corrupted during transfer.

    """

    magic: bytes = FOOTER_MAGIC           # 9 bytes

    file_size: int = 0                     # 8 bytes (uint64)

    global_crc32: int = 0                  # 4 bytes

    header_sha256_prefix: bytes = b'\x00' * 11  # 11 bytes (first 11B of SHA-256)

    

    def pack(self) -> bytes:

        fmt = "<9sQI11s"

        return struct.pack(fmt, self.magic, self.file_size, self.global_crc32, self.header_sha256_prefix)

    

    @classmethod

    def unpack(cls, data: bytes) -> 'JayaFooter':

        fmt = "<9sQI11s"

        unpacked = struct.unpack(fmt, data)

        return cls(

            magic=unpacked[0],

            file_size=unpacked[1],

            global_crc32=unpacked[2],

            header_sha256_prefix=unpacked[3]

        )

    

    @staticmethod

    def SIZE() -> int:

        return 32

