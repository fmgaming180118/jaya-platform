"""
The Crucible - Advanced Simulation Sandbox for Autonomous Discovery
Unlike the standard Sandbox which just tests existing mutator changes,
The Crucible allows the Digital Twin to write entirely new experimental
Python scripts (e.g., simulating a new math formula), run them safely,
and extract empirical metrics to prove or disprove a hypothesis.
"""
import os
import sys
import uuid
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

class Crucible:
    def __init__(self, workspace_id: str = "default"):
         self.workspace_id = workspace_id
         # Base directory for crucible experiments
         # Using JAYA_RESEARCH/data/crucible
         self.base_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent / "data" / "crucible" / workspace_id
         self.base_dir.mkdir(parents=True, exist_ok=True)
         
    def get_experiment_dir(self, exp_id: str) -> Path:
         return self.base_dir / exp_id
         
    def run_experiment(self, hypothesis: str, python_code: str, timeout_seconds: int = 60) -> Tuple[bool, str, Dict[str, Any]]:
         """
         Writes the generated python_code to a temporary file and executes it.
         The python_code MUST print a JSON object at the end containing its results.
         """
         exp_id = f"exp_{uuid.uuid4().hex[:8]}"
         exp_dir = self.get_experiment_dir(exp_id)
         exp_dir.mkdir(parents=True, exist_ok=True)
         
         print(f"[CRUCIBLE] Preparing experiment {exp_id}...")
         
         # Write script
         script_path = exp_dir / "simulation.py"
         with open(script_path, "w", encoding="utf-8") as f:
             f.write(python_code)
             
         # Write hypothesis manifest
         manifest_path = exp_dir / "manifest.json"
         with open(manifest_path, "w", encoding="utf-8") as f:
             json.dump({"hypothesis": hypothesis}, f)
             
         print(f"[CRUCIBLE] Igniting {exp_id} (Timeout: {timeout_seconds}s)")
         
         # Execute
         try:
             result = subprocess.run(
                 [sys.executable, str(script_path)],
                 cwd=str(exp_dir),
                 capture_output=True,
                 text=True,
                 timeout=timeout_seconds
             )
             
             stdout = result.stdout
             stderr = result.stderr
             
             if result.returncode != 0:
                 print(f"[CRUCIBLE] Experiment failed: {stderr}")
                 return False, f"Execution failed with return code {result.returncode}.\nStderr: {stderr}", {}
                 
             # Try to parse the last line of stdout as JSON metrics
             metrics = {}
             lines = [line.strip() for line in stdout.split('\n') if line.strip()]
             if lines:
                  last_line = lines[-1]
                  try:
                      metrics = json.loads(last_line)
                  except json.JSONDecodeError:
                      # If it didn't print strict JSON at the end, just return all stdout
                      metrics = {"raw_output": stdout}
             
             print(f"[CRUCIBLE] Experiment {exp_id} completed successfully.")
             return True, stdout, metrics
             
         except subprocess.TimeoutExpired:
             print("[CRUCIBLE] Experiment timed out.")
             return False, "Timeout expired during simulation.", {}
         except Exception as e:
             print(f"[CRUCIBLE] Unexpected error: {e}")
             return False, f"Unexpected error: {str(e)}", {}

if __name__ == "__main__":
    # Test Crucible
    crucible = Crucible(workspace_id="test")
    test_code = """
import json
import time

def simulate():
    time.sleep(1)
    return {"accuracy": 0.95, "loss": 0.05, "novelty_score": 0.8}

results = simulate()
print("Simulation complete.")
print(json.dumps(results))
"""
    success, log, metrics = crucible.run_experiment("Test Hypothesis", test_code)
    print(f"Success: {success}")
    print(f"Metrics: {metrics}")
