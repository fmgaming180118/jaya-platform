
import json
import os
import sys
from sandbox import Sandbox

# Ensure import path
sys.path.append(os.path.dirname(__file__))

def test_dataset_execution():
    path = os.path.join(os.path.dirname(__file__), '..', 'data', 'seed_dataset.json')
    if not os.path.exists(path):
        print(f"[!] Data not found at {path}")
        return

    with open(path, "r") as f:
        data = json.load(f)

    sb = Sandbox()
    
    print(f"[*] Testing execution of {len(data)} dataset samples...")
    
    success_count = 0
    
    for i, item in enumerate(data):
        print(f"\n--- Sample {i+1}: {item['input_logic']} ---")
        llvm_ir = item['output_llvm']
        
        # LLVM IR from NIM often lacks a 'main' function if it's just a library function like 'add'.
        # We need to wrap it in a C main that calls it, OR try to compile it as an object and link.
        # But 'run_llvm_ir' expects a standalone executable by default in my simple implementation.
        
        # Strategy:
        # 1. Check if 'define i32 @main' exists.
        # 2. If not, create a wrapper C file that declares the function and calls it.
        # 3. Compile wrapper + llvm_ir.
        
        # For this test, let's just Try directly. If it fails due to missing main, we know why.
        # Many LLVM IR examples from LLMs include a main if asked, but I asked for "only the function".
        
        # Let's verify what we have.
        if "define" not in llvm_ir:
            print("[!] Invalid LLVM IR")
            continue
            
        # Create a simple C wrapper if it's 'add'
        if "def add" in item['input_logic']:
             # Create a C wrapper
             wrapper_c = """
             #include <stdio.h>
             // Declare the LLVM function
             int add(int a, int b);
             
             int main() {
                 int result = add(10, 20);
                 printf("Result: %d", result);
                 return 0;
             }
             """
             # Save wrapper
             wrapper_path = os.path.join(sb.work_dir, "wrapper.c")
             with open(wrapper_path, "w") as f:
                 f.write(wrapper_c)
                 
             # Save LLVM
             ll_path = os.path.join(sb.work_dir, "lib.ll")
             with open(ll_path, "w") as f:
                 f.write(llvm_ir)
                 
             # Compile: clang wrapper.c lib.ll -o out.exe
             print("[*] Compiling Wrapper + LLVM...")
             exe_path = os.path.join(sb.work_dir, "test_add.exe")
             cmd = [sb.clang_path, wrapper_path, ll_path, "-o", exe_path, "-Wno-override-module"]
             
             import subprocess
             res = subprocess.run(cmd, capture_output=True, text=True)
             
             if res.returncode != 0:
                 print(f"[FAIL] Compile Error: {res.stderr}")
                 continue
                 
             # Run
             run_res = subprocess.run([exe_path], capture_output=True, text=True)
             print(f"[*] Output: {run_res.stdout}")
             if "Result: 30" in run_res.stdout:
                 print("[SUCCESS] Execution Verified!")
                 success_count += 1
             else:
                 print("[FAIL] Wrong Result")
                 
        else:
             print("[*] Skipping non-add test for now (need specific wrappers)")
             
    print(f"\n[SUMMARY] Verified {success_count} executable samples.")

if __name__ == "__main__":
    test_dataset_execution()
