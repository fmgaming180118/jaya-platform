
import os
import sys
import time
from teacher import Teacher
from introspection import Introspection
from immune_system import ImmuneSystem

class Optimizer:
    def __init__(self, target_file="engine.py"):
        self.default_target = target_file
        self.teacher = Teacher()
        self.intro = Introspection("src")
        # ImmuneSystem handles the backup/restore/test cycle

    def evolve(self, target_file=None, focus="speed, memory footprint reduction, and Numba JIT optimization"):
        target = target_file or self.default_target
        print(f"\n[EVOLUTION] 🧬 Starting Evolution Cycle for {target}...")
        
        # 1. Introspection
        print("[EVOLUTION] 👁️  Reading Source Code...")
        original_code = self.intro.read_module_source(target)
        if "[ERROR]" in original_code:
            print(original_code)
            return False

        # 2. Consultation (The "Teacher")
        print(f"[EVOLUTION] 🧠 Consulting Teacher for Optimization (Focus: {focus})...")
        optimized_code = self.teacher.suggest_optimization(original_code, focus=focus)
        
        if not optimized_code or len(optimized_code) < 10:
            print("[EVOLUTION] ⚠️ Teacher returned invalid code.")
            return False

        # 3. Mutation (The "Gene Editing")
        print(f"[EVOLUTION] 💉 Applying Mutation ({len(original_code)} -> {len(optimized_code)} chars)...")
        
        # Determine path
        if target.startswith("src/") or target.startswith("src\\"):
            target_path = target
        else:
            target_path = os.path.join("src", target)
            
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        try:
            with ImmuneSystem() as immune:
                # Dangerous Operation: Overwrite 'Brain'
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(optimized_code)
                
                print("[EVOLUTION] 📝 Code Rewritten. Testing Survival...")
                # Upon exit, ImmuneSystem will trigger Integrity Checks.
                # If they fail, it rolls back.
                
            if not immune.passed:
                print("[EVOLUTION] ❌ Evolution failed validation.")
                return False
                
            print("[EVOLUTION] 🏁 Evolution Cycle Complete.")
            return True
        except Exception as e:
            print(f"[EVOLUTION] ❌ Evolution error: {e}")
            return False

if __name__ == "__main__":
    opt = Optimizer()
    opt.evolve()
