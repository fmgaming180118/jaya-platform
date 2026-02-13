import asyncio
from src.evolution.twin import DigitalTwin

async def test_twin_sandbox():
    print("Initializing Twin...")
    twin = DigitalTwin()
    
    code = """
import math
print(f"Hello from the Sandbox! PI is {math.pi}")
"""
    print("Running Experiment...")
    await twin.experiment(code)
    
    print("Checking Memory...")
    thoughts = twin.memory.get_recent_thoughts(1)
    print(f"Last Thought: {thoughts[0]['content']}")

if __name__ == "__main__":
    asyncio.run(test_twin_sandbox())
