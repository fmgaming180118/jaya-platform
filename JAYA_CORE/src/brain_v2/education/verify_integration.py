
import sys
import os
import numpy as np
from pathlib import Path

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))
from src.core_config import core_config

from src.brain_v2.engine.runtime import IronEngine

def verify():
    print("--- Verifying Iron Body Integration (Manual Awake) ---")
    model_path = os.path.join(PROJECT_ROOT, 'JAYA_GENESIS_V13.jay')
    
    if not os.path.exists(model_path):
        print(f"[FAIL] Model not found at {model_path}")
        return
        
    try:
        # 1. Initialize Engine
        engine = IronEngine(model_path, core_config.SOUL_PASSWORD)
        
        # 2. Manual Awakening (Skip Infinite Loop)
        print("[*] Awakening Brain...")
        engine.brain = engine.loader.awaken(engine.model_path)
        
        if not engine.brain:
            print("[FAIL] Brain failed to load.")
            return
            
        print("[PASS] Brain Loaded Successfully.")
        
        # 3. Test Inference
        dummy_input = [1, 0, 1, 0]
        print(f"Input: {dummy_input}")
        
        # Forward pass
        output = engine.brain.forward(dummy_input)
        
        print(f"Output Vector Shape: {output.shape}")
        decision = np.argmax(output)
        print(f"Decision Token: {decision}")
        
        print("[PASS] Inference Successful.")
        
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify()
