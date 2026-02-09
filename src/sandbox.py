
import subprocess
import os
import time
import tempfile
import sys

class Sandbox:
    def __init__(self, work_dir="sandbox_env"):
        self.work_dir = work_dir
        os.makedirs(self.work_dir, exist_ok=True)
        # Try full paths first, fallback to short names
        self.clang_path = r"C:\Program Files\LLVM\bin\clang.exe"
        if not os.path.exists(self.clang_path):
            self.clang_path = "clang"
            
        self.gcc_path = r"C:\mingw64\bin\gcc.exe"
        if not os.path.exists(self.gcc_path):
            self.gcc_path = "gcc"

    def run_llvm_ir(self, llvm_code, func_name="main"):
        """
        Compiles and runs LLVM IR code.
        Requires 'clang' to be in PATH.
        """
        # 1. Write LLVM IR to file
        ll_path = os.path.join(self.work_dir, f"{func_name}.ll")
        exe_path = os.path.join(self.work_dir, f"{func_name}.exe")
        
        with open(ll_path, "w") as f:
            f.write(llvm_code)

        # 2. Compile: clang input.ll -o output.exe
        # Note: We need a wrapper main function in C if the LLVM IR is just a function (like 'add')
        # But if it's a full program, we can compile directly.
        # For now, let's assume it's a full program or we provide a wrapper.
        
        # Checking if raw compile works
        compile_cmd = [self.clang_path, ll_path, "-o", exe_path, "-Wno-override-module"]
        
        try:
            start_compile = time.time()
            result = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=10)
            compile_time = time.time() - start_compile
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "stage": "compile",
                    "error": result.stderr,
                    "exit_code": result.returncode
                }

            # 3. Run
            start_run = time.time()
            if not os.path.exists(exe_path):
                 return {"success": False, "error": "Executable not created"}

            run_result = subprocess.run([exe_path], capture_output=True, text=True, timeout=5)
            run_time = time.time() - start_run

            return {
                "success": run_result.returncode == 0,
                "stage": "runtime",
                "output": run_result.stdout.strip(),
                "error": run_result.stderr,
                "compile_time": compile_time,
                "run_time": run_time
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Execution Timed Out (Limit 5s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_c_code(self, c_code, filename="generated"):
        c_path = os.path.join(self.work_dir, f"{filename}.c")
        exe_path = os.path.join(self.work_dir, f"{filename}.exe")
        
        with open(c_path, "w") as f:
            f.write(c_code)
            
        compile_cmd = [self.gcc_path, c_path, "-o", exe_path]
        
        try:
            res = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                 return {"success": False, "stage": "compile", "error": res.stderr}
            
            if not os.path.exists(exe_path):
                 return {"success": False, "error": "Executable not created"}

            run_res = subprocess.run([exe_path], capture_output=True, text=True, timeout=5)
            return {
                "success": run_res.returncode == 0,
                "output": run_res.stdout.strip(),
                "error": run_res.stderr
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # Test
    sb = Sandbox()
    
    # Test C Code (Simple)
    c_code = """
    #include <stdio.h>
    int main() {
        printf("Hello from Micro-AGI Sandbox!");
        return 0;
    }
    """
    print("[*] Testing GCC...")
    res = sb.run_c_code(c_code)
    print(res)

    # Test LLVM IR (Simple Helper)
    # Note: Running pure LLVM IR requires a main entry point.
    # We will skip complex LLVM test here unless user provides valid IR.
