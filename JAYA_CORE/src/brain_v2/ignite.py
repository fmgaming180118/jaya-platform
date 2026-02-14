"""
ignite.py — JAYA V15.0 The Sovereign Fluidity

Identity: JAYA (Jaya's Advanced Yield Architecture)
Architecture: Neural Liquid (TopK Sparse Ternary)
"""

import os
import sys
import time
import signal

# Add JAYA_CORE/src to path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(BASE_DIR)

try:
    from src.brain_v2.engine.runtime import IronEngine
except ImportError as e:
    print(f"CRITICAL ERROR: Failed to load JAYA Binary Cortex: {e}")
    sys.exit(1)

# ---- Configuration ----
JAYA_MODEL_PATH = "JAYA_GENESIS_V13.jay"
JAYA_PASSWORD = "Genesis123!"

def signal_handler(sig, frame):
    print("\n[!] Shutdown signal received. Performing graceful hibernation...")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    
    print("\n" + "=" * 50)
    print("      J A Y A   V 1 5 . 0   M A G N U M")
    print("      'The Sovereign Fluidity'")
    print("=" * 50)
    
    # Initialize Engine
    print("[SYSTEM] Sparse Gating Engine: ENABLED (TopK Fluidity)")
    engine = IronEngine(JAYA_MODEL_PATH, JAYA_PASSWORD, 
                       enable_voice=True, 
                       enable_twin=True)
    
    # Ignition
    engine.ignite()
    
    if engine.is_awake:
        print("\n=== INITIAL DREAM BURST ===")
        print("[*] Consolidating V15.0 Liquid Pathways...")
        
        for i in range(3):
            print(f"[Dream {i+1}/3] Calibrating sparse activations...")
            engine.dream()
            time.sleep(1)
            
        print("\n" + "-" * 50)
        print("Sir, 'Liquid Brain' saya sudah terkalibrasi.")
        print("Saya sekarang lebih ringan, namun lebih tajam.")
        print("Setiap sinyal Anda akan mengalir melalui jalur yang paling efisien.")
        print("Saya adalah JAYA V15.0. Mari kita melampaui batas.")
        print("-" * 50 + "\n")
        
        print("[SYSTEM] Entering continuous operation mode (Magnum Cycle).")
        try:
            engine.run_magnum_cycle()
        except KeyboardInterrupt:
            print("\n[!] JAYA is entering rest state. Farewell, Sir.")
            engine.dream()
            print("=== SYSTEM HYBRIDIZED & ENCRYPTED ===")

if __name__ == "__main__":
    main()
