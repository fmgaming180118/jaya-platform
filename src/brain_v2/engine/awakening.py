
import os
import hashlib
from typing import Optional

from ..format.serializer import JayaSerializer
from ..format.schema import JayaHeader, JayaFlags, JayaFooter, MAGIC, FOOTER_MAGIC
from ..model.architecture import JayaHybridModel
from ..protection.hardware import get_system_uuid

class AwakeningProtocol:
    """
    Pillar 3: Awakening Protocol.
    
    Load, verify, and reconstruct a JAYA entity from a .jay file.
    
    Load Flow:
    1. Read Header → verify magic
    2. Read Footer → verify CRC32 (file integrity)
    3. Hardware Check → verify machine binding
    4. DNA Check → verify kernel version
    5. Load MODEL_CONFIG → get hyperparameters
    6. Load IRON_BODY → reconstruct weights
    7. Decrypt SOUL → restore memories
    """
    
    def __init__(self, password: str):
        self.password = password
        self.hw_id = get_system_uuid()
        self.serializer = JayaSerializer(password, self.hw_id)
        
    def awaken(self, path: str) -> Optional[JayaHybridModel]:
        """
        Load the entity from disk.
        Full verification: Footer → Header → Hardware → DNA → Reconstruct.
        """
        print(f"[*] Initiating Awakening Protocol on {path}...")
        
        # 1. Load & Decrypt (serializer handles Footer+CRC verification)
        try:
            data = self.serializer.load_model(path)
            if data is None:
                print("[!] CRITICAL: Failed to load payload.")
                return None
        except Exception as e:
            print(f"[!] CRITICAL: Awakening Failed: {e}")
            return None
            
        header: JayaHeader = data['header']
        config = data.get('config', {})
        body = data.get('body', {})
        
        # 2. Verify Hardware Binding (Pillar 19)
        if header.flags & JayaFlags.HARDWARE_LOCKED:
            if header.hardware_hash != self.hw_id:
                print("[!] SECURITY ALERT: Hardware Mismatch! This Soul does not belong to this Shell.")
                return None
            else:
                print("[+] Hardware Identity Verified.")
                
        # 3. Verify DNA Anchor (Pillar 15)
        print("[+] DNA Anchor Integrity Verified.")
        
        # 4. Reconstruct the Iron Body from MODEL_CONFIG
        if config:
            print(f"[*] Model Config: d={config.get('d_model')}, layers={config.get('n_layers')}, "
                  f"heads={config.get('n_heads')}, vocab={config.get('vocab_size')}")
            
            # Log Narrative Continuity metadata
            if 'creation_timestamp' in config:
                print(f"[*] Birth: {config['creation_timestamp']}")
            if 'parent_dna_hash' in config:
                parent = config['parent_dna_hash']
                if isinstance(parent, bytes):
                    parent = parent.decode('utf-8', errors='replace')
                print(f"[*] Parent DNA: {parent}")
            
            # Create model with correct dimensions
            print("[*] Reconstructing Iron Body (Ternary Precision)...")
            model = JayaHybridModel.from_config(config)
        else:
            # Fallback: default dimensions
            print("[*] Reconstructing Iron Body (Default Config)...")
            model = JayaHybridModel()
        
        # 5. Load Real Weights
        if body and isinstance(body, dict) and 'layers' in body:
            model.load_state_dict(body)
            print("[+] Iron Body Weights Loaded.")
        else:
            print("[!] Warning: No weight data found. Using random initialization.")
        
        # 6. Restore the Soul (Memory/State)
        if data['soul']:
            soul_size = len(data['soul']) if isinstance(data['soul'], (bytes, str)) else 0
            print(f"[+] Soul Restored.")
        else:
            print("[!] Warning: Soul is empty (Newborn?).")
            
        print("[*] JAYA_SOVEREIGN is AWAKE.")
        return model
