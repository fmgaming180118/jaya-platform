
import time
import os
import sys

from engine import Value
# from engine_candidate import Value # Toggle this to test candidate

import random

def benchmark_operation(name, operation, iterations=1000):
    start = time.time()
    for _ in range(iterations):
        operation()
    end = time.time()
    return (end - start)

def run_benchmark():
    print(f"[BENCHMARK] 🏎️  Running Performance Tests (Iterations=1000)...")
    
    # Test 1: Forward Pass (Addition/Mult)
    def test_forward():
        a = Value(random.random())
        b = Value(random.random())
        c = a * b + a
        return c.data
    
    t_fwd = benchmark_operation("Forward", test_forward, 5000)
    print(f"[BENCHMARK] Forward Pass (5k ops): {t_fwd:.4f}s")
    
    # Test 2: Backward Pass
    def test_backward():
        a = Value(0.5)
        b = Value(0.2)
        c = a * b
        d = c.exp()
        d.backward()
        
    t_bwd = benchmark_operation("Backward", test_backward, 2000)
    print(f"[BENCHMARK] Backward Pass (2k ops): {t_bwd:.4f}s")
    
    # Test 3: Complex Graph
    def test_complex():
        a = Value(0.5)
        b = Value(0.2)
        c = (a + b).tanh()
        d = (c * a).relu()
        e = d.log()
        e.backward()
        
    t_cplx = benchmark_operation("Complex", test_complex, 1000)
    print(f"[BENCHMARK] Complex Graph (1k ops): {t_cplx:.4f}s")
    
    total_time = t_fwd + t_bwd + t_cplx
    print(f"[BENCHMARK] 🏁 Total Score (Lower is Better): {total_time:.4f}s")
    
    # Save result to history
    with open("benchmark_history.txt", "a") as f:
        f.write(f"{time.time()},{total_time}\n")

if __name__ == "__main__":
    run_benchmark()
