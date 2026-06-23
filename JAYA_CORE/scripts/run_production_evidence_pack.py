import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

COMMANDS = [
    [sys.executable, "-m", "pytest", "JAYA_CORE/tests/test_phase1_jaya_ir.py", "-v"],
    [sys.executable, "-m", "pytest", "JAYA_CORE/tests/test_phase1_ir_benchmark.py", "JAYA_CORE/tests/test_phase1_benchmark_gate.py", "JAYA_CORE/tests/test_phase1_architecture_boundary.py", "-v"],
    [sys.executable, "-m", "pytest", "JAYA_CORE/tests/test_phase2_evolution_gate.py", "JAYA_CORE/tests/test_phase2_rollback.py", "JAYA_CORE/tests/test_phase2_manifest.py", "-v"],
    [sys.executable, "-m", "pytest", "JAYA_CORE/tests/test_phase1_agentic_rag_runtime_gate.py", "-v"],
    [sys.executable, "JAYA_CORE/scripts/benchmark_phase1_ir.py", "--rounds", "40", "--gate", "--fail-on-gate", "--max-warm-p50-ms", "0.05", "--max-warm-p95-ms", "0.10", "--min-hit-rate", "0.95"],
]


def main() -> int:
    print("JAYA_CORE Production Evidence Pack")
    print("=" * 72)
    for command in COMMANDS:
        print("RUN:", " ".join(command))
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode != 0:
            print("FAILED:", " ".join(command))
            return result.returncode
        print("PASS:\n")
    print("ALL EVIDENCE GATES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
