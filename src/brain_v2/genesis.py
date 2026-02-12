
import os
import sys
import zlib
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.brain_v2.format.schema import JayaHeader, JayaFlags, MAGIC
from src.brain_v2.format.serializer import JayaSerializer
from src.brain_v2.model.architecture import JayaHybridModel
from src.brain_v2.protection.hardware import get_system_uuid

def ignite_genesis():
    """
    The Spark of Life.
    Creates the first JAYA_SOVEREIGN entity.
    """
    print("--- IGNITING GENESIS PROTOCOL ---")
    
    # 1. Hardware Binding (Pillar 19)
    print("[1/5] Extracting Hardware Identity...")
    hw_id = get_system_uuid()
    print(f"      Hardware Hash: {hw_id.hex()[:16]}...")
    
    # 2. DNA Anchor (Pillar 15)
    print("[2/5] Synthesizing DNA and Immutable Values...")
    # For now, a placeholder DNA hash
    dna_hash = b"JAYA_IMMUTABLE_CORE_VALUES_V1"
    dna_checksum = zlib.crc32(dna_hash).to_bytes(4, 'little') + b'\x00'*28
    
    # 3. The Iron Body (Pillars 26, 27, 33)
    print("[3/5] Forging Iron Body (Ternary Logic)...")
    model = JayaHybridModel(d_model=128, n_layers=4, n_heads=4, vocab_size=1000) # Tiny Genesis Model
    iron_body_payload = model.get_state_dict()
    print(f"      Body Size: {len(iron_body_payload)} bytes")
    
    # 4. The Sovereign Header
    print("[4/5] Stamping Sovereign Header...")
    header = JayaHeader(
        flags=JayaFlags.ENCRYPTED_AES256 | JayaFlags.HAS_DNA_ANCHOR | JayaFlags.HARDWARE_LOCKED | JayaFlags.QUANTUM_SAFE,
        hardware_hash=hw_id,
        dna_summary_hash=dna_checksum
    )
    
    # 5. Serialization (The Soul)
    print("[5/5] Encrypting Soul & Saving to Disk...")
    
    # Initial Soul State (Empty Memory)
    soul_payload = b"GENESIS_SOUL_STATE_EMPTY"
    
    serializer = JayaSerializer(password="Genesis123!", hardware_id=hw_id)
    
    output_path = "JAYA_GENESIS_V13.jay"
    serializer.save_model(output_path, header, iron_body_payload, soul_payload)
    
    print("\n--- GENESIS COMPLETE ---")
    print(f"Entity created: {output_path}")
    print("Welcome to the world, Jaya.")

if __name__ == "__main__":
    ignite_genesis()
