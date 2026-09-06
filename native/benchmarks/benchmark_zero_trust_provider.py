"""Benchmark the real P18 reference and Rust authorization-scope providers."""

# ruff: noqa: EM101, PLR2004, TRY003

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.providers import TrustedZeroTrustGate, ZeroTrustAuthorizationContract


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


def _workload() -> ZeroTrustAuthorizationContract:
    return ZeroTrustAuthorizationContract(
        envelope_id="trust-benchmark-envelope",
        principal_id="principal-benchmark",
        envelope_node_id="node-benchmark",
        capability_id="core.logic.evaluate",
        nonce="nonce-benchmark",
        principal_status=1,
        principal_state=0,
        attestation_state=1,
        persisted_node_id="node-benchmark",
        capability_ids=("core.logic.evaluate", "core.memory.read"),
        claimed_payload_sha256="a" * 64,
        actual_payload_sha256="a" * 64,
    )


def _measure(gate: TrustedZeroTrustGate, iterations: int, samples: int) -> dict[str, Any]:
    contract = _workload()
    for _ in range(100):
        gate.evaluate(contract)
    timings_per_decision: list[int] = []
    effect = 0
    reason_code = ""
    for _ in range(samples):
        started = time.perf_counter_ns()
        for _ in range(iterations):
            decision = gate.evaluate(contract)
            effect = decision.effect
            reason_code = decision.reason_code
        elapsed = time.perf_counter_ns() - started
        timings_per_decision.append(elapsed // iterations)
    timings_per_decision.sort()
    return {
        "provider": gate.profile(),
        "samples": samples,
        "iterations_per_sample": iterations,
        "total_decisions": samples * iterations,
        "median_ns_per_decision": int(statistics.median(timings_per_decision)),
        "p95_ns_per_decision": timings_per_decision[int(len(timings_per_decision) * 0.95)],
        "decision": {"effect": effect, "reason_code": reason_code},
    }


def main() -> int:
    args = _arguments()
    if args.iterations < 100:
        raise ValueError("iterations must be at least 100")
    if not 5 <= args.samples <= 100:
        raise ValueError("samples must be between 5 and 100")
    reference = _measure(TrustedZeroTrustGate("python-reference"), args.iterations, args.samples)
    native = _measure(TrustedZeroTrustGate("trusted-rust"), args.iterations, args.samples)
    if reference["decision"] != native["decision"]:
        raise RuntimeError("native zero-trust decision differs from the reference provider")
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
            "principal_status": "ACTIVE",
            "principal_state": "CURRENT",
            "capabilities": 2,
            "payload_digest_matches": True,
            "attestation_result": "VERIFIED",
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
            "payload_crosses_ffi": False,
            "secret_material_crosses_ffi": False,
            "signature_crosses_ffi": False,
            "memory_safe_scope_parser": True,
            "two_stage_attestation_gate": True,
            "performance_improvement": (
                native["median_ns_per_decision"] < reference["median_ns_per_decision"]
            ),
            "full_zero_trust_gateway_in_rust": False,
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
