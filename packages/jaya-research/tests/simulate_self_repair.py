import asyncio
import os
from jaya_research.evolution.twin import DigitalTwin

async def simulate_repair():
    print("--- Starting Self-Repair Simulation ---")
    
    # 1. Create a buggy file
    buggy_code = """
def calculate_average(numbers):
    total = sum(numbers)
    # BUG: Division by zero if list is empty, and raw exception unsafeness
    return total / len(numbers)

print(calculate_average([]))
"""
    buggy_path = "src/playground/buggy_script.py"
    with open(buggy_path, "w") as f:
        f.write(buggy_code)
    print(f"[Setup] Created {buggy_path} with a bug.")

    # 2. Init Twin
    twin = DigitalTwin()
    
    # 3. Inject "Command" into thought process (forcing it to evolve)
    # We do this by calling evolve() directly for the test, 
    # to simulate the Twin deciding to do it.
    instruction = "Fix the division by zero error in calculate_average"
    
    print(f"[Twin] Attempting to fix {buggy_path}...")
    await twin.evolve(buggy_path, instruction)
    
    # 4. Verify Fix
    with open(buggy_path, "r") as f:
        new_code = f.read()
    
    print("\n--- Fixed Code ---")
    print(new_code)
    
    if "if not numbers" in new_code or "if len(numbers) == 0" in new_code or "try:" in new_code:
        print("\n[SUCCESS] The Twin fixed the bug!")
    else:
        print("\n[FAILURE] The bug might still be there.")

if __name__ == "__main__":
    asyncio.run(simulate_repair())
