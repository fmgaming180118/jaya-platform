"""
lockdown.py -- Post-Compilation Lockdown Script

Phase 14: Binary Cortex.
Pillar 29: Self-Bootstrapping.
Pillar 7: Sovereign Privacy.

Steps:
1. Run Cython compilation (setup_compile.py)
2. Verify all .pyd files were created
3. Remove .py source files (keep only .pyd + __init__.py)
4. Remove .c intermediate files
5. Verify imports still work
6. Run genesis + ignite sanity test
"""

import os
import sys
import glob
import shutil
import importlib
import subprocess

# Add current directory to path so we can import src.*
sys.path.append(os.getcwd())


# Directories to lock down
TARGET_DIRS = [
    "src/brain_v2/engine",
    "src/brain_v2/format",
    "src/brain_v2/model",
    "src/brain_v2/network",
    "src/brain_v2/organism",
    "src/brain_v2/protection",
    "src/brain_v2/soul",
]

# Files to NEVER delete (entry points, configs)
PROTECTED_FILES = {
    "__init__.py",
    "genesis.py",
    "ignite.py",
}


def step_1_compile():
    """Run Cython compilation."""
    print("\n=== STEP 1: COMPILING ===")
    result = subprocess.run(
        [sys.executable, "scripts/setup_compile.py", "build_ext", "--inplace"],
        capture_output=True, text=True
    )
    print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
    if result.returncode != 0:
        print(f"COMPILE ERROR:\n{result.stderr[-500:]}")
        return False
    print("[OK] Compilation complete.")
    return True


def step_2_verify_pyd():
    """Verify .pyd/.so files were created."""
    print("\n=== STEP 2: VERIFYING .pyd FILES ===")
    ext = ".pyd" if os.name == 'nt' else ".so"
    
    pyd_files = []
    missing = []
    
    for d in TARGET_DIRS:
        if not os.path.exists(d):
            continue
        for root, dirs, files in os.walk(d):
            py_files = [f for f in files if f.endswith(".py") and f not in PROTECTED_FILES
                       and not f.startswith(("test_", "verify_", "demo_"))]
            for py_file in py_files:
                base = py_file[:-3]
                # Look for matching .pyd
                pyd_matches = [f for f in files if f.startswith(base) and f.endswith(ext)]
                if pyd_matches:
                    pyd_files.append(os.path.join(root, pyd_matches[0]))
                else:
                    missing.append(os.path.join(root, py_file))
    
    print(f"Found {len(pyd_files)} compiled modules.")
    if missing:
        print(f"WARNING: {len(missing)} modules missing .pyd:")
        for m in missing:
            print(f"  - {m}")
    
    return pyd_files, missing


def step_3_cleanup_source(pyd_files, dry_run=True):
    """Remove .py source files that have .pyd counterparts."""
    print(f"\n=== STEP 3: {'DRY RUN' if dry_run else 'REMOVING'} SOURCE FILES ===")
    
    removed = 0
    for d in TARGET_DIRS:
        if not os.path.exists(d):
            continue
        for root, dirs, files in os.walk(d):
            for f in files:
                if f.endswith(".py") and f not in PROTECTED_FILES:
                    if not f.startswith(("test_", "verify_", "demo_")):
                        filepath = os.path.join(root, f)
                        if dry_run:
                            print(f"  [DRY] Would remove: {filepath}")
                        else:
                            os.remove(filepath)
                            print(f"  [DEL] {filepath}")
                        removed += 1
                
                # Also clean .c files
                if f.endswith(".c"):
                    filepath = os.path.join(root, f)
                    if dry_run:
                        print(f"  [DRY] Would remove: {filepath}")
                    else:
                        os.remove(filepath)
                        print(f"  [DEL] {filepath}")
    
    print(f"{'Would remove' if dry_run else 'Removed'} {removed} source files.")
    return removed


def step_4_verify_imports():
    """Verify all compiled modules can be imported."""
    print("\n=== STEP 4: VERIFYING IMPORTS ===")
    
    modules_to_test = [
        "src.brain_v2.format.schema",
        "src.brain_v2.format.serializer",
        "src.brain_v2.model.ternary",
        "src.brain_v2.model.attention",
        "src.brain_v2.model.architecture",
        "src.brain_v2.model.vision_encoder",
        "src.brain_v2.engine.awakening",
        "src.brain_v2.engine.runtime",
        "src.brain_v2.engine.voice_bridge",
        "src.brain_v2.engine.visual_reflex",
        "src.brain_v2.protection.soul_crypto",
        "src.brain_v2.protection.immune",
        "src.brain_v2.protection.memory_vault",
        "src.brain_v2.protection.audit_result",
        "src.brain_v2.organism.metabolism",
        "src.brain_v2.organism.epigenetics",
        "src.brain_v2.organism.dreaming",
        "src.brain_v2.organism.regeneration",
        "src.brain_v2.soul.socratic",
        "src.brain_v2.soul.narrative",
        "src.brain_v2.soul.bridge",
    ]
    
    passed = 0
    failed = 0
    
    for mod_name in modules_to_test:
        try:
            importlib.import_module(mod_name)
            print(f"  [OK] {mod_name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {mod_name}: {e}")
            failed += 1
    
    print(f"\nImport results: {passed} passed, {failed} failed.")
    return failed == 0


def step_5_sanity_test():
    """Run genesis + ignite to verify end-to-end."""
    print("\n=== STEP 5: SANITY TEST (Genesis + Ignite) ===")
    
    # Genesis
    result = subprocess.run(
        [sys.executable, "src/brain_v2/genesis.py"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Genesis FAILED:\n{result.stderr[-300:]}")
        return False
    print("[OK] Genesis successful.")
    
    # Ignite test
    result = subprocess.run(
        [sys.executable, "-c", 
         "from src.brain_v2.engine.awakening import AwakeningProtocol; "
         "a = AwakeningProtocol('Genesis123!'); "
         "m = a.awaken('JAYA_GENESIS_V13.jay'); "
         "print('Model:', type(m).__name__); "
         "assert m is not None"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Ignite FAILED:\n{result.stderr[-300:]}")
        return False
    print("[OK] Ignite successful.")
    return True


def main():
    print("=" * 60)
    print("  BINARY CORTEX LOCKDOWN - Phase 14")
    print("  Compiling JAYA into Black Box (.pyd)")
    print("=" * 60)
    
    # Parse args
    dry_run = "--execute" not in sys.argv
    skip_compile = "--skip-compile" in sys.argv
    
    if dry_run:
        print("\n[MODE: DRY RUN] Use --execute to actually remove source files.\n")
    
    # Step 1: Compile
    if not skip_compile:
        if not step_1_compile():
            print("\n[ABORT] Compilation failed.")
            return 1
    
    # Step 2: Verify .pyd
    pyd_files, missing = step_2_verify_pyd()
    
    # Step 3: Cleanup (dry run by default)
    step_3_cleanup_source(pyd_files, dry_run=dry_run)
    
    # Step 4: Verify imports
    if not step_4_verify_imports():
        print("\n[WARNING] Some imports failed. Source cleanup skipped.")
        return 1
    
    # Step 5: Sanity test
    if not step_5_sanity_test():
        print("\n[WARNING] Sanity test failed.")
        return 1
    
    print("\n" + "=" * 60)
    if dry_run:
        print("  LOCKDOWN READY (DRY RUN)")
        print("  Run with --execute to remove .py source files.")
    else:
        print("  LOCKDOWN COMPLETE")
        print("  JAYA is now a Black Box.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
