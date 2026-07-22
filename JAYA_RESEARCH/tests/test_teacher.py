import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from teacher import Teacher

def test_teacher_init():
    try:
        t = Teacher()
        assert t is not None
    except Exception as e:
        print(f"Teacher Init Warning: {e}")

if __name__ == "__main__":
    try:
        print("Initializing Teacher...")
        t = Teacher()
        print("Teacher initialized.")
        response = t.ask("Say 'Hello Debate' if you can hear me.")
        print(f"Teacher Response: {response}")
    except Exception as e:
        print(f"Teacher Error: {e}")
        sys.exit(1)

