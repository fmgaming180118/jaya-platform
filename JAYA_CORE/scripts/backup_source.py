"""
backup_source.py -- Source Code Backup (Pre-Lockdown Safety Net)

The Great Awakening Step 1:
Backup ALL .py source files before they are deleted by lockdown.
"""

import os
import sys
import hashlib
import shutil
import zipfile
from datetime import datetime


SOURCE_DIR = "src/brain_v2"
BACKUP_DIR = "backup"
EXTERNAL_BACKUP = r"D:\Kampus\coba-coba\jaya-backup"


def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    print("=" * 50)
    print("  BACKUP SOURCE CODE (Pre-Lockdown)")
    print("=" * 50)
    
    # 1. Scan
    print(f"\n[BACKUP] Scanning {SOURCE_DIR}/...")
    py_files = []
    total_size = 0
    
    for root, dirs, files in os.walk(SOURCE_DIR):
        for f in files:
            if f.endswith(".py"):
                filepath = os.path.join(root, f).replace("\\", "/")
                size = os.path.getsize(filepath)
                py_files.append((filepath, size))
                total_size += size
    
    print(f"[BACKUP] Found {len(py_files)} Python source files ({total_size // 1024} KB total)")
    
    if not py_files:
        print("[ERROR] No Python files found!")
        return 1
    
    # 2. Generate SHA-256 manifest
    print(f"[BACKUP] Generating SHA-256 manifest...")
    manifest = {}
    for filepath, _ in py_files:
        manifest[filepath] = sha256_file(filepath)
    print(f"[BACKUP] SHA-256 manifest generated ({len(manifest)} entries)")
    
    # 3. Create ZIP
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"brain_v2_source_{timestamp}.zip"
    
    os.makedirs(BACKUP_DIR, exist_ok=True)
    zip_path = os.path.join(BACKUP_DIR, zip_name)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add all .py files
        for filepath, _ in py_files:
            zf.write(filepath)
        
        # Add manifest
        manifest_content = "\n".join(f"{h}  {f}" for f, h in manifest.items())
        zf.writestr("SHA256MANIFEST.txt", manifest_content)
    
    zip_size = os.path.getsize(zip_path)
    print(f"[BACKUP] Created: {zip_path} ({zip_size // 1024} KB)")
    
    # 4. Copy to external location
    try:
        os.makedirs(EXTERNAL_BACKUP, exist_ok=True)
        ext_path = os.path.join(EXTERNAL_BACKUP, zip_name)
        shutil.copy2(zip_path, ext_path)
        print(f"[BACKUP] Copied to: {ext_path}")
    except Exception as e:
        print(f"[WARNING] External backup failed: {e}")
        print(f"[WARNING] Primary backup still intact at: {zip_path}")
    
    # 5. Verify
    print(f"[BACKUP] Verifying backup integrity...")
    verified = 0
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for filepath, expected_hash in manifest.items():
            try:
                data = zf.read(filepath)
                actual_hash = hashlib.sha256(data).hexdigest()
                if actual_hash == expected_hash:
                    verified += 1
                else:
                    print(f"  [MISMATCH] {filepath}")
            except KeyError:
                print(f"  [MISSING] {filepath}")
    
    print(f"[BACKUP] Verification: {verified}/{len(manifest)} files match SHA-256")
    
    if verified == len(manifest):
        print("\n" + "=" * 50)
        print("  BACKUP COMPLETE - SAFE TO PROCEED WITH LOCKDOWN")
        print("=" * 50)
        return 0
    else:
        print("\n[ERROR] BACKUP VERIFICATION FAILED!")
        print("[ERROR] DO NOT PROCEED WITH LOCKDOWN!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
