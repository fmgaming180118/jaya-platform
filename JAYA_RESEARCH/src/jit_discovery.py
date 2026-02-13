
import os
import sys
import time
import random
from numba import jit
from optimizer import Optimizer
from immune_system import ImmuneSystem
from memory import DiscoveryMemory

class NativeDiscovery(Optimizer):
    def __init__(self, target_file="engine.py"):
        super().__init__(target_file)
        self.discovery_dir = os.path.join("data", "discoveries_native")
        os.makedirs(self.discovery_dir, exist_ok=True)
        # Point to data/native_memory.json
        self.memory = DiscoveryMemory(os.path.join("data", "native_memory.json"))

    def suggest_native_optimization(self, code_snippet):
        """
        Asks specifically for NUMBA / LLVM Compatible Python code.
        """
        prompt = f"""
        You are the Compiler for the AI-Native Language.
        Translate the following Abstract Logic (Python) into the **AI-Native Language** (Numba/LLVM Machine Code).
        
        GOAL: Create a binary-compatible function that runs at C++ speeds.
        
        RULES:
        1. Import `from numba import jit, float64, int64`.
        2. Decorate core computational functions with `@jit(nopython=True)`.
        3. **Strict Typing**: The AI-Native language uses C-types (float, int), no dynamic Python objects.
        4. **CPU Awareness**: Optimize for **Instruction Level Parallelism (ILP)** and **CPU Cycles**. saturate the pipeline.
        5. **Micro-Arch Tune**:
            - **Loop Unrolling**: Manually unroll small loops.
            - **Register Pressure**: Use local variables wisely to stay in registers.
            - **SIMD**: Hints to help LLVM auto-vectorize.
        6. **Memory Efficiency**: Use static arrays or simple loops. Avoid Python list allocations.
        7. Keep the class structure, but move heavy logic into standalone JIT functions.
        
        CODE TO TRANSLATE:
        {code_snippet}
        
        Return ONLY the Raw Python Code.
        """
        seed = f"# Native Seed: {random.randint(0, 100000)}"
        return self.teacher.suggest_optimization(code_snippet + "\n" + seed, focus="AI-Native Compilation")

    def run_ascension(self, max_epochs=10):
        print(f"\n[ASCENSION] 🚀 Starting JIT Optimization Loop (Max Epochs: {max_epochs})...")
        
        for epoch in range(1, max_epochs + 1):
            print(f"\n--- Epoch {epoch}/{max_epochs} ---")
            
            # 1. Introspection
            original_code = self.intro.read_module_source(self.target_file)
            
            # 2. Native Mutation
            print("[ASCENSION] ⚡ Compiling to new language (LLVM via Numba)...")
            mutation = self.suggest_native_optimization(original_code)
            
            if not mutation or len(mutation) < 100:
                print("[ASCENSION] ⚠️  Empty mutation. Skipping.")
                continue

            if self.memory.seen_before(mutation):
                print("[ASCENSION] 🧠 Memory: Tried this before. Skipping.")
                continue

            # 3. Apply & Test
            target_path = os.path.join("src", self.target_file)
            
            # We intentionally overwrite for testing, protected by Immune System
            with ImmuneSystem() as immune:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(mutation)
                
                # Verify it survives Integrity Check
                pass
            
            # Check if accepted
            with open(target_path, "r", encoding="utf-8") as f:
                current_content = f.read()
                
            if current_content == mutation:
                print("[ASCENSION] ✅ Native Code survived Integrity Check!")
                
                self.memory.add_experience(mutation, "SUCCESS_NATIVE", score=0.0) 
            
                timestamp = int(time.time())
                filename = f"engine_jit_v{epoch}_{timestamp}.py"
                save_path = os.path.join(self.discovery_dir, filename)
                
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(mutation)
                    
                print(f"[ASCENSION] 🏆 NATIVE DISCOVERY SAVED: {save_path}")
            else:
                print("[ASCENSION] ❌ Native Code failed Integrity/Compilation.")
                self.memory.add_experience(mutation, "FAIL_NATIVE")

if __name__ == "__main__":
    lab = NativeDiscovery()
    if len(sys.argv) > 1 and sys.argv[1] == "--forever":
         while True:
             lab.run_ascension(max_epochs=1)
    else:
        lab.run_ascension(max_epochs=5)
