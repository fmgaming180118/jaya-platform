from config import config

import os
import time
import json
import sys

# Add src to path to allow imports when running from root
sys.path.append(os.path.join(os.getcwd(), 'src'))
# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

from teacher import Teacher

# Definisikan apa yang ingin kita ajarkan ke AI kecil
LOGIC_SAMPLES = [
    "def add(a, b): return a + b",
    "def subtract(a, b): return a - b",
    "def multiply(a, b): return a * b",
    "def divide(a, b): return a / b if b != 0 else 0",
    "def square(x): return x * x",
    "def is_even(x): return x % 2 == 0",
    "def get_max(a, b): return a if a > b else b",
    "def loop_sum(n): total = 0; for i in range(n): total += i; return total"
]

def generate_dataset():
    try:
        teacher = Teacher()
        print("[*] Teacher Connected. Starting lesson...")
        
        dataset = []
        
        for logic in LOGIC_SAMPLES:
            print(f"\n[*] Asking Teacher to convert: {logic}")
            
            # Minta Guru konversi ke LLVM IR
            prompt = f"""
            Act as an expert compiler. Convert the following Python logic into optimized LLVM IR (Intermediate Representation).
            Output ONLY the LLVM IR code within a code block. No explanation.
            
            Logic:
            {logic}
            """
            
            llvm_ir = teacher.ask(prompt, system_instruction="You are a strict LLVM IR compiler.")
            print(f"    -> Received LLVM IR ({len(llvm_ir)} chars)")
            
            # Simpan ke dataset
            entry = {
                "input_logic": logic,
                "output_llvm": llvm_ir,
                "timestamp": time.time()
            }
            dataset.append(entry)
            
            # Hindari Rate Limit
            time.sleep(1)
            
        # Simpan ke file
        os.makedirs("data", exist_ok=True)
        with open(config.SEED_DATASET_PATH, "w") as f:
            json.dump(dataset, f, indent=2)
            
        print("\n[SUCCESS] Dataset generated at data/seed_dataset.json")
        
    except Exception as e:
        print(f"[FAIL] Error: {e}")

if __name__ == "__main__":
    generate_dataset()
