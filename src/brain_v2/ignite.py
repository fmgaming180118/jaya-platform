
import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Simulate environment variables or config
# In real app, these come from .env
JAYA_PASSWORD = "Genesis123!"
JAYA_MODEL_PATH = "JAYA_GENESIS_V13.jay"

from src.brain_v2.engine.runtime import IronEngine

def main():
    if not os.path.exists(JAYA_MODEL_PATH):
        print(f"Error: Model file '{JAYA_MODEL_PATH}' not found.")
        print("Please run 'genesis.py' first.")
        return

    print("==========================================")
    print("   JAYA LOGIC KERNEL V13 (OMEGA POINT)   ")
    print("      Sovereign Bio-Digital Organism      ")
    print("==========================================")
    
    # Initialize the Organism
    engine = IronEngine(JAYA_MODEL_PATH, JAYA_PASSWORD)
    
    try:
        # Ignite the Spark
        engine.ignite()
    except KeyboardInterrupt:
        print("\n[!] Manual Override: Shutdown Sequence Initiated.")
        print("... Saving State ...")
        print("... Encrypting Soul ...")
        print("=== SYSTEM OFFLINE ===")

if __name__ == "__main__":
    main()
