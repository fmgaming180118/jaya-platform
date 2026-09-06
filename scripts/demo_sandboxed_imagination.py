"""Demo script for Pilar 23 Sandboxed Imagination (core.sandbox.expression)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
core_src = repo_root / "packages" / "jaya-core" / "src"
if str(core_src) not in sys.path:
    sys.path.insert(0, str(core_src))

from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability
from jaya_core.pillars.local_capabilities import LocalPillarError


def main() -> None:
    print("=" * 70)
    print(" JAYA PLATFORM — PILAR 23: SANDBOXED IMAGINATION DEMO")
    print("=" * 70)

    sandbox = SandboxedImaginationCapability(timeout_seconds=2.0)
    print(f"\n[1] Health Check: {'PASSED' if sandbox.health_check() else 'FAILED'}")

    print("\n[2] Executing Legitimate Declarative Expressions:")
    expressions = [
        "(125 * 4) + (250 / 5) == 550",
        "['simulation_a', 'simulation_b'][0] == 'simulation_a'",
        "{'temperature': 37.5, 'heartbeat_bpm': 72}['heartbeat_bpm'] * 1.2",
    ]
    for expr in expressions:
        res = sandbox.evaluate(expr)
        print(f"  • Expr: {expr}")
        print(f"    -> Result: {res.data['result']} | Label: {res.data['epistemic_label']} ({res.data['epistemic_status']}) | Latency: {res.data['duration_ns']/1_000_000:.2f}ms")

    print("\n[3] Testing Adversarial / Security Rejections:")
    attacks = [
        ("__import__('os').system('echo attack')", "Module Import Escape"),
        ("getattr(__builtins__, 'eval')('1+1')", "Builtin Reflection Bypass"),
        ("().__class__.__bases__[0]", "Class Hierarchy Traversal"),
        ("2 ** 999999", "Exponential Power Bomb"),
        ("100 / 0", "Division by Zero"),
    ]
    for attack_expr, attack_type in attacks:
        try:
            sandbox.evaluate(attack_expr)
            print(f"  [!] FAILED TO BLOCK: {attack_type}")
        except LocalPillarError as err:
            print(f"  [+] BLOCKED {attack_type}: code={err.code} ({err})")

    print("\n" + "=" * 70)
    print(" DEMO COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    main()
