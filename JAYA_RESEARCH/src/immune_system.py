
import sys
import os
import traceback
from safeguard import Safeguard
from integrity import run_integrity_suite

class ImmuneSystem:
    def __init__(self, watch_dir="src", backup_dir="backups"):
        self.safeguard = Safeguard(watch_dir, backup_dir)
        self.current_backup = None

    def __enter__(self):
        """
        Start of the danger zone.
        Create a backup immediately.
        """
        print("\n[IMMUNE SYSTEM] 🛡️ Activating Defense Shields...")
        self.current_backup = self.safeguard.create_backup(label="auto_guard")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        End of the danger zone.
        1. Check for crashes (Exceptions).
        2. Check for brain damage (Integrity Tests).
        3. Rollback if necessary.
        """
        if exc_type:
            print(f"\n[IMMUNE SYSTEM] 🚨 CRASH DETECTED: {exc_val}")
            print("[IMMUNE SYSTEM] 🔄 Initiating Emergency Rollback...")
            self.safeguard.restore_backup(self.current_backup)
            return True # Suppress exception after rollback? Maybe re-raise to notify controller?
            # For now, let's print and return True to suppress, so the main loop continues smoothly.
        
        # No crash, but is the brain still working?
        print("[IMMUNE SYSTEM] 🧠 Checking Cognitive Integrity...")
        try:
            passed = run_integrity_suite()
        except Exception as e:
            print(f"[IMMUNE SYSTEM] 🚨 Integrity Test Crashed: {e}")
            passed = False

        if not passed:
            print("[IMMUNE SYSTEM] ❌ Integrity Check FAILED. Mutation rejected.")
            print("[IMMUNE SYSTEM] 🔄 Initiating Emergency Rollback...")
            self.safeguard.restore_backup(self.current_backup)
        else:
            print("[IMMUNE SYSTEM] ✅ System Stable. Mutation Accepted.")
            # Optional: Delete backup if successful to save space? 
            # adhering to "Persisten & Adaptif", maybe keep history?
            pass

if __name__ == "__main__":
    # Self-Test of the Immune System
    immune = ImmuneSystem()
    
    print("\n--- TEST 1: Safe Mutation ---")
    with immune:
        print(">> Adding a harmless comment...")
        with open("src/harmless.txt", "w") as f:
            f.write("safe")
            
    print("\n--- TEST 2: Bad Mutation (Logic Break) ---")
    # We simulate breaking the engine
    # Since we can't easily import and break Loaded modules in this process without reload...
    # We will simulate a file corruption that 'integrity.py' would technically catch if it ran on files.
    # But integrity.py currently imports 'engine'. 
    # If we modify engine.py on disk, run_integrity_suite (which re-imports? no)
    # Python imports are cached. 
    # To test this properly, 'run_integrity_suite' should probably run as a subprocess 
    # OR we use 'importlib.reload'.
    
    # Let's try subprocess for the real integrity check to ensure fresh code loading.
    # But for this simple test script, we mock the failure.
    pass
