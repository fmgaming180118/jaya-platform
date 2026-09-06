"""Representative verification runner for Pillar 20 Sovereign Privacy."""

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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psutil
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jaya_core.brain_v2.protection.dna_anchor import EncryptedFileKeyStore
from jaya_core.security.approval_trust import (
    ApprovalTrustAction,
    ApprovalTrustRegistry,
)
from jaya_core.security.sovereign_privacy import (
    DataClassification,
    DataDestination,
    DataPurpose,
    PrivacyEffect,
    PrivacyError,
    PrivacyFailureCode,
    PrivacyUseRequest,
    SovereignPrivacy,
    create_consent_grant,
)

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "workload",
    "source_files",
}
_WORKLOAD_FIELDS = {
    "records",
    "retention_records",
    "minimum_elapsed_seconds",
    "max_mean_latency_ms",
    "max_p95_latency_ms",
    "max_full_audit_seconds",
    "max_rss_growth_bytes",
    "max_storage_bytes_per_record",
    "min_retention_records_per_second",
}
_OWNER = "p20-representative-owner"
_APPROVER = "p20-consent-owner"
_PROVIDER = "p20-representative-provider"


class SovereignPrivacyVerificationError(RuntimeError):
    """Stable P20 representative verification failure."""

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
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _load_profile(path: Path) -> dict[str, Any]:
    try:
        raw = path.expanduser().resolve().read_bytes()
        profile = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SovereignPrivacyVerificationError(
            "PROFILE_INVALID",
            "P20 verification profile is invalid",
        ) from exc
    workload = profile.get("workload") if isinstance(profile, dict) else None
    if (
        not isinstance(profile, dict)
        or set(profile) != _PROFILE_FIELDS
        or profile.get("schema_version") != 1
        or not _PROFILE_ID.fullmatch(str(profile.get("profile_id", "")))
        or not isinstance(profile.get("scope"), str)
        or not profile["scope"].strip()
        or not isinstance(profile.get("supported_os"), str)
        or not isinstance(workload, dict)
        or set(workload) != _WORKLOAD_FIELDS
        or not isinstance(profile.get("source_files"), list)
        or not profile["source_files"]
        or any(not isinstance(item, str) or not item for item in profile["source_files"])
    ):
        raise SovereignPrivacyVerificationError(
            "PROFILE_INVALID",
            "P20 verification profile fields are invalid",
        )
    for field in ("records", "retention_records"):
        value = workload[field]
        if type(value) is not int or not 10 <= value <= 10_000:
            raise SovereignPrivacyVerificationError(
                "PROFILE_INVALID",
                "P20 workload record limit is invalid",
            )
    if type(workload["max_rss_growth_bytes"]) is not int or workload["max_rss_growth_bytes"] <= 0:
        raise SovereignPrivacyVerificationError(
            "PROFILE_INVALID",
            "P20 RSS threshold is invalid",
        )
    for field in _WORKLOAD_FIELDS - {
        "records",
        "retention_records",
        "max_rss_growth_bytes",
    }:
        value = workload[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise SovereignPrivacyVerificationError(
                "PROFILE_INVALID",
                "P20 workload threshold is invalid",
            )
    return {**profile, "profile_sha256": _digest(raw)}


def _host() -> dict[str, object]:
    return {
        "os": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "memory_bytes": psutil.virtual_memory().total,
        "dependencies": {
            name: importlib.metadata.version(name) for name in ("cryptography", "psutil")
        },
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
        if completed.returncode != 0:
            raise SovereignPrivacyVerificationError(
                "GIT_UNAVAILABLE",
                "P20 git version is unavailable",
            )
        return completed.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD"),
        "worktree_dirty": bool(run("status", "--porcelain")),
    }


def _source_bundle_sha256(root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
            raw = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise SovereignPrivacyVerificationError(
                "SOURCE_UNAVAILABLE",
                "P20 verification source bundle is unavailable",
            ) from exc
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "little"))
        digest.update(raw)
    return f"sha256:{digest.hexdigest()}"


def _private_bytes(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )


def _public_bytes(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _signer(store: EncryptedFileKeyStore):
    def sign(payload: bytes) -> bytes:
        material, _ = store.load()
        return Ed25519PrivateKey.from_private_bytes(material).sign(payload)

    return sign


def _trust_event(
    registry: ApprovalTrustRegistry,
    recovery_store: EncryptedFileKeyStore,
    action: ApprovalTrustAction,
    reason: str,
    public_key: bytes | None = None,
):
    return registry.prepare_event(
        approver_id=_APPROVER,
        action=action,
        reason=reason,
        public_key=public_key,
        occurred_at=datetime.now(UTC).isoformat(),
        signer=_signer(recovery_store),
    )


def _grant(
    owner_store: EncryptedFileKeyStore,
    consent_id: str,
    *,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
):
    issued = issued_at or datetime.now(UTC)
    expires = expires_at or (issued + timedelta(minutes=5))
    return create_consent_grant(
        approver_id=_APPROVER,
        owner_id=_OWNER,
        subject_id=_OWNER,
        classifications=(DataClassification.CONFIDENTIAL,),
        purposes=(DataPurpose.MODEL_INFERENCE,),
        providers=(_PROVIDER,),
        issued_at=issued.isoformat(),
        expires_at=expires.isoformat(),
        signer=_signer(owner_store),
        consent_id=consent_id,
    )


def _request(
    consent_id: str | None,
    *,
    provider: str = _PROVIDER,
    purpose: DataPurpose = DataPurpose.MODEL_INFERENCE,
) -> PrivacyUseRequest:
    return PrivacyUseRequest(
        request_id=f"p20-request-{uuid.uuid4().hex}",
        actor_id=_OWNER,
        owner_id=_OWNER,
        subject_id=_OWNER,
        data_id="p20-primary-record",
        classification=DataClassification.CONFIDENTIAL,
        purpose=purpose,
        destination=DataDestination.EXTERNAL_PROVIDER,
        provider_id=provider,
        payload_sha256="a" * 64,
        consent_id=consent_id,
    )


def _expect_privacy_error(function: Any, code: PrivacyFailureCode) -> str:
    try:
        function()
    except PrivacyError as exc:
        if exc.code is not code:
            raise SovereignPrivacyVerificationError(
                "UNEXPECTED_FAILURE",
                f"expected {code.value}, received {exc.code.value}",
            ) from exc
        return exc.code.value
    raise SovereignPrivacyVerificationError(
        "EXPECTED_FAILURE_MISSING",
        f"expected {code.value}",
    )


def _sqlite_backup(source: Path, destination: Path) -> None:
    with (
        sqlite3.connect(source) as source_connection,
        sqlite3.connect(destination) as destination_connection,
    ):
        source_connection.backup(destination_connection)


def _leak_scan(root: Path, needles: tuple[str, ...]) -> dict[str, object]:
    scanned_files = 0
    scanned_bytes = 0
    matches: list[str] = []
    encoded_needles = tuple(item.encode("utf-8") for item in needles if item)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SovereignPrivacyVerificationError(
                "LEAK_SCAN_FAILED",
                "P20 verification artifact could not be scanned",
            ) from exc
        scanned_files += 1
        scanned_bytes += len(raw)
        if any(needle in raw for needle in encoded_needles):
            matches.append(str(path.relative_to(root)))
    return {
        "scanned_files": scanned_files,
        "scanned_bytes": scanned_bytes,
        "matches": matches,
    }


def _run_demo(root: Path, workspace: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(root / "scripts" / "demo_sovereign_privacy.py"),
        "--workspace",
        str(workspace),
    ]
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SovereignPrivacyVerificationError(
            "DEMO_FAILED",
            "P20 production-path demo returned invalid output",
        ) from exc
    if completed.returncode != 0:
        raise SovereignPrivacyVerificationError(
            "DEMO_FAILED",
            "P20 production-path demo failed",
        )
    return {"command": command, "result": value, "stderr": completed.stderr.strip()}


def _gate(name: str, passed: bool, actual: Any, limit: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "limit": limit}


def verify_sovereign_privacy(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Execute the approved P20 profile against production privacy code."""

    normalized_approver = " ".join(str(approver).strip().split())
    if not 3 <= len(normalized_approver) <= 160:
        raise SovereignPrivacyVerificationError(
            "APPROVAL_REQUIRED",
            "P20 approver role is required",
        )
    root = repository_root.expanduser().resolve()
    profile = _load_profile(profile_path)
    host = _host()
    if host["os"] != profile["supported_os"]:
        raise SovereignPrivacyVerificationError(
            "HOST_UNSUPPORTED",
            "P20 host does not match the approved profile",
        )
    run_id = f"p20-verified-{uuid.uuid4().hex}"
    run_root = output_directory.expanduser().resolve() / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    vault_secret = secrets.token_urlsafe(48)
    unlock_secret = secrets.token_urlsafe(48)
    plaintext_needle = f"P20-PRIVATE-{secrets.token_hex(24)}"

    recovery_v1 = Ed25519PrivateKey.generate()
    owner_v1 = Ed25519PrivateKey.generate()
    recovery_store = EncryptedFileKeyStore(
        run_root / "recovery-keystore",
        unlock_secret,
    )
    owner_store = EncryptedFileKeyStore(run_root / "owner-keystore", unlock_secret)
    recovery_store.create(_private_bytes(recovery_v1), 1)
    owner_store.create(_private_bytes(owner_v1), 1)
    trust_db = run_root / "consent-trust.db"
    privacy_db = run_root / "sovereign-privacy.db"
    registry = ApprovalTrustRegistry(trust_db, _public_bytes(recovery_v1))
    registry.apply(
        _trust_event(
            registry,
            recovery_store,
            ApprovalTrustAction.INSTALL,
            "representative privacy owner enrollment",
            _public_bytes(owner_v1),
        )
    )
    privacy = SovereignPrivacy(
        privacy_db,
        vault_secret,
        consent_key_resolver=registry.resolve_public_key,
    )
    try:
        denied_without_consent = privacy.evaluate(_request(None))
        descriptor = privacy.store(
            actor_id=_OWNER,
            owner_id=_OWNER,
            subject_id=_OWNER,
            data_id="p20-primary-record",
            classification=DataClassification.CONFIDENTIAL,
            allowed_purposes=(DataPurpose.MEMORY, DataPurpose.EXPORT),
            payload={"private_value": plaintext_needle, "sequence": 1},
            retention_seconds=600,
        )
        idempotent = privacy.store(
            actor_id=_OWNER,
            owner_id=_OWNER,
            subject_id=_OWNER,
            data_id="p20-primary-record",
            classification=DataClassification.CONFIDENTIAL,
            allowed_purposes=(DataPurpose.MEMORY, DataPurpose.EXPORT),
            payload={"private_value": plaintext_needle, "sequence": 1},
            retention_seconds=600,
        )
        duplicate_failure = _expect_privacy_error(
            lambda: privacy.store(
                actor_id=_OWNER,
                owner_id=_OWNER,
                subject_id=_OWNER,
                data_id="p20-primary-record",
                classification=DataClassification.CONFIDENTIAL,
                allowed_purposes=(DataPurpose.MEMORY,),
                payload={"private_value": "conflicting-value"},
                retention_seconds=600,
            ),
            PrivacyFailureCode.INVALID_INPUT,
        )
        wrong_owner = _expect_privacy_error(
            lambda: privacy.retrieve(
                actor_id="p20-other-owner",
                data_id=descriptor.data_id,
                purpose=DataPurpose.MEMORY,
            ),
            PrivacyFailureCode.OWNER_MISMATCH,
        )
        wrong_data_purpose = _expect_privacy_error(
            lambda: privacy.retrieve(
                actor_id=_OWNER,
                data_id=descriptor.data_id,
                purpose=DataPurpose.TELEMETRY,
            ),
            PrivacyFailureCode.PURPOSE_DENIED,
        )
        grant_v1 = _grant(owner_store, "p20-consent-v1")
        privacy.install_consent(grant_v1)
        allowed_v1 = privacy.evaluate(_request(grant_v1.consent_id))

        owner_v2 = Ed25519PrivateKey.generate()
        registry.apply(
            _trust_event(
                registry,
                recovery_store,
                ApprovalTrustAction.ROTATE,
                "scheduled representative consent rotation",
                _public_bytes(owner_v2),
            )
        )
        retired_key = _expect_privacy_error(
            lambda: privacy.evaluate(_request(grant_v1.consent_id)),
            PrivacyFailureCode.CONSENT_INVALID,
        )
        owner_store.replace(_private_bytes(owner_v2), 2)
        grant_v2 = _grant(owner_store, "p20-consent-v2")
        privacy.install_consent(grant_v2)
        allowed_v2 = privacy.evaluate(_request(grant_v2.consent_id))

        registry.apply(
            _trust_event(
                registry,
                recovery_store,
                ApprovalTrustAction.REVOKE,
                "representative consent signer suspension",
            )
        )
        revoked_trust = _expect_privacy_error(
            lambda: privacy.evaluate(_request(grant_v2.consent_id)),
            PrivacyFailureCode.CONSENT_INVALID,
        )
        owner_v3 = Ed25519PrivateKey.generate()
        registry.apply(
            _trust_event(
                registry,
                recovery_store,
                ApprovalTrustAction.RECOVER,
                "approved representative consent recovery",
                _public_bytes(owner_v3),
            )
        )
        owner_store.replace(_private_bytes(owner_v3), 3)
        grant_v3 = _grant(owner_store, "p20-consent-v3")
        privacy.install_consent(grant_v3)
        recovered = privacy.evaluate(_request(grant_v3.consent_id))
        wrong_provider = _expect_privacy_error(
            lambda: privacy.evaluate(_request(grant_v3.consent_id, provider="untrusted-provider")),
            PrivacyFailureCode.CONSENT_INVALID,
        )
        wrong_consent_purpose = _expect_privacy_error(
            lambda: privacy.evaluate(_request(grant_v3.consent_id, purpose=DataPurpose.TELEMETRY)),
            PrivacyFailureCode.CONSENT_INVALID,
        )
        expired_at = datetime.now(UTC) - timedelta(minutes=1)
        expired_grant = _grant(
            owner_store,
            "p20-consent-expired",
            issued_at=expired_at - timedelta(minutes=5),
            expires_at=expired_at,
        )
        privacy.install_consent(expired_grant)
        expired_consent = _expect_privacy_error(
            lambda: privacy.evaluate(_request(expired_grant.consent_id)),
            PrivacyFailureCode.CONSENT_EXPIRED,
        )
        privacy_audit_before_restart = privacy.audit_chain_valid()
        trust_before_restart = registry.status()
        privacy_status = privacy.status()
    finally:
        privacy.close()
        registry.close()

    restarted_registry = ApprovalTrustRegistry(trust_db, _public_bytes(recovery_v1))
    restarted_privacy = SovereignPrivacy(
        privacy_db,
        vault_secret,
        consent_key_resolver=restarted_registry.resolve_public_key,
    )
    backup_db = run_root / "managed-backup.db"
    try:
        restored_payload = restarted_privacy.retrieve(
            actor_id=_OWNER,
            data_id="p20-primary-record",
            purpose=DataPurpose.MEMORY,
        )
        restart_consent = restarted_privacy.evaluate(_request(grant_v3.consent_id))
        exported = restarted_privacy.export_owner(_OWNER)
        export_body = {
            "schema_version": exported["schema_version"],
            "owner_id": exported["owner_id"],
            "records": exported["records"],
        }
        export_digest_valid = (
            hashlib.sha256(_canonical(export_body)).hexdigest() == exported["sha256"]
        )
        _sqlite_backup(privacy_db, backup_db)
        backup_privacy = SovereignPrivacy(
            backup_db,
            vault_secret,
            consent_key_resolver=restarted_registry.resolve_public_key,
        )
        try:
            backup_restored = backup_privacy.retrieve(
                actor_id=_OWNER,
                data_id="p20-primary-record",
                purpose=DataPurpose.MEMORY,
            )
            backup_deletion = backup_privacy.delete_owner(_OWNER)
            backup_deleted = _expect_privacy_error(
                lambda: backup_privacy.retrieve(
                    actor_id=_OWNER,
                    data_id="p20-primary-record",
                    purpose=DataPurpose.MEMORY,
                ),
                PrivacyFailureCode.DATA_DELETED,
            )
            backup_audit = backup_privacy.audit_chain_valid()
        finally:
            backup_privacy.close()
        live_deletion = restarted_privacy.delete_owner(_OWNER)
        live_deleted = _expect_privacy_error(
            lambda: restarted_privacy.retrieve(
                actor_id=_OWNER,
                data_id="p20-primary-record",
                purpose=DataPurpose.MEMORY,
            ),
            PrivacyFailureCode.DATA_DELETED,
        )
        restarted_privacy.revoke_consent(_OWNER, grant_v3.consent_id)
        revoked_consent = _expect_privacy_error(
            lambda: restarted_privacy.evaluate(_request(grant_v3.consent_id)),
            PrivacyFailureCode.CONSENT_REVOKED,
        )
        privacy_audit_after_restart = restarted_privacy.audit_chain_valid()
        trust_after_restart = restarted_registry.status()
    finally:
        restarted_privacy.close()
        restarted_registry.close()

    failure_seed = run_root / "failure-seed.db"
    failure_privacy = SovereignPrivacy(failure_seed, vault_secret)
    failure_privacy.store(
        actor_id=_OWNER,
        owner_id=_OWNER,
        subject_id=_OWNER,
        data_id="p20-failure-record",
        classification=DataClassification.CONFIDENTIAL,
        allowed_purposes=(DataPurpose.MEMORY,),
        payload={"value": "encrypted-failure-fixture"},
        retention_seconds=600,
    )
    failure_privacy.close()
    wrong_key_privacy = SovereignPrivacy(failure_seed, secrets.token_urlsafe(48))
    try:
        wrong_key_failure = _expect_privacy_error(
            lambda: wrong_key_privacy.retrieve(
                actor_id=_OWNER,
                data_id="p20-failure-record",
                purpose=DataPurpose.MEMORY,
            ),
            PrivacyFailureCode.DECRYPTION_FAILED,
        )
    finally:
        wrong_key_privacy.close()
    tampered_db = run_root / "failure-tampered.db"
    shutil.copy2(failure_seed, tampered_db)
    with sqlite3.connect(tampered_db) as connection:
        connection.execute(
            "UPDATE privacy_vault SET ciphertext = ciphertext || 'A' "
            "WHERE data_id = 'p20-failure-record'"
        )
    tampered_privacy = SovereignPrivacy(tampered_db, vault_secret)
    try:
        tamper_failure = _expect_privacy_error(
            lambda: tampered_privacy.retrieve(
                actor_id=_OWNER,
                data_id="p20-failure-record",
                purpose=DataPurpose.MEMORY,
            ),
            PrivacyFailureCode.CORRUPT_DATA,
        )
    finally:
        tampered_privacy.close()

    retention_now = [datetime(2026, 8, 30, 12, 0, tzinfo=UTC)]
    retention_db = run_root / "retention.db"
    retention_privacy = SovereignPrivacy(
        retention_db,
        vault_secret,
        clock=lambda: retention_now[0],
    )
    retention_records = int(profile["workload"]["retention_records"])
    try:
        for index in range(retention_records):
            retention_privacy.store(
                actor_id=_OWNER,
                owner_id=_OWNER,
                subject_id=_OWNER,
                data_id=f"retention-{index}",
                classification=DataClassification.CONFIDENTIAL,
                allowed_purposes=(DataPurpose.MEMORY,),
                payload={"sequence": index},
                retention_seconds=1,
            )
        retention_now[0] += timedelta(seconds=2)
        retention_started = time.perf_counter()
        retention_purged = retention_privacy.purge_expired()
        retention_elapsed = time.perf_counter() - retention_started
        retention_throughput = retention_purged / max(retention_elapsed, 0.000001)
        retention_deleted = _expect_privacy_error(
            lambda: retention_privacy.retrieve(
                actor_id=_OWNER,
                data_id="retention-0",
                purpose=DataPurpose.MEMORY,
            ),
            PrivacyFailureCode.DATA_DELETED,
        )
        retention_audit = retention_privacy.audit_chain_valid()
    finally:
        retention_privacy.close()

    process = psutil.Process()
    rss_before = process.memory_info().rss
    workload_db = run_root / "workload.db"
    workload_privacy = SovereignPrivacy(workload_db, vault_secret)
    latencies: list[float] = []
    workload_records = int(profile["workload"]["records"])
    workload_started = time.perf_counter()
    try:
        for index in range(workload_records):
            value = hashlib.sha256(f"{run_id}:{index}".encode()).hexdigest()
            started = time.perf_counter()
            workload_privacy.store(
                actor_id=_OWNER,
                owner_id=_OWNER,
                subject_id=_OWNER,
                data_id=f"workload-{index}",
                classification=DataClassification.CONFIDENTIAL,
                allowed_purposes=(DataPurpose.MEMORY,),
                payload={"sequence": index, "value": value},
                retention_seconds=600,
            )
            restored = workload_privacy.retrieve(
                actor_id=_OWNER,
                data_id=f"workload-{index}",
                purpose=DataPurpose.MEMORY,
            )
            latencies.append((time.perf_counter() - started) * 1_000)
            if restored.get("value") != value:
                raise SovereignPrivacyVerificationError(
                    "WORKLOAD_INVARIANT",
                    "P20 workload returned a different encrypted payload",
                )
        workload_elapsed = time.perf_counter() - workload_started
        audit_started = time.perf_counter()
        workload_audit = workload_privacy.audit_chain_valid()
        full_audit_seconds = time.perf_counter() - audit_started
        workload_status = workload_privacy.status()
        workload_deletion = workload_privacy.delete_owner(_OWNER)
    finally:
        workload_privacy.close()
    with sqlite3.connect(workload_db) as workload_connection:
        workload_deleted_records = int(
            workload_connection.execute(
                "SELECT COUNT(*) FROM privacy_vault "
                "WHERE deleted_at IS NOT NULL AND nonce = '' AND ciphertext = ''"
            ).fetchone()[0]
        )
    rss_after = process.memory_info().rss
    sorted_latencies = sorted(latencies)
    p95_index = max(0, int(len(sorted_latencies) * 0.95) - 1)
    storage_bytes = sum(path.stat().st_size for path in run_root.rglob("*") if path.is_file())
    workload = {
        "records": workload_records,
        "elapsed_seconds": workload_elapsed,
        "mean_latency_ms": sum(latencies) / len(latencies),
        "p95_latency_ms": sorted_latencies[p95_index],
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "rss_growth_bytes": max(0, rss_after - rss_before),
        "storage_bytes": storage_bytes,
        "storage_bytes_per_record": storage_bytes / workload_records,
        "full_audit_seconds": full_audit_seconds,
    }

    demo = _run_demo(root, run_root / "production-path-demo")
    leak_scan = _leak_scan(
        run_root,
        (plaintext_needle, vault_secret, unlock_secret),
    )
    config = profile["workload"]
    demo_result = demo["result"]
    gates = [
        _gate(
            "external_default_deny",
            denied_without_consent.effect is PrivacyEffect.DENY,
            denied_without_consent.effect.value,
            "DENY",
        ),
        _gate(
            "encrypted_store_idempotence",
            descriptor.data_id == idempotent.data_id
            and duplicate_failure == PrivacyFailureCode.INVALID_INPUT.value,
            {"same_id": descriptor.data_id == idempotent.data_id, "conflict": duplicate_failure},
            {"same_id": True, "conflict": PrivacyFailureCode.INVALID_INPUT.value},
        ),
        _gate(
            "owner_and_data_purpose_boundary",
            wrong_owner == PrivacyFailureCode.OWNER_MISMATCH.value
            and wrong_data_purpose == PrivacyFailureCode.PURPOSE_DENIED.value,
            {"owner": wrong_owner, "purpose": wrong_data_purpose},
            {
                "owner": PrivacyFailureCode.OWNER_MISMATCH.value,
                "purpose": PrivacyFailureCode.PURPOSE_DENIED.value,
            },
        ),
        _gate(
            "signed_consent_allow",
            allowed_v1.effect is PrivacyEffect.ALLOW and allowed_v2.effect is PrivacyEffect.ALLOW,
            {"v1": allowed_v1.effect.value, "v2": allowed_v2.effect.value},
            "ALLOW",
        ),
        _gate(
            "dynamic_consent_trust",
            privacy_status["consent_trust_source"] == "dynamic_resolver",
            privacy_status["consent_trust_source"],
            "dynamic_resolver",
        ),
        _gate(
            "rotation_retires_old_key",
            retired_key == PrivacyFailureCode.CONSENT_INVALID.value,
            retired_key,
            PrivacyFailureCode.CONSENT_INVALID.value,
        ),
        _gate(
            "trust_revoke_and_recovery",
            revoked_trust == PrivacyFailureCode.CONSENT_INVALID.value
            and recovered.effect is PrivacyEffect.ALLOW,
            {"revoked": revoked_trust, "recovered": recovered.effect.value},
            {"revoked": PrivacyFailureCode.CONSENT_INVALID.value, "recovered": "ALLOW"},
        ),
        _gate(
            "consent_scope_binding",
            wrong_provider == PrivacyFailureCode.CONSENT_INVALID.value
            and wrong_consent_purpose == PrivacyFailureCode.CONSENT_INVALID.value,
            {"provider": wrong_provider, "purpose": wrong_consent_purpose},
            PrivacyFailureCode.CONSENT_INVALID.value,
        ),
        _gate(
            "consent_expiry_and_revocation",
            expired_consent == PrivacyFailureCode.CONSENT_EXPIRED.value
            and revoked_consent == PrivacyFailureCode.CONSENT_REVOKED.value,
            {"expired": expired_consent, "revoked": revoked_consent},
            {
                "expired": PrivacyFailureCode.CONSENT_EXPIRED.value,
                "revoked": PrivacyFailureCode.CONSENT_REVOKED.value,
            },
        ),
        _gate(
            "restart_restores_policy_and_data",
            restored_payload.get("private_value") == plaintext_needle
            and restart_consent.effect is PrivacyEffect.ALLOW
            and trust_after_restart["events"] == 4,
            {
                "payload": restored_payload.get("private_value") == plaintext_needle,
                "consent": restart_consent.effect.value,
                "trust_events": trust_after_restart["events"],
            },
            {"payload": True, "consent": "ALLOW", "trust_events": 4},
        ),
        _gate(
            "owner_export_integrity",
            len(exported["records"]) == 1 and export_digest_valid,
            {"records": len(exported["records"]), "digest_valid": export_digest_valid},
            {"records": 1, "digest_valid": True},
        ),
        _gate(
            "live_owner_deletion",
            live_deletion["event"] == "OWNER_DATA_DELETED"
            and live_deleted == PrivacyFailureCode.DATA_DELETED.value,
            {"event": live_deletion["event"], "failure": live_deleted},
            {"event": "OWNER_DATA_DELETED", "failure": PrivacyFailureCode.DATA_DELETED.value},
        ),
        _gate(
            "managed_backup_deletion",
            backup_restored.get("private_value") == plaintext_needle
            and backup_deletion["event"] == "OWNER_DATA_DELETED"
            and backup_deleted == PrivacyFailureCode.DATA_DELETED.value
            and backup_audit,
            {
                "restored": backup_restored.get("private_value") == plaintext_needle,
                "event": backup_deletion["event"],
                "failure": backup_deleted,
                "audit": backup_audit,
            },
            {
                "restored": True,
                "event": "OWNER_DATA_DELETED",
                "failure": PrivacyFailureCode.DATA_DELETED.value,
                "audit": True,
            },
        ),
        _gate(
            "wrong_key_fail_closed",
            wrong_key_failure == PrivacyFailureCode.DECRYPTION_FAILED.value,
            wrong_key_failure,
            PrivacyFailureCode.DECRYPTION_FAILED.value,
        ),
        _gate(
            "ciphertext_tamper_fail_closed",
            tamper_failure == PrivacyFailureCode.CORRUPT_DATA.value,
            tamper_failure,
            PrivacyFailureCode.CORRUPT_DATA.value,
        ),
        _gate(
            "retention_batch",
            retention_purged == retention_records
            and retention_deleted == PrivacyFailureCode.DATA_DELETED.value
            and retention_audit,
            {"purged": retention_purged, "failure": retention_deleted, "audit": retention_audit},
            {
                "purged": retention_records,
                "failure": PrivacyFailureCode.DATA_DELETED.value,
                "audit": True,
            },
        ),
        _gate(
            "retention_throughput",
            retention_throughput >= float(config["min_retention_records_per_second"]),
            retention_throughput,
            {"minimum": float(config["min_retention_records_per_second"])},
        ),
        _gate(
            "privacy_audit_chains",
            privacy_audit_before_restart
            and privacy_audit_after_restart
            and trust_before_restart["audit_chain_valid"]
            and trust_after_restart["audit_chain_valid"]
            and workload_audit,
            {
                "before_restart": privacy_audit_before_restart,
                "after_restart": privacy_audit_after_restart,
                "trust_before": trust_before_restart["audit_chain_valid"],
                "trust_after": trust_after_restart["audit_chain_valid"],
                "workload": workload_audit,
            },
            True,
        ),
        _gate(
            "plaintext_and_secret_leak_scan", not leak_scan["matches"], leak_scan, {"matches": []}
        ),
        _gate(
            "production_path_demo",
            demo_result.get("status") == "VERIFIED_LOCAL"
            and demo_result.get("restart_restored") is True
            and demo_result.get("plaintext_absent") is True
            and demo_result.get("external_without_consent") == "DENY"
            and demo_result.get("external_with_consent") == "ALLOW",
            demo_result,
            "VERIFIED_LOCAL_PRIVACY_LIFECYCLE",
        ),
        _gate(
            "workload_record_count",
            workload_status["encrypted_records"] == workload_records
            and workload_deleted_records == workload_records
            and workload_deletion["event"] == "OWNER_DATA_DELETED",
            {
                "stored": workload_status["encrypted_records"],
                "deleted": workload_deleted_records,
                "event": workload_deletion["event"],
            },
            workload_records,
        ),
        _gate(
            "workload_duration",
            workload_elapsed >= float(config["minimum_elapsed_seconds"]),
            workload_elapsed,
            {"minimum": float(config["minimum_elapsed_seconds"])},
        ),
        _gate(
            "workload_mean_latency",
            workload["mean_latency_ms"] <= float(config["max_mean_latency_ms"]),
            workload["mean_latency_ms"],
            {"maximum": float(config["max_mean_latency_ms"])},
        ),
        _gate(
            "workload_p95_latency",
            workload["p95_latency_ms"] <= float(config["max_p95_latency_ms"]),
            workload["p95_latency_ms"],
            {"maximum": float(config["max_p95_latency_ms"])},
        ),
        _gate(
            "full_audit_latency",
            full_audit_seconds <= float(config["max_full_audit_seconds"]),
            full_audit_seconds,
            {"maximum": float(config["max_full_audit_seconds"])},
        ),
        _gate(
            "workload_rss_growth",
            workload["rss_growth_bytes"] <= int(config["max_rss_growth_bytes"]),
            workload["rss_growth_bytes"],
            {"maximum": int(config["max_rss_growth_bytes"])},
        ),
        _gate(
            "storage_per_record",
            workload["storage_bytes_per_record"] <= float(config["max_storage_bytes_per_record"]),
            workload["storage_bytes_per_record"],
            {"maximum": float(config["max_storage_bytes_per_record"])},
        ),
    ]
    verified = all(item["passed"] for item in gates)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE" if verified else "FAILED",
        "pillar": "P020",
        "scope": profile["scope"],
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "verified_at": datetime.now(UTC).isoformat(),
        "approval": {
            "approver": normalized_approver,
            "basis": "explicit repository-owner request to verify the next pillar",
        },
        "version": {
            **_git_version(root),
            "source_bundle_sha256": _source_bundle_sha256(
                root,
                profile["source_files"],
            ),
        },
        "environment": host,
        "trust_lifecycle": {
            "before_restart": trust_before_restart,
            "after_restart": trust_after_restart,
            "retired_key_failure": retired_key,
            "revoked_trust_failure": revoked_trust,
            "expired_consent_failure": expired_consent,
            "revoked_consent_failure": revoked_consent,
        },
        "data_lifecycle": {
            "descriptor_sha256": descriptor.plaintext_sha256,
            "export_sha256": exported["sha256"],
            "live_deletion_event_sha256": live_deletion["event_sha256"],
            "backup_deletion_event_sha256": backup_deletion["event_sha256"],
            "retention_purged": retention_purged,
            "retention_records_per_second": retention_throughput,
        },
        "failure_paths": {
            "duplicate": duplicate_failure,
            "wrong_owner": wrong_owner,
            "wrong_data_purpose": wrong_data_purpose,
            "wrong_provider": wrong_provider,
            "wrong_consent_purpose": wrong_consent_purpose,
            "wrong_key": wrong_key_failure,
            "tamper": tamper_failure,
        },
        "production_path_demo": demo,
        "leak_scan": leak_scan,
        "workload": workload,
        "gates": gates,
        "limitations": [
            "verified only for the named single-workstation Windows profile",
            "private keys use an encrypted-file keystore, not TPM, HSM, or a remote secret manager",
            "backup deletion covers only the explicitly managed SQLite backup created by this profile; uncontrolled copies remain outside scope",
            "retention is verified as a bounded local run, not as a continuously supervised deployment scheduler",
            "multi-day telemetry, recovery alert delivery, and provider-side deletion attestations remain outside this representative profile",
            "worktree source is bound by digest because verification may precede commit",
        ],
        "rollback": {
            "action": "restore P020 manifest status to INTEGRATED",
            "data": "retain encrypted databases and reports for forensic review; revoke the active consent signer before disabling the dynamic resolver",
        },
    }
    report_path = run_root / "verified-sovereign-privacy-report.json"
    raw_report = _canonical(report)
    report_path.write_bytes(raw_report)
    Path(f"{report_path}.sha256").write_text(
        f"{_digest(raw_report)}\n",
        encoding="ascii",
    )
    if not verified:
        failures = ", ".join(item["name"] for item in gates if not item["passed"])
        raise SovereignPrivacyVerificationError(
            "VERIFICATION_FAILED",
            f"P20 gates failed: {failures}",
        )
    return report_path, report


__all__ = [
    "SovereignPrivacyVerificationError",
    "verify_sovereign_privacy",
]
