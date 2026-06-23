import os
import json
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from src.evolution.crucible import Crucible

def test_crucible_success():
    crucible = Crucible(workspace_id="pytest_env")
    
    # A simple script that calculates something and outputs JSON metrics
    python_code = """
import json
def calc():
    return {"accuracy": 0.99, "status": "ok"}
print(json.dumps(calc()))
"""
    
    success, log, metrics = crucible.run_experiment("Test Math", python_code, timeout_seconds=5)
    
    assert success is True
    assert "accuracy" in metrics
    assert metrics["accuracy"] == 0.99
    assert metrics["status"] == "ok"

def test_crucible_syntax_error():
    crucible = Crucible(workspace_id="pytest_env")
    
    # Intentionally broken code
    python_code = """
import json
def calc()
    return {"accuracy": 0.99}
print(json.dumps(calc()))
"""
    
    success, log, metrics = crucible.run_experiment("Test Broken Code", python_code, timeout_seconds=5)
    
    assert success is False
    assert "SyntaxError" in log

def test_crucible_timeout():
    crucible = Crucible(workspace_id="pytest_env")
    
    # Infinite loop
    python_code = """
import time
while True:
    time.sleep(0.1)
"""
    
    success, log, metrics = crucible.run_experiment("Test Timeout", python_code, timeout_seconds=1)
    
    assert success is False
    assert "Timeout expired" in log

if __name__ == "__main__":
    print("Running Crucible Sandbox tests...")
    try:
        print("\n1. Testing crucible success...")
        test_crucible_success()
        print("=> Success!")
        
        print("\n2. Testing crucible syntax error...")
        test_crucible_syntax_error()
        print("=> Success!")
        
        print("\n3. Testing crucible timeout...")
        test_crucible_timeout()
        print("=> Success!")
        
        print("\nAll Crucible tests passed successfully!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        import sys
        sys.exit(1)
