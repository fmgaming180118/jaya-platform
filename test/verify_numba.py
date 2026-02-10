import random
import sys
import os
import time
from numba import jit

# Add parent directory to sys.path to allow importing from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine import Value

def pure_python_task(n):
    acc = 0.0
    for i in range(n):
        acc += (i ** 0.5) + (i ** 2)
    return acc

@jit(nopython=True)
def numba_task(n):
    acc = 0.0
    for i in range(n):
        acc += (i ** 0.5) + (i ** 2)
    return acc

def run_test():
    N = 10_000_000
    
    print(f"[*] Benchmarking Loop with N={N}...")
    
    # 1. Pure Python
    start = time.time()
    pure_python_task(N)
    py_time = time.time() - start
    py_ops = N / py_time
    print(f"    - Pure Python: {py_time:.4f}s  |  OPS: {py_ops:,.0f} ops/sec")
    
    # 2. Numba (First run includes compilation overhead)
    start = time.time()
    numba_task(N)
    jit_compile_time = time.time() - start
    print(f"    - Numba (Compile+Run): {jit_compile_time:.4f}s")
    
    # 3. Numba (Second run is pure machine code)
    start = time.time()
    numba_task(N)
    jit_run_time = time.time() - start
    jit_ops = N / jit_run_time
    print(f"    - Numba (Cached): {jit_run_time:.4f}s     |  OPS: {jit_ops:,.0f} ops/sec")
    
    speedup = py_time / jit_run_time
    print(f"\n[*] SPEEDUP FACTOR: {speedup:.1f}x FASTER 🚀")
    print(f"[*] OPS GAIN: +{jit_ops - py_ops:,.0f} extra operations per second!")

if __name__ == "__main__":
    run_test()
