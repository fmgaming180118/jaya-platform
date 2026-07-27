import sys
import os
import time
import asyncio
import pytest
from pathlib import Path

# Configure sys.stdout to handle UTF-8 printing in Windows terminals
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add project root and src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from src.evolution.twin import DigitalTwin, TwinState
from src.optimizer import Optimizer

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

async def test_ram_monitoring():
    print("\n--- 1. Testing RAM Monitoring & Garbage Collection ---")
    twin = DigitalTwin()
    
    import psutil
    process = psutil.Process(os.getpid())
    current_ram = process.memory_info().rss / 1024 / 1024
    print(f"[*] Process RSS Memory: {current_ram:.2f} MB")
    
    # Run a single cycle of the twin
    print("[*] Running DigitalTwin.cycle() once...")
    await twin.cycle()
    print("[*] Cycle completed successfully.")

async def test_resource_optimization_evolution():
    print("\n--- 2. Testing Otonom Resource Optimization Evolve Cycle ---")
    opt = Optimizer(target_file="engine.py")
    
    # We will run an evolve cycle on engine.py with JIT/memory footprint focus
    print("[*] Starting Optimizer evolution on engine.py...")
    success = opt.evolve(target_file="engine.py", focus="speed, JIT compiler integration via Numba, and minimal memory overhead")
    
    print(f"[*] Evolution finished. Status: {success}")
    if success:
        print("[*] SUCCESS: Engine evolved and validated successfully by ImmuneSystem!")
    else:
        print("[!] FAILED: Evolution failed or was rolled back.")

async def main():
    print("=" * 60)
    print("JAYA Research - Resource-Aware Self-Evolution Verification Suite")
    print("=" * 60)
    
    await test_ram_monitoring()
    await test_resource_optimization_evolution()
    
    print("\n" + "=" * 60)
    print("All verification tests finished!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
