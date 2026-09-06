"""Representative verification runner for P29 Binary Cortex."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean
from typing import Any

import psutil

from jaya_core.brain_v2.protection.dna_anchor import (
    DNAAnchor,
    DNAAnchorError,
    EncryptedFileKeyStore,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.binary_cortex import BinaryCortexService
from jaya_core.pillars.local_capabilities import BINARY_DOT_CAPABILITY_ID
from jaya_core.pillars.local_types import LocalPillarError
from jaya_core.security.cryptographic_skin import CryptographicSkin

_APPROVER = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._@:-]{2,127}")
_EXPECTED_PROFILE_KEYS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "workload",
    "source_files",
}
_EXPECTED_WORKLOAD_KEYS = {
    "input_features",
    "output_units",
    "inference_operations",
    "concurrent_operations",
    "benchmark_iterations",
    "max_inference_mean_latency_ms",
    "max_inference_p95_latency_ms",
    "max_install_latency_ms",
    "min_storage_compression_ratio",
    "min_kernel_speedup_excluding_pack",
    "max_rss_growth_bytes",
    "max_storage_bytes_per_operation",
}


class BinaryCortexVerificationError(RuntimeError):
    """Stable verifier failure with a machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _load_profile(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BinaryCortexVerificationError(
            "PROFILE_INVALID", "P29 verification profile cannot be read"
        ) from exc
    if (
        not isinstance(value, dict)
        or set(value) != _EXPECTED_PROFILE_KEYS
        or value.get("schema_version") != 1
        or value.get("profile_id") != "p29-windows-authenticated-binary-cortex-v1"
        or value.get("supported_os") != "Windows"
        or not isinstance(value.get("scope"), str)
        or not isinstance(value.get("source_files"), list)
        or not value["source_files"]
        or any(not isinstance(item, str) or not item for item in value["source_files"])
        or not isinstance(value.get("workload"), dict)
        or set(value["workload"]) != _EXPECTED_WORKLOAD_KEYS
    ):
        raise BinaryCortexVerificationError(
            "PROFILE_INVALID", "P29 verification profile schema is invalid"
        )
    workload = value["workload"]
    integer_fields = {
        "input_features",
        "output_units",
        "inference_operations",
        "concurrent_operations",
        "benchmark_iterations",
        "max_rss_growth_bytes",
        "max_storage_bytes_per_operation",
    }
    numeric_fields = set(workload) - integer_fields
    if any(type(workload[field]) is not int or workload[field] <= 0 for field in integer_fields):
        raise BinaryCortexVerificationError(
            "PROFILE_INVALID", "P29 integer workload limits must be positive"
        )
    if any(
        isinstance(workload[field], bool)
        or not isinstance(workload[field], (int, float))
        or float(workload[field]) <= 0
        for field in numeric_fields
    ):
        raise BinaryCortexVerificationError(
            "PROFILE_INVALID", "P29 numeric workload limits must be positive"
        )
    return value


def _source_bundle_sha256(root: Path, source_files: list[str]) -> str:
    digest = hashlib.sha256()
    resolved_root = root.resolve()
    for relative in sorted(source_files):
        candidate = (resolved_root / relative).resolve()
        if resolved_root not in candidate.parents or not candidate.is_file():
            raise BinaryCortexVerificationError(
                "SOURCE_INVALID", f"P29 source file is missing or outside repository: {relative}"
            )
        digest.update(relative.replace("\\", "/").encode())
        digest.update(b"\0")
        digest.update(candidate.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _host() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    return {
        "os": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "memory_bytes": int(memory.total),
        "dependencies": {
            "cryptography": __import__("cryptography").__version__,
            "psutil": psutil.__version__,
        },
    }


def _git(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return completed.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD") or "UNAVAILABLE",
        "branch": run("branch", "--show-current") or "DETACHED_OR_UNAVAILABLE",
        "dirty": bool(run("status", "--porcelain")),
    }


def _components(
    root: Path, identity_secret: str, skin_secret: str, *, database: Path | None = None
) -> tuple[DNAAnchor, CryptographicSkin]:
    identity_root = root / "identity"
    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
    )
    try:
        anchor.load_identity()
    except DNAAnchorError:
        anchor.enroll()
    skin = CryptographicSkin(
        database or (root / "security.db"),
        skin_secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    return anchor, skin


def _runtime(root: Path, anchor: DNAAnchor, skin: CryptographicSkin) -> JayaCoreRuntime:
    return JayaCoreRuntime(
        db_path=root / "runtime.db",
        local_pillar_data_dir=root / "pillar-capabilities",
        identity_anchor=anchor,
        cryptographic_skin=skin,
    )


def _weights(rows: int, features: int) -> list[list[int]]:
    return [
        [1 if (row * 13 + column * 7) % 11 else -1 for column in range(features)]
        for row in range(rows)
    ]


def _dense(weights: list[list[int]], vector: list[int]) -> list[int]:
    return [sum(a * b for a, b in zip(row, vector, strict=True)) for row in weights]


def _failure_code(action: Any) -> str:
    try:
        action()
    except LocalPillarError as exc:
        return exc.code
    return "UNEXPECTED_SUCCESS"


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _gate(name: str, passed: bool, actual: Any, expected: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "expected": expected}


def _scan_for_secrets(root: Path, tokens: list[bytes]) -> dict[str, Any]:
    matches: list[str] = []
    checked = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        checked += 1
        if any(token and token in payload for token in tokens):
            matches.append(str(path.relative_to(root)))
    return {"checked_files": checked, "matches": matches}


def _run_demo(repository_root: Path, workspace: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(repository_root / "scripts" / "demo_binary_cortex.py"),
        "--workspace",
        str(workspace),
    ]
    completed = subprocess.run(
        command,
        cwd=repository_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout[completed.stdout.find("{") :])
    except json.JSONDecodeError as exc:
        raise BinaryCortexVerificationError(
            "DEMO_INVALID", "P29 production-path demo did not return JSON"
        ) from exc
    return {
        "command": command,
        "exit_code": completed.returncode,
        "result": payload,
        "stderr": completed.stderr[-4000:],
    }


def verify_binary_cortex(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Execute P29 representative gates and persist a checksum-bound report."""

    root = repository_root.expanduser().resolve()
    normalized_approver = approver.strip()
    if _APPROVER.fullmatch(normalized_approver) is None:
        raise BinaryCortexVerificationError(
            "APPROVER_INVALID", "P29 verification approver is invalid"
        )
    profile = _load_profile(profile_path)
    host = _host()
    if host["os"] != profile["supported_os"]:
        raise BinaryCortexVerificationError(
            "HOST_UNSUPPORTED", "P29 representative profile requires Windows"
        )
    config = profile["workload"]
    run_root = output_directory.expanduser().resolve() / f"p29-verified-{uuid.uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=False)
    identity_secret = secrets.token_urlsafe(48)
    skin_secret = secrets.token_urlsafe(48)
    features = int(config["input_features"])
    outputs = int(config["output_units"])
    weights = _weights(outputs, features)
    vector = [1 if index % 5 else -1 for index in range(features)]
    dense_expected = _dense(weights, vector)
    process = psutil.Process()
    rss_before = process.memory_info().rss

    anchor, skin = _components(run_root, identity_secret, skin_secret)
    runtime = _runtime(run_root, anchor, skin)
    install_started = time.perf_counter()
    installed = runtime.execute_local_pillar(
        BINARY_DOT_CAPABILITY_ID,
        {"action": "install", "artifact_id": "representative-model", "weights": weights},
    )
    install_latency_ms = (time.perf_counter() - install_started) * 1_000
    profile_result = runtime.execute_local_pillar(BINARY_DOT_CAPABILITY_ID, {"action": "profile"})
    artifact_path = Path(installed.data["artifact_path"])
    artifact_ciphertext = artifact_path.read_bytes()

    inference_latencies: list[float] = []
    inference_results = []
    for _ in range(int(config["inference_operations"])):
        started = time.perf_counter()
        result = runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {
                "action": "infer",
                "artifact_id": "representative-model",
                "input": vector,
            },
        )
        inference_latencies.append((time.perf_counter() - started) * 1_000)
        inference_results.append(result)
    first = inference_results[0]
    receipt = runtime.execute_local_pillar(
        BINARY_DOT_CAPABILITY_ID,
        {"action": "verify_receipt", "receipt_id": first.data["receipt_id"]},
    )
    benchmark = runtime.execute_local_pillar(
        BINARY_DOT_CAPABILITY_ID,
        {
            "action": "benchmark",
            "left": vector,
            "right": weights[0],
            "iterations": int(config["benchmark_iterations"]),
        },
    )
    shape_code = _failure_code(
        lambda: runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {
                "action": "infer",
                "artifact_id": "representative-model",
                "input": vector[:-1],
            },
        )
    )
    invalid_code = _failure_code(
        lambda: runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {
                "action": "infer",
                "artifact_id": "representative-model",
                "input": [0] * features,
            },
        )
    )
    traversal_code = _failure_code(
        lambda: runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {"action": "inspect", "artifact_id": "../escape"},
        )
    )

    with ThreadPoolExecutor(max_workers=int(config["concurrent_operations"])) as pool:
        concurrent_results = list(
            pool.map(
                lambda _: runtime.execute_local_pillar(
                    BINARY_DOT_CAPABILITY_ID,
                    {
                        "action": "infer",
                        "artifact_id": "representative-model",
                        "input": vector,
                    },
                ),
                range(int(config["concurrent_operations"])),
            )
        )
    runtime.close()

    restarted_anchor, restarted_skin = _components(run_root, identity_secret, skin_secret)
    restarted = _runtime(run_root, restarted_anchor, restarted_skin)
    restart_result = restarted.execute_local_pillar(
        BINARY_DOT_CAPABILITY_ID,
        {"action": "infer", "artifact_id": "representative-model", "input": vector},
    )
    unavailable = BinaryCortexService(
        artifact_root=run_root / "pillar-capabilities" / "binary_cortex",
        cryptographic_skin=restarted_skin,
        kernel_probe=lambda: False,
    )
    unavailable_code = _failure_code(lambda: unavailable.infer("representative-model", vector))
    fallback = unavailable.infer("representative-model", vector, allow_dense_fallback=True)
    ticks = iter((0.0, 0.01, 0.02))
    timed = BinaryCortexService(
        artifact_root=run_root / "pillar-capabilities" / "binary_cortex",
        cryptographic_skin=restarted_skin,
        monotonic=lambda: next(ticks),
    )
    timeout_code = _failure_code(
        lambda: timed.infer("representative-model", vector, timeout_seconds=0.001)
    )
    no_security_code = _failure_code(
        lambda: BinaryCortexService(artifact_root=run_root / "no-security").install_artifact(
            "blocked-model", weights[:1]
        )
    )

    tamper_root = run_root / "tamper-binary"
    shutil.copytree(run_root / "pillar-capabilities" / "binary_cortex", tamper_root)
    tamper_path = tamper_root / "artifacts" / "representative-model.jaya-binary-envelope.json"
    tampered_envelope = json.loads(tamper_path.read_text(encoding="utf-8"))
    ciphertext = tampered_envelope["ciphertext"]
    tampered_envelope["ciphertext"] = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
    tamper_path.write_text(json.dumps(tampered_envelope), encoding="utf-8")
    tampered_service = BinaryCortexService(
        artifact_root=tamper_root,
        cryptographic_skin=restarted_skin,
    )
    tamper_code = _failure_code(lambda: tampered_service.inspect_artifact("representative-model"))

    recovery_security = run_root / "recovery-security.db"
    with (
        sqlite3.connect(run_root / "security.db") as source,
        sqlite3.connect(recovery_security) as target,
    ):
        source.backup(target)
    recovery_binary = run_root / "recovery-binary"
    shutil.copytree(run_root / "pillar-capabilities" / "binary_cortex", recovery_binary)
    restarted.close()

    recovery_anchor, recovery_skin = _components(
        run_root, identity_secret, skin_secret, database=recovery_security
    )
    recovery_service = BinaryCortexService(
        artifact_root=recovery_binary,
        cryptographic_skin=recovery_skin,
    )
    recovery_result = recovery_service.infer("representative-model", vector)
    recovery_skin.close()
    recovery_anchor.close()

    demo = _run_demo(root, run_root / "production-path-demo")
    rss_growth = max(0, process.memory_info().rss - rss_before)
    operation_count = int(config["inference_operations"]) + int(config["concurrent_operations"]) + 3
    storage_bytes = sum(path.stat().st_size for path in run_root.rglob("*") if path.is_file())
    storage_per_operation = storage_bytes / operation_count
    packed_secret = BinaryCortexService._pack(tuple(weights[0]))[:64]
    leak_scan = _scan_for_secrets(
        run_root,
        [identity_secret.encode(), skin_secret.encode(), packed_secret],
    )
    inference_mean = mean(inference_latencies)
    inference_p95 = _p95(inference_latencies)
    concurrent_receipts = {result.data["receipt_id"] for result in concurrent_results}
    demo_result = demo["result"] if isinstance(demo["result"], dict) else {}

    gates = [
        _gate("windows_representative_host", host["os"] == "Windows", host["os"], "Windows"),
        _gate(
            "binary_kernel_available", profile_result.data["available"], profile_result.data, True
        ),
        _gate(
            "no_false_hardware_acceleration_claim",
            profile_result.data["hardware_accelerated"] is False,
            profile_result.data["hardware_accelerated"],
            False,
        ),
        _gate(
            "authenticated_artifact_installed",
            installed.code == "BINARY_ARTIFACT_INSTALLED",
            installed.code,
            "BINARY_ARTIFACT_INSTALLED",
        ),
        _gate(
            "encrypted_artifact_plaintext_absent",
            b'"packed_rows"' not in artifact_ciphertext
            and packed_secret not in artifact_ciphertext,
            {"artifact_bytes": len(artifact_ciphertext)},
            "P13 ciphertext without packed plaintext",
        ),
        _gate(
            "tail_bit_storage_compression",
            installed.data["storage_compression_ratio"]
            >= float(config["min_storage_compression_ratio"]),
            installed.data["storage_compression_ratio"],
            config["min_storage_compression_ratio"],
        ),
        _gate(
            "install_latency",
            install_latency_ms <= float(config["max_install_latency_ms"]),
            install_latency_ms,
            config["max_install_latency_ms"],
        ),
        _gate(
            "exact_binary_inference",
            all(result.data["outputs"] == dense_expected for result in inference_results),
            len(inference_results),
            config["inference_operations"],
        ),
        _gate(
            "binary_path_no_fallback",
            all(result.data["fallback_used"] is False for result in inference_results),
            first.data["kernel"],
            "PYTHON_INT_XNOR_POPCOUNT",
        ),
        _gate(
            "signed_execution_receipt",
            receipt.code == "BINARY_RECEIPT_VERIFIED"
            and receipt.data["output_sha256"] == first.data["output_sha256"],
            receipt.code,
            "authenticated matching receipt",
        ),
        _gate(
            "restart_exact",
            restart_result.data["outputs"] == dense_expected,
            restart_result.data["output_sha256"],
            first.data["output_sha256"],
        ),
        _gate(
            "concurrent_inference_exact",
            all(result.data["outputs"] == dense_expected for result in concurrent_results),
            len(concurrent_results),
            config["concurrent_operations"],
        ),
        _gate(
            "concurrent_receipts_unique",
            len(concurrent_receipts) == int(config["concurrent_operations"]),
            len(concurrent_receipts),
            config["concurrent_operations"],
        ),
        _gate(
            "unsupported_kernel_rejected",
            unavailable_code == "KERNEL_UNAVAILABLE",
            unavailable_code,
            "KERNEL_UNAVAILABLE",
        ),
        _gate(
            "dense_fallback_explicit_and_exact",
            fallback.code == "DENSE_FALLBACK_EXECUTED"
            and fallback.data["fallback_used"] is True
            and fallback.data["outputs"] == dense_expected,
            {"code": fallback.code, "kernel": fallback.data["kernel"]},
            "labeled exact fallback",
        ),
        _gate(
            "bounded_timeout",
            timeout_code == "EXECUTION_TIMEOUT",
            timeout_code,
            "EXECUTION_TIMEOUT",
        ),
        _gate(
            "shape_mismatch_rejected", shape_code == "SHAPE_MISMATCH", shape_code, "SHAPE_MISMATCH"
        ),
        _gate(
            "invalid_value_rejected", invalid_code == "INVALID_INPUT", invalid_code, "INVALID_INPUT"
        ),
        _gate(
            "path_traversal_rejected",
            traversal_code == "INVALID_INPUT",
            traversal_code,
            "INVALID_INPUT",
        ),
        _gate(
            "p13_required_for_artifacts",
            no_security_code == "ARTIFACT_SECURITY_UNAVAILABLE",
            no_security_code,
            "ARTIFACT_SECURITY_UNAVAILABLE",
        ),
        _gate(
            "artifact_tamper_rejected",
            tamper_code == "ARTIFACT_AUTHENTICATION_FAILED",
            tamper_code,
            "ARTIFACT_AUTHENTICATION_FAILED",
        ),
        _gate(
            "sqlite_and_artifact_backup_recovery",
            recovery_result.data["outputs"] == dense_expected,
            recovery_result.data["output_sha256"],
            first.data["output_sha256"],
        ),
        _gate(
            "benchmark_exact",
            benchmark.data["dot_product"] == dense_expected[0]
            and benchmark.data["verified_against"] == "PYTHON_SCALAR_DOT",
            benchmark.data["dot_product"],
            dense_expected[0],
        ),
        _gate(
            "bitwise_operation_reduction",
            first.data["binary_kernel_operations"] < first.data["dense_reference_multiply_adds"],
            {
                "binary": first.data["binary_kernel_operations"],
                "dense": first.data["dense_reference_multiply_adds"],
            },
            "binary operation count below dense reference",
        ),
        _gate(
            "kernel_speedup_excluding_pack",
            benchmark.data["kernel_speedup_excluding_pack"]
            >= float(config["min_kernel_speedup_excluding_pack"]),
            benchmark.data["kernel_speedup_excluding_pack"],
            config["min_kernel_speedup_excluding_pack"],
        ),
        _gate(
            "inference_mean_latency",
            inference_mean <= float(config["max_inference_mean_latency_ms"]),
            inference_mean,
            config["max_inference_mean_latency_ms"],
        ),
        _gate(
            "inference_p95_latency",
            inference_p95 <= float(config["max_inference_p95_latency_ms"]),
            inference_p95,
            config["max_inference_p95_latency_ms"],
        ),
        _gate(
            "rss_growth",
            rss_growth <= int(config["max_rss_growth_bytes"]),
            rss_growth,
            config["max_rss_growth_bytes"],
        ),
        _gate(
            "storage_per_operation",
            storage_per_operation <= int(config["max_storage_bytes_per_operation"]),
            storage_per_operation,
            config["max_storage_bytes_per_operation"],
        ),
        _gate("secret_leak_scan", not leak_scan["matches"], leak_scan, "no plaintext secret"),
        _gate(
            "production_path_demo",
            demo["exit_code"] == 0
            and all(
                demo_result.get(key) is True
                for key in (
                    "artifact_authenticated",
                    "plaintext_absent",
                    "binary_exact",
                    "receipt_verified",
                    "restart_exact",
                    "fallback_labeled",
                )
            ),
            demo_result,
            "all production-path checks true",
        ),
        _gate(
            "external_acceleration_truth_boundary",
            True,
            "BLOCKED_EXTERNAL",
            "native SIMD/GPU/NPU, energy, and sustained production excluded",
        ),
    ]
    passed = sum(1 for gate in gates if gate["passed"])
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE" if passed == len(gates) else "FAILED",
        "pillar": "P029",
        "profile_id": profile["profile_id"],
        "scope": profile["scope"],
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "approval": {"approver": normalized_approver, "scope": "representative-local"},
        "environment": host,
        "version": _git(root),
        "artifact_integrity": {
            "profile_sha256": "sha256:" + hashlib.sha256(profile_path.read_bytes()).hexdigest(),
            "source_bundle_sha256": _source_bundle_sha256(root, profile["source_files"]),
            "source_files": profile["source_files"],
        },
        "kernel_profile": profile_result.data,
        "artifact": installed.data,
        "performance": {
            "inference_operations": len(inference_latencies),
            "inference_mean_latency_ms": inference_mean,
            "inference_p95_latency_ms": inference_p95,
            "install_latency_ms": install_latency_ms,
            "benchmark": benchmark.data,
            "rss_growth_bytes": rss_growth,
            "storage_bytes": storage_bytes,
            "storage_bytes_per_operation": storage_per_operation,
        },
        "failure_paths": {
            "unsupported_kernel": unavailable_code,
            "timeout": timeout_code,
            "shape": shape_code,
            "invalid_value": invalid_code,
            "path_traversal": traversal_code,
            "missing_security": no_security_code,
            "tamper": tamper_code,
        },
        "recovery": {
            "restart_exact": restart_result.data["outputs"] == dense_expected,
            "backup_exact": recovery_result.data["outputs"] == dense_expected,
            "concurrent_operations": len(concurrent_results),
            "unique_receipts": len(concurrent_receipts),
        },
        "production_path_demo": demo,
        "secret_leak_scan": leak_scan,
        "limitations": [
            "CPython integer bit_count is real binary execution but is not claimed as native SIMD/GPU/NPU acceleration.",
            "Target-device energy and model-level quality calibration remain BLOCKED_EXTERNAL.",
            "Sustained production observation remains BLOCKED_EXTERNAL.",
            "This report is representative verification, not a production deployment certificate.",
        ],
        "rollback": {
            "artifact": "restore the authenticated envelope and P13 SQLite backup",
            "runtime": "set allow_dense_fallback explicitly when the binary kernel is unavailable",
            "recovery_artifact_root": str(recovery_binary),
            "recovery_security_database": str(recovery_security),
        },
        "gates": {"passed": passed, "total": len(gates), "results": gates},
    }
    report_path = run_root / "verified-binary-cortex-report.json"
    report_bytes = json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ).encode("utf-8")
    report_path.write_bytes(report_bytes)
    digest = hashlib.sha256(report_bytes).hexdigest()
    report_path.with_suffix(report_path.suffix + ".sha256").write_text(
        f"sha256:{digest}  {report_path.name}\n", encoding="utf-8"
    )
    if passed != len(gates):
        failed = ", ".join(gate["name"] for gate in gates if not gate["passed"])
        raise BinaryCortexVerificationError(
            "GATE_FAILED", f"P29 representative gates failed: {failed}"
        )
    return report_path, report
