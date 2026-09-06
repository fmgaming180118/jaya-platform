"""Benchmark the real P13 reference and Rust cryptographic-envelope providers."""

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

from jaya_core.providers import (
    CryptographicEnvelopeContract,
    NativeProviderError,
    TrustedCryptographicSkinGate,
)


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


def _workload() -> CryptographicEnvelopeContract:
    return CryptographicEnvelopeContract(
        envelope_id="env-benchmark-1",
        key_id="key-benchmark-1",
        purpose="core.artifact",
        subject="artifact:benchmark-1",
        content_type="application/jaya-artifact",
        schema_version=1,
        algorithm_suite_code=1,
        operation_code=2,
        key_state=1,
        attestation_state=1,
        temporal_state=1,
        nonce_size_bytes=12,
        ciphertext_size_bytes=128,
        max_payload_bytes=4096,
    )


def _measure(gate: TrustedCryptographicSkinGate, iterations: int, samples: int) -> dict[str, Any]:
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

    reference = _measure(
        TrustedCryptographicSkinGate("python-reference"), args.iterations, args.samples
    )

    native: dict[str, Any] | None = None
    native_error: str | None = None
    try:
        native = _measure(
            TrustedCryptographicSkinGate("trusted-rust"), args.iterations, args.samples
        )
        if reference["decision"] != native["decision"]:
            raise RuntimeError("native cryptographic decision differs from the reference provider")
    except NativeProviderError as exc:
        native_error = f"{exc.code}: {exc}"

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    artifact: dict[str, Any] = {
        "schema_version": 1,
        "status": "PASS",
        "created_at": datetime.now(UTC).astimezone().isoformat(),
        "pillar": "p13_cryptographic_skin",
        "workload": {
            "name": "cryptographic_envelope_admission",
            "samples": args.samples,
            "iterations": args.iterations,
        },
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "reference": reference,
        "native": native,
        "native_status": "AVAILABLE" if native is not None else "UNAVAILABLE",
        "native_error": native_error,
    }

    if native is not None and native["provider"].get("library_path"):
        lib_path = Path(str(native["provider"]["library_path"]))
        if lib_path.exists():
            artifact["library"] = {
                "path": str(lib_path),
                "sha256": _digest(lib_path),
                "size_bytes": lib_path.stat().st_size,
            }

    rendered = json.dumps(artifact, indent=2, sort_keys=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(f"Benchmark results written to {output_path}")
    print(f"Reference Median Latency: {reference['median_ns_per_decision']} ns/decision")
    if native is not None:
        print(f"Native Rust Median Latency: {native['median_ns_per_decision']} ns/decision")
    else:
        print(f"Native Rust Provider: {native_error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
