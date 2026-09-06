
import sys
import os
import math

# Ensure import path
sys.path.append(os.path.dirname(__file__))

from jaya_research.engine import Value

def test_sanity():
    """Basic 1+1=2 check"""
    a = Value(1.0)
    b = Value(1.0)
    c = a + b
    if abs(c.data - 2.0) > 1e-6:
        print(f"[FAIL] Sanity Check: 1+1 != 2 (Got {c.data})")
        return False
    return True

def test_gradient_simple():
    """
    f(x) = x^2
    f'(x) = 2x
    at x=3, f'(x)=6
    """
    x = Value(3.0)
    y = x * x # x^2
    y.backward()
    
    if abs(x.grad - 6.0) > 1e-6:
        print(f"[FAIL] Gradient Check (Simple): Expected 6.0, Got {x.grad}")
        return False
    return True

def test_gradient_complex():
    """
    f(a,b) = (a+b) * a
    grad_a = 2a + b
    grad_b = a
    at a=2, b=3:
    grad_a = 4+3=7
    grad_b = 2
    """
    a = Value(2.0)
    b = Value(3.0)
    c = (a + b) * a
    c.backward()
    
    ok = True
    if abs(a.grad - 7.0) > 1e-6:
        print(f"[FAIL] Gradient Check (Complex) a.grad: Expected 7.0, Got {a.grad}")
        ok = False
    if abs(b.grad - 2.0) > 1e-6:
        print(f"[FAIL] Gradient Check (Complex) b.grad: Expected 2.0, Got {b.grad}")
        ok = False
    return ok

def test_activation_relu():
    """Relu check"""
    a = Value(-1.0)
    b = a.relu()
    if b.data != 0.0:
        print(f"[FAIL] RELU(-1) != 0")
        return False
        
    c = Value(2.0)
    d = c.relu()
    if d.data != 2.0:
        print(f"[FAIL] RELU(2) != 2")
        return False
        
    # Grad
    # d/dx ReLU(x) at 2.0 is 1.0
    d.backward()
    if c.grad != 1.0:
        print(f"[FAIL] RELU Grad mismatch")
        return False
    return True

def run_integrity_suite():
    print("[*] Running Integrity Suite (The Sempoa Test)...")
    tests = [
        test_sanity,
        test_gradient_simple,
        test_gradient_complex,
        test_activation_relu
    ]
    
    passed = 0
    for t in tests:
        try:
            if t():
                passed += 1
            else:
                print(f"[!] Test {t.__name__} FAILED")
        except Exception as e:
            print(f"[!] Test {t.__name__} CRASHED: {e}")
            
    total = len(tests)
    print(f"[*] Result: {passed}/{total} Passed")
    
    return passed == total

if __name__ == "__main__":
    success = run_integrity_suite()
    if not success:
        sys.exit(1)
