
import struct
import hashlib
from enum import IntFlag, auto
from dataclasses import dataclass
from typing import Optional

# -- CONSTANTS --
MAGIC = b"JAYA_SOUL"
FOOTER_MAGIC = b"JAYA_SEAL"
VERSION_MAJOR = 13
VERSION_MINOR = 0
ALIGNMENT = 4096  # 4KB block alignment for SSD/CPU performance

def align_to_4k(offset: int) -> int:
    """Round up offset to next 4KB boundary."""
    return (offset + ALIGNMENT - 1) & ~(ALIGNMENT - 1)

class JayaFlags(IntFlag):
    """32-bit Flags for Global Features (Pillars)"""
    QUANTIZED = auto()
    ENCRYPTED_AES256 = auto()    # Pillar 16
    HAS_DNA_ANCHOR = auto()      # Pillar 15
    QUANTUM_SAFE = auto()        # Pillar 18
    HARDWARE_LOCKED = auto()     # Pillar 19
    HAS_LORA = auto()
    HAS_HOLOGRAPHIC_MEM = auto() # Pillar 8
    HAS_ENTANGLEMENT = auto()    # Pillar 34

@dataclass
class JayaHeader:
    """
    Jaya V13.0 Header Design (Fixed + Dynamic)
    
    Fixed Part (128 bytes):
    - Magic (9 bytes)
    - Version (2 bytes)
    - Flags (4 bytes)
    - HardwareHash (32 bytes) - Pillar 19
    - DNA_Summary_Hash (32 bytes) - Pillar 15
    - Entanglement_ID (16 bytes) - Pillar 34
    - Epigenetic_Profile_ID (4 bytes) - Pillar 11
    - Salt (16 bytes) - For AES Key Derivation
    - Reserved (13 bytes)
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
    reserved: bytes = b'\x00' * 13
    
    def pack(self) -> bytes:
        """Pack header into 128 bytes binary format"""
        # Struct format: 9s B B I 32s 32s 16s I 16s 13x
        fmt = "<9sBBI32s32s16sI16s13x"
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
        fmt = "<9sBBI32s32s16sI16s13x"
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
    IRON_BODY = 1     # Weights, Semantic Maps (Public)
    SOUL_AES = 2      # LoRA, Narrative, Memory (Encrypted)
    KEYS_PQC = 3      # Post-Quantum Keys (Encrypted by HW Key)
    MODEL_CONFIG = 4  # Hyperparameters + Metadata
    EPIGENETIC = 5    # Epigenetic Profile Data

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
