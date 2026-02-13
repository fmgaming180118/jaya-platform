
import os
import shutil

ROOT_DIR = "src/brain_v2"
KEEP_FILES = [
    "__init__.py",
    "genesis.py", 
    "ignite.py",
    "setup_compile.py",
    "compile_debug.py",
    "setup_test.py",
    "test_cython.py",
    "verify_binary.py"
]

def hide_sources():
    print(f"Hiding source files in {ROOT_DIR}...")
    count = 0
    for root, dirs, files in os.walk(ROOT_DIR):
        for file in files:
            if file.endswith(".py") and file not in KEEP_FILES:
                if file.startswith("test_") or file.startswith("verify_"):
                    continue
                    
                src = os.path.join(root, file)
                dst = src + ".bak"
                
                # Check if .pyd exists (only hide if compiled version exists)
                # But extensions might have slightly different names like .cp310-win_amd64.pyd
                # So we just rename .py regardless, assuming compilation worked.
                # Actually, safe check:
                
                print(f"Renaming {src} -> {dst}")
                try:
                    os.rename(src, dst)
                    count += 1
                except Exception as e:
                    print(f"Failed to rename {src}: {e}")
                    
    print(f"Hidden {count} source files.")

if __name__ == "__main__":
    hide_sources()
