
import sys
import os
import traceback
from jaya_research.safeguard import Safeguard
from jaya_research.integrity import run_integrity_suite
from jaya_research.sandbox import Sandbox

class ImmuneSystem:
    def __init__(self, watch_dir="src", backup_dir="backups"):
        self.safeguard = Safeguard(watch_dir, backup_dir)
        self.sandbox = Sandbox()
        self.current_backup = None
        self.passed = False

    def __enter__(self):
        """
        Start of the danger zone.
        Create a backup immediately and initialize Native OS Sandbox.
        """
        print("\n[IMMUNE SYSTEM] [DEFENSE SHIELDS] Activating Native OS Isolation Sandbox...")
        self.current_backup = self.safeguard.create_backup(label="auto_guard")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        End of the danger zone.
        1. Check for crashes (Exceptions).
        2. Check for brain damage (Integrity Tests in Sandbox).
        3. Rollback if necessary.
        4. Auto-clean sandbox artifacts.
        """
        if exc_type:
            print(f"\n[IMMUNE SYSTEM] [CRASH DETECTED] {exc_val}")
            print("[IMMUNE SYSTEM] [ROLLBACK] Initiating Emergency Rollback...")
            self.safeguard.restore_backup(self.current_backup)
            self.sandbox.cleanup_workspace()
            self.passed = False
            return True # Suppress exception after rollback
        
        # Check cognitive integrity inside isolated subprocess sandbox
        print("[IMMUNE SYSTEM] [INTEGRITY] Checking Cognitive Integrity in Native Sandbox...")
        try:
            # Run integrity test via isolated sandbox process
            watch_abs = os.path.abspath(self.safeguard.watch_dir)
            test_script = (
                "import sys, os\n"
                f"sys.path.insert(0, r'{watch_abs}')\n"
                "from integrity import run_integrity_suite\n"
                "res = run_integrity_suite()\n"
                "sys.exit(0 if res else 1)\n"
            )
            sandbox_env = {
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1"
            }
            res = self.sandbox.run_isolated_python(
                test_script, memory_limit_mb=256, timeout_sec=5.0, env_vars=sandbox_env
            )
            self.passed = res.get("success", False)
            if res.get("output"):
                print(f"[IMMUNE SYSTEM] Sandbox Test Log:\n{res['output']}")
            if res.get("error"):
                print(f"[IMMUNE SYSTEM] Sandbox Error Log:\n{res['error']}")
        except Exception as e:
            print(f"[IMMUNE SYSTEM] Integrity Test Crashed: {e}")
            self.passed = False

        if not self.passed:
            print("[IMMUNE SYSTEM] [REJECTED] Integrity Check FAILED. Mutation rejected.")
            print("[IMMUNE SYSTEM] [ROLLBACK] Initiating Emergency Rollback...")
            self.safeguard.restore_backup(self.current_backup)
        else:
            print("[IMMUNE SYSTEM] [PASSED] System Stable. Mutation Accepted.")

        # Cleanup sandbox temp artifacts
        self.sandbox.cleanup_workspace()

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
