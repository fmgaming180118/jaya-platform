
import os
import hashlib
import base64
from typing import Tuple, Optional

# Try importing critical security libraries
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    import argon2
    HAS_CRYPTO_LIB = True
except ImportError:
    HAS_CRYPTO_LIB = False
    print("WARNING: 'cryptography' or 'argon2-cffi' not found. Using simulation mode for Security Layer.")

class CryptoSkin:
    """
    Pillar 16 & 18: Cryptographic Skin & PQC Wrapper.
    Handles encryption/decryption of the 'Soul' section of .jay files.
    """
    
    def __init__(self):
        self.salt_size = 16
        self.nonce_size = 12
        self.key_size = 32 # AES-256

    def derive_key(self, password: str, hardware_id: bytes, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """
        Derive AES key from Password + HardwareID using Argon2id (or PBKDF2 fallback).
        Returns (key, salt).
        """
        if salt is None:
            salt = os.urandom(self.salt_size)
            
        payload = password.encode() + hardware_id
        
        if HAS_CRYPTO_LIB and 'argon2' in globals():
            # Use Argon2id if available (Memory-hard)
            ph = argon2.PasswordHasher(
                time_cost=2, 
                memory_cost=102400, # 100MB
                parallelism=2, 
                hash_len=self.key_size, 
                salt_len=self.salt_size,
                type=argon2.Type.ID
            )
            # Argon2 usually produces a string hash, here we'd use low-level api for raw bytes
            # For simplicity in this implementation plan, we failover to PBKDF2 or simulate
            # In a real impl, we would use argon2.low_level.hash_secret_raw
            try:
                key = argon2.low_level.hash_secret_raw(
                    secret=payload,
                    salt=salt,
                    time_cost=2,
                    memory_cost=102400,
                    parallelism=2,
                    hash_len=self.key_size,
                    type=argon2.Type.ID
                )
                return key, salt
            except Exception as e:
                print(f"Argon2 Error: {e}, falling back to PBKDF2")
        
        # Fallback: PBKDF2-HMAC-SHA256
        # This is standard if argon2 is missing or fails
        kdf = hashlib.pbkdf2_hmac(
            'sha256',
            payload,
            salt,
            100000, # Iterations
            dklen=self.key_size
        )
        return kdf, salt

    def encrypt_soul(self, data: bytes, key: bytes) -> bytes:
        """
        Encrypt data using AES-256-GCM.
        Prepend Nonce to output.
        """
        if not HAS_CRYPTO_LIB:
            # Simulation Mode: XOR or just Base64 (INSECURE - TEST ONLY)
            return b"SIMULATED_ENC:" + base64.b64encode(data)
            
        aesgcm = AESGCM(key)
        nonce = os.urandom(self.nonce_size)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    def decrypt_soul(self, blob: bytes, key: bytes) -> bytes:
        """
        Decrypt data using AES-256-GCM.
        Expects Nonce prepended.
        """
        if not HAS_CRYPTO_LIB:
            if blob.startswith(b"SIMULATED_ENC:"):
                return base64.b64decode(blob[14:])
            raise ValueError("Invalid Simulated Ciphertext")
            
        nonce = blob[:self.nonce_size]
        ciphertext = blob[self.nonce_size:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def sign_pqc(self, data: bytes) -> bytes:
        """
        Pillar 18: Post-Quantum Signature (Dilithium placeholder).
        """
        # In a real implementation, this would use liboqs or pqcrypto
        # Here we simulate a signature by hashing.
        return b"PQC_SIG:" + hashlib.sha3_512(data).digest()

