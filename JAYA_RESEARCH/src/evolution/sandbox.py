import subprocess
import sys
import os
import time
from pathlib import Path
from typing import Dict, Any, Tuple

class EvolutionSandbox:
    """
    A safe execution environment for the Digital Twin.
    Ensures that AI generated code can only run within specific bounds.
    For this MVP, we enforce that code operations happen in `src/playground`.
    """
    def __init__(self, playground_dir="src/playground"):
        self.playground_dir = Path(playground_dir)
        self.playground_dir.mkdir(parents=True, exist_ok=True)

    def write_experiment(self, filename: str, code: str) -> Path:
        """Writes AI code to the playground."""
        # Security check: Prevent path traversal
        if ".." in filename or filename.startswith("/"):
            raise ValueError("Security Violation: Cannot write outside playground.")
        
        target_path = self.playground_dir / filename
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(code)
        return target_path

    def run_code(self, code: str, timeout=10) -> Dict[str, Any]:
        """
        Writes and executes Python code in the sandbox environment.
        """
        temp_name = f"temp_exp_{int(time.time() * 1000)}.py"
        try:
            target = self.write_experiment(temp_name, code)
            success, output = self.run_experiment(temp_name, timeout=timeout)
            return {
                "success": success,
                "output": output,
                "error": "" if success else output
            }
        except Exception as e:
            return {"success": False, "error": str(e), "output": str(e)}
        finally:
            self.cleanup(temp_name)

    def run_experiment(self, filename: str, timeout=10) -> Tuple[bool, str]:
        """
        Runs a script from the playground in a separate subprocess.
        Returns: (success: bool, output: str)
        """
        target_path = self.playground_dir / filename
        if not target_path.exists():
            return False, "File not found."

        try:
            # Run in a separate process
            result = subprocess.run(
                [sys.executable, str(target_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.playground_dir) # Isolate execution cwd
            )
            
            output = result.stdout + result.stderr
            success = result.returncode == 0
            return success, output

        except subprocess.TimeoutExpired:
            return False, "Execution Timed Out (Safety Limit Reached)."
        except Exception as e:
            return False, f"System Error: {str(e)}"

    def cleanup(self, filename: str):
        """Removes an experiment file."""
        target_path = self.playground_dir / filename
        if target_path.exists():
            target_path.unlink()
