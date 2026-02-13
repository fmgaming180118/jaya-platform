
import struct
import zlib
import hashlib
import mmap
import numpy as np
import msgpack
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from ..protection.soul_crypto import SoulCrypto
from .schema import (
    JayaHeader, JayaFlags, SectionType, SectionHeader, 
    JayaFooter, MAGIC, FOOTER_MAGIC, ALIGNMENT, align_to_4k
)

# ---- Numpy <-> MsgPack Helpers ----

def _serialize_numpy(arr: np.ndarray) -> dict:
    """Pack a numpy array into a msgpack-friendly dict."""
    return {
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
        "data": arr.tobytes()
    }

def _deserialize_numpy(d: dict) -> np.ndarray:
    """Reconstruct a numpy array from a msgpack dict."""
    return np.frombuffer(d["data"], dtype=np.dtype(d["dtype"])).reshape(d["shape"])

def _serialize_state_dict(state: dict) -> dict:
    """Recursively convert numpy arrays in a state dict for msgpack."""
    result = {}
    for key, val in state.items():
        if isinstance(val, np.ndarray):
            result[key] = _serialize_numpy(val)
        elif isinstance(val, dict):
            result[key] = _serialize_state_dict(val)
        elif isinstance(val, list):
            result[key] = [_serialize_state_dict(v) if isinstance(v, dict) else v for v in val]
        else:
            result[key] = val
    return result

def _deserialize_state_dict(state: dict) -> dict:
    """Recursively reconstruct numpy arrays in a state dict from msgpack."""
    result = {}
    for key, val in state.items():
        if isinstance(val, dict) and "shape" in val and "dtype" in val and "data" in val:
            result[key] = _deserialize_numpy(val)
        elif isinstance(val, dict):
            result[key] = _deserialize_state_dict(val)
        elif isinstance(val, list):
            result[key] = [_deserialize_state_dict(v) if isinstance(v, dict) else v for v in val]
        else:
            result[key] = val
    return result


class JayaSerializer:
    """
    Handles Read/Write operations for .jay V13.0 files.
    
    Features:
    - 4KB-aligned sections for mmap/SSD performance
    - MODEL_CONFIG section with metadata extensibility
    - Footer seal (CRC32 + SHA-256 prefix) for integrity
    - Numpy array serialization for real weights
    - AES-256-GCM encryption for Soul data
    """
    
    def __init__(self, password: str, hardware_id: bytes):
        self.crypto = SoulCrypto()
        self.password = password
        self.hardware_id = hardware_id
        
    def save_model(self, 
                   path: str,
                   header: JayaHeader,
                   iron_body: dict, 
                   soul_payload: Any,
                   model_config: dict = None):
        """
        Write the Sovereign Entity to disk (4KB-aligned, CRC-sealed).
        
        iron_body: dict of numpy arrays (real weights)
        soul_payload: dict of memories/state (will be encrypted)
        model_config: dict of hyperparameters + metadata
        """
        # 1. Derive Key
        kek, salt = self.crypto.derive_key(self.password, self.hardware_id)
        self.crypto.key = kek
        
        # 2. Update Header
        header.salt = salt
        header_bytes = header.pack()
        
        # 3. Serialize MODEL_CONFIG (MsgPack, unencrypted)
        if model_config is None:
            model_config = {"version": "13.0"}
        config_packed = msgpack.packb(model_config, use_bin_type=True)
        
        # 4. Serialize IRON_BODY (convert numpy arrays, then MsgPack)
        body_serializable = _serialize_state_dict(iron_body)
        body_packed = msgpack.packb(body_serializable, use_bin_type=True)
        
        # 5. Encrypt SOUL (MsgPack + AES-GCM)
        nonce, soul_cipher, soul_tag = self.crypto.encrypt(soul_payload)
        final_soul_blob = nonce + soul_tag + soul_cipher
        
        # 6. Calculate 4KB-aligned offsets
        header_size = 128
        num_sections = 3  # CONFIG + BODY + SOUL
        section_header_size = 24
        section_table_size = 4 + (num_sections * section_header_size)  # 4B count + headers
        
        # Config starts at first 4KB boundary after header+table
        config_offset = align_to_4k(header_size + section_table_size)
        # Body starts at next 4KB boundary after config
        body_offset = align_to_4k(config_offset + len(config_packed))
        # Soul starts at next 4KB boundary after body
        soul_offset = align_to_4k(body_offset + len(body_packed))
        
        # 7. Build Section Headers
        section_config = SectionHeader(
            type=SectionType.MODEL_CONFIG,
            offset=config_offset,
            length=len(config_packed),
            checksum_crc32=zlib.crc32(config_packed)
        )
        section_body = SectionHeader(
            type=SectionType.IRON_BODY,
            offset=body_offset,
            length=len(body_packed),
            checksum_crc32=zlib.crc32(body_packed)
        )
        section_soul = SectionHeader(
            type=SectionType.SOUL_AES,
            offset=soul_offset,
            length=len(final_soul_blob),
            checksum_crc32=zlib.crc32(final_soul_blob)
        )
        
        # 8. Write File
        with open(path, "wb") as f:
            # Header (128B)
            f.write(header_bytes)
            
            # Section Table
            f.write(struct.pack("<I", num_sections))
            f.write(section_config.pack())
            f.write(section_body.pack())
            f.write(section_soul.pack())
            
            # Pad to config offset
            current = f.tell()
            f.write(b'\x00' * (config_offset - current))
            
            # MODEL_CONFIG
            f.write(config_packed)
            
            # Pad to body offset
            current = f.tell()
            f.write(b'\x00' * (body_offset - current))
            
            # IRON_BODY
            f.write(body_packed)
            
            # Pad to soul offset
            current = f.tell()
            f.write(b'\x00' * (soul_offset - current))
            
            # SOUL_AES
            f.write(final_soul_blob)
            
        # 9. Footer (written separately — need to read file for CRC32)
        # Re-read all data for global CRC
        with open(path, "rb") as f:
            all_data = f.read()
        data_end = len(all_data)
        total_size = data_end + JayaFooter.SIZE()
        global_crc = zlib.crc32(all_data)
        
        # SHA-256 of header (first 11 bytes of digest)
        header_sha = hashlib.sha256(header_bytes).digest()[:11]
        
        footer = JayaFooter(
            file_size=total_size,
            global_crc32=global_crc,
            header_sha256_prefix=header_sha
        )
        
        # Append footer
        with open(path, "ab") as f:
            f.write(footer.pack())
            
        print(f"[FORMAT] .jay V13.0 saved: {path}")
        print(f"         Config: {len(config_packed)}B | Body: {len(body_packed)}B | Soul: {len(final_soul_blob)}B")
        print(f"         Alignment: 4KB | Footer: CRC32 sealed")

    def load_model(self, path: str) -> Dict[str, Any]:
        """
        Awaken the Entity from Binary.
        Full verification: Footer → Header → Sections → CRC32.
        """
        with open(path, "rb") as f:
            # ---- STEP 1: Read Footer (last 32 bytes) ----
            f.seek(0, 2)  # Seek to end
            file_size = f.tell()
            
            if file_size < 128 + JayaFooter.SIZE():
                raise ValueError("File too small to be a valid .jay")
            
            f.seek(file_size - JayaFooter.SIZE())
            footer = JayaFooter.unpack(f.read(JayaFooter.SIZE()))
            
            if footer.magic != FOOTER_MAGIC:
                raise ValueError("Invalid Footer: File may be truncated.")
            if footer.file_size != file_size:
                raise ValueError(f"Footer size mismatch: expected {footer.file_size}, got {file_size}")
            
            # Verify global CRC32 (everything except footer)
            f.seek(0)
            data_without_footer = f.read(file_size - JayaFooter.SIZE())
            if zlib.crc32(data_without_footer) != footer.global_crc32:
                raise ValueError("CRC32 mismatch: File is corrupted.")
            
            print("[LOAD] Footer Seal verified ✓")
            
            # ---- STEP 2: Read Header (128 bytes) ----
            f.seek(0)
            header_data = f.read(128)
            if header_data[:9] != MAGIC:
                raise ValueError("Invalid JAYA Magic Bytes.")
            
            # Verify header SHA-256 prefix
            header_sha = hashlib.sha256(header_data).digest()[:11]
            if header_sha != footer.header_sha256_prefix:
                raise ValueError("Header SHA-256 mismatch: Header tampered.")
            
            header = JayaHeader.unpack(header_data)
            print("[LOAD] Header Identity verified ✓")
            
            # ---- STEP 3: Derive Key ----
            kek, _ = self.crypto.derive_key(self.password, self.hardware_id, salt=header.salt)
            self.crypto.key = kek
            
            # ---- STEP 4: Read Section Table ----
            num_sections = struct.unpack("<I", f.read(4))[0]
            sections = []
            for _ in range(num_sections):
                sections.append(SectionHeader(*struct.unpack("<IQQI", f.read(24))))
            
            # ---- STEP 5: Load Sections ----
            config_data = {}
            body_data = {}
            soul_data = None
            
            for sec in sections:
                f.seek(sec.offset)
                blob = f.read(sec.length)
                
                # CRC32 per-section
                if zlib.crc32(blob) != sec.checksum_crc32:
                    raise ValueError(f"CRC32 mismatch in Section {sec.type}")
                
                if sec.type == SectionType.MODEL_CONFIG:
                    config_data = msgpack.unpackb(blob, raw=False)
                    print(f"[LOAD] MODEL_CONFIG loaded ✓ ({len(blob)}B)")
                    
                elif sec.type == SectionType.IRON_BODY:
                    raw_body = msgpack.unpackb(blob, raw=False)
                    body_data = _deserialize_state_dict(raw_body)
                    print(f"[LOAD] IRON_BODY loaded ✓ ({len(blob)}B)")
                    
                elif sec.type == SectionType.SOUL_AES:
                    nonce = blob[:16]
                    tag = blob[16:32]
                    ciphertext = blob[32:]
                    try:
                        soul_data = self.crypto.decrypt(nonce, ciphertext, tag)
                        print(f"[LOAD] SOUL decrypted ✓ ({len(blob)}B)")
                    except Exception as e:
                        print(f"[LOAD] Soul Decryption Failed: {e}")
                        return None
                        
            return {
                "header": header,
                "config": config_data,
                "body": body_data,
                "soul": soul_data
            }
