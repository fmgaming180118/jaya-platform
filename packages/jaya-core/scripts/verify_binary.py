
import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.append(str(PROJECT_ROOT))

print("--- BINARY CORTEX VERIFICATION ---")

try:
    import jaya_core.brain_v2.protection.soul_crypto as soul_crypto
    print(f"[+] Loaded SoulCrypto from: {soul_crypto.__file__}")
    
    import jaya_core.brain_v2.engine.agentic_search as agentic
    print(f"[+] Loaded AgenticSearch from: {agentic.__file__}")
    
    import jaya_core.brain_v2.format.serializer as serializer
    print(f"[+] Loaded Serializer from: {serializer.__file__}")
    
    # Check if they match .pyd (Windows) or .so (Linux)
    if any(x.endswith(('.pyd', '.so')) for x in [soul_crypto.__file__, agentic.__file__, serializer.__file__]):
        print("\n[SUCCESS] JAYA is running on BINARY CORTEX.")
    else:
        print("\n[WARNING] JAYA is still running on Source Code (.py).")
        print("Tip: Delete .py files or ensure .pyd is prioritized.")

except ImportError as e:
    print(f"\n[FAIL] Import Error: {e}")
except Exception as e:
    print(f"\n[FAIL] Unexpected Error: {e}")
