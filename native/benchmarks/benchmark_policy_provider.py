"""Benchmark the real P15 reference and Rust policy providers."""

# ruff: noqa: EM101, PLR2004, TRY003

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jaya_core.providers import TrustedPolicyGate, TrustedPolicyRule


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=1_000)
    parser.add_argument("--samples", type=int, default=25)
    return parser.parse_args()


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _measure(
    gate: TrustedPolicyGate, iterations: int, samples: int
) -> tuple[int, dict[str, Any]]:
    rules = (
        TrustedPolicyRule(effect=2, risk_mask=1 << 2),
        TrustedPolicyRule(
            effect=1,
            risk_mask=1 << 0,
            capability_ids=("core.logic.evaluate",),
        ),
        TrustedPolicyRule(effect=3, risk_mask=0),
    )
    for _ in range(100):
        gate.evaluate(
            capability_id="core.logic.evaluate",
            risk_code=0,
            rules=rules,
            default_effect=2,
        )
    timings_per_decision: list[int] = []
    effect = 0
    rule_index: int | None = None
    for _ in range(samples):
        started = time.perf_counter_ns()
        for _ in range(iterations):
            decision = gate.evaluate(
                capability_id="core.logic.evaluate",
                risk_code=0,
                rules=rules,
                default_effect=2,
            )
            effect = decision.effect
            rule_index = decision.rule_index
        elapsed = time.perf_counter_ns() - started
        timings_per_decision.append(elapsed // iterations)
    timings_per_decision.sort()
    return effect, {
        "provider": gate.profile(),
        "samples": samples,
        "iterations_per_sample": iterations,
        "total_decisions": samples * iterations,
        "median_ns_per_decision": int(statistics.median(timings_per_decision)),
        "p95_ns_per_decision": timings_per_decision[int(len(timings_per_decision) * 0.95)],
        "decision": {"effect": effect, "rule_index": rule_index},
    }


def main() -> int:
    args = _arguments()
    if args.iterations < 100 or not 5 <= args.samples <= 100:
        raise ValueError("iterations must be at least 100")
    reference_effect, reference = _measure(
        TrustedPolicyGate("python-reference"), args.iterations, args.samples
    )
    native_gate = TrustedPolicyGate("trusted-rust")
    native_effect, native = _measure(native_gate, args.iterations, args.samples)
    if reference["decision"] != native["decision"] or reference_effect != native_effect:
        raise RuntimeError("native policy decision differs from the reference provider")
    library_path = Path(str(native["provider"]["library_path"]))
    artifact = {
        "schema_version": 1,
        "status": "PASS",
        "created_at": datetime.now(UTC).astimezone().isoformat(),
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "processor": platform.processor(),
        },
        "workload": {
            "rules": 3,
            "capability": "core.logic.evaluate",
            "risk_code": 0,
        },
        "reference": reference,
        "native": native,
        "native_to_reference_latency_ratio": (
            native["median_ns_per_decision"] / reference["median_ns_per_decision"]
        ),
        "correctness": {"decision_equal": True},
        "library": {
            "path": str(library_path.resolve()),
            "size_bytes": library_path.stat().st_size,
            "sha256": _digest(library_path),
        },
        "claims": {
            "memory_safe_rule_parser": True,
            "performance_improvement": (
                native["median_ns_per_decision"]
                < reference["median_ns_per_decision"]
            ),
            "full_policy_engine_in_rust": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
