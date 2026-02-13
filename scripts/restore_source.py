
import os
import shutil

ROOT_DIR = "src/brain_v2"

def restore_sources():
    print(f"Restoring source files in {ROOT_DIR}...")
    count = 0
    for root, dirs, files in os.walk(ROOT_DIR):
        for file in files:
            if file.endswith(".py.bak"):
                src = os.path.join(root, file)
                dst = src[:-4] # Remove .bak
                
                print(f"Restoring {src} -> {dst}")
                try:
                    if os.path.exists(dst):
                        os.remove(dst) # Overwrite if exists
                    os.rename(src, dst)
                    count += 1
                except Exception as e:
                    print(f"Failed to restore {src}: {e}")
                    
    print(f"Restored {count} source files.")

if __name__ == "__main__":
    restore_sources()
