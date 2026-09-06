"""Representative verification runner for Pillar 14 Hardware Locked."""

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
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import psutil

from jaya_core.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from jaya_core.brain_v2.protection.hardware import (
    HardwareBindingError,
    HardwareBindingFailureCode,
    NodeBindingAuthority,
    WindowsDPAPIMachineProvider,
)
from jaya_core.security.cryptographic_skin import CryptographicSkin

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
    "provider_roundtrips",
    "boot_authorizations",
    "concurrent_workers",
    "operations_per_worker",
    "payload_bytes",
    "max_provider_mean_latency_ms",
    "max_boot_mean_latency_ms",
    "max_boot_p95_latency_ms",
    "max_migration_latency_ms",
    "max_recovery_latency_ms",
    "max_full_audit_seconds",
    "max_rss_growth_bytes",
    "max_storage_bytes_per_operation",
}


class HardwareLockedVerificationError(RuntimeError):
    """Stable P14 representative verification failure."""

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
        raise HardwareLockedVerificationError(
            "PROFILE_INVALID", "P14 verification profile is invalid"
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
        raise HardwareLockedVerificationError(
            "PROFILE_INVALID", "P14 verification profile fields are invalid"
        )
    integer_fields = {
        "provider_roundtrips",
        "boot_authorizations",
        "concurrent_workers",
        "operations_per_worker",
        "payload_bytes",
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
            raise HardwareLockedVerificationError(
                "PROFILE_INVALID", f"P14 workload threshold {field} is invalid"
            )
    if not 10 <= workload["provider_roundtrips"] <= 10_000:
        raise HardwareLockedVerificationError(
            "PROFILE_INVALID", "P14 provider roundtrip count is invalid"
        )
    if not 10 <= workload["boot_authorizations"] <= 10_000:
        raise HardwareLockedVerificationError(
            "PROFILE_INVALID", "P14 boot authorization count is invalid"
        )
    if not 2 <= workload["concurrent_workers"] <= 8:
        raise HardwareLockedVerificationError(
            "PROFILE_INVALID", "P14 concurrent worker count is invalid"
        )
    if not 1 <= workload["payload_bytes"] <= 16 * 1024 * 1024:
        raise HardwareLockedVerificationError("PROFILE_INVALID", "P14 payload size is invalid")
    return {**profile, "profile_sha256": _digest(raw)}


def _host() -> dict[str, object]:
    dependencies: dict[str, str] = {}
    for name in ("cryptography", "psutil", "pywin32"):
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
            raise HardwareLockedVerificationError(
                "SOURCE_INVALID", f"P14 source file is missing or outside repository: {relative}"
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


def _authority(
    database: Path,
    anchor: DNAAnchor,
    provider: WindowsDPAPIMachineProvider,
) -> NodeBindingAuthority:
    return NodeBindingAuthority(
        database,
        provider,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )


def _failure_code(action: Any) -> str:
    try:
        action()
    except HardwareBindingError as exc:
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
            str(root / "scripts" / "demo_hardware_binding.py"),
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
        raise HardwareLockedVerificationError(
            "DEMO_INVALID", "P14 production-path demo did not return JSON"
        ) from exc
    return {
        "command": completed.args,
        "exit_code": completed.returncode,
        "result": result,
        "stderr": completed.stderr[-4000:],
    }


def verify_hardware_locked(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Execute real local P14 gates and persist a digest-addressable report."""

    root = repository_root.expanduser().resolve()
    normalized_approver = approver.strip()
    if not _APPROVER.fullmatch(normalized_approver):
        raise HardwareLockedVerificationError(
            "APPROVER_INVALID", "P14 verification approver is invalid"
        )
    profile = _load_profile(profile_path)
    host = _host()
    if host["os"] != profile["supported_os"]:
        raise HardwareLockedVerificationError(
            "HOST_UNSUPPORTED", "P14 representative profile requires Windows"
        )
    provider = WindowsDPAPIMachineProvider()
    if not provider.available():
        raise HardwareLockedVerificationError(
            "PROVIDER_UNAVAILABLE", "Windows DPAPI machine provider is unavailable"
        )
    output_root = output_directory.expanduser().resolve()
    run_root = output_root / f"p14-verified-{uuid.uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=False)
    database = run_root / "hardware-locked.db"
    identity_root = run_root / "identity"
    envelope_path = run_root / "portable-brain.jaya-envelope.json"
    config = profile["workload"]
    identity_secret = secrets.token_urlsafe(48)
    skin_secret = secrets.token_urlsafe(48)
    payload = secrets.token_bytes(int(config["payload_bytes"]))
    process = psutil.Process()
    rss_before = process.memory_info().rss

    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
    )
    identity, _ = anchor.enroll()

    provider_latencies: list[float] = []
    for _ in range(int(config["provider_roundtrips"])):
        plaintext = secrets.token_bytes(32)
        associated_data = secrets.token_bytes(32)
        started = time.perf_counter()
        wrapped = provider.wrap(plaintext, associated_data)
        restored = provider.unwrap(wrapped, associated_data)
        provider_latencies.append((time.perf_counter() - started) * 1_000)
        if restored != plaintext or wrapped == plaintext:
            raise HardwareLockedVerificationError(
                "PROVIDER_ROUNDTRIP_FAILED", "DPAPI roundtrip returned invalid data"
            )

    authority = _authority(database, anchor, provider)
    enrolled = authority.enroll(identity.brain_id, "representative-node-a")
    boot_latencies: list[float] = []
    boot_receipts = []
    for _ in range(int(config["boot_authorizations"])):
        started = time.perf_counter()
        receipt = authority.authorize_boot(
            identity.brain_id, "representative-node-a", secrets.token_bytes(32)
        )
        boot_latencies.append((time.perf_counter() - started) * 1_000)
        boot_receipts.append(receipt)
    source_context = authority.binding_key_context(identity.brain_id, "representative-node-a")
    status_before_restart = authority.status(identity.brain_id)
    authority.close()

    skin = CryptographicSkin(
        database,
        skin_secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        key_binding_context=source_context,
    )
    envelope = skin.seal(
        payload,
        purpose="core.brain-capsule",
        subject=f"brain:{identity.brain_id}",
    )
    envelope_path.write_text(
        json.dumps(envelope.to_dict(), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    skin.close()

    restarted = _authority(database, anchor, provider)
    restart_receipt = restarted.authorize_boot(
        identity.brain_id, "representative-node-a", secrets.token_bytes(32)
    )
    status_after_restart = restarted.status(identity.brain_id)
    migration_started = time.perf_counter()
    migrated = restarted.migrate(identity.brain_id, "representative-node-b", provider)
    migration_latency_ms = (time.perf_counter() - migration_started) * 1_000
    restarted.close()

    target = _authority(database, anchor, provider)
    migrated_receipt = target.authorize_boot(
        identity.brain_id, "representative-node-b", secrets.token_bytes(32)
    )
    target_context = target.binding_key_context(identity.brain_id, "representative-node-b")
    wrong_node_code = _failure_code(
        lambda: target.authorize_boot(
            identity.brain_id, "unauthorized-clone-node", secrets.token_bytes(32)
        )
    )
    target.close()

    migrated_skin = CryptographicSkin(
        database,
        skin_secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        key_binding_context=target_context,
    )
    migrated_payload = migrated_skin.open(envelope)
    migrated_skin.close()

    concurrent_operations = int(config["operations_per_worker"])

    worker_count = int(config["concurrent_workers"])
    worker_anchors = [
        DNAAnchor(
            identity_root,
            EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
        )
        for _ in range(worker_count)
    ]
    worker_authorities = [
        _authority(database, worker_anchor, provider) for worker_anchor in worker_anchors
    ]

    def authorize_worker(worker: int) -> list[str]:
        local = worker_authorities[worker]
        try:
            return [
                local.authorize_boot(
                    identity.brain_id,
                    "representative-node-b",
                    hashlib.sha256(f"{worker}:{operation}:{uuid.uuid4()}".encode()).digest(),
                ).instance_id
                for operation in range(concurrent_operations)
            ]
        finally:
            local.close()
            worker_anchors[worker].close()

    with ThreadPoolExecutor(max_workers=int(config["concurrent_workers"])) as pool:
        concurrent_ids = [
            instance_id
            for batch in pool.map(authorize_worker, range(worker_count))
            for instance_id in batch
        ]
    audit_authority = _authority(database, anchor, provider)
    audit_started = time.perf_counter()
    audit_valid_after_concurrency = audit_authority.audit_chain_valid()
    full_audit_seconds = time.perf_counter() - audit_started
    audit_authority.close()

    recovery_database = run_root / "recovery.db"
    recovery_started = time.perf_counter()
    with sqlite3.connect(database) as source, sqlite3.connect(recovery_database) as target_db:
        source.backup(target_db)
    recovered = _authority(recovery_database, anchor, provider)
    try:
        recovery_receipt = recovered.authorize_boot(
            identity.brain_id, "representative-node-b", secrets.token_bytes(32)
        )
        recovery_audit_valid = recovered.audit_chain_valid()
    finally:
        recovered.close()
    recovery_latency_ms = (time.perf_counter() - recovery_started) * 1_000

    interruption_database = run_root / "interrupted-migration.db"
    interrupted = _authority(interruption_database, anchor, provider)
    interrupted.enroll(identity.brain_id, "interruption-node-a")
    with interrupted._connection:
        interrupted._connection.execute(
            """
            CREATE TRIGGER reject_verifier_migration_audit
            BEFORE INSERT ON hardware_binding_audit
            WHEN NEW.event = 'NODE_MIGRATED'
            BEGIN
                SELECT RAISE(ABORT, 'verification fault injection');
            END
            """
        )
    interruption_code = _failure_code(
        lambda: interrupted.migrate(identity.brain_id, "interruption-node-b", provider)
    )
    with interrupted._connection:
        interrupted._connection.execute("DROP TRIGGER reject_verifier_migration_audit")
    interruption_receipt = interrupted.authorize_boot(
        identity.brain_id, "interruption-node-a", secrets.token_bytes(32)
    )
    interruption_rows = [
        tuple(row)
        for row in interrupted._connection.execute(
            "SELECT node_id, state FROM hardware_bindings ORDER BY created_at"
        ).fetchall()
    ]
    interrupted.close()

    binding_tamper_database = run_root / "binding-tamper.db"
    shutil.copy2(database, binding_tamper_database)
    with sqlite3.connect(binding_tamper_database) as connection:
        connection.execute(
            "UPDATE hardware_bindings SET wrapped_secret = 'AAAA' WHERE state = 'ACTIVE'"
        )
    tampered_binding = _authority(binding_tamper_database, anchor, provider)
    binding_tamper_code = _failure_code(
        lambda: tampered_binding.authorize_boot(
            identity.brain_id, "representative-node-b", secrets.token_bytes(32)
        )
    )
    tampered_binding.close()

    audit_tamper_database = run_root / "audit-tamper.db"
    shutil.copy2(database, audit_tamper_database)
    with sqlite3.connect(audit_tamper_database) as connection:
        row = connection.execute(
            """
            SELECT event_id, occurred_at, event, previous_sha256
            FROM hardware_binding_audit ORDER BY event_id DESC LIMIT 1
            """
        ).fetchone()
        forged_payload = {"forged": True}
        forged = {
            "occurred_at": row[1],
            "event": row[2],
            "payload": forged_payload,
            "previous_sha256": row[3],
        }
        connection.execute(
            """
            UPDATE hardware_binding_audit SET payload_json = ?, event_sha256 = ?
            WHERE event_id = ?
            """,
            (
                _canonical(forged_payload).decode(),
                hashlib.sha256(_canonical(forged)).hexdigest(),
                row[0],
            ),
        )
    audit_tamper_code = _failure_code(lambda: _authority(audit_tamper_database, anchor, provider))

    final_authority = _authority(database, anchor, provider)
    final_authority.revoke(identity.brain_id)
    revoked_code = _failure_code(
        lambda: final_authority.authorize_boot(
            identity.brain_id, "representative-node-b", secrets.token_bytes(32)
        )
    )
    final_status = final_authority.status(identity.brain_id)
    final_authority.close()

    demo = _run_demo(root, run_root / "production-path-demo")
    rss_growth = max(0, process.memory_info().rss - rss_before)
    operation_count = (
        int(config["boot_authorizations"])
        + len(concurrent_ids)
        + int(config["provider_roundtrips"])
    )
    storage_bytes = sum(path.stat().st_size for path in run_root.rglob("*") if path.is_file())
    storage_per_operation = storage_bytes / operation_count
    leak_scan = _scan_for_secrets(
        run_root,
        [identity_secret.encode(), skin_secret.encode(), payload],
    )
    provider_mean = mean(provider_latencies)
    boot_mean = mean(boot_latencies)
    boot_p95 = _percentile_95(boot_latencies)
    provider_health = provider.health()
    demo_result = demo["result"] if isinstance(demo["result"], dict) else {}

    gates = [
        _gate("windows_representative_host", host["os"] == "Windows", host["os"], "Windows"),
        _gate("dpapi_provider_available", provider.available(), provider_health, "available"),
        _gate(
            "provider_truth_boundary",
            provider_health.get("hardware_backed") is False
            and provider_health.get("hardware_attestation") == "BLOCKED_EXTERNAL",
            provider_health,
            "OS machine scope; not TPM-attested",
        ),
        _gate(
            "provider_roundtrips",
            len(provider_latencies) == int(config["provider_roundtrips"]),
            len(provider_latencies),
            config["provider_roundtrips"],
        ),
        _gate(
            "provider_mean_latency",
            provider_mean <= float(config["max_provider_mean_latency_ms"]),
            provider_mean,
            config["max_provider_mean_latency_ms"],
        ),
        _gate(
            "binding_enrolled",
            enrolled.state.value == "ACTIVE",
            {
                "binding_id": enrolled.binding_id,
                "brain_id": enrolled.brain_id,
                "node_id": enrolled.node_id,
                "provider_id": enrolled.provider_id,
                "hardware_backed": enrolled.hardware_backed,
                "state": enrolled.state.value,
            },
            "ACTIVE",
        ),
        _gate(
            "brain_node_instance_separation",
            identity.brain_id == enrolled.brain_id
            and enrolled.node_id == "representative-node-a"
            and len({item.instance_id for item in boot_receipts}) == len(boot_receipts),
            len({item.instance_id for item in boot_receipts}),
            len(boot_receipts),
        ),
        _gate(
            "restart_authorized",
            restart_receipt.binding_id == enrolled.binding_id
            and status_after_restart["ready"] is True,
            status_after_restart,
            "same binding ready",
        ),
        _gate(
            "signed_audit_schema",
            status_before_restart["storage_schema_version"] == 2
            and status_before_restart["audit_attestations_verified"] is True,
            status_before_restart,
            "schema 2 signed audit",
        ),
        _gate(
            "wrong_node_rejected",
            wrong_node_code == HardwareBindingFailureCode.NODE_MISMATCH.value,
            wrong_node_code,
            HardwareBindingFailureCode.NODE_MISMATCH.value,
        ),
        _gate(
            "owner_migration_lineage",
            migrated.previous_binding_id == enrolled.binding_id
            and migrated_receipt.binding_id == migrated.binding_id,
            {
                "binding_id": migrated.binding_id,
                "previous_binding_id": migrated.previous_binding_id,
                "node_id": migrated.node_id,
                "provider_id": migrated.provider_id,
                "state": migrated.state.value,
            },
            "signed lineage preserved",
        ),
        _gate(
            "p13_portability_after_rewrap",
            source_context == target_context and migrated_payload == payload,
            {
                "context_stable": source_context == target_context,
                "payload_restored": migrated_payload == payload,
            },
            "both true",
        ),
        _gate(
            "migration_latency",
            migration_latency_ms <= float(config["max_migration_latency_ms"]),
            migration_latency_ms,
            config["max_migration_latency_ms"],
        ),
        _gate(
            "concurrent_authorizations",
            len(concurrent_ids)
            == int(config["concurrent_workers"]) * int(config["operations_per_worker"])
            and len(set(concurrent_ids)) == len(concurrent_ids)
            and audit_valid_after_concurrency,
            {
                "operations": len(concurrent_ids),
                "unique_instances": len(set(concurrent_ids)),
                "audit_valid": audit_valid_after_concurrency,
            },
            "all unique; audit valid",
        ),
        _gate(
            "atomic_migration_rollback",
            interruption_code == HardwareBindingFailureCode.STORAGE_ERROR.value
            and interruption_receipt.node_id == "interruption-node-a"
            and interruption_rows == [("interruption-node-a", "ACTIVE")],
            {"code": interruption_code, "rows": interruption_rows},
            "source remains active",
        ),
        _gate(
            "sqlite_recovery",
            recovery_receipt.node_id == "representative-node-b" and recovery_audit_valid,
            {"node_id": recovery_receipt.node_id, "audit_valid": recovery_audit_valid},
            "restored and audited",
        ),
        _gate(
            "recovery_latency",
            recovery_latency_ms <= float(config["max_recovery_latency_ms"]),
            recovery_latency_ms,
            config["max_recovery_latency_ms"],
        ),
        _gate(
            "binding_tamper_rejected",
            binding_tamper_code == HardwareBindingFailureCode.CORRUPT_BINDING.value,
            binding_tamper_code,
            HardwareBindingFailureCode.CORRUPT_BINDING.value,
        ),
        _gate(
            "recomputed_audit_rejected",
            audit_tamper_code == HardwareBindingFailureCode.AUDIT_CORRUPT.value,
            audit_tamper_code,
            HardwareBindingFailureCode.AUDIT_CORRUPT.value,
        ),
        _gate(
            "revocation_fail_closed",
            revoked_code == HardwareBindingFailureCode.BINDING_NOT_FOUND.value
            and final_status["ready"] is False,
            {"code": revoked_code, "status": final_status},
            "revoked and not ready",
        ),
        _gate(
            "boot_mean_latency",
            boot_mean <= float(config["max_boot_mean_latency_ms"]),
            boot_mean,
            config["max_boot_mean_latency_ms"],
        ),
        _gate(
            "boot_p95_latency",
            boot_p95 <= float(config["max_boot_p95_latency_ms"]),
            boot_p95,
            config["max_boot_p95_latency_ms"],
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
                    "provider_available",
                    "brain_id_stable",
                    "instance_rotated",
                    "restart_restored",
                    "migration_restored",
                    "migration_lineage",
                    "binding_context_stable",
                    "plaintext_absent",
                    "p13_hardware_bound",
                    "clone_rejected",
                    "audit_chain_valid",
                    "audit_attestations_verified",
                )
            ),
            demo_result,
            "all production-path checks true",
        ),
        _gate(
            "hardware_attestation_truth_boundary",
            True,
            "BLOCKED_EXTERNAL",
            "TPM/Secure Enclave excluded from representative claim",
        ),
    ]
    failed = [gate["name"] for gate in gates if not gate["passed"]]
    if failed:
        raise HardwareLockedVerificationError(
            "GATE_FAILED", f"P14 representative gates failed: {', '.join(failed)}"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE",
        "pillar": "P014",
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
        "provider": provider_health,
        "identity_and_binding": {
            "brain_id": identity.brain_id,
            "source_binding_id": enrolled.binding_id,
            "target_binding_id": migrated.binding_id,
            "source_node_id": enrolled.node_id,
            "target_node_id": migrated.node_id,
            "restart_instance_id": restart_receipt.instance_id,
            "migration_instance_id": migrated_receipt.instance_id,
            "context_stable_after_rewrap": source_context == target_context,
        },
        "failure_paths": {
            "wrong_node": wrong_node_code,
            "binding_tamper": binding_tamper_code,
            "recomputed_audit": audit_tamper_code,
            "migration_interruption": interruption_code,
            "revocation": revoked_code,
        },
        "recovery": {
            "database": str(recovery_database),
            "node_id": recovery_receipt.node_id,
            "audit_valid": recovery_audit_valid,
            "latency_ms": recovery_latency_ms,
        },
        "concurrency": {
            "workers": config["concurrent_workers"],
            "operations": len(concurrent_ids),
            "unique_instances": len(set(concurrent_ids)),
            "audit_valid": audit_valid_after_concurrency,
        },
        "performance": {
            "provider_roundtrips": len(provider_latencies),
            "provider_mean_latency_ms": provider_mean,
            "boot_authorizations": len(boot_latencies),
            "boot_mean_latency_ms": boot_mean,
            "boot_p95_latency_ms": boot_p95,
            "migration_latency_ms": migration_latency_ms,
            "full_audit_seconds": full_audit_seconds,
            "rss_growth_bytes": rss_growth,
            "storage_bytes": storage_bytes,
            "storage_bytes_per_operation": storage_per_operation,
        },
        "production_path_demo": demo,
        "secret_leak_scan": leak_scan,
        "limitations": [
            "Windows DPAPI LOCAL_MACHINE is an OS-managed machine boundary and is not claimed as TPM-backed.",
            "TPM/Secure Enclave attestation and measured boot remain BLOCKED_EXTERNAL.",
            "The migration drill is a representative node-ID rewrap on one Windows host; cross-machine handoff remains external.",
            "Whole-database anti-rollback requires an external monotonic TPM/KMS anchor and is outside this profile.",
            "This report is representative verification, not sustained production deployment evidence.",
        ],
        "rollback": {
            "schema": "storage schema v2 upgrades legacy audit hashes by DNA-signing each valid event without deleting binding records",
            "operations": "failed migrations roll back binding state and audit event in one BEGIN IMMEDIATE transaction",
            "recovery_artifact": str(recovery_database),
        },
        "gates": {"passed": len(gates), "total": len(gates), "results": gates},
    }
    report_path = run_root / "verified-hardware-locked-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report_digest = _digest(report_path.read_bytes())
    report_path.with_suffix(report_path.suffix + ".sha256").write_text(
        f"{report_digest}  {report_path.name}\n", encoding="utf-8"
    )
    return report_path, report


__all__ = [
    "HardwareLockedVerificationError",
    "verify_hardware_locked",
]
