import os
import sys
import random
import time
import argparse
from optimizer import Optimizer
from immune_system import ImmuneSystem
from memory import DiscoveryMemory

class DigitalTwinCompiler(Optimizer):
    """
    A specific breed of Optimizer that doesn't just optimize code,
    but EVOLVES A NEW COMPILER and SYNTAX.
    """
    def __init__(self, target_file="engine.py"):
        super().__init__(target_file)
        # Separate folder for the "New Language" artifacts
        self.language_dir = os.path.join("data", "language_evolution")
        os.makedirs(self.language_dir, exist_ok=True)
        self.memory = DiscoveryMemory(os.path.join("data", "evolution_memory.json"))

    def evolve_syntax(self, current_syntax_spec, mode="Optimization"):
        """
        Ask the 'Teacher' to invent a more efficient syntax for Autograd.
        """
        radical_prompt = ""
        if mode == "Radical Rewrite":
            radical_prompt = "CRITICAL: IGNORE PREVIOUS CONSTRAINTS. REINVENT THE LANGUAGE FROM SCRATCH. USE UNCONVENTIONAL SYMBOLS AND STRUCTURES."
            
        prompt = f"""
        You are a Programming Language Architect.
        Your goal is to design the SYNTAX for a new language: **JAYA-Native**.
        
        GOAL: The syntax must be concise, expressive, and easily compiled to Machine Code.
        {radical_prompt}
        
        CURRENT SYNTAX SPEC (BNF/Pseudo-code):
        {current_syntax_spec}
        
        TASK:
        1. Analyze the current syntax.
        2. Propose a VASTLY SIMPLIFIED syntax that removes Python overhead.
        3. Introduce "Kernel Primitives" (e.g., `grad_add`, `dot_product`).
        4. Focus on "Data Layout" (structs of arrays vs arrays of structs).
        
        OUTPUT:
        Return the NEW JAYA Syntax Specification.
        """
        seed = f"# Syntax Seed: {random.randint(0, 100000)}"
        return self.teacher.suggest_optimization(current_syntax_spec + "\n" + seed, focus="Language Design")

    def evolve_compiler(self, syntax_spec, current_compiler_code, mode="Optimization"):
        """
        Ask the 'Teacher' to write/improve the Python script that compiles JAYA -> Executable.
        """
        radical_prompt = ""
        if mode == "Radical Rewrite":
            radical_prompt = "CRITICAL: REWRITE THE COMPILER LOGIC COMPLETELY. USE A DIFFERENT ARCHITECTURE (Stack vs Register vs Graph)."

        prompt = f"""
        You are a LLVM Compiler Engineer.
        Write a Python function `compile_jaya(source_code)` that translates the following JAYA Syntax into Numba/LLVM calls.
        {radical_prompt}
        
        SYNTAX SPEC:
        {syntax_spec}
        
        PREVIOUS COMPILER:
        {current_compiler_code}
        
        TASK:
        1. Update the compiler to support the new syntax.
        2. Optimize the emitted code (Loop Unrolling, SIMD).
        3. Handle memory management (Static Allocation).
        
        OUTPUT:
        Return the RAW PYTHON CODE for the compiler.
        """
        seed = f"# Compiler Seed: {random.randint(0, 100000)}"
        return self.teacher.suggest_optimization(current_compiler_code + "\n" + seed, focus="Compiler Engineering")

    def check_correctness(self, compiler_code):
        """
        Verifies that the compiler code is functional and not trivial.
        Returns True if valid, False otherwise.
        """
        # Check 1: Must contain 'compile_jaya' function
        if 'def compile_jaya' not in compiler_code:
            return False
        
        # Check 2: Must not be a trivial stub
        trivial_patterns = [
            "return 'binary_blob'",
            'return "binary_blob"',
            "return ''",
            'return ""',
        ]
        
        # If it's just a simple return statement, it's trivial
        lines = [l.strip() for l in compiler_code.split('\n') if l.strip() and not l.strip().startswith('#')]
        non_def_lines = [l for l in lines if not l.startswith('def ')]
        
        # If there are only 1-2 non-def lines and they match trivial patterns, reject
        if len(non_def_lines) <= 2:
            for pattern in trivial_patterns:
                if any(pattern in line for line in non_def_lines):
                    return False
        
        # Check 3: Try to execute it (basic syntax check)
        try:
            exec_globals = {}
            exec(compiler_code, exec_globals)
            if 'compile_jaya' not in exec_globals:
                return False
            
            # Check 4: Try calling it with a simple input
            compile_func = exec_globals['compile_jaya']
            result = compile_func("x = 1")
            
            # If result is just 'binary_blob' or empty, it's trivial
            if result in ['binary_blob', '', None]:
                return False
                
            return True
        except Exception:
            # If it errors, it's broken
            return False

    def evaluate_variant(self, syntax, compiler):
        """
        Heuristic Scoring Function with Correctness Check.
        In a real twin, this would run benchmarks.
        Here we use 'Code Density' as a proxy for 'Logic Compression'.
        Shorter syntax + Shorter Compiler (usually) = Higher Abstraction/Efficiency.
        """
        len_sys = len(syntax)
        len_comp = len(compiler)
        
        if len_sys == 0 or len_comp == 0:
            return 0.0
        
        # NEW: Functional Correctness Check
        # Prevent "Reward Hacking" where AI writes trivial code to get high brevity score
        if not self.check_correctness(compiler):
            return 0.0  # Penalize broken/trivial code
            
        # Score: Higher is better. 
        # We value semantic density.
        score = (10000.0 / (len_sys + 1)) + (10000.0 / (len_comp + 1))
        return score

    def run_evolution_loop(self, generations=5, forever=False):
        loop_desc = "INFINITE" if forever else f"{generations} Gens"
        print(f"\n[DIGITAL TWIN] 🧬 Starting Language Evolution ({loop_desc})...")
        
        # Initial Seeds: Start with BLOATED code so we have room to optimize.
        current_syntax = "Type: Value { data: f32, grad: f32, prev: List[Value], op: str, label: str, _backward: Callable, creation_time: float, memory_footprint: int, ... } # VERBOSE INITIAL STATE"
        current_compiler = """def compile_jaya(source_code):
    # Bloated tokenizer
    tokens = []
    current = ""
    for c in source_code:
        if c in [' ', '\\n', '\\t']:
            if current:
                tokens.append(current)
                current = ""
        else:
            current += c
    if current:
        tokens.append(current)
    
    # Bloated parser
    ast = [{'type': 'id', 'val': t} for t in tokens]
    
    # Bloated code gen
    lines = ['# JAYA Output']
    for node in ast:
        lines.append(f"# Token: {node['val']}")
    
    return '\\n'.join(lines)
"""
        
        best_score = self.evaluate_variant(current_syntax, current_compiler)
        generation = 1
        
        print(f"[DIGITAL TWIN] 🏁 Baseline Score: {best_score:.2f} (Starting with Bloated v1)")
        
        stagnation_counter = 0
        
        while True:
            if not forever and generation > generations:
                break
                
            print(f"\n--- Generation {generation} (Current Best Score: {best_score:.2f}) ---")
            
            # ADAPTIVE STRATEGY:
            # If we are stuck (stagnation > 5), force a RADICAL mutation.
            mode = "Optimization"
            if stagnation_counter > 5:
                mode = "Radical Rewrite"
                print(f"[DIGITAL TWIN] ⚠️  Stagnation Detected ({stagnation_counter} gens). Forcing RADICAL AI Mutation!")
                
            # 1. Mutation
            print(f"[DIGITAL TWIN] 🔠 Mutating Syntax & Compiler (Mode: {mode})...")
            
            # Inject "Radical" instruction if stagnant
            if mode == "Radical Rewrite":
                # We append a special instruction to the mutation prompt internally
                # (You might need to adjust evolve_syntax signature or just rely on random seed/prompt trick)
                pass 

            new_syntax = self.evolve_syntax(current_syntax, mode=mode)
            new_compiler = self.evolve_compiler(new_syntax, current_compiler, mode=mode)
            
            # 2. Evaluation
            new_score = self.evaluate_variant(new_syntax, new_compiler)
            
            # 3. Selection (Survival of the Fittest + Simulated Annealing)
            # If radical mode, we accept ANY valid change even if score is slightly lower (to escape local optima)
            # But here we stick to strict check for now, unless user wants annealing.
            # Let's keep strict check but rely on the RADICAL mutation to find a BETTER peak.
            
            print(f"[DIGITAL TWIN] 📊 Score: {new_score:.2f} vs Best: {best_score:.2f}")

            # RADICAL ACCEPTANCE: If in Radical Mode, accept anything > 10% of best (to allow escape)
            is_improvement = new_score > best_score
            is_radical_escape = (mode == "Radical Rewrite" and new_score > best_score * 0.1)

            if is_improvement or is_radical_escape:
                if is_radical_escape and not is_improvement:
                     print(f"[DIGITAL TWIN] ☢️  RADICAL ACCEPTANCE! Score is LOWER ({new_score:.2f}) but adopted to escape local optima.")
                else:
                     print(f"[DIGITAL TWIN] 🚀 IMPROVEMENT FOUND! (+{new_score - best_score:.2f}) Adopted.")
                
                best_score = new_score
                current_syntax = new_syntax
                current_compiler = new_compiler
                stagnation_counter = 0 # Reset
                
                # Save to Memory instead of files
                self.memory.add_variant(new_syntax, new_compiler, generation, new_score)
                self.memory.add_experience(new_compiler, "SUCCESS_IMPROVEMENT", score=new_score)
            else:
                stagnation_counter += 1
                print(f"[DIGITAL TWIN] 📉 Regression or Stagnation ({stagnation_counter}). Mutation Discarded.")
            
            generation += 1
            if forever:
                 time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--forever", action="store_true", help="Run indefinitely until stopped.")
    parser.add_argument("--gens", type=int, default=1000, help="Number of generations (Default: 1000).")
    parser.add_argument("--cleanup", action="store_true", help="Delete old evolution files from data/language_evolution/.")
    args = parser.parse_args()
    
    twin = DigitalTwinCompiler()
    
    # Cleanup old files if requested
    if args.cleanup:
        import shutil
        if os.path.exists(twin.language_dir):
            print(f"[DIGITAL TWIN] 🗑️  Cleaning up old files in {twin.language_dir}...")
            shutil.rmtree(twin.language_dir)
            os.makedirs(twin.language_dir, exist_ok=True)
            print(f"[DIGITAL TWIN] ✅ Cleanup complete.")
    
    twin.run_evolution_loop(generations=args.gens, forever=args.forever)
