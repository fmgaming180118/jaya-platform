
import shutil
import os
import time
import glob
import hashlib

class Safeguard:
    def __init__(self, watch_dir="src", backup_dir="backups"):
        self.watch_dir = watch_dir
        self.backup_dir = backup_dir
        os.makedirs(self.backup_dir, exist_ok=True)
        
    def create_backup(self, label="pre_mutation"):
        """
        Creates a snapshot of the watch_dir.
        Returns the path to the backup zip.
        """
        timestamp = int(time.time())
        # Create a unique hash for the state
        state_hash = self._calculate_directory_hash()
        
        backup_name = f"{timestamp}_{label}_{state_hash[:8]}"
        backup_path = os.path.join(self.backup_dir, backup_name)
        
        # Create Zip
        shutil.make_archive(backup_path, 'zip', self.watch_dir)
        final_path = f"{backup_path}.zip"
        
        print(f"[SAFEGUARD] Backup created: {final_path}")
        return final_path

    def restore_backup(self, backup_path):
        """
        Restores the watch_dir from a backup zip.
        WARNING: Overwrites current files.
        """
        if not os.path.exists(backup_path):
            print(f"[SAFEGUARD] Error: Backup not found {backup_path}")
            return False
            
        print(f"[SAFEGUARD] ⚠️ Restoring system from {backup_path}...")
        
        try:
            # Clean watch_dir first to ensure exact state restoration
            # We keep __pycache__ or ignore it? Better to clean everything to be safe.
            # But we must be careful not to delete the script running this if possible?
            # Actually, safeguard.py is IN watch_dir (src).
            # If we delete it while running, it might crash or be fine (loaded in memory).
            # Let's try to delete all files except the running script? 
            # Or just rely on overwrite? 
            # The user requirement "Corruption removed" implies exact state.
            # Let's delete all files in watch_dir.
            
            for root, dirs, files in os.walk(self.watch_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            
            shutil.unpack_archive(backup_path, self.watch_dir)
            print("[SAFEGUARD] System restored successfully.")
            return True
        except Exception as e:
            print(f"[SAFEGUARD] RESTORE FAILED: {e}")
            return False

    def _calculate_directory_hash(self):
        sha = hashlib.sha256()
        for root, _, files in os.walk(self.watch_dir):
            for names in sorted(files):
                if names.endswith(".pyc") or names == "__pycache__": continue
                filepath = os.path.join(root, names)
                try:
                    with open(filepath, 'rb') as f1:
                        while True:
                            buf = f1.read(4096)
                            if not buf: break
                            sha.update(buf)
                except: pass
        return sha.hexdigest()

if __name__ == "__main__":
    # Test
    sg = Safeguard()
    
    # 1. Backup
    bp = sg.create_backup("test_init")
    
    # 2. Modify something (Simulate corruption)
    test_file = os.path.join("src", "corruption_test.txt")
    with open(test_file, "w") as f:
        f.write("I am a bug!")
    
    print(f"Propagated corruption: {os.path.exists(test_file)}")
    
    # 3. Restore
    sg.restore_backup(bp)
    
    print(f"Corruption removed? {not os.path.exists(test_file)}")
