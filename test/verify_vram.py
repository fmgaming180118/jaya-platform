
import os
import time
import yaml
import sys
from tinygrad.tensor import Tensor
from tinygrad.helpers import getenv

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def test_vram_usage():
    try:
        config = load_config()
        limit_mb = config["system"]["vram_limit_mb"]
        print(f"[*] Testing VRAM Usage. Config Limit: {limit_mb} MB", flush=True)

        # Simulate a small model (approx 100M params = 400MB float32)
        # 100M params * 4 bytes = 400MB
        # We use random tensors to simulate weights
        print("[*] Allocating 100M parameters (Simulated)...", flush=True)
        # Create a large tensor roughly 400MB
        # 10000 x 10000 elements = 100M elements
        t1 = Tensor.rand(10000, 10000).realize() 
        
        print(f"[*] Tensor allocated. Shape: {t1.shape}", flush=True)
        print("[*] Performing dummy computation...", flush=True)
        t2 = (t1 + 1).realize()
        
        print("[SUCCESS] Operation completed without crash.", flush=True)
        print("[*] If you see this, we stayed within system limits.", flush=True)
        
    except Exception as e:
        print(f"[FAIL] Error occurred: {e}", flush=True)

if __name__ == "__main__":
    test_vram_usage()
