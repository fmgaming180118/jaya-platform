
import os
import json
import msgpack
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from typing import Any, Tuple

class SoulCrypto:
    """
    Pillar 7 (Partial): Soul Protection.
    Provides AES-256-GCM encryption for the .jay Binary Format.
    """
    
    def __init__(self, key: bytes = None):
        # In a real deployed binary, this key would be obfuscated or derived 
        # from hardware ID (Pillar 29). For now, we use a fixed key or generate one.
        # This key MUST be persistent to read back the file.
        self.key = key or b'JAYA_SOUL_KEY_V13_256BIT_SECRET!' 
        if len(self.key) != 32:
            print(f"DEBUG: Key len is {len(self.key)}")
            raise ValueError("Key must be 32 bytes for AES-256")

    def encrypt(self, data: Any) -> Tuple[bytes, bytes, bytes]:
        """
        Encrypts a Python object using MsgPack + AES-GCM.
        Returns: (nonce, ciphertext, tag)
        """
        # 1. Serialize to Binary (MsgPack)
        packed_data = msgpack.packb(data, use_bin_type=True)
        
        # 2. Encrypt (AES-GCM)
        cipher = AES.new(self.key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(packed_data)
        
        return cipher.nonce, ciphertext, tag

    def decrypt(self, nonce: bytes, ciphertext: bytes, tag: bytes) -> Any:
        """
        Decrypts AES-GCM ciphertext and unpacks MsgPack.
        """
        cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
        try:
            decrypted_data = cipher.decrypt_and_verify(ciphertext, tag)
            return msgpack.unpackb(decrypted_data, raw=False)
        except Exception as e:
            raise ValueError(f"Decryption failed (Tampered/Wrong Key): {e}")

    @staticmethod
    def generate_key() -> bytes:
        return get_random_bytes(32)

    def derive_key(self, password: str, hardware_id: bytes, salt: bytes = None) -> Tuple[bytes, bytes]:
        """
        Derives a 32-byte AES key from password + hardware_id + salt.
        Returns: (derived_key, salt)
        """
        from Crypto.Protocol.KDF import PBKDF2
        from Crypto.Hash import SHA256
        
        if salt is None:
            salt = get_random_bytes(16)
            
        # Combine static pass + hw_id for unique per-device key
        pass_bytes = password.encode() + hardware_id
        
        key = PBKDF2(pass_bytes, salt, dkLen=32, count=100000, hmac_hash_module=SHA256)
        return key, salt
