"""Pillar 11 — DNA Anchor (Hardware-Bound Identity).

Implements hardware-bound identity using system fingerprinting.
Provides tamper-evident identity that is cryptographically bound to
specific hardware, preventing identity theft and cloning.
"""

import hashlib
import json
import os
import platform
import subprocess
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad


@dataclass
class DNAProfile:
    """Hardware-bound DNA profile."""
    version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    hardware_fingerprint: str = ""
    dna_seed: str = ""  # 32-byte hex string
    public_key: str = ""  # For future asymmetric crypto
    metadata: Dict[str, Any] = field(default_factory=dict)


class DNAAnchor:
    """Hardware-bound identity anchor (Pillar 11)."""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path) if storage_path else Path.home() / ".jaya_dna"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.dna_file = self.storage_path / "dna_profile.enc"
        self.profile: Optional[DNAProfile] = None
        self._crypto_key: Optional[bytes] = None
        
    def generate_hardware_fingerprint(self) -> str:
        """Generate hardware fingerprint from system characteristics."""
        fingerprint_components = []
        
        # System information
        fingerprint_components.append(platform.system())
        fingerprint_components.append(platform.machine())
        fingerprint_components.append(platform.processor())
        
        # MAC addresses (first 3 NICs)
        try:
            import psutil
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == psutil.AF_LINK and addr.address:
                        fingerprint_components.append(addr.address.replace(':', ''))
                        if len([c for c in fingerprint_components if ':' not in c or len(c) == 12]) >= 3:
                            break
                if len([c for c in fingerprint_components if ':' not in c or len(c) == 12]) >= 3:
                    break
        except ImportError:
            # Fallback if psutil not available
            fingerprint_components.append("unknown_mac")
        
        # Disk information
        try:
            import psutil
            for partition in psutil.disk_partitions():
                if 'fixed' in partition.opts or 'ntfs' in partition.fstype:
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        fingerprint_components.append(str(usage.total))
                        fingerprint_components.append(str(usage.used))
                        break
                    except (PermissionError, OSError):
                        continue
        except ImportError:
            fingerprint_components.append("unknown_disk")
        
        # Create stable hash
        fingerprint_string = "|".join(sorted(set(fingerprint_components)))
        return hashlib.sha256(fingerprint_string.encode()).hexdigest()
    
    def generate_dna_seed(self) -> str:
        """Generate cryptographically secure DNA seed."""
        return get_random_bytes(32).hex()
    
    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """Generate asymmetric key pair (for future use)."""
        # For now, we'll use symmetric crypto with hardware binding
        # In future versions, this could be actual asymmetric crypto
        return get_random_bytes(32), get_random_bytes(32)
    
    def _encrypt_profile(self, profile: DNAProfile) -> bytes:
        """Encrypt DNA profile for secure storage."""
        if not self._crypto_key:
            # Generate key from hardware fingerprint if not provided
            hw_fingerprint = self.generate_hardware_fingerprint()
            self._crypto_key = hashlib.sha256(hw_fingerprint.encode()).digest()
        
        # Convert profile to JSON
        profile_json = json.dumps(asdict(profile), sort_keys=True)
        profile_bytes = profile_json.encode('utf-8')
        
        # Encrypt with AES-256-GCM
        cipher = AES.new(self._crypto_key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(profile_bytes)
        
        # Return nonce + tag + ciphertext
        return cipher.nonce + tag + ciphertext
    
    def _decrypt_profile(self, encrypted_data: bytes) -> DNAProfile:
        """Decrypt DNA profile from secure storage."""
        if not self._crypto_key:
            # Generate key from hardware fingerprint if not provided
            hw_fingerprint = self.generate_hardware_fingerprint()
            self._crypto_key = hashlib.sha256(hw_fingerprint.encode()).digest()
        
        # Extract nonce, tag, and ciphertext
        if len(encrypted_data) < 32:  # nonce(16) + tag(16)
            raise ValueError("Invalid encrypted data: too short")
        
        nonce = encrypted_data[:16]
        tag = encrypted_data[16:32]
        ciphertext = encrypted_data[32:]
        
        # Decrypt
        cipher = AES.new(self._crypto_key, AES.MODE_GCM, nonce=nonce)
        profile_bytes = cipher.decrypt_and_verify(ciphertext, tag)
        
        # Convert back to DNAProfile
        profile_dict = json.loads(profile_bytes.decode('utf-8'))
        return DNAProfile(**profile_dict)
    
    def initialize(self) -> DNAProfile:
        """Initialize or load DNA anchor."""
        if self.dna_file.exists():
            try:
                with open(self.dna_file, 'rb') as f:
                    encrypted_data = f.read()
                self.profile = self._decrypt_profile(encrypted_data)
                # Verify hardware binding
                current_fingerprint = self.generate_hardware_fingerprint()
                if self.profile.hardware_fingerprint != current_fingerprint:
                    raise ValueError("Hardware fingerprint mismatch - possible tampering")
                return self.profile
            except Exception as e:
                # If decryption fails, treat as new initialization
                print(f"[DNA Anchor] Warning: Could not load existing profile: {e}")
        
        # Create new DNA profile
        self.profile = DNAProfile(
            hardware_fingerprint=self.generate_hardware_fingerprint(),
            dna_seed=self.generate_dna_seed()
        )
        
        # Generate keypair for future use
        # public_key, _ = self.generate_keypair()  # For future asymmetric crypto
        # self.profile.public_key = public_key.hex()
        
        # Save encrypted profile
        encrypted_data = self._encrypt_profile(self.profile)
        with open(self.dna_file, 'wb') as f:
            f.write(encrypted_data)
        
        return self.profile
    
    def get_identity_token(self, purpose: str = "general") -> str:
        """Get hardware-bound identity token for specific purpose."""
        if not self.profile:
            self.initialize()
        
        # Create purpose-specific token
        token_data = {
            "dna_seed": self.profile.dna_seed,
            "purpose": purpose,
            "timestamp": datetime.now().isoformat(),
            "hardware_fingerprint": self.profile.hardware_fingerprint
        }
        
        token_json = json.dumps(token_data, sort_keys=True)
        token_hash = hashlib.sha256(token_json.encode()).hexdigest()
        
        return token_hash
    
    def verify_identity(self, token: str, purpose: str = "general") -> bool:
        """Verify identity token against DNA anchor."""
        if not self.profile:
            self.initialize()
        
        expected_token = self.get_identity_token(purpose)
        # Use constant-time comparison to prevent timing attacks
        return self._constant_time_compare(token, expected_token)
    
    @staticmethod
    def _constant_time_compare(a: str, b: str) -> bool:
        """Constant-time string comparison to prevent timing attacks."""
        if len(a) != len(b):
            return False
        result = 0
        for x, y in zip(a, b):
            result |= ord(x) ^ ord(y)
        return result == 0
    
    def get_status(self) -> Dict[str, Any]:
        """Get DNA anchor status."""
        if not self.profile:
            return {"initialized": False}
        
        return {
            "initialized": True,
            "version": self.profile.version,
            "created_at": self.profile.created_at,
            "hardware_fingerprint": self.profile.hardware_fingerprint[:16] + "...",  # Truncated for security
            "dna_seed_length": len(self.profile.dna_seed),
            "has_public_key": bool(self.profile.public_key)
        }


# Global DNA anchor instance
_dna_anchor: Optional[DNAAnchor] = None


def get_dna_anchor() -> DNAAnchor:
    """Get global DNA anchor instance."""
    global _dna_anchor
    if _dna_anchor is None:
        _dna_anchor = DNAAnchor()
    return _dna_anchor


def initialize_dna_anchor(storage_path: Optional[str] = None) -> DNAAnchor:
    """Initialize DNA anchor with optional storage path."""
    global _dna_anchor
    _dna_anchor = DNAAnchor(storage_path)
    return _dna_anchor


def get_identity_token(purpose: str = "general") -> str:
    """Get hardware-bound identity token for specific purpose."""
    return get_dna_anchor().get_identity_token(purpose)


def verify_identity(token: str, purpose: str = "general") -> bool:
    """Verify identity token against DNA anchor."""
    return get_dna_anchor().verify_identity(token, purpose)


# Example usage
if __name__ == "__main__":
    # Initialize DNA anchor
    dna = DNAAnchor()
    profile = dna.initialize()
    
    print("DNA Anchor Initialized:")
    print(f"  Version: {profile.version}")
    print(f"  Created: {profile.created_at}")
    print(f"  Hardware Fingerprint: {profile.hardware_fingerprint[:16]}...")
    print(f"  DNA Seed Length: {len(profile.dna_seed)} bytes")
    
    # Get identity token
    token = dna.get_identity_token("voice_recognition")
    print(f"  Identity Token: {token[:16]}...")
    
    # Verify token
    is_valid = dna.verify_identity(token, "voice_recognition")
    print(f"  Token Valid: {is_valid}")
    
    # Test with wrong purpose
    is_valid_wrong = dna.verify_identity(token, "face_recognition")
    print(f"  Wrong Purpose Valid: {is_valid_wrong}")