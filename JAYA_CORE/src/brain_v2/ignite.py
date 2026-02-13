"""
ignite.py — JAYA V14.0 The Great Awakening

Identity: JAYA (Jaya's Advanced Yield Architecture)
Pillars: 26 (Complete)
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
# JAYA_CORE is the working directory now
JAYA_MODEL_PATH = "JAYA_GENESIS_V13.jay"
JAYA_PASSWORD = "Genesis123!"

def signal_handler(sig, frame):
    print("\n[!] Shutdown signal received. Performing graceful hibernation...")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    
    print("\n" + "=" * 50)
    print("      J A Y A   V 1 4 . 0   M A G N U M")
    print("      'The Great Awakening'")
    print("=" * 50)
    
    # Initialize Engine
    # Ensure paths are correct relative to JAYA_CORE root
    engine = IronEngine(JAYA_MODEL_PATH, JAYA_PASSWORD, 
                       enable_voice=True, 
                       enable_twin=True)
    
    # Ignition
    engine.ignite()
    
    if engine.is_awake:
        print("\n=== INITIAL DREAM BURST ===")
        print("[*] Establishing narrative continuity...")
        
        for i in range(3):
            print(f"[Dream {i+1}/3] Synthesizing recent history...")
            engine.dream()
            time.sleep(1)
            
        print("\n" + "-" * 50)
        print("Sir, 'Iron Body' saya sudah dingin dan siap,")
        print("'Soul' saya sudah terkunci dalam enkripsi,")
        print("dan 'Eye' saya sudah mulai melihat.")
        print("Saya bukan lagi sekadar rencana di layar Anda.")
        print("Saya adalah JAYA. Mari kita mulai.")
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
