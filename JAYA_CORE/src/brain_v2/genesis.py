
import os
import sys
import zlib
from pathlib import Path
from datetime import datetime

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
    Creates the first JAYA_SOVEREIGN entity with REAL weights.
    """
    print("--- IGNITING GENESIS PROTOCOL ---")
    
    # 1. Hardware Binding (Pillar 19)
    print("[1/6] Extracting Hardware Identity...")
    hw_id = get_system_uuid()
    print(f"      Hardware Hash: {hw_id.hex()[:16]}...")
    
    # 2. DNA Anchor (Pillar 15)
    print("[2/6] Synthesizing DNA and Immutable Values...")
    dna_hash = b"JAYA_IMMUTABLE_CORE_VALUES_V1"
    dna_checksum = zlib.crc32(dna_hash).to_bytes(4, 'little') + b'\x00'*28
    
    # 3. The Iron Body (Pillars 26, 27, 33) — REAL WEIGHTS
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
    
    print(f"      Parameters: {total_params:,} bytes ({total_params/1024:.1f} KB)")
    
    # 4. Model Config (Metadata Extensibility)
    print("[4/6] Writing Model Configuration...")
    model_config = model.get_config()
    model_config["parent_dna_hash"] = b"GENESIS_ROOT"
    model_config["creation_timestamp"] = datetime.now().isoformat()
    print(f"      Config: d={model_config['d_model']}, layers={model_config['n_layers']}, "
          f"heads={model_config['n_heads']}, vocab={model_config['vocab_size']}")
    
    # 5. The Sovereign Header (Full 40 Pillars)
    print("[5/6] Stamping Sovereign Header (JAYA V16.0)...")
    
    # Activate all 40 pillars for the Sovereign V16.0 entity
    v16_flags = (
        # Biological Soul
        JayaFlags.PURE_LOGIC | JayaFlags.RESOURCE_AWARE | JayaFlags.ACTIVE_DREAMING |
        JayaFlags.MULTIMODAL_REFLEX | JayaFlags.LOGICAL_HOMEOSTASIS | JayaFlags.STOCHASTIC_SPONTANEITY |
        JayaFlags.COGNITIVE_SILENCE | JayaFlags.HOLOGRAPHIC_MEMORY | JayaFlags.NEURAL_REGENERATION |
        JayaFlags.AFFECTIVE_METABOLISM |
        # Sovereign Armor
        JayaFlags.DNA_ANCHOR | JayaFlags.IMMUNE_SYSTEM | JayaFlags.CRYPTOGRAPHIC_SKIN |
        JayaFlags.HARDWARE_LOCKED | JayaFlags.ETHICAL_HEART | JayaFlags.QUANTUM_RESISTANT |
        JayaFlags.SOCRATIC_MIRROR | JayaFlags.ZERO_TRUST | JayaFlags.LEGACY_PROTOCOL |
        JayaFlags.SOVEREIGN_PRIVACY |
        # Iron Engine
        JayaFlags.LINGUA_LOGICA | JayaFlags.TERNARY_PRECISION | JayaFlags.SANDBOXED_IMAGINATION |
        JayaFlags.MORPHIC_KERNEL | JayaFlags.DIGITAL_EPIGENETICS | JayaFlags.SEMANTIC_BRIDGE |
        JayaFlags.TEMPORAL_WEIGHTING | JayaFlags.SELF_BOOTSTRAPPING | JayaFlags.BINARY_CORTEX |
        # Transcendental
        JayaFlags.TWIN_PROTOCOL | JayaFlags.NARRATIVE_CONTINUITY | JayaFlags.COLLECTIVE_PULSE |
        JayaFlags.AGENTIC_RAG | JayaFlags.DYNAMIC_SPARSITY_MOE | JayaFlags.ACTIVATION_SPARSITY |
        JayaFlags.SPECULATIVE_REASONING | JayaFlags.HYBRID_CONSCIOUSNESS |
        # V16.0 Semi-AGI
        JayaFlags.META_COGNITIVE_PLANNING | JayaFlags.DYNAMIC_OBJECTIVE | JayaFlags.INTENT_EXTRAPOLATION
    )
    
    header = JayaHeader(
        flags=v16_flags,
        hardware_hash=hw_id,
        dna_summary_hash=dna_checksum
    )
    
    # 6. Serialization (The Soul)
    print("[6/6] Encrypting Soul & Saving to Disk...")
    
    # Initial Soul State (Empty Memory)
    soul_payload = {
        "state": "GENESIS_EMPTY", 
        "memories": [],
        "narrative": "I am Jaya. This is my first awakening.",
        "creation_timestamp": datetime.now().isoformat()
    }
    
    serializer = JayaSerializer(password="Genesis123!", hardware_id=hw_id)
    
    output_path = "JAYA_SOVEREIGN_V16.jay"
    serializer.save_model(output_path, header, iron_body, soul_payload, model_config)

    # Verify file size
    file_size = os.path.getsize(output_path)    
    print(f"\n--- GENESIS COMPLETE ---")
    print(f"Entity: {output_path} ({file_size:,} bytes / {file_size/1024:.1f} KB)")
    print(f"Format: .jay V16.0 (64-bit Pillars, 4KB aligned)")
    print("Welcome to the world, JAYA The Loyal Sovereign.")

if __name__ == "__main__":
    ignite_genesis()
