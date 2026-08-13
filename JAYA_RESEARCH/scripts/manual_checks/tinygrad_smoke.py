
"""Manual optional Tinygrad smoke check; excluded from the offline unit suite."""

import os
os.environ["DEFAULT_DEVICE"] = "CPU" # Force CPU for testing

import tinygrad
from tinygrad.tensor import Tensor
from tinygrad.nn.optim import Adam

print(f"Tinygrad Version: {getattr(tinygrad, '__version__', 'Unknown')}")

try:
    print("1. Tensor Creation")
    # Make sure we realize them
    x = Tensor([1.0, 2.0], requires_grad=True).realize()
    y = Tensor([3.0, 4.0]).realize()
    
    print("2. Forward")
    z = (x * y).sum()
    z.realize()
    print(f"   Z val: {z.numpy()}")
    
    print("3. Backward")
    z.backward()
    
    # Check grad
    # x.grad is lazy, need to realize
    if x.grad is not None:
        x.grad.realize()
        print(f"   Grad: {x.grad.numpy()}")
    else:
        print("   Grad is None!")
    
    print("4. Optimizer")
    optim = Adam([x], lr=0.1)
    optim.zero_grad()
    optim.step()
    x.realize()
    print(f"   X new: {x.numpy()}")
    
    print("[SUCCESS] Tinygrad basic loop works.")
except Exception as e:
    print(f"[FAIL] {e}")
    import traceback
    traceback.print_exc()
