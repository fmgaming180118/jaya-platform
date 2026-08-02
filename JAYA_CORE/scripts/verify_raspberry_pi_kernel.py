"""
verify_raspberry_pi_kernel.py — Raspberry Pi Low-Memory Kernel Compilation & Runtime Verification Script.

Verifies that the 11-component Cognitive Kernel compiles and executes within
the 512 MB RAM footprint constraint for Raspberry Pi / Edge targets.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

from src.cognitive.contracts import UserRequest
from src.cognitive.portable_kernel import PORTABLE_MAX_RAM_MB, PortableCognitiveKernelRunner


def run_raspberry_pi_kernel_verification() -> dict:
    runner = PortableCognitiveKernelRunner()
    user_req = UserRequest(
        request_id="req-rpi-001",
        raw_prompt="Initialize Raspberry Pi low-memory kernel compilation check",
    )

    result = runner.run_portable_request(user_req)

    is_ram_ok = result.metrics.total_memory_mb <= PORTABLE_MAX_RAM_MB
    is_components_ok = len(result.components_status) == 11
    is_status_ok = result.status == "PORTABLE_KERNEL_READY"

    return {
        "target_profile": "RASPBERRY_PI_4_512MB",
        "total_memory_mb": result.metrics.total_memory_mb,
        "max_allowed_memory_mb": PORTABLE_MAX_RAM_MB,
        "ram_constraint_passed": is_ram_ok,
        "components_compiled_count": len(result.components_status),
        "all_11_components_ready": is_components_ok,
        "kernel_status": result.status,
        "verification_result": "SUCCESS" if (is_ram_ok and is_components_ok and is_status_ok) else "FAILED",
    }


def main() -> int:
    print("VERIFIKASI KOMPILASI COGNITIVE KERNEL DI RASPBERRY PI (RAM <= 512 MB)...")
    res = run_raspberry_pi_kernel_verification()
    print(json.dumps(res, indent=2))

    if res["verification_result"] == "SUCCESS":
        print("\nRaspberry Pi Cognitive Kernel compilation & runtime VERIFIED SUCCESSFUL!")
        return 0

    print("\nRaspberry Pi Cognitive Kernel verification FAILED!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
