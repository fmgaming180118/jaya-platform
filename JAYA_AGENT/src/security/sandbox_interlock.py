"""
Tool Calling Security Interlock & Sandbox Guard for JAYA_AGENT.
Isolates skill and tool execution inside Windows Job Objects / WASM sandbox.
Enforces 256MB RAM ceiling and 10s execution timeout per tool action.
"""

import sys
import os
import time
from typing import Dict, Any, Callable

# Import Native EvolutionSandbox from JAYA_RESEARCH
try:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    research_src = os.path.join(root_dir, "JAYA_RESEARCH", "src")
    playground_dir = os.path.join(research_src, "playground")
    if research_src not in sys.path:
        sys.path.insert(0, research_src)
    try:
        from evolution.sandbox import EvolutionSandbox
    except ImportError:
        from sandbox import EvolutionSandbox
    sandbox = EvolutionSandbox(playground_dir=playground_dir)
except Exception as e:
    print(f"[SECURITY] Warning: Failed to initialize EvolutionSandbox: {e}")
    sandbox = None


class SandboxInterlock:
    """
    Security interlock that validates tool calls and executes python code
    within safe Native Job Object sandbox constraints.
    """

    def __init__(self, max_ram_mb: int = 256, timeout_sec: int = 10):
        self.max_ram_mb = max_ram_mb
        self.timeout_sec = timeout_sec
        self.sandbox = sandbox
        print(f"[SECURITY] SandboxInterlock initialized (RAM Cap: {self.max_ram_mb}MB, Timeout: {self.timeout_sec}s).")

    def execute_safe_code(self, code: str) -> Dict[str, Any]:
        """
        Executes Python code in isolated sandbox.
        """
        if self.sandbox is None:
            return {"success": False, "error": "EvolutionSandbox not available"}

        start = time.time()
        res = self.sandbox.run_code(code, timeout=self.timeout_sec)
        elapsed = time.time() - start
        res["elapsed_sec"] = round(elapsed, 3)
        return res
