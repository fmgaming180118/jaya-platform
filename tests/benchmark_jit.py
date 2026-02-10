
import time
import random
import os
import sys

# Add parent directory to sys.path to allow importing from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine import Value as ValuePy
from src.engine_jit import Value as ValueJit


def benchmark_engine(name, ValueClass, iterations=1000):
    print(f"\nDistilling {name}...")
    start = time.time()
    for _ in range(iterations):
        a = ValueClass(0.5)
        b = ValueClass(0.2)
        c = (a + b).tanh()
        d = (c * a).relu()
        e = d.log()
        e.backward()
    end = time.time()
    print(f"[{name}] Time: {end - start:.4f}s")
    return end - start

if __name__ == "__main__":
    print("[BENCHMARK] ⚔️  Python vs Numba JIT ⚔️")
    
    # Warmup Numba
    benchmark_engine("Numba (Warmup)", ValueJit, 100)
    
    N = 5000
    t_py = benchmark_engine("Pure Python", ValuePy, N)
    t_jit = benchmark_engine("Numba JIT", ValueJit, N)
    
    speedup = t_py / t_jit
    print(f"\n[RESULT] 🏆 Speedup: {speedup:.2f}x")
