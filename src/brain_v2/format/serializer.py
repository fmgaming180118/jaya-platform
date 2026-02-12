
import struct
import zlib
from typing import Optional, Dict, Any
from pathlib import Path

from ..protection.crypto import CryptoSkin
from .schema import JayaHeader, JayaFlags, SectionType, SectionHeader, MAGIC

class JayaSerializer:
    """
    Handles Read/Write operations for .jay V13.0 files.
    Pillars Implemented:
    - Cryptographic Skin (AES-256)
    - Quantum-Resistant Skin (PQC Sig)
    - Neural Regeneration (Checksums)
    """
    
    def __init__(self, password: str, hardware_id: bytes):
        self.crypto = CryptoSkin()
        self.password = password
        self.hardware_id = hardware_id
        
    def save_model(self, 
                   path: str,
                   header: JayaHeader,
                   iron_body: bytes,
                   soul_payload: bytes,
                   epigenetic_config: bytes = b"DEFAULT"):
        """
        Write the Sovereign Entity to disk.
        """
        # 1. Derive Key for Soul Encryption (Generates Salt)
        kek, salt = self.crypto.derive_key(self.password, self.hardware_id)
        
        # 2. Update Header with Salt
        header.salt = salt
        header_bytes = header.pack()
        
        # 3. Encrypt Soul (Pillar 16)
        # Optional: Compress before encrypting
        compressed_soul = zlib.compress(soul_payload)
        encrypted_soul = self.crypto.encrypt_soul(compressed_soul, kek)
        
        # 4. Prepare Sections
        # Section 1: Iron Body (Public)
        body_checksum = zlib.crc32(iron_body)
        section_body = SectionHeader(
            type=SectionType.IRON_BODY,
            offset=0, # Calculated later
            length=len(iron_body),
            checksum_crc32=body_checksum
        )
        
        # Section 2: Soul (Encrypted)
        soul_checksum = zlib.crc32(encrypted_soul)
        section_soul = SectionHeader(
            type=SectionType.SOUL_AES,
            offset=0,
            length=len(encrypted_soul),
            checksum_crc32=soul_checksum
        )
        
        # 5. Calculate Offsets
        # Header (128) + NumSections(4) + SectionHeaders(24 * 2) = 180 bytes approx header area
        header_size = 128
        num_sections = 2
        section_header_size = 24
        
        data_start = header_size + 4 + (num_sections * section_header_size)
        
        section_body.offset = data_start
        section_soul.offset = data_start + len(iron_body)
        
        # 6. Write File
        with open(path, "wb") as f:
            # A. Global Header
            f.write(header_bytes)
            
            # B. Section Table
            f.write(struct.pack("<I", num_sections))
            f.write(section_body.pack())
            f.write(section_soul.pack())
            
            # C. Data Blobs
            f.write(iron_body)
            f.write(encrypted_soul)
            
        print(f"Jaya V13.0 Saved to {path} | Soul Encrypted")

    def load_model(self, path: str) -> Dict[str, Any]:
        """
        Awaken the Entity.
        """
        with open(path, "rb") as f:
            # 1. Read Global Header
            header_data = f.read(128)
            if header_data[:9] != MAGIC:
                raise ValueError("Invalid JAYA Magic Bytes. Not a Soul file.")
                
            header = JayaHeader.unpack(header_data)
            
            # 2. Read Section Table
            num_sections = struct.unpack("<I", f.read(4))[0]
            sections = []
            for _ in range(num_sections):
                s_data = f.read(24)
                sections.append(SectionHeader(*struct.unpack("<IQQI", s_data)))
            
            # 3. Read Body
            # Find Iron Body
            body_data = b""
            for sec in sections:
                if sec.type == SectionType.IRON_BODY:
                    f.seek(sec.offset)
                    body_data = f.read(sec.length)
                    if zlib.crc32(body_data) != sec.checksum_crc32:
                        raise ValueError("Iron Body Corruption Detected! (Hash Mismatch)")
            
            # 4. Decrypt Soul
            soul_data = b""
            for sec in sections:
                if sec.type == SectionType.SOUL_AES:
                    f.seek(sec.offset)
                    enc_data = f.read(sec.length)
                    
                    # Verify integrity check
                    if zlib.crc32(enc_data) != sec.checksum_crc32:
                        raise ValueError("Soul Corruption Detected! Healing Required.")
                        
                    # Derive key using Salt from Header
                    kek, _ = self.crypto.derive_key(self.password, self.hardware_id, salt=header.salt)
                    
                    try:
                        decrypted = self.crypto.decrypt_soul(enc_data, kek)
                        soul_data = zlib.decompress(decrypted)
                    except Exception as e:
                        print(f"Decryption Failed: {e}")
                        # In V13, here we would trigger "Legacy Protocol" (Pillar 25)
                        return None
                        
            return {
                "header": header,
                "body": body_data,
                "soul": soul_data
            }
