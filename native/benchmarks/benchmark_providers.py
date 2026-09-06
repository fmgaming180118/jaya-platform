# ruff: noqa: PLR0914, PLR2004, TRY003, TRY004
"""Measure the first-party providers against the active Python reference paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from jaya_core.pillars.binary_cortex import BinaryCortexService
from jaya_core.providers import ComputeProvider, TrustedArtifactGate


def _measure(operation: Callable[[], Any], *, samples: int, warmup: int = 3) -> dict[str, Any]:
    for _ in range(warmup):
        operation()
    values: list[int] = []
    for _ in range(samples):
        started = time.perf_counter_ns()
        operation()
        values.append(max(1, time.perf_counter_ns() - started))
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, max(0, round(0.95 * len(ordered)) - 1))
    return {
        "samples": samples,
        "min_ns": ordered[0],
        "median_ns": int(statistics.median(ordered)),
        "p95_ns": ordered[p95_index],
        "max_ns": ordered[-1],
    }


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _library_evidence(profile: dict[str, Any]) -> dict[str, Any]:
    raw_path = profile.get("library_path")
    if not isinstance(raw_path, str):
        raise RuntimeError("strict native benchmark did not load a shared library")
    path = Path(raw_path).resolve()
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _command_version(command: str) -> str | None:
    try:
        completed = subprocess.run(
            [command, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    first_line = completed.stdout.splitlines() or completed.stderr.splitlines()
    return first_line[0].strip() if first_line else None


def _cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        try:
            for line in cpuinfo.read_text(encoding="utf-8").splitlines():
                if line.casefold().startswith("model name") and ":" in line:
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or "UNKNOWN"


def run_benchmark(*, binary_length: int, samples: int) -> dict[str, Any]:
    if not 1_024 <= binary_length <= BinaryCortexService.MAX_VECTOR_LENGTH:
        raise ValueError("binary length is outside the P29 execution contract")
    if not 5 <= samples <= 1_000:
        raise ValueError("samples must be between 5 and 1000")

    native_compute = ComputeProvider("native-cpu")
    native_trusted = TrustedArtifactGate("trusted-rust")
    reference_compute = ComputeProvider("python-reference")
    reference_trusted = TrustedArtifactGate("python-reference")
    native_service = BinaryCortexService(
        compute_provider=native_compute,
        trusted_gate=native_trusted,
    )
    reference_service = BinaryCortexService(
        compute_provider=reference_compute,
        trusted_gate=reference_trusted,
    )

    indexes = np.arange(binary_length)
    left = np.where(indexes % 3, 1, -1).astype(np.int8).tolist()
    right = np.where(indexes % 7, 1, -1).astype(np.int8).tolist()
    reference_dot = reference_service.dot(left, right)
    native_dot = native_service.dot(left, right)
    if reference_dot.data["dot_product"] != native_dot.data["dot_product"]:
        raise RuntimeError("P29 native result differs from the Python reference")

    rng = np.random.default_rng(20260831)
    ternary_input = rng.normal(size=(16, 64)).astype(np.float32)
    ternary_weights = rng.integers(-1, 2, size=(64, 512), dtype=np.int8)
    reference_ternary = reference_compute.ternary_linear(ternary_input, ternary_weights)
    native_ternary = native_compute.ternary_linear(ternary_input, ternary_weights)
    max_abs_error = float(np.max(np.abs(reference_ternary - native_ternary)))
    if not np.allclose(reference_ternary, native_ternary, rtol=1e-5, atol=1e-5):
        raise RuntimeError("P22 native result differs from the NumPy reference")

    process = psutil.Process()
    rss_before = process.memory_info().rss
    binary_reference = _measure(lambda: reference_service.dot(left, right), samples=samples)
    binary_native = _measure(lambda: native_service.dot(left, right), samples=samples)
    ternary_reference = _measure(
        lambda: reference_compute.ternary_linear(ternary_input, ternary_weights),
        samples=samples,
    )
    ternary_native = _measure(
        lambda: native_compute.ternary_linear(ternary_input, ternary_weights),
        samples=samples,
    )
    rss_after = process.memory_info().rss

    compute_profile = native_compute.profile()
    trusted_profile = native_trusted.profile()
    return {
        "schema_version": 1,
        "run_id": f"native-benchmark-{uuid.uuid4().hex}",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS",
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": _cpu_model(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "cpu_logical": psutil.cpu_count(logical=True),
            "cpu_physical": psutil.cpu_count(logical=False),
            "memory_total_bytes": psutil.virtual_memory().total,
            "rss_before_bytes": rss_before,
            "rss_after_bytes": rss_after,
            "rss_delta_bytes": rss_after - rss_before,
            "energy_measurement": "UNAVAILABLE_NOT_CLAIMED",
            "toolchain": {
                "cxx": _command_version("c++"),
                "rustc": _command_version("rustc"),
                "cargo": _command_version("cargo"),
                "cmake": _command_version("cmake"),
            },
        },
        "providers": {
            "compute": compute_profile,
            "trusted": trusted_profile,
            "compute_library": _library_evidence(compute_profile),
            "trusted_library": _library_evidence(trusted_profile),
        },
        "p29_binary_dot": {
            "length": binary_length,
            "expected_dot_product": reference_dot.data["dot_product"],
            "native_dot_product": native_dot.data["dot_product"],
            "reference": binary_reference,
            "native": binary_native,
            "median_speed_ratio_reference_over_native": (
                binary_reference["median_ns"] / binary_native["median_ns"]
            ),
        },
        "p22_ternary_linear": {
            "input_shape": list(ternary_input.shape),
            "weight_shape": list(ternary_weights.shape),
            "max_absolute_error": max_abs_error,
            "reference": ternary_reference,
            "native": ternary_native,
            "median_speed_ratio_reference_over_native": (
                ternary_reference["median_ns"] / ternary_native["median_ns"]
            ),
        },
        "claims": {
            "hardware_acceleration": False,
            "gpu_provider": None,
            "windows_native_verified": False,
            "linux_x86_64_native_verified": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary-length", type=int, default=65_536)
    parser.add_argument("--samples", type=int, default=25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_benchmark(binary_length=args.binary_length, samples=args.samples)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(payload)
        return 0
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
