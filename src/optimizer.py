
import os
import sys
import time
from teacher import Teacher
from introspection import Introspection
from immune_system import ImmuneSystem

class Optimizer:
    def __init__(self, target_file="engine.py"):
        self.target_file = target_file
        self.teacher = Teacher()
        self.intro = Introspection("src")
        # ImmuneSystem handles the backup/restore/test cycle

    def evolve(self):
        print(f"\n[EVOLUTION] 🧬 Starting Evolution Cycle for {self.target_file}...")
        
        # 1. Introspection
        print("[EVOLUTION] 👁️  Reading Source Code...")
        original_code = self.intro.read_module_source(self.target_file)
        if "[ERROR]" in original_code:
            print(original_code)
            return

        # 2. Consultation (The "Teacher")
        print("[EVOLUTION] 🧠 Consulting Teacher for Optimization (Focus: Speed)...")
        optimized_code = self.teacher.suggest_optimization(original_code, focus="speed and minimalism")
        
        if not optimized_code or len(optimized_code) < 10:
            print("[EVOLUTION] ⚠️ Teacher returned invalid code.")
            return

        # 3. Mutation (The "Gene Editing")
        print(f"[EVOLUTION] 💉 Applying Mutation ({len(original_code)} -> {len(optimized_code)} chars)...")
        
        # IMMUNE SYSTEM ENGAGED
        # We need to write the file, BUT inside the ImmuneSystem context.
        # The ImmuneSystem doesn't write for us, it just backups and monitors.
        # We must perform the write operation inside the 'with' block.
        
        target_path = os.path.join("src", self.target_file)
        
        with ImmuneSystem() as immune:
            # Dangerous Operation: Overwrite 'Brain'
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(optimized_code)
            
            print("[EVOLUTION] 📝 Code Rewritten. Testing Survival...")
            # Upon exit, ImmuneSystem will triggering Integrity Checks.
            # If they fail, it rolls back.
            
        print("[EVOLUTION] 🏁 Evolution Cycle Complete.")

if __name__ == "__main__":
    opt = Optimizer()
    opt.evolve()
