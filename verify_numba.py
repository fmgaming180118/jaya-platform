
import time
from numba import jit
import random

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
    print(f"    - Pure Python: {py_time:.4f}s")
    
    # 2. Numba (First run includes compilation overhead)
    start = time.time()
    numba_task(N)
    jit_compile_time = time.time() - start
    print(f"    - Numba (Compile+Run): {jit_compile_time:.4f}s")
    
    # 3. Numba (Second run is pure machine code)
    start = time.time()
    numba_task(N)
    jit_run_time = time.time() - start
    print(f"    - Numba (Cached): {jit_run_time:.4f}s")
    
    speedup = py_time / jit_run_time
    print(f"\n[*] SPEEDUP FACTOR: {speedup:.1f}x FASTER 🚀")

if __name__ == "__main__":
    run_test()
