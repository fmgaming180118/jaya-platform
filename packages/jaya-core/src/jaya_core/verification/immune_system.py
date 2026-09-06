"""Representative verification runner for Pillar 12 Immune System."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import platform
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import psutil

from jaya_core.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from jaya_core.security.cryptographic_skin import CryptographicSkin
from jaya_core.security.immune_system import (
    ImmuneFailureCode,
    ImmuneSystem,
    ImmuneSystemError,
)

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_APPROVER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{2,127}$")
_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "workload",
    "source_files",
}
_WORKLOAD_FIELDS = {
    "healthy_scan_operations",
    "artifact_bytes",
    "concurrent_scans",
    "probe_timeout_seconds",
    "max_scan_mean_latency_ms",
    "max_scan_p95_latency_ms",
    "max_quarantine_latency_ms",
    "max_recovery_latency_ms",
    "max_full_audit_seconds",
    "max_rss_growth_bytes",
    "max_storage_bytes_per_operation",
}


class ImmuneSystemVerificationError(RuntimeError):
    """Stable P12 representative verification failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _load_profile(path: Path) -> dict[str, Any]:
    try:
        raw = path.expanduser().resolve().read_bytes()
        profile = json.loads(raw.decode())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ImmuneSystemVerificationError(
            "PROFILE_INVALID", "P12 verification profile is invalid"
        ) from exc
    workload = profile.get("workload") if isinstance(profile, dict) else None
    if (
        not isinstance(profile, dict)
        or set(profile) != _PROFILE_FIELDS
        or profile.get("schema_version") != 1
        or not _PROFILE_ID.fullmatch(str(profile.get("profile_id", "")))
        or not isinstance(profile.get("scope"), str)
        or not profile["scope"].strip()
        or profile.get("supported_os") != "Windows"
        or not isinstance(workload, dict)
        or set(workload) != _WORKLOAD_FIELDS
        or not isinstance(profile.get("source_files"), list)
        or not profile["source_files"]
        or any(not isinstance(item, str) or not item for item in profile["source_files"])
    ):
        raise ImmuneSystemVerificationError(
            "PROFILE_INVALID", "P12 verification profile fields are invalid"
        )
    integer_fields = {
        "healthy_scan_operations",
        "artifact_bytes",
        "concurrent_scans",
        "max_rss_growth_bytes",
        "max_storage_bytes_per_operation",
    }
    for field, value in workload.items():
        valid = (
            type(value) is int and value > 0
            if field in integer_fields
            else not isinstance(value, bool) and isinstance(value, (int, float)) and value > 0
        )
        if not valid:
            raise ImmuneSystemVerificationError(
                "PROFILE_INVALID", f"P12 workload threshold {field} is invalid"
            )
    if not 10 <= workload["healthy_scan_operations"] <= 10_000:
        raise ImmuneSystemVerificationError(
            "PROFILE_INVALID", "P12 healthy scan operation count is invalid"
        )
    if not 2 <= workload["concurrent_scans"] <= 32:
        raise ImmuneSystemVerificationError(
            "PROFILE_INVALID", "P12 concurrent scan count is invalid"
        )
    if not 1 <= workload["artifact_bytes"] <= 16 * 1024 * 1024:
        raise ImmuneSystemVerificationError("PROFILE_INVALID", "P12 artifact size is invalid")
    if not 0.05 <= float(workload["probe_timeout_seconds"]) <= 5.0:
        raise ImmuneSystemVerificationError("PROFILE_INVALID", "P12 probe timeout is invalid")
    return {**profile, "profile_sha256": _digest(raw)}


def _host() -> dict[str, object]:
    dependencies: dict[str, str] = {}
    for name in ("cryptography", "psutil"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "UNAVAILABLE"
    return {
        "os": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "memory_bytes": psutil.virtual_memory().total,
        "dependencies": dependencies,
    }


def _git_version(root: Path) -> dict[str, object]:
    def run(*arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        return completed.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD") or "UNAVAILABLE",
        "branch": run("branch", "--show-current") or "DETACHED_OR_UNAVAILABLE",
        "dirty": bool(run("status", "--porcelain")),
    }


def _source_bundle_sha256(root: Path, source_files: list[str]) -> str:
    digest = hashlib.sha256()
    resolved_root = root.resolve()
    for relative in sorted(source_files):
        candidate = (resolved_root / relative).resolve()
        if resolved_root not in candidate.parents or not candidate.is_file():
            raise ImmuneSystemVerificationError(
                "SOURCE_INVALID", f"P12 source file is missing or outside repository: {relative}"
            )
        digest.update(relative.replace("\\", "/").encode())
        digest.update(b"\0")
        digest.update(candidate.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def _signer(anchor: DNAAnchor):
    return lambda purpose, digest: anchor.sign_attestation(purpose, digest).to_dict()


def _components(
    *,
    database: Path,
    data_root: Path,
    identity_root: Path,
    identity_secret: str,
    skin_secret: str,
    probe_timeout_seconds: float,
) -> tuple[DNAAnchor, CryptographicSkin, ImmuneSystem]:
    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
    )
    try:
        anchor.load_identity()
    except RuntimeError:
        anchor.enroll()
    signer = _signer(anchor)
    skin = CryptographicSkin(
        database,
        skin_secret,
        attestation_signer=signer,
        attestation_verifier=anchor.verify_attestation,
    )
    immune = ImmuneSystem(
        database,
        data_root,
        skin,
        attestation_signer=signer,
        attestation_verifier=anchor.verify_attestation,
        dependency_probe_timeout_seconds=probe_timeout_seconds,
    )
    return anchor, skin, immune


def _close(components: tuple[DNAAnchor, CryptographicSkin, ImmuneSystem]) -> None:
    anchor, skin, immune = components
    immune.close()
    skin.close()
    anchor.close()


def _failure_code(action: Any) -> str:
    try:
        action()
    except ImmuneSystemError as exc:
        return exc.code.value
    return "NO_FAILURE"


def _gate(name: str, passed: bool, actual: object, expected: object) -> dict[str, object]:
    return {"name": name, "passed": bool(passed), "actual": actual, "expected": expected}


def _scan_for_secrets(root: Path, tokens: list[bytes]) -> dict[str, object]:
    matches: list[str] = []
    checked = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            continue
        checked += 1
        data = path.read_bytes()
        if any(token and token in data for token in tokens):
            matches.append(str(path.relative_to(root)))
    return {"checked_files": checked, "matches": matches}


def _run_demo(root: Path, workspace: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "demo_immune_system.py"),
            "--workspace",
            str(workspace),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ImmuneSystemVerificationError(
            "DEMO_INVALID", "P12 production-path demo did not return JSON"
        ) from exc
    return {
        "command": completed.args,
        "exit_code": completed.returncode,
        "result": result,
        "stderr": completed.stderr[-4000:],
    }


def verify_immune_system(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Execute real local P12 gates and persist a checksum-bound report."""

    root = repository_root.expanduser().resolve()
    normalized_approver = approver.strip()
    if not _APPROVER.fullmatch(normalized_approver):
        raise ImmuneSystemVerificationError(
            "APPROVER_INVALID", "P12 verification approver is invalid"
        )
    profile = _load_profile(profile_path)
    host = _host()
    if host["os"] != profile["supported_os"]:
        raise ImmuneSystemVerificationError(
            "HOST_UNSUPPORTED", "P12 representative profile requires Windows"
        )
    config = profile["workload"]
    output_root = output_directory.expanduser().resolve()
    run_root = output_root / f"p12-verified-{uuid.uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=False)
    database = run_root / "immune-system.db"
    identity_root = run_root / "identity"
    target = run_root / "runtime-component.bin"
    concurrent_target = run_root / "concurrent-component.bin"
    identity_secret = secrets.token_urlsafe(48)
    skin_secret = secrets.token_urlsafe(48)
    approved = secrets.token_bytes(int(config["artifact_bytes"]))
    unsafe = secrets.token_bytes(int(config["artifact_bytes"]))
    process = psutil.Process()
    rss_before = process.memory_info().rss
    components = _components(
        database=database,
        data_root=run_root,
        identity_root=identity_root,
        identity_secret=identity_secret,
        skin_secret=skin_secret,
        probe_timeout_seconds=float(config["probe_timeout_seconds"]),
    )
    _, _, immune = components
    target.write_bytes(approved)
    approved_digest = hashlib.sha256(approved).hexdigest()
    immune.register_target("representative-target", target, approved_digest, critical=True)

    scan_latencies: list[float] = []
    for _ in range(int(config["healthy_scan_operations"])):
        started = time.perf_counter()
        healthy = immune.scan("representative-target")
        scan_latencies.append((time.perf_counter() - started) * 1_000)
        if healthy is not None:
            raise ImmuneSystemVerificationError(
                "HEALTHY_SCAN_FAILED", "P12 healthy artifact opened an incident"
            )

    target.write_bytes(unsafe)
    quarantine_started = time.perf_counter()
    incident = immune.scan("representative-target")
    quarantine_latency_ms = (time.perf_counter() - quarantine_started) * 1_000
    if incident is None or incident.quarantine_path is None:
        raise ImmuneSystemVerificationError(
            "QUARANTINE_FAILED", "P12 did not quarantine the changed artifact"
        )
    quarantine_path = run_root / incident.quarantine_path
    quarantine_ciphertext = quarantine_path.read_bytes()
    target_isolated = not target.exists()
    quarantine_roundtrip = immune.open_quarantine(incident.incident_id) == unsafe
    for failure_code in ("TIMEOUT", "TIMEOUT", "INVALID_RESPONSE"):
        immune.record_dependency_failure("representative-dependency", failure_code)
    circuit_open = not immune.can_execute("representative-dependency")
    status_before_restart = immune.status()
    _close(components)

    restarted_components = _components(
        database=database,
        data_root=run_root,
        identity_root=identity_root,
        identity_secret=identity_secret,
        skin_secret=skin_secret,
        probe_timeout_seconds=float(config["probe_timeout_seconds"]),
    )
    _, _, restarted = restarted_components
    status_after_restart = restarted.status()
    target.write_bytes(b"wrong-replacement")
    wrong_recovery_code = _failure_code(lambda: restarted.recover_target("representative-target"))
    unhealthy_probe_code = _failure_code(
        lambda: restarted.recover_dependency("representative-dependency", lambda: False)
    )

    def failing_probe() -> bool:
        raise ValueError("representative provider failure")

    failed_probe_code = _failure_code(
        lambda: restarted.recover_dependency("representative-dependency", failing_probe)
    )
    probe_blocker = threading.Event()
    timeout_started = time.perf_counter()
    timeout_probe_code = _failure_code(
        lambda: restarted.recover_dependency(
            "representative-dependency", lambda: probe_blocker.wait(2.0)
        )
    )
    timeout_elapsed = time.perf_counter() - timeout_started
    probe_blocker.set()

    recovery_started = time.perf_counter()
    target.write_bytes(approved)
    target_recovery = restarted.recover_target("representative-target")
    dependency_recovery = restarted.recover_dependency("representative-dependency", lambda: True)
    recovery_latency_ms = (time.perf_counter() - recovery_started) * 1_000

    concurrent_target.write_bytes(approved)
    restarted.register_target(
        "concurrent-target",
        concurrent_target,
        approved_digest,
        critical=True,
    )
    concurrent_target.write_bytes(unsafe)
    with ThreadPoolExecutor(max_workers=int(config["concurrent_scans"])) as pool:
        concurrent_incidents = list(
            pool.map(
                lambda _: restarted.scan("concurrent-target"),
                range(int(config["concurrent_scans"])),
            )
        )
    concurrent_ids = {item.incident_id for item in concurrent_incidents if item is not None}
    concurrent_paths = {item.quarantine_path for item in concurrent_incidents if item is not None}
    concurrent_target.write_bytes(approved)
    restarted.recover_target("concurrent-target")
    audit_started = time.perf_counter()
    audit_valid = restarted.audit_chain_valid()
    full_audit_seconds = time.perf_counter() - audit_started
    status_after_recovery = restarted.status()

    envelope = json.loads(quarantine_path.read_text(encoding="utf-8"))
    envelope["subject"] = "target:forged"
    quarantine_path.write_text(json.dumps(envelope), encoding="utf-8")
    quarantine_tamper_code = _failure_code(lambda: restarted.open_quarantine(incident.incident_id))
    _close(restarted_components)

    recovery_database = run_root / "recovery.db"
    backup_started = time.perf_counter()
    with sqlite3.connect(database) as source, sqlite3.connect(recovery_database) as target_db:
        source.backup(target_db)
    recovery_components = _components(
        database=recovery_database,
        data_root=run_root,
        identity_root=identity_root,
        identity_secret=identity_secret,
        skin_secret=skin_secret,
        probe_timeout_seconds=float(config["probe_timeout_seconds"]),
    )
    recovery_status = recovery_components[2].status()
    _close(recovery_components)
    backup_recovery_latency_ms = (time.perf_counter() - backup_started) * 1_000

    audit_tamper_database = run_root / "audit-tamper.db"
    shutil.copy2(database, audit_tamper_database)
    with sqlite3.connect(audit_tamper_database) as connection:
        row = connection.execute(
            """
            SELECT event_id, occurred_at, event, previous_sha256
            FROM immune_audit ORDER BY event_id DESC LIMIT 1
            """
        ).fetchone()
        forged_payload = {"forged": True}
        forged_content = {
            "occurred_at": row[1],
            "event": row[2],
            "payload": forged_payload,
            "previous_sha256": row[3],
        }
        connection.execute(
            """
            UPDATE immune_audit SET payload_json = ?, event_sha256 = ?
            WHERE event_id = ?
            """,
            (
                _canonical(forged_payload).decode(),
                hashlib.sha256(_canonical(forged_content)).hexdigest(),
                row[0],
            ),
        )

    def open_tampered(database_path: Path) -> None:
        tampered = _components(
            database=database_path,
            data_root=run_root,
            identity_root=identity_root,
            identity_secret=identity_secret,
            skin_secret=skin_secret,
            probe_timeout_seconds=float(config["probe_timeout_seconds"]),
        )
        _close(tampered)

    audit_tamper_code = _failure_code(lambda: open_tampered(audit_tamper_database))

    state_tamper_database = run_root / "state-tamper.db"
    shutil.copy2(database, state_tamper_database)
    with sqlite3.connect(state_tamper_database) as connection:
        row = connection.execute(
            "SELECT incident_id, record_json FROM immune_incidents LIMIT 1"
        ).fetchone()
        record = json.loads(row[1])
        record["source_id"] = "forged-source"
        serialized = _canonical(record).decode()
        connection.execute(
            """
            UPDATE immune_incidents SET record_json = ?, source_id = ?, row_digest = ?
            WHERE incident_id = ?
            """,
            (
                serialized,
                "forged-source",
                hashlib.sha256(serialized.encode()).hexdigest(),
                row[0],
            ),
        )
    state_tamper_code = _failure_code(lambda: open_tampered(state_tamper_database))

    legacy_root = run_root / "legacy-upgrade"
    legacy_root.mkdir()
    legacy_database = legacy_root / "legacy.db"
    legacy_target = legacy_root / "legacy.bin"
    legacy_target.write_bytes(approved)
    legacy_components = _components(
        database=legacy_database,
        data_root=legacy_root,
        identity_root=identity_root,
        identity_secret=identity_secret,
        skin_secret=skin_secret,
        probe_timeout_seconds=float(config["probe_timeout_seconds"]),
    )
    legacy_immune = legacy_components[2]
    legacy_immune.register_target("legacy-target", legacy_target, approved_digest, critical=True)
    legacy_immune.record_dependency_failure("legacy-dependency", "TIMEOUT")
    _close(legacy_components)
    with sqlite3.connect(legacy_database) as connection:
        connection.execute("UPDATE immune_circuit_breakers SET attestation_json = NULL")
        connection.execute("UPDATE immune_audit SET attestation_json = NULL")
    upgraded_components = _components(
        database=legacy_database,
        data_root=legacy_root,
        identity_root=identity_root,
        identity_secret=identity_secret,
        skin_secret=skin_secret,
        probe_timeout_seconds=float(config["probe_timeout_seconds"]),
    )
    legacy_status = upgraded_components[2].status()
    _close(upgraded_components)

    demo = _run_demo(root, run_root / "production-path-demo")
    rss_growth = max(0, process.memory_info().rss - rss_before)
    operation_count = int(config["healthy_scan_operations"]) + int(config["concurrent_scans"])
    storage_bytes = sum(path.stat().st_size for path in run_root.rglob("*") if path.is_file())
    storage_per_operation = storage_bytes / operation_count
    leak_scan = _scan_for_secrets(
        run_root,
        [identity_secret.encode(), skin_secret.encode(), unsafe],
    )
    scan_mean = mean(scan_latencies)
    scan_p95 = _percentile_95(scan_latencies)
    demo_result = demo["result"] if isinstance(demo["result"], dict) else {}

    gates = [
        _gate("windows_representative_host", host["os"] == "Windows", host["os"], "Windows"),
        _gate(
            "healthy_scan_workload",
            len(scan_latencies) == int(config["healthy_scan_operations"]),
            len(scan_latencies),
            config["healthy_scan_operations"],
        ),
        _gate(
            "scan_mean_latency",
            scan_mean <= float(config["max_scan_mean_latency_ms"]),
            scan_mean,
            config["max_scan_mean_latency_ms"],
        ),
        _gate(
            "scan_p95_latency",
            scan_p95 <= float(config["max_scan_p95_latency_ms"]),
            scan_p95,
            config["max_scan_p95_latency_ms"],
        ),
        _gate(
            "encrypted_quarantine",
            incident.quarantine_path is not None
            and target_isolated
            and unsafe not in quarantine_ciphertext,
            {
                "path": incident.quarantine_path,
                "plaintext_absent": unsafe not in quarantine_ciphertext,
                "target_isolated": target_isolated,
            },
            "isolated and encrypted",
        ),
        _gate("quarantine_roundtrip", quarantine_roundtrip, quarantine_roundtrip, True),
        _gate(
            "quarantine_tamper_rejected",
            quarantine_tamper_code == ImmuneFailureCode.QUARANTINE_CORRUPT.value,
            quarantine_tamper_code,
            ImmuneFailureCode.QUARANTINE_CORRUPT.value,
        ),
        _gate(
            "quarantine_latency",
            quarantine_latency_ms <= float(config["max_quarantine_latency_ms"]),
            quarantine_latency_ms,
            config["max_quarantine_latency_ms"],
        ),
        _gate(
            "persistent_safe_stop",
            status_before_restart["safe_stop"] is True
            and status_after_restart["safe_stop"] is True,
            {"before": status_before_restart, "after": status_after_restart},
            "true before and after restart",
        ),
        _gate("circuit_breaker_open", circuit_open, circuit_open, True),
        _gate(
            "wrong_recovery_rejected",
            wrong_recovery_code == ImmuneFailureCode.RECOVERY_REJECTED.value,
            wrong_recovery_code,
            ImmuneFailureCode.RECOVERY_REJECTED.value,
        ),
        _gate(
            "unhealthy_probe_rejected",
            unhealthy_probe_code == ImmuneFailureCode.RECOVERY_REJECTED.value,
            unhealthy_probe_code,
            ImmuneFailureCode.RECOVERY_REJECTED.value,
        ),
        _gate(
            "probe_exception_stable",
            failed_probe_code == ImmuneFailureCode.PROBE_FAILED.value,
            failed_probe_code,
            ImmuneFailureCode.PROBE_FAILED.value,
        ),
        _gate(
            "probe_timeout_bounded",
            timeout_probe_code == ImmuneFailureCode.PROBE_TIMEOUT.value
            and timeout_elapsed < float(config["probe_timeout_seconds"]) + 0.5,
            {"code": timeout_probe_code, "elapsed_seconds": timeout_elapsed},
            "PROBE_TIMEOUT within bound",
        ),
        _gate(
            "verified_recovery",
            target_recovery.state.value == "RESOLVED"
            and dependency_recovery.state.value == "RESOLVED"
            and status_after_recovery["ready"] is True,
            status_after_recovery,
            "all resolved and ready",
        ),
        _gate(
            "recovery_latency",
            recovery_latency_ms <= float(config["max_recovery_latency_ms"]),
            recovery_latency_ms,
            config["max_recovery_latency_ms"],
        ),
        _gate(
            "concurrent_scan_idempotency",
            len(concurrent_ids) == 1 and len(concurrent_paths) == 1,
            {"incident_ids": len(concurrent_ids), "quarantine_paths": len(concurrent_paths)},
            "one incident and quarantine",
        ),
        _gate("signed_audit_valid", audit_valid, audit_valid, True),
        _gate(
            "recomputed_audit_rejected",
            audit_tamper_code == ImmuneFailureCode.AUDIT_CORRUPT.value,
            audit_tamper_code,
            ImmuneFailureCode.AUDIT_CORRUPT.value,
        ),
        _gate(
            "recomputed_state_rejected",
            state_tamper_code == ImmuneFailureCode.AUDIT_CORRUPT.value,
            state_tamper_code,
            ImmuneFailureCode.AUDIT_CORRUPT.value,
        ),
        _gate(
            "legacy_state_upgrade",
            legacy_status["storage_schema_version"] == 2
            and legacy_status["state_authenticated"] is True,
            legacy_status,
            "schema 2 authenticated",
        ),
        _gate(
            "sqlite_backup_recovery",
            recovery_status["ready"] is True and recovery_status["state_authenticated"] is True,
            recovery_status,
            "ready and authenticated",
        ),
        _gate(
            "backup_recovery_latency",
            backup_recovery_latency_ms <= float(config["max_recovery_latency_ms"]),
            backup_recovery_latency_ms,
            config["max_recovery_latency_ms"],
        ),
        _gate(
            "full_audit_time",
            full_audit_seconds <= float(config["max_full_audit_seconds"]),
            full_audit_seconds,
            config["max_full_audit_seconds"],
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
                demo_result.get(field) is True
                for field in (
                    "healthy_scan",
                    "quarantined",
                    "quarantine_roundtrip",
                    "plaintext_absent",
                    "circuit_open",
                    "unhealthy_probe_rejected",
                    "safe_stop",
                    "restart_safe_stop",
                    "verified_recovery",
                    "audit_chain_valid",
                    "state_authenticated",
                )
            ),
            demo_result,
            "all production-path checks true",
        ),
        _gate(
            "external_observation_truth_boundary",
            True,
            "BLOCKED_EXTERNAL",
            "live telemetry exporter and sustained production observation excluded",
        ),
    ]
    failed = [gate["name"] for gate in gates if not gate["passed"]]
    if failed:
        raise ImmuneSystemVerificationError(
            "GATE_FAILED", f"P12 representative gates failed: {', '.join(failed)}"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE",
        "pillar": "P012",
        "profile_id": profile["profile_id"],
        "scope": profile["scope"],
        "verified_at": datetime.now(UTC).isoformat(),
        "approval": {"approver": normalized_approver, "scope": "representative-local"},
        "environment": host,
        "version": _git_version(root),
        "artifact_integrity": {
            "profile_sha256": profile["profile_sha256"],
            "source_bundle_sha256": _source_bundle_sha256(root, profile["source_files"]),
            "source_files": profile["source_files"],
        },
        "lifecycle": {
            "status_before_restart": status_before_restart,
            "status_after_restart": status_after_restart,
            "status_after_recovery": status_after_recovery,
            "quarantine_roundtrip": quarantine_roundtrip,
            "concurrent_incident_ids": len(concurrent_ids),
            "concurrent_quarantine_paths": len(concurrent_paths),
        },
        "failure_paths": {
            "wrong_recovery": wrong_recovery_code,
            "unhealthy_probe": unhealthy_probe_code,
            "failed_probe": failed_probe_code,
            "timeout_probe": timeout_probe_code,
            "quarantine_tamper": quarantine_tamper_code,
            "recomputed_audit": audit_tamper_code,
            "recomputed_state": state_tamper_code,
        },
        "recovery": {
            "database": str(recovery_database),
            "status": recovery_status,
            "lifecycle_latency_ms": recovery_latency_ms,
            "backup_latency_ms": backup_recovery_latency_ms,
        },
        "performance": {
            "healthy_scans": len(scan_latencies),
            "artifact_bytes": config["artifact_bytes"],
            "scan_mean_latency_ms": scan_mean,
            "scan_p95_latency_ms": scan_p95,
            "quarantine_latency_ms": quarantine_latency_ms,
            "full_audit_seconds": full_audit_seconds,
            "rss_growth_bytes": rss_growth,
            "storage_bytes": storage_bytes,
            "storage_bytes_per_operation": storage_per_operation,
        },
        "production_path_demo": demo,
        "secret_leak_scan": leak_scan,
        "limitations": [
            "Telemetry is sanitized local runtime data; no live SIEM/OTel exporter is claimed.",
            "Sustained production incident observation and independent security review remain BLOCKED_EXTERNAL.",
            "Whole-database anti-rollback requires an external monotonic TPM/KMS anchor.",
            "This report is representative verification, not a production deployment certificate.",
        ],
        "rollback": {
            "schema": "storage schema v2 signs valid legacy incident, circuit, and audit state without deleting records",
            "operations": "failed state transitions roll back state and audit in one BEGIN IMMEDIATE transaction",
            "recovery_artifact": str(recovery_database),
        },
        "gates": {"passed": len(gates), "total": len(gates), "results": gates},
    }
    report_path = run_root / "verified-immune-system-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report_digest = _digest(report_path.read_bytes())
    report_path.with_suffix(report_path.suffix + ".sha256").write_text(
        f"{report_digest}  {report_path.name}\n", encoding="utf-8"
    )
    return report_path, report


__all__ = ["ImmuneSystemVerificationError", "verify_immune_system"]
