"""Representative verification runner for Pillar 11 DNA Anchor."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from jaya_core.brain_v2.protection.dna_anchor import (
    DNAAnchor,
    DNAAnchorError,
    DNAFailureCode,
    EncryptedFileKeyStore,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "purposes",
    "rotations",
    "resource_limits",
    "soak",
    "source_files",
}
_RESOURCE_FIELDS = {
    "max_outstanding_challenges",
    "storage_timeout_seconds",
    "max_lock_elapsed_seconds",
}
_SOAK_FIELDS = {
    "iterations",
    "minimum_elapsed_seconds",
    "max_mean_roundtrip_latency_ms",
    "max_full_audit_seconds",
    "max_rss_growth_bytes",
    "max_storage_bytes_per_roundtrip",
    "max_package_joules_per_roundtrip",
}


class DNAVerificationError(RuntimeError):
    """Stable P11 verification failure carrying the failed boundary."""

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
    try:
        raw = path.expanduser().resolve().read_bytes()
        profile = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DNAVerificationError("PROFILE_INVALID", "P11 profile is invalid") from exc
    resource = profile.get("resource_limits") if isinstance(profile, dict) else None
    soak = profile.get("soak") if isinstance(profile, dict) else None
    purposes = profile.get("purposes") if isinstance(profile, dict) else None
    if (
        not isinstance(profile, dict)
        or set(profile) != _PROFILE_FIELDS
        or profile["schema_version"] != 1
        or not _PROFILE_ID.fullmatch(str(profile["profile_id"]))
        or not isinstance(profile["scope"], str)
        or not profile["scope"].strip()
        or not isinstance(profile["supported_os"], str)
        or not isinstance(purposes, list)
        or len(purposes) < 3
        or len(set(purposes)) != len(purposes)
        or any(not isinstance(item, str) or not item for item in purposes)
        or type(profile["rotations"]) is not int
        or not 1 <= profile["rotations"] <= 10
        or not isinstance(resource, dict)
        or set(resource) != _RESOURCE_FIELDS
        or not isinstance(soak, dict)
        or set(soak) != _SOAK_FIELDS
        or not isinstance(profile["source_files"], list)
        or not profile["source_files"]
    ):
        raise DNAVerificationError("PROFILE_INVALID", "P11 profile fields are invalid")
    if (
        type(resource["max_outstanding_challenges"]) is not int
        or not 1 <= resource["max_outstanding_challenges"] <= 100
        or isinstance(resource["storage_timeout_seconds"], bool)
        or not isinstance(resource["storage_timeout_seconds"], (int, float))
        or not 0.001 <= float(resource["storage_timeout_seconds"]) <= 5.0
        or isinstance(resource["max_lock_elapsed_seconds"], bool)
        or not isinstance(resource["max_lock_elapsed_seconds"], (int, float))
        or not 0.01 <= float(resource["max_lock_elapsed_seconds"]) <= 10.0
        or type(soak["iterations"]) is not int
        or not 1_000 <= soak["iterations"] <= 100_000
    ):
        raise DNAVerificationError("PROFILE_INVALID", "P11 profile limits are invalid")
    for field in _SOAK_FIELDS - {"iterations", "max_rss_growth_bytes"}:
        value = soak[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise DNAVerificationError("PROFILE_INVALID", "P11 soak limits are invalid")
    if type(soak["max_rss_growth_bytes"]) is not int or soak["max_rss_growth_bytes"] <= 0:
        raise DNAVerificationError("PROFILE_INVALID", "P11 RSS limit is invalid")
    return {**profile, "profile_sha256": _digest(raw)}


def _source_bundle_sha256(root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
            raw = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise DNAVerificationError(
                "SOURCE_UNAVAILABLE", "P11 verification source bundle is unavailable"
            ) from exc
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "little"))
        digest.update(raw)
    return f"sha256:{digest.hexdigest()}"


def _git_version(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10.0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DNAVerificationError("GIT_UNAVAILABLE", "git version unavailable") from exc
        if completed.returncode != 0:
            raise DNAVerificationError("GIT_UNAVAILABLE", "git version unavailable")
        return completed.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD"),
        "worktree_dirty": bool(run("status", "--porcelain")),
    }


def _host() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "ram_bytes": psutil.virtual_memory().total,
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "cryptography": importlib.metadata.version("cryptography"),
        "psutil": psutil.__version__,
    }


def _anchor(
    root: Path,
    secret: str,
    *,
    storage_timeout_seconds: float = 5.0,
    max_outstanding_challenges: int = 10_000,
) -> DNAAnchor:
    return DNAAnchor(
        root,
        EncryptedFileKeyStore(root / "keystore", secret),
        storage_timeout_seconds=storage_timeout_seconds,
        max_outstanding_challenges=max_outstanding_challenges,
    )


def _expect_error(call: Callable[[], object], code: DNAFailureCode) -> str:
    try:
        call()
    except DNAAnchorError as exc:
        if exc.code is not code:
            raise DNAVerificationError(
                "FAULT_DRILL_FAILED", "P11 returned an unexpected failure code"
            ) from exc
        return exc.code.value
    raise DNAVerificationError("FAULT_DRILL_FAILED", "P11 accepted invalid state")


def _copy_identity(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with (
        sqlite3.connect(source / "dna_identity.db") as source_connection,
        sqlite3.connect(destination / "dna_identity.db") as destination_connection,
    ):
        source_connection.backup(destination_connection)
    shutil.copytree(source / "keystore", destination / "keystore")


def _storage_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _envelope_probe(root: Path, secret: str) -> dict[str, Any]:
    path = root / "keystore" / "dna_private_key.json"
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    with sqlite3.connect(root / "dna_identity.db") as connection:
        columns = {
            row[1]
            for table in ("brain_identity_records", "identity_audit", "identity_challenges")
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
    return {
        "fields": sorted(payload),
        "kdf": payload.get("kdf"),
        "size_bytes": len(raw),
        "secret_absent": secret.encode("utf-8") not in raw,
        "private_key_field_absent": b"private_key" not in raw,
        "private_database_column_absent": all("private" not in item for item in columns),
    }


def _runtime_probe(root: Path, secret: str, node_id: str) -> dict[str, Any]:
    anchor = _anchor(root, secret)
    runtime = JayaCoreRuntime(
        db_path=root.parent / f"{node_id}.sqlite3",
        identity_anchor=anchor,
        identity_required=True,
        node_id=node_id,
    )
    try:
        snapshot = runtime.operational_snapshot()
        return {
            "ready": runtime.is_ready(),
            "brain_id": snapshot["brain_id"],
            "node_id": snapshot["node_id"],
            "identity_mode": snapshot["identity_mode"],
        }
    finally:
        runtime.close()


def _lifecycle(root: Path, secret: str, profile: dict[str, Any]) -> dict[str, Any]:
    anchor = _anchor(root, secret)
    try:
        initial = anchor.load_identity()
        initial_health = anchor.health_check()
        purpose_receipts: list[str] = []
        replay_code = ""
        for index, purpose in enumerate(profile["purposes"]):
            challenge = anchor.issue_challenge(purpose)
            signature = anchor.sign_challenge(challenge)
            receipt = anchor.verify_challenge(challenge, signature)
            purpose_receipts.append(receipt.event)
            if index == 0:
                replay_code = _expect_error(
                    lambda item=challenge, proof=signature: anchor.verify_challenge(item, proof),
                    DNAFailureCode.REPLAY_DETECTED,
                )

        malformed = anchor.issue_challenge("runtime.malformed")
        malformed_code = _expect_error(
            lambda: anchor.sign_challenge(replace(malformed, expires_at="invalid")),
            DNAFailureCode.CHALLENGE_INVALID,
        )
        unknown = anchor.issue_challenge("runtime.unknown")
        with sqlite3.connect(root / "dna_identity.db") as connection:
            connection.execute(
                "DELETE FROM identity_challenges WHERE purpose=?", (unknown.purpose,)
            )
        unknown_code = _expect_error(
            lambda: anchor.sign_challenge(unknown),
            DNAFailureCode.CHALLENGE_INVALID,
        )
        invalid_signature_challenge = anchor.issue_challenge("runtime.invalid-signature")
        invalid_signature_code = _expect_error(
            lambda: anchor.verify_challenge(invalid_signature_challenge, "invalid"),
            DNAFailureCode.SIGNATURE_INVALID,
        )

        digest = hashlib.sha256(b"p11 historical attestation").hexdigest()
        historical_attestation = anchor.sign_attestation("artifact.sign", digest)
        tampered_attestation = {
            **historical_attestation.to_dict(),
            "payload_sha256": hashlib.sha256(b"tampered").hexdigest(),
        }
        pending = anchor.issue_challenge("runtime.rotation-boundary")
        pending_signature = anchor.sign_challenge(pending)
        rotations = []
        for _ in range(int(profile["rotations"])):
            record, receipt = anchor.rotate_key()
            rotations.append(
                {
                    "key_version": record.key_version,
                    "brain_id": record.brain_id,
                    "owner_id": record.owner_id,
                    "event": receipt.event,
                    "previous_key_fingerprint": record.previous_key_fingerprint,
                    "rotation_proof_present": bool(record.rotation_proof),
                }
            )
        current = anchor.load_identity()
        old_signature_code = _expect_error(
            lambda: anchor.verify_challenge(pending, pending_signature),
            DNAFailureCode.SIGNATURE_INVALID,
        )
        return {
            "initial_health": initial_health,
            "brain_id": initial.brain_id,
            "owner_id": initial.owner_id,
            "purpose_receipts": purpose_receipts,
            "replay_code": replay_code,
            "malformed_code": malformed_code,
            "unknown_code": unknown_code,
            "invalid_signature_code": invalid_signature_code,
            "attestation_valid": anchor.verify_attestation(historical_attestation),
            "tampered_attestation_rejected": not anchor.verify_attestation(tampered_attestation),
            "rotations": rotations,
            "current_key_version": current.key_version,
            "brain_stable": current.brain_id == initial.brain_id,
            "owner_stable": current.owner_id == initial.owner_id,
            "old_signature_code": old_signature_code,
            "audit_valid": anchor.audit_chain_valid(),
        }
    finally:
        anchor.close()


def _restart_and_migration(
    run_root: Path, source: Path, secret: str, brain_id: str, owner_id: str
) -> dict[str, Any]:
    restarted = _anchor(source, secret)
    try:
        record = restarted.load_identity()
        restart = {
            "healthy": restarted.health_check(),
            "brain_id": record.brain_id,
            "owner_id": record.owner_id,
        }
    finally:
        restarted.close()

    migrated_root = run_root / "official-migration"
    _copy_identity(source, migrated_root)
    migrated = _anchor(migrated_root, secret)
    try:
        record = migrated.load_identity()
        migration = {
            "healthy": migrated.health_check(),
            "brain_id": record.brain_id,
            "owner_id": record.owner_id,
        }
    finally:
        migrated.close()
    return {
        "restart": restart,
        "migration": migration,
        "expected_brain_id": brain_id,
        "expected_owner_id": owner_id,
    }


def _copy_faults(run_root: Path, source: Path, secret: str) -> dict[str, Any]:
    clone_root = run_root / "database-only-clone"
    clone_root.mkdir()
    with (
        sqlite3.connect(source / "dna_identity.db") as source_connection,
        sqlite3.connect(clone_root / "dna_identity.db") as destination_connection,
    ):
        source_connection.backup(destination_connection)
    clone = _anchor(clone_root, secret)
    try:
        clone_code = _expect_error(clone.load_identity, DNAFailureCode.KEYSTORE_UNAVAILABLE)
    finally:
        clone.close()

    wrong_secret_root = run_root / "wrong-secret"
    _copy_identity(source, wrong_secret_root)
    wrong_secret = _anchor(wrong_secret_root, secrets.token_urlsafe(48))
    try:
        wrong_secret_code = _expect_error(
            wrong_secret.load_identity, DNAFailureCode.KEYSTORE_DECRYPTION_FAILED
        )
    finally:
        wrong_secret.close()

    kdf_root = run_root / "kdf-tamper"
    _copy_identity(source, kdf_root)
    keystore_path = kdf_root / "keystore" / "dna_private_key.json"
    envelope = json.loads(keystore_path.read_text(encoding="utf-8"))
    envelope["kdf"] = "untrusted-kdf"
    keystore_path.write_text(json.dumps(envelope), encoding="utf-8")
    kdf = _anchor(kdf_root, secret)
    try:
        kdf_code = _expect_error(kdf.load_identity, DNAFailureCode.KEYSTORE_DECRYPTION_FAILED)
    finally:
        kdf.close()

    identity_root = run_root / "identity-tamper"
    _copy_identity(source, identity_root)
    with sqlite3.connect(identity_root / "dna_identity.db") as connection:
        connection.execute(
            "UPDATE brain_identity_records SET public_key='tampered' WHERE status='ACTIVE'"
        )
    identity = _anchor(identity_root, secret)
    try:
        identity_code = _expect_error(identity.load_identity, DNAFailureCode.IDENTITY_CORRUPT)
        identity_health = identity.health_check()
    finally:
        identity.close()

    audit_root = run_root / "audit-tamper"
    _copy_identity(source, audit_root)
    with sqlite3.connect(audit_root / "dna_identity.db") as connection:
        connection.execute("UPDATE identity_audit SET event='TAMPERED' WHERE event_id=1")
    audit = _anchor(audit_root, secret)
    try:
        audit_chain = audit.audit_chain_valid()
        audit_health = audit.health_check()
    finally:
        audit.close()

    schema_root = run_root / "schema-tamper"
    _copy_identity(source, schema_root)
    with sqlite3.connect(schema_root / "dna_identity.db") as connection:
        connection.execute("UPDATE dna_meta SET value='999' WHERE key='schema_version'")
    schema_code = _expect_error(
        lambda: _anchor(schema_root, secret),
        DNAFailureCode.STORAGE_SCHEMA_UNSUPPORTED,
    )
    return {
        "database_only_clone": clone_code,
        "wrong_secret": wrong_secret_code,
        "kdf_tamper": kdf_code,
        "identity_tamper": identity_code,
        "identity_tamper_health": identity_health,
        "audit_chain_after_tamper": audit_chain,
        "audit_tamper_health": audit_health,
        "newer_schema": schema_code,
    }


def _runtime_audit_fault(run_root: Path, source: Path, secret: str) -> dict[str, Any]:
    root = run_root / "runtime-audit-tamper"
    _copy_identity(source, root)
    anchor = _anchor(root, secret)
    runtime = JayaCoreRuntime(
        db_path=run_root / "runtime-audit.sqlite3",
        identity_anchor=anchor,
        identity_required=True,
        node_id="p11-audit-fault-node",
    )
    try:
        before = runtime.is_ready()
        with sqlite3.connect(root / "dna_identity.db") as connection:
            connection.execute("UPDATE identity_audit SET event='TAMPERED' WHERE event_id=1")
        after = runtime.is_ready()
    finally:
        runtime.close()
    return {"ready_before": before, "ready_after": after}


def _resource_faults(run_root: Path, secret: str, config: dict[str, Any]) -> dict[str, Any]:
    resource_root = run_root / "resource-limit"
    max_outstanding = int(config["max_outstanding_challenges"])
    resource = _anchor(
        resource_root,
        secret,
        max_outstanding_challenges=max_outstanding,
    )
    try:
        resource.enroll()
        challenges = [resource.issue_challenge("runtime.capacity") for _ in range(max_outstanding)]
        limit_code = _expect_error(
            lambda: resource.issue_challenge("runtime.capacity"),
            DNAFailureCode.RESOURCE_LIMIT,
        )
        signature = resource.sign_challenge(challenges[0])
        resource.verify_challenge(challenges[0], signature)
        released = resource.issue_challenge("runtime.capacity")
    finally:
        resource.close()

    lock_root = run_root / "storage-lock"
    timeout_seconds = float(config["storage_timeout_seconds"])
    locked = _anchor(lock_root, secret, storage_timeout_seconds=timeout_seconds)
    locked.enroll()
    blocker = sqlite3.connect(lock_root / "dna_identity.db", timeout=1.0)
    try:
        blocker.execute("BEGIN IMMEDIATE")
        started = time.perf_counter()
        lock_code = _expect_error(
            lambda: locked.issue_challenge("runtime.locked"),
            DNAFailureCode.STORAGE_ERROR,
        )
        elapsed = time.perf_counter() - started
    finally:
        blocker.rollback()
        blocker.close()
        locked.close()
    return {
        "resource_limit_code": limit_code,
        "consumed_slot_released": bool(released.nonce),
        "lock_code": lock_code,
        "lock_elapsed_seconds": elapsed,
        "configured_timeout_seconds": timeout_seconds,
    }


def _revocation_fault(run_root: Path, secret: str) -> dict[str, Any]:
    root = run_root / "revocation"
    anchor = _anchor(root, secret)
    try:
        record, _ = anchor.enroll()
        receipt = anchor.revoke("representative P11 revocation drill")
        revoked_code = _expect_error(anchor.load_identity, DNAFailureCode.IDENTITY_REVOKED)
        return {
            "brain_id": record.brain_id,
            "event": receipt.event,
            "load_code": revoked_code,
            "healthy": anchor.health_check(),
            "keystore_exists": (root / "keystore" / "dna_private_key.json").exists(),
        }
    finally:
        anchor.close()


def _soak(root: Path, secret: str, config: dict[str, Any]) -> dict[str, Any]:
    anchor = _anchor(root, secret)
    iterations = int(config["iterations"])
    meter = WindowsEmiEnergyMeter(timeout_seconds=20.0)
    try:
        energy_start = meter.sample()
    except EnergyMeterError as exc:
        anchor.close()
        raise DNAVerificationError("ENERGY_REQUIRED", "P11 energy counter unavailable") from exc
    process = psutil.Process()
    rss_before = process.memory_info().rss
    storage_before = _storage_bytes(root)
    errors = 0
    started = time.perf_counter()
    for index in range(iterations):
        try:
            challenge = anchor.issue_challenge("runtime.soak")
            signature = anchor.sign_challenge(challenge)
            anchor.verify_challenge(challenge, signature)
        except DNAAnchorError:
            errors += 1
    elapsed = time.perf_counter() - started
    audit_started = time.perf_counter()
    audit_valid = anchor.audit_chain_valid()
    audit_elapsed = time.perf_counter() - audit_started
    storage_after = _storage_bytes(root)
    rss_after = process.memory_info().rss
    try:
        energy = meter.measure(energy_start, meter.sample())
    except EnergyMeterError as exc:
        raise DNAVerificationError("ENERGY_REQUIRED", "P11 energy measurement failed") from exc
    finally:
        anchor.close()
    return {
        "iterations": iterations,
        "errors": errors,
        "elapsed_seconds": elapsed,
        "mean_roundtrip_latency_ms": elapsed * 1_000.0 / iterations,
        "roundtrips_per_second": iterations / elapsed,
        "full_audit_seconds": audit_elapsed,
        "audit_valid": audit_valid,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "rss_growth_bytes": max(0, rss_after - rss_before),
        "storage_before_bytes": storage_before,
        "storage_after_bytes": storage_after,
        "storage_bytes_per_roundtrip": max(0, storage_after - storage_before) / iterations,
        "energy": {**energy.to_dict(), "joules_per_roundtrip": energy.joules / iterations},
    }


def _clean_shutdown_probe(root: Path) -> bool:
    moved = root.with_name(root.name + "-closed-probe")
    try:
        root.replace(moved)
        moved.replace(root)
        return root.is_dir()
    except OSError:
        return False


def _gate(name: str, passed: bool, actual: Any, limit: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "limit": limit}


def verify_dna_anchor(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Execute the approved P11 profile against production identity code."""

    normalized_approver = " ".join(str(approver).strip().split())
    if not 3 <= len(normalized_approver) <= 160:
        raise DNAVerificationError("APPROVAL_REQUIRED", "P11 approver role required")
    root = repository_root.expanduser().resolve()
    profile = _load_profile(profile_path)
    host = _host()
    if host["os"] != profile["supported_os"]:
        raise DNAVerificationError("HOST_UNSUPPORTED", "P11 host profile differs")
    run_id = f"p11-verified-{uuid.uuid4().hex}"
    run_root = output_directory.expanduser().resolve() / run_id
    identity_root = run_root / "identity"
    identity_root.mkdir(parents=True, exist_ok=False)
    secret = secrets.token_urlsafe(48)

    enrolled = _anchor(identity_root, secret)
    try:
        initial, receipt = enrolled.enroll()
        enrollment = {
            "brain_id": initial.brain_id,
            "owner_id": initial.owner_id,
            "key_version": initial.key_version,
            "event": receipt.event,
            "health": enrolled.health_check(),
        }
        envelope = _envelope_probe(identity_root, secret)
    finally:
        enrolled.close()

    runtime_a = _runtime_probe(identity_root, secret, "p11-node-alpha")
    runtime_b = _runtime_probe(identity_root, secret, "p11-node-beta")
    lifecycle = _lifecycle(identity_root, secret, profile)
    restart = _restart_and_migration(
        run_root,
        identity_root,
        secret,
        initial.brain_id,
        initial.owner_id,
    )
    faults = _copy_faults(run_root, identity_root, secret)
    runtime_fault = _runtime_audit_fault(run_root, identity_root, secret)
    resources = _resource_faults(run_root, secret, profile["resource_limits"])
    revocation = _revocation_fault(run_root, secret)
    soak = _soak(identity_root, secret, profile["soak"])
    clean_shutdown = _clean_shutdown_probe(identity_root)

    expected_fields = ["ciphertext", "kdf", "nonce", "salt", "schema_version"]
    soak_config = profile["soak"]
    resource_config = profile["resource_limits"]
    rotations = lifecycle["rotations"]
    gates = [
        _gate("enrollment_health", enrollment["health"], enrollment["health"], True),
        _gate(
            "enrollment_receipt", enrollment["event"] == "ENROLLED", enrollment["event"], "ENROLLED"
        ),
        _gate(
            "encrypted_keystore_contract",
            envelope["fields"] == expected_fields and envelope["kdf"] == "scrypt-n16384-r8-p1",
            {"fields": envelope["fields"], "kdf": envelope["kdf"]},
            {"fields": expected_fields, "kdf": "scrypt-n16384-r8-p1"},
        ),
        _gate(
            "no_plain_private_material",
            envelope["secret_absent"]
            and envelope["private_key_field_absent"]
            and envelope["private_database_column_absent"],
            envelope,
            {"secret_absent": True, "private_material_absent": True},
        ),
        _gate("runtime_boot", runtime_a["ready"], runtime_a, {"ready": True}),
        _gate(
            "portable_brain_distinct_nodes",
            runtime_a["brain_id"] == runtime_b["brain_id"] == initial.brain_id
            and runtime_a["node_id"] != runtime_b["node_id"],
            {"runtime_a": runtime_a, "runtime_b": runtime_b},
            {"same_brain": True, "different_nodes": True},
        ),
        _gate(
            "challenge_purpose_matrix",
            lifecycle["purpose_receipts"] == ["CHALLENGE_VERIFIED"] * len(profile["purposes"]),
            lifecycle["purpose_receipts"],
            ["CHALLENGE_VERIFIED"] * len(profile["purposes"]),
        ),
        _gate(
            "replay_rejected",
            lifecycle["replay_code"] == "REPLAY_DETECTED",
            lifecycle["replay_code"],
            "REPLAY_DETECTED",
        ),
        _gate(
            "malformed_rejected",
            lifecycle["malformed_code"] == "CHALLENGE_INVALID",
            lifecycle["malformed_code"],
            "CHALLENGE_INVALID",
        ),
        _gate(
            "unknown_rejected",
            lifecycle["unknown_code"] == "CHALLENGE_INVALID",
            lifecycle["unknown_code"],
            "CHALLENGE_INVALID",
        ),
        _gate(
            "invalid_signature_rejected",
            lifecycle["invalid_signature_code"] == "SIGNATURE_INVALID",
            lifecycle["invalid_signature_code"],
            "SIGNATURE_INVALID",
        ),
        _gate(
            "attestation_valid",
            lifecycle["attestation_valid"],
            lifecycle["attestation_valid"],
            True,
        ),
        _gate(
            "attestation_tamper",
            lifecycle["tampered_attestation_rejected"],
            lifecycle["tampered_attestation_rejected"],
            True,
        ),
        _gate(
            "rotation_lineage",
            len(rotations) == profile["rotations"]
            and all(item["event"] == "KEY_ROTATED" for item in rotations)
            and all(item["previous_key_fingerprint"] for item in rotations)
            and all(item["rotation_proof_present"] for item in rotations),
            rotations,
            {"rotations": profile["rotations"], "lineage_proofs": True},
        ),
        _gate(
            "stable_owner_and_brain",
            lifecycle["brain_stable"] and lifecycle["owner_stable"],
            {"brain": lifecycle["brain_stable"], "owner": lifecycle["owner_stable"]},
            {"brain": True, "owner": True},
        ),
        _gate(
            "historical_attestation",
            lifecycle["attestation_valid"],
            lifecycle["attestation_valid"],
            True,
        ),
        _gate(
            "old_challenge_signature",
            lifecycle["old_signature_code"] == "SIGNATURE_INVALID",
            lifecycle["old_signature_code"],
            "SIGNATURE_INVALID",
        ),
        _gate("lifecycle_audit", lifecycle["audit_valid"], lifecycle["audit_valid"], True),
        _gate(
            "restart_persistence",
            restart["restart"]["healthy"]
            and restart["restart"]["brain_id"] == restart["expected_brain_id"]
            and restart["restart"]["owner_id"] == restart["expected_owner_id"],
            restart["restart"],
            {"healthy": True, "same_identity": True},
        ),
        _gate(
            "official_file_migration",
            restart["migration"]["healthy"]
            and restart["migration"]["brain_id"] == restart["expected_brain_id"]
            and restart["migration"]["owner_id"] == restart["expected_owner_id"],
            restart["migration"],
            {"healthy": True, "same_identity": True},
        ),
        _gate(
            "database_only_clone",
            faults["database_only_clone"] == "KEYSTORE_UNAVAILABLE",
            faults["database_only_clone"],
            "KEYSTORE_UNAVAILABLE",
        ),
        _gate(
            "wrong_secret",
            faults["wrong_secret"] == "KEYSTORE_DECRYPTION_FAILED",
            faults["wrong_secret"],
            "KEYSTORE_DECRYPTION_FAILED",
        ),
        _gate(
            "kdf_tamper",
            faults["kdf_tamper"] == "KEYSTORE_DECRYPTION_FAILED",
            faults["kdf_tamper"],
            "KEYSTORE_DECRYPTION_FAILED",
        ),
        _gate(
            "identity_corruption",
            faults["identity_tamper"] == "IDENTITY_CORRUPT"
            and not faults["identity_tamper_health"],
            {"code": faults["identity_tamper"], "health": faults["identity_tamper_health"]},
            {"code": "IDENTITY_CORRUPT", "health": False},
        ),
        _gate(
            "audit_corruption",
            not faults["audit_chain_after_tamper"] and not faults["audit_tamper_health"],
            {"chain": faults["audit_chain_after_tamper"], "health": faults["audit_tamper_health"]},
            {"chain": False, "health": False},
        ),
        _gate(
            "runtime_audit_fail_closed",
            runtime_fault["ready_before"] and not runtime_fault["ready_after"],
            runtime_fault,
            {"ready_before": True, "ready_after": False},
        ),
        _gate(
            "newer_schema",
            faults["newer_schema"] == "STORAGE_SCHEMA_UNSUPPORTED",
            faults["newer_schema"],
            "STORAGE_SCHEMA_UNSUPPORTED",
        ),
        _gate(
            "challenge_resource_limit",
            resources["resource_limit_code"] == "RESOURCE_LIMIT",
            resources["resource_limit_code"],
            "RESOURCE_LIMIT",
        ),
        _gate(
            "consumed_slot_release",
            resources["consumed_slot_released"],
            resources["consumed_slot_released"],
            True,
        ),
        _gate(
            "storage_lock_timeout",
            resources["lock_code"] == "STORAGE_ERROR"
            and resources["lock_elapsed_seconds"]
            <= float(resource_config["max_lock_elapsed_seconds"]),
            resources,
            {
                "code": "STORAGE_ERROR",
                "maximum_seconds": resource_config["max_lock_elapsed_seconds"],
            },
        ),
        _gate(
            "revocation",
            revocation["event"] == "IDENTITY_REVOKED"
            and revocation["load_code"] == "IDENTITY_REVOKED"
            and not revocation["healthy"]
            and not revocation["keystore_exists"],
            revocation,
            {"event": "IDENTITY_REVOKED", "health": False, "keystore_exists": False},
        ),
        _gate("soak_errors", soak["errors"] == 0, soak["errors"], 0),
        _gate(
            "soak_duration",
            soak["elapsed_seconds"] >= float(soak_config["minimum_elapsed_seconds"]),
            soak["elapsed_seconds"],
            {"minimum": soak_config["minimum_elapsed_seconds"]},
        ),
        _gate(
            "soak_latency",
            soak["mean_roundtrip_latency_ms"]
            <= float(soak_config["max_mean_roundtrip_latency_ms"]),
            soak["mean_roundtrip_latency_ms"],
            {"maximum": soak_config["max_mean_roundtrip_latency_ms"]},
        ),
        _gate(
            "full_audit_latency",
            soak["full_audit_seconds"] <= float(soak_config["max_full_audit_seconds"]),
            soak["full_audit_seconds"],
            {"maximum": soak_config["max_full_audit_seconds"]},
        ),
        _gate("soak_audit", soak["audit_valid"], soak["audit_valid"], True),
        _gate(
            "soak_rss_growth",
            soak["rss_growth_bytes"] <= int(soak_config["max_rss_growth_bytes"]),
            soak["rss_growth_bytes"],
            {"maximum": soak_config["max_rss_growth_bytes"]},
        ),
        _gate(
            "storage_growth",
            soak["storage_bytes_per_roundtrip"]
            <= float(soak_config["max_storage_bytes_per_roundtrip"]),
            soak["storage_bytes_per_roundtrip"],
            {"maximum": soak_config["max_storage_bytes_per_roundtrip"]},
        ),
        _gate(
            "package_energy_per_roundtrip",
            soak["energy"]["joules_per_roundtrip"]
            <= float(soak_config["max_package_joules_per_roundtrip"]),
            soak["energy"]["joules_per_roundtrip"],
            {"maximum": soak_config["max_package_joules_per_roundtrip"]},
        ),
        _gate("clean_shutdown", clean_shutdown, clean_shutdown, True),
    ]
    verified = all(item["passed"] for item in gates)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE" if verified else "FAILED",
        "pillar": "P011",
        "scope": profile["scope"],
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "verified_at": datetime.now(UTC).isoformat(),
        "approval": {
            "approver": normalized_approver,
            "basis": "explicit repository-owner request to continue pillar verification",
        },
        "version": {
            **_git_version(root),
            "source_bundle_sha256": _source_bundle_sha256(root, profile["source_files"]),
        },
        "environment": host,
        "enrollment": enrollment,
        "keystore": envelope,
        "runtime": {"node_alpha": runtime_a, "node_beta": runtime_b},
        "lifecycle": lifecycle,
        "restart_and_migration": restart,
        "fault_drills": {
            **faults,
            "runtime_audit": runtime_fault,
            "resources": resources,
            "revocation": revocation,
        },
        "soak": soak,
        "gates": gates,
        "limitations": [
            "verified on one Windows workstation with the encrypted file keystore and local SQLite",
            "the encrypted file keystore is not an OS secret manager, TPM, HSM, or remote custody system",
            "the operator-provided unlock secret lifecycle and backup custody remain deployment responsibilities",
            "energy is CPU-package total and is not process-attributed",
            "multi-process high-contention and sustained multi-day operation are outside this profile",
            "worktree source is bound by digest because verification may precede commit",
        ],
        "rollback": {
            "action": "restore P011 manifest status to INTEGRATED",
            "data_impact": "none; schema version 2 remains backward-readable by this implementation",
        },
    }
    report_path = run_root / "verified-dna-anchor-report.json"
    raw_report = _canonical_json(report)
    report_path.write_bytes(raw_report)
    Path(f"{report_path}.sha256").write_text(f"{_digest(raw_report)}\n", encoding="ascii")
    if not verified:
        failures = ", ".join(item["name"] for item in gates if not item["passed"])
        raise DNAVerificationError("VERIFICATION_FAILED", f"P11 gates failed: {failures}")
    return report_path, report


__all__ = ["DNAVerificationError", "verify_dna_anchor"]
