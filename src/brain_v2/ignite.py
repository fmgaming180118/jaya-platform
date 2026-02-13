"""
ignite.py — System Boot Sequence for JAYA Logic Kernel V13.

This is the entry point for running the JAYA engine.
"""
import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(PROJECT_ROOT)

from src.brain_v2.engine.runtime import IronEngine

# ---- Configuration ----
JAYA_MODEL_PATH = "JAYA_GENESIS_V13.jay"
JAYA_PASSWORD = "Genesis123!"

def main():
    print("=" * 42)
    print("   JAYA LOGIC KERNEL V13 (Binary Cortex)")
    print("=" * 42)
    
    engine = IronEngine(JAYA_MODEL_PATH, JAYA_PASSWORD)
    engine.ignite()

if __name__ == "__main__":
    main()
