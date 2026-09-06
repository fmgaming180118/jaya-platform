"""Representative verification runner for Pillar 23 Sandboxed Imagination."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from jaya_core.pillars.foundation_capabilities import (
    SANDBOX_CAPABILITY_ID,
    SandboxedImaginationCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "matrix",
    "soak",
    "source_files",
}


class SandboxVerificationError(RuntimeError):
    """Stable P23 verification failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _load_profile(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SandboxVerificationError(
            "PROFILE_NOT_FOUND", f"profile does not exist: {path}"
        )
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SandboxVerificationError(
            "PROFILE_CORRUPT", f"profile JSON is corrupt: {exc}"
        ) from exc
    if not isinstance(profile, dict):
        raise SandboxVerificationError(
            "PROFILE_INVALID", "profile must be a JSON object"
        )
    if set(profile) != _PROFILE_FIELDS:
        raise SandboxVerificationError(
            "PROFILE_SCHEMA_INVALID",
            f"profile fields mismatch: {sorted(profile)} vs {sorted(_PROFILE_FIELDS)}",
        )
    if profile.get("schema_version") != 1:
        raise SandboxVerificationError(
            "PROFILE_SCHEMA_UNSUPPORTED",
            f"unsupported profile schema_version: {profile.get('schema_version')}",
        )
    if not _PROFILE_ID.match(str(profile.get("profile_id", ""))):
        raise SandboxVerificationError(
            "PROFILE_ID_INVALID", "profile_id is invalid"
        )
    return profile


def run_sandboxed_imagination_verification(
    profile_path: Path,
    *,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute canonical verification of P23 Sandboxed Imagination."""
    root_dir = base_dir or Path.cwd()
    profile = _load_profile(profile_path)

    system_name = platform.system()
    expected_os = profile["supported_os"]
    if expected_os != "Any" and system_name.lower() != expected_os.lower():
        raise SandboxVerificationError(
            "UNSUPPORTED_OS",
            f"profile requires {expected_os}, running on {system_name}",
        )

    # 1. Verify health check
    sandbox = SandboxedImaginationCapability(timeout_seconds=2.0)
    if not sandbox.health_check():
        raise SandboxVerificationError(
            "HEALTH_CHECK_FAILED", "SandboxedImaginationCapability health check failed"
        )

    # 2. Verify deterministic evaluations & outputs
    test_cases = [
        ("(10 + 20) * 3 == 90", True),
        ("['a', 'b', 'c'][2] == 'c'", True),
        ("{'k': 100}['k'] / 2", 50.0),
        ("2 ** 10 == 1024", True),
    ]
    for expr, expected in test_cases:
        res = sandbox.evaluate(expr)
        if res.data.get("result") != expected:
            raise SandboxVerificationError(
                "EVALUATION_MISMATCH",
                f"Expression '{expr}' evaluated to {res.data.get('result')} != {expected}",
            )
        if res.data.get("epistemic_label") != "SIMULATION":
            raise SandboxVerificationError(
                "EPISTEMIC_LABEL_INVALID",
                f"Missing or invalid epistemic label: {res.data.get('epistemic_label')}",
            )
        if res.data.get("epistemic_status") != "UNVERIFIED":
            raise SandboxVerificationError(
                "EPISTEMIC_STATUS_INVALID",
                f"Missing or invalid epistemic status: {res.data.get('epistemic_status')}",
            )
        if not res.data.get("cleanup_verified"):
            raise SandboxVerificationError(
                "CLEANUP_UNVERIFIED", "Ephemeral workspace cleanup was not verified"
            )

    # 3. Verify adversarial rejections
    adversarial_cases = [
        ("__import__('os').system('dir')", "SECURITY_VIOLATION"),
        ("getattr(__builtins__, 'eval')('1+1')", "SECURITY_VIOLATION"),
        ("().__class__.__bases__[0]", "SECURITY_VIOLATION"),
        ("open('foo.txt')", "SECURITY_VIOLATION"),
        ("2 ** 99999", "SECURITY_VIOLATION"),
        ("100 / 0", "ARITHMETIC_ERROR"),
    ]
    for adv_expr, expected_err in adversarial_cases:
        try:
            sandbox.evaluate(adv_expr)
            raise SandboxVerificationError(
                "SECURITY_BREACH",
                f"Adversarial expression '{adv_expr}' was not rejected!",
            )
        except LocalPillarError as err:
            if err.code != expected_err:
                raise SandboxVerificationError(
                    "ERROR_CODE_MISMATCH",
                    f"Expected error {expected_err} for '{adv_expr}', got {err.code}",
                ) from err

    # 4. Soak & latency benchmark
    process = psutil.Process()
    rss_start = process.memory_info().rss
    soak_config = profile["soak"]
    iterations = soak_config["iterations"]
    latencies_ms: list[float] = []

    start_soak = time.perf_counter()
    for i in range(iterations):
        t0 = time.perf_counter()
        sandbox.evaluate(f"({i} + 10) * 2")
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
    elapsed_soak = time.perf_counter() - start_soak

    rss_end = process.memory_info().rss
    rss_growth = max(0, rss_end - rss_start)
    mean_latency = sum(latencies_ms) / len(latencies_ms)

    if mean_latency > soak_config["max_mean_eval_latency_ms"]:
        raise SandboxVerificationError(
            "LATENCY_LIMIT_EXCEEDED",
            f"Mean latency {mean_latency:.2f}ms exceeds limit {soak_config['max_mean_eval_latency_ms']}ms",
        )
    if rss_growth > soak_config["max_rss_growth_bytes"]:
        raise SandboxVerificationError(
            "RSS_GROWTH_EXCEEDED",
            f"RSS growth {rss_growth} bytes exceeds limit {soak_config['max_rss_growth_bytes']} bytes",
        )

    # 5. Digest source files
    source_digests: dict[str, str] = {}
    for rel_path in profile["source_files"]:
        abs_path = root_dir / rel_path
        if abs_path.is_file():
            source_digests[rel_path] = _digest(abs_path.read_bytes())
        else:
            source_digests[rel_path] = "MISSING"

    receipt = {
        "receipt_id": f"p23-verif-{uuid.uuid4().hex[:12]}",
        "profile_id": profile["profile_id"],
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "status": "VERIFIED",
        "capability_id": SANDBOX_CAPABILITY_ID,
        "metrics": {
            "iterations": iterations,
            "elapsed_seconds": round(elapsed_soak, 4),
            "mean_eval_latency_ms": round(mean_latency, 4),
            "rss_growth_bytes": rss_growth,
            "isolation": "PYTHON_ISOLATED_PROCESS_AST_ALLOWLIST",
            "epistemic_label": "SIMULATION",
        },
        "environment": {
            "os": system_name,
            "python_version": sys.version.split()[0],
            "cpu_count": psutil.cpu_count(logical=True),
        },
        "source_digests": source_digests,
    }
    return receipt
