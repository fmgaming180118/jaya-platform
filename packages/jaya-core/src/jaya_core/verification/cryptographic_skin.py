"""Representative verification runner for Pillar 13 Cryptographic Skin."""

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
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

import psutil

from jaya_core.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from jaya_core.core_config import CoreConfig
from jaya_core.memory.backup import SQLiteBackupEngine
from jaya_core.security.capsule import CapsuleError, CapsuleKind, JayaCapsuleCodec
from jaya_core.security.cryptographic_skin import (
    CryptographicSkin,
    CryptographicSkinError,
    CryptographicSkinFailureCode,
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
    "seal_open_operations",
    "payload_bytes",
    "concurrent_writers",
    "operations_per_writer",
    "max_clock_skew_seconds",
    "minimum_elapsed_seconds",
    "max_mean_latency_ms",
    "max_p95_latency_ms",
    "min_operations_per_second",
    "max_full_audit_seconds",
    "max_rss_growth_bytes",
    "max_storage_bytes_per_operation",
    "max_envelope_overhead_bytes",
}


class CryptographicSkinVerificationError(RuntimeError):
    """Stable P13 representative verification failure."""

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
        raise CryptographicSkinVerificationError(
            "PROFILE_INVALID", "P13 verification profile is invalid"
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
        raise CryptographicSkinVerificationError(
            "PROFILE_INVALID", "P13 verification profile fields are invalid"
        )
    for field in (
        "seal_open_operations",
        "payload_bytes",
        "concurrent_writers",
        "operations_per_writer",
        "max_rss_growth_bytes",
        "max_storage_bytes_per_operation",
        "max_envelope_overhead_bytes",
    ):
        value = workload[field]
        if type(value) is not int or value <= 0:
            raise CryptographicSkinVerificationError(
                "PROFILE_INVALID", "P13 integer workload threshold is invalid"
            )
    if not 10 <= workload["seal_open_operations"] <= 10_000:
        raise CryptographicSkinVerificationError(
            "PROFILE_INVALID", "P13 operation count is invalid"
        )
    if not 1 <= workload["payload_bytes"] <= 16 * 1024 * 1024:
        raise CryptographicSkinVerificationError("PROFILE_INVALID", "P13 payload size is invalid")
    if not 2 <= workload["concurrent_writers"] <= 8:
        raise CryptographicSkinVerificationError(
            "PROFILE_INVALID", "P13 concurrent writer count is invalid"
        )
    for field in _WORKLOAD_FIELDS - {
        "seal_open_operations",
        "payload_bytes",
        "concurrent_writers",
        "operations_per_writer",
        "max_rss_growth_bytes",
        "max_storage_bytes_per_operation",
        "max_envelope_overhead_bytes",
    }:
        value = workload[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise CryptographicSkinVerificationError(
                "PROFILE_INVALID", "P13 numeric workload threshold is invalid"
            )
    if not 0 < float(workload["max_clock_skew_seconds"]) <= 300:
        raise CryptographicSkinVerificationError(
            "PROFILE_INVALID", "P13 clock skew threshold is invalid"
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
            raise CryptographicSkinVerificationError(
                "GIT_UNAVAILABLE", "P13 git version is unavailable"
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
            raise CryptographicSkinVerificationError(
                "SOURCE_UNAVAILABLE", "P13 source bundle is unavailable"
            ) from exc
        encoded = relative.encode()
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "little"))
        digest.update(raw)
    return f"sha256:{digest.hexdigest()}"


def _anchor(root: Path, secret: str) -> DNAAnchor:
    return DNAAnchor(root, EncryptedFileKeyStore(root / "keystore", secret))


def _skin(
    database: Path,
    anchor: DNAAnchor,
    secret: str,
    **options: object,
) -> CryptographicSkin:
    return CryptographicSkin(
        database,
        secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        **options,  # type: ignore[arg-type]
    )


def _expect_error(function: Any, code: CryptographicSkinFailureCode) -> str:
    try:
        function()
    except CryptographicSkinError as exc:
        if exc.code is not code:
            raise CryptographicSkinVerificationError(
                "UNEXPECTED_FAILURE",
                f"expected {code.value}, received {exc.code.value}",
            ) from exc
        return exc.code.value
    raise CryptographicSkinVerificationError("EXPECTED_FAILURE_MISSING", f"expected {code.value}")


def _run_demo(root: Path, workspace: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(root / "scripts" / "demo_cryptographic_skin.py"),
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
        raise CryptographicSkinVerificationError(
            "DEMO_FAILED", "P13 production-path demo returned invalid output"
        ) from exc
    if completed.returncode != 0:
        raise CryptographicSkinVerificationError("DEMO_FAILED", "P13 production-path demo failed")
    return {"command": command, "result": value, "stderr": completed.stderr.strip()}


def _launcher_probe(
    root: Path,
    workspace: Path,
) -> tuple[dict[str, object], tuple[str, ...]]:
    from scripts.run_jaya_core_server import _build_runtime

    data_dir = workspace / "data"
    identity_dir = data_dir / "identity"
    data_dir.mkdir(parents=True)
    identity_secret = secrets.token_urlsafe(48)
    privacy_secret = secrets.token_urlsafe(48)
    skin_secret = secrets.token_urlsafe(48)
    payload_marker = f"P13-LAUNCHER-{secrets.token_hex(16)}"
    anchor = _anchor(identity_dir, identity_secret)
    anchor.enroll()
    anchor.close()
    config = CoreConfig.from_env(
        {
            "JAYA_ENVIRONMENT": "test",
            "JAYA_SOUL_PASSWORD": "soul-" + secrets.token_urlsafe(40),
            "JAYA_CORE_API_KEY": "api-" + secrets.token_urlsafe(40),
            "JAYA_CORE_DATA_DIR": str(data_dir),
            "JAYA_NODE_ID": "p13-launcher-node",
            "JAYA_REQUIRE_IDENTITY": "true",
            "JAYA_IDENTITY_KEY_SECRET": identity_secret,
            "JAYA_IDENTITY_DIR": str(identity_dir),
            "JAYA_REQUIRE_PRIVACY": "true",
            "JAYA_PRIVACY_KEY_SECRET": privacy_secret,
            "JAYA_REQUIRE_ZERO_TRUST": "true",
            "JAYA_REQUIRE_CRYPTOGRAPHIC_SKIN": "true",
            "JAYA_CRYPTOGRAPHIC_SKIN_SECRET": skin_secret,
        },
        core_dir=root,
    )
    runtime = _build_runtime(config)
    try:
        envelope = runtime.seal_artifact(
            payload_marker.encode(),
            purpose="core.artifact",
            subject="artifact:p13-launcher",
        )
        restored = runtime.open_artifact(envelope)
        snapshot = runtime.operational_snapshot()
    finally:
        runtime.close()
    return (
        {
            "roundtrip": restored.decode() == payload_marker,
            "runtime_ready": snapshot.get("ready"),
            "identity_mode": snapshot.get("identity_mode"),
            "privacy_ready": snapshot.get("sovereign_privacy", {}).get("ready"),
            "zero_trust_ready": snapshot.get("zero_trust", {}).get("ready"),
            "cryptographic_skin_ready": snapshot.get("cryptographic_skin", {}).get("ready"),
            "state_authenticated": snapshot.get("cryptographic_skin", {}).get(
                "state_authenticated"
            ),
        },
        (identity_secret, privacy_secret, skin_secret, payload_marker),
    )


def _capsule_probe(root: Path, skin: CryptographicSkin) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    codec = JayaCapsuleCodec(skin)
    kind_results: dict[str, bool] = {}
    plaintext_absent = True
    for kind in CapsuleKind:
        payload = f"P13-{kind.value}-capsule-payload".encode()
        capsule = codec.seal(payload, kind=kind, subject=f"subject:{kind.value}")
        kind_results[kind.value] = (
            codec.open(
                capsule,
                expected_kind=kind,
                expected_subject=f"subject:{kind.value}",
            )
            == payload
        )
        plaintext_absent = plaintext_absent and payload not in capsule
    scoped = codec.seal(
        b"scope-target",
        kind=CapsuleKind.MESH,
        subject="subject:mesh-scope",
    )
    scope_rejected = False
    try:
        codec.open(
            scoped,
            expected_kind=CapsuleKind.BRAIN,
            expected_subject="subject:mesh-scope",
        )
    except CapsuleError:
        scope_rejected = True

    source = root / "backup-source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE memory(value TEXT NOT NULL)")
        connection.execute("INSERT INTO memory VALUES ('p13-backup-value')")
    capsule_path = root / "backup.jayac"
    restored = root / "backup-restored.db"
    backup = SQLiteBackupEngine()
    backup.create_secure_backup(
        source,
        capsule_path,
        codec,
        subject="memory:p13-representative",
    )
    backup.restore_secure_backup(
        capsule_path,
        restored,
        codec,
        subject="memory:p13-representative",
    )
    with sqlite3.connect(restored) as connection:
        backup_value = connection.execute("SELECT value FROM memory").fetchone()[0]
    return {
        "kind_results": kind_results,
        "plaintext_absent": plaintext_absent,
        "scope_rejected": scope_rejected,
        "backup_restored": backup_value == "p13-backup-value",
        "backup_plaintext_absent": b"p13-backup-value" not in capsule_path.read_bytes(),
    }


def _concurrency_probe(
    root: Path,
    identity_secret: str,
    skin_secret: str,
    writers: int,
    operations_per_writer: int,
) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    identity_root = root / "identity"
    enrollment = _anchor(identity_root, identity_secret)
    enrollment.enroll()
    enrollment.close()
    database = root / "concurrent.db"
    anchors = [_anchor(identity_root, identity_secret) for _ in range(writers)]
    skins = [_skin(database, anchor, skin_secret) for anchor in anchors]

    def exercise(index: int) -> list[str]:
        nonces: list[str] = []
        for sequence in range(operations_per_writer):
            payload = f"writer-{index}-{sequence}".encode()
            envelope = skins[index].seal(
                payload,
                purpose="core.concurrent",
                subject=f"artifact:writer-{index}-{sequence}",
            )
            if skins[index].open(envelope) != payload:
                raise CryptographicSkinVerificationError(
                    "CONCURRENCY_INVARIANT", "P13 concurrent roundtrip failed"
                )
            nonces.append(envelope.nonce)
        return nonces

    try:
        with ThreadPoolExecutor(max_workers=writers) as executor:
            futures = [executor.submit(exercise, index) for index in range(writers)]
            nonces = [nonce for future in futures for nonce in future.result()]
    finally:
        for skin in skins:
            skin.close()
        for anchor in anchors:
            anchor.close()
    restart_anchor = _anchor(identity_root, identity_secret)
    restarted = _skin(database, restart_anchor, skin_secret)
    try:
        status = restarted.status()
    finally:
        restarted.close()
        restart_anchor.close()
    return {
        "operations": len(nonces),
        "unique_nonces": len(set(nonces)),
        "ready_after_restart": status["ready"],
        "audit_chain_valid": status["audit_chain_valid"],
        "state_authenticated": status["state_authenticated"],
    }


def _recomputed_key_digest(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT key_id, state, retired_at, previous_key_id
        FROM crypto_skin_keys WHERE state = 'ACTIVE'
        """
    ).fetchone()
    if row is None:
        raise CryptographicSkinVerificationError(
            "TAMPER_PROBE_FAILED", "P13 active key is unavailable"
        )
    created_at = "2026-08-30T00:00:00+00:00"
    digest = hashlib.sha256(
        _canonical(
            {
                "created_at": created_at,
                "key_id": row[0],
                "previous_key_id": row[3],
                "retired_at": row[2],
                "state": row[1],
            }
        )
    ).hexdigest()
    connection.execute(
        "UPDATE crypto_skin_keys SET created_at = ?, row_digest = ? WHERE key_id = ?",
        (created_at, digest, row[0]),
    )


def _recomputed_audit_digest(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT event_id, occurred_at, event, previous_sha256
        FROM crypto_skin_audit ORDER BY event_id DESC LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise CryptographicSkinVerificationError(
            "TAMPER_PROBE_FAILED", "P13 audit row is unavailable"
        )
    payload = {"envelope_id": "env-attacker-recomputed"}
    digest = hashlib.sha256(
        _canonical(
            {
                "occurred_at": row[1],
                "event": row[2],
                "payload": payload,
                "previous_sha256": row[3],
            }
        )
    ).hexdigest()
    connection.execute(
        """
        UPDATE crypto_skin_audit SET payload_json = ?, event_sha256 = ?
        WHERE event_id = ?
        """,
        (_canonical(payload).decode(), digest, row[0]),
    )


def _tamper_probes(
    root: Path,
    source: Path,
    identity_root: Path,
    identity_secret: str,
    skin_secret: str,
) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}
    mutations = {
        "salt": lambda connection: connection.execute(
            "UPDATE crypto_skin_metadata SET value = ? WHERE key = 'kdf_salt'",
            ("cXFxcXFxcXFxcXFxcXFxcQ",),
        ),
        "registry": _recomputed_key_digest,
        "nonce": lambda connection: connection.execute(
            "UPDATE crypto_skin_nonces SET reserved_at = '2026-08-30T00:00:00+00:00'"
        ),
        "audit": _recomputed_audit_digest,
    }
    anchor = _anchor(identity_root, identity_secret)
    try:
        for name, mutate in mutations.items():
            database = root / f"tamper-{name}.db"
            shutil.copy2(source, database)
            with sqlite3.connect(database) as connection:
                mutate(connection)
            results[name] = _expect_error(
                lambda database=database: _skin(database, anchor, skin_secret),
                CryptographicSkinFailureCode.AUDIT_CORRUPT,
            )
        schema = root / "unsupported-schema.db"
        shutil.copy2(source, schema)
        with sqlite3.connect(schema) as connection:
            connection.execute(
                """
                UPDATE crypto_skin_metadata SET value = '999'
                WHERE key = 'storage_schema_version'
                """
            )
        results["schema"] = _expect_error(
            lambda: _skin(schema, anchor, skin_secret),
            CryptographicSkinFailureCode.STORAGE_SCHEMA_UNSUPPORTED,
        )

        recovery = root / "recovery.db"
        backup = root / "recovery-backup.db"
        shutil.copy2(source, recovery)
        shutil.copy2(source, backup)
        with sqlite3.connect(recovery) as connection:
            connection.execute("DELETE FROM crypto_skin_nonces")
        results["recovery_detected"] = _expect_error(
            lambda: _skin(recovery, anchor, skin_secret),
            CryptographicSkinFailureCode.AUDIT_CORRUPT,
        )
        shutil.copy2(backup, recovery)
        restored = _skin(recovery, anchor, skin_secret)
        try:
            results["recovery_restored"] = "READY" if restored.status()["ready"] else "FAIL"
        finally:
            restored.close()
    finally:
        anchor.close()
    return results


def _provider_probes(
    root: Path,
    anchor: DNAAnchor,
    identity_secret: str,
    skin_secret: str,
) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    signer = CryptographicSkin(
        root / "signer.db",
        skin_secret,
        attestation_signer=lambda _purpose, _digest: (_ for _ in ()).throw(
            RuntimeError("signer detail")
        ),
        attestation_verifier=anchor.verify_attestation,
    )
    signer_code = _expect_error(
        lambda: signer.seal(
            b"signer-target",
            purpose="core.artifact",
            subject="artifact:signer",
        ),
        CryptographicSkinFailureCode.ATTESTATION_UNAVAILABLE,
    )
    signer_ready = signer.status()["ready"]
    signer.close()

    verifier_db = root / "verifier.db"
    normal = _skin(verifier_db, anchor, skin_secret)
    verifier_envelope = normal.seal(
        b"verifier-target",
        purpose="core.artifact",
        subject="artifact:verifier",
    )
    normal.close()
    verifier = CryptographicSkin(
        verifier_db,
        skin_secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=lambda _value: (_ for _ in ()).throw(RuntimeError("verifier detail")),
    )
    verifier_code = _expect_error(
        lambda: verifier.open(verifier_envelope),
        CryptographicSkinFailureCode.ATTESTATION_UNAVAILABLE,
    )
    verifier.close()

    nonce = _skin(
        root / "nonce.db",
        anchor,
        skin_secret,
        nonce_factory=lambda _size: (_ for _ in ()).throw(RuntimeError("nonce detail")),
    )
    nonce_code = _expect_error(
        lambda: nonce.seal(
            b"nonce-target",
            purpose="core.artifact",
            subject="artifact:nonce",
        ),
        CryptographicSkinFailureCode.NONCE_UNAVAILABLE,
    )
    nonce_ready = nonce.status()["ready"]
    nonce.close()

    def broken_clock() -> datetime:
        raise RuntimeError("clock detail")

    clock_code = _expect_error(
        lambda: _skin(root / "clock.db", anchor, skin_secret, clock=broken_clock),
        CryptographicSkinFailureCode.CLOCK_UNAVAILABLE,
    )

    storage_db = root / "storage-lock.db"
    initialized = _skin(storage_db, anchor, skin_secret)
    initialized.close()
    blocker = sqlite3.connect(storage_db, timeout=1.0)
    blocker.execute("BEGIN EXCLUSIVE")
    started = time.perf_counter()
    try:
        storage_code = _expect_error(
            lambda: _skin(
                storage_db,
                anchor,
                skin_secret,
                storage_timeout_seconds=0.05,
            ),
            CryptographicSkinFailureCode.STORAGE_ERROR,
        )
    finally:
        blocker.rollback()
        blocker.close()
    return {
        "signer": signer_code,
        "signer_state_ready": signer_ready,
        "verifier": verifier_code,
        "nonce": nonce_code,
        "nonce_state_ready": nonce_ready,
        "clock": clock_code,
        "storage": storage_code,
        "storage_elapsed_seconds": time.perf_counter() - started,
        "identity_secret_not_returned": bool(identity_secret),
    }


def _leak_scan(root: Path, needles: tuple[str, ...]) -> dict[str, object]:
    matches: list[str] = []
    scanned_files = 0
    scanned_bytes = 0
    encoded = tuple(item.encode() for item in needles if item)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise CryptographicSkinVerificationError(
                "LEAK_SCAN_FAILED", "P13 artifact leak scan failed"
            ) from exc
        scanned_files += 1
        scanned_bytes += len(raw)
        if any(item in raw for item in encoded):
            matches.append(str(path.relative_to(root)))
    return {
        "scanned_files": scanned_files,
        "scanned_bytes": scanned_bytes,
        "matches": matches,
    }


def _gate(name: str, passed: bool, actual: Any, limit: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "limit": limit}


def verify_cryptographic_skin(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Execute the approved P13 profile against production cryptographic code."""

    normalized_approver = " ".join(str(approver).strip().split())
    if not 3 <= len(normalized_approver) <= 160:
        raise CryptographicSkinVerificationError(
            "APPROVAL_REQUIRED", "P13 approver role is required"
        )
    root = repository_root.expanduser().resolve()
    profile = _load_profile(profile_path)
    host = _host()
    if host["os"] != profile["supported_os"]:
        raise CryptographicSkinVerificationError(
            "HOST_UNSUPPORTED", "P13 host does not match the approved profile"
        )
    run_id = f"p13-verified-{uuid.uuid4().hex}"
    run_root = output_directory.expanduser().resolve() / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    config = profile["workload"]
    identity_secret = secrets.token_urlsafe(48)
    skin_secret = secrets.token_urlsafe(48)
    private_marker = f"P13-PRIVATE-{secrets.token_hex(24)}"
    identity_root = run_root / "identity"
    database = run_root / "cryptographic-skin.db"
    current_time = [datetime.now(UTC)]
    anchor = _anchor(identity_root, identity_secret)
    anchor.enroll()
    skin = _skin(
        database,
        anchor,
        skin_secret,
        clock=lambda: current_time[0],
        max_clock_skew_seconds=float(config["max_clock_skew_seconds"]),
    )
    primary = skin.seal(
        private_marker.encode(),
        purpose="core.artifact",
        subject="artifact:p13-primary",
        content_type="application/jaya-artifact",
        ttl_seconds=600,
    )
    roundtrip = skin.open(primary) == private_marker.encode()
    envelope_json = _canonical(primary.to_dict())
    plaintext_absent = (
        private_marker.encode() not in envelope_json
        and private_marker.encode() not in database.read_bytes()
    )
    purpose_tamper = _expect_error(
        lambda: skin.open(replace(primary, purpose="core.backup")),
        CryptographicSkinFailureCode.SIGNATURE_INVALID,
    )
    subject_tamper = _expect_error(
        lambda: skin.open(replace(primary, subject="artifact:other")),
        CryptographicSkinFailureCode.SIGNATURE_INVALID,
    )
    content_tamper = _expect_error(
        lambda: skin.open(replace(primary, content_type="application/octet-stream")),
        CryptographicSkinFailureCode.SIGNATURE_INVALID,
    )
    ciphertext_tamper = _expect_error(
        lambda: skin.open(replace(primary, ciphertext="AAAA")),
        CryptographicSkinFailureCode.SIGNATURE_INVALID,
    )
    nonce_tamper = _expect_error(
        lambda: skin.open(replace(primary, nonce="AAAA")),
        CryptographicSkinFailureCode.SIGNATURE_INVALID,
    )
    downgrade = _expect_error(
        lambda: skin.open(replace(primary, algorithm_suite="BASE64")),
        CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
    )
    unknown_field = _expect_error(
        lambda: skin.open({**primary.to_dict(), "unexpected": True}),
        CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
    )
    invalid_signature = _expect_error(
        lambda: skin.open(
            replace(primary, attestation={**primary.attestation, "signature": "AAAA"})
        ),
        CryptographicSkinFailureCode.SIGNATURE_INVALID,
    )

    base_time = current_time[0]
    current_time[0] = base_time + timedelta(seconds=float(config["max_clock_skew_seconds"]) + 1)
    future = skin.seal(
        b"future-target",
        purpose="core.artifact",
        subject="artifact:future",
    )
    current_time[0] = base_time
    clock_skew = _expect_error(lambda: skin.open(future), CryptographicSkinFailureCode.CLOCK_SKEW)
    expiring = skin.seal(
        b"expiry-target",
        purpose="core.artifact",
        subject="artifact:expiry",
        ttl_seconds=1,
    )
    current_time[0] = base_time + timedelta(seconds=1)
    expired = _expect_error(
        lambda: skin.open(expiring), CryptographicSkinFailureCode.ENVELOPE_EXPIRED
    )
    current_time[0] = base_time

    old_key = primary.key_id
    new_key = skin.rotate_key()
    rotation_continuity = skin.open(primary) == private_marker.encode()
    current = skin.seal(
        b"current-key-target",
        purpose="core.artifact",
        subject="artifact:current-key",
    )

    process = psutil.Process()
    rss_before = process.memory_info().rss
    payload_size = int(config["payload_bytes"])
    operations = int(config["seal_open_operations"])
    latencies: list[float] = []
    envelope_sizes: list[int] = []
    workload_started = time.perf_counter()
    for index in range(operations):
        prefix = hashlib.sha256(f"{run_id}:{index}".encode()).digest()
        payload = (prefix * math.ceil(payload_size / len(prefix)))[:payload_size]
        started = time.perf_counter()
        envelope = skin.seal(
            payload,
            purpose="core.benchmark",
            subject=f"artifact:benchmark-{index}",
        )
        restored = skin.open(envelope)
        latencies.append((time.perf_counter() - started) * 1_000)
        envelope_sizes.append(len(_canonical(envelope.to_dict())))
        if restored != payload:
            raise CryptographicSkinVerificationError(
                "WORKLOAD_INVARIANT", "P13 workload roundtrip failed"
            )
    workload_elapsed = time.perf_counter() - workload_started
    throughput = operations / max(workload_elapsed, 0.000001)
    audit_started = time.perf_counter()
    audit_valid = skin.audit_chain_valid()
    full_audit_seconds = time.perf_counter() - audit_started
    status_before_restart = skin.status()
    capsule = _capsule_probe(run_root / "capsules", skin)
    skin.close()
    anchor.close()
    rss_after = process.memory_info().rss

    restarted_anchor = _anchor(identity_root, identity_secret)
    restarted = _skin(
        database,
        restarted_anchor,
        skin_secret,
        clock=lambda: base_time,
        max_clock_skew_seconds=float(config["max_clock_skew_seconds"]),
    )
    restart_old = restarted.open(primary) == private_marker.encode()
    restart_current = restarted.open(current) == b"current-key-target"
    restarted.revoke_key(old_key)
    revoked = _expect_error(
        lambda: restarted.open(primary), CryptographicSkinFailureCode.KEY_REVOKED
    )
    active_after_revoke = restarted.active_key_id() == new_key
    status_after_restart = restarted.status()
    restarted.close()
    restarted_anchor.close()

    wrong_anchor = _anchor(identity_root, identity_secret)
    wrong_secret = _expect_error(
        lambda: _skin(database, wrong_anchor, secrets.token_urlsafe(48)),
        CryptographicSkinFailureCode.AUDIT_CORRUPT,
    )
    wrong_anchor.close()

    tamper = _tamper_probes(
        run_root / "tamper-probes",
        database,
        identity_root,
        identity_secret,
        skin_secret,
    )
    provider_anchor = _anchor(identity_root, identity_secret)
    providers = _provider_probes(
        run_root / "provider-probes",
        provider_anchor,
        identity_secret,
        skin_secret,
    )
    provider_anchor.close()
    concurrency = _concurrency_probe(
        run_root / "concurrency",
        secrets.token_urlsafe(48),
        secrets.token_urlsafe(48),
        int(config["concurrent_writers"]),
        int(config["operations_per_writer"]),
    )
    launcher, launcher_needles = _launcher_probe(root, run_root / "launcher")
    demo = _run_demo(root, run_root / "production-path-demo")
    leak_scan = _leak_scan(
        run_root,
        (identity_secret, skin_secret, private_marker, *launcher_needles),
    )

    sorted_latencies = sorted(latencies)
    p95 = sorted_latencies[max(0, math.ceil(len(sorted_latencies) * 0.95) - 1)]
    mean_latency = mean(latencies)
    storage_bytes = database.stat().st_size
    storage_per_operation = storage_bytes / operations
    max_overhead = max(size - payload_size for size in envelope_sizes)
    rss_growth = max(0, rss_after - rss_before)
    all_tamper_codes = all(
        value == CryptographicSkinFailureCode.AUDIT_CORRUPT.value
        for key, value in tamper.items()
        if key in {"salt", "registry", "nonce", "audit", "recovery_detected"}
    )
    gates = [
        _gate("roundtrip", roundtrip, roundtrip, True),
        _gate("plaintext_absent", plaintext_absent, plaintext_absent, True),
        _gate(
            "aes_256_gcm_ed25519_suite",
            primary.algorithm_suite == "AES-256-GCM+ED25519",
            primary.algorithm_suite,
            "AES-256-GCM+ED25519",
        ),
        _gate("strict_schema", primary.schema_version == 1, primary.schema_version, 1),
        _gate(
            "purpose_binding",
            purpose_tamper.endswith("SIGNATURE_INVALID"),
            purpose_tamper,
            "SIGNATURE_INVALID",
        ),
        _gate(
            "subject_binding",
            subject_tamper.endswith("SIGNATURE_INVALID"),
            subject_tamper,
            "SIGNATURE_INVALID",
        ),
        _gate(
            "content_type_binding",
            content_tamper.endswith("SIGNATURE_INVALID"),
            content_tamper,
            "SIGNATURE_INVALID",
        ),
        _gate(
            "ciphertext_tamper",
            ciphertext_tamper.endswith("SIGNATURE_INVALID"),
            ciphertext_tamper,
            "SIGNATURE_INVALID",
        ),
        _gate(
            "nonce_tamper",
            nonce_tamper.endswith("SIGNATURE_INVALID"),
            nonce_tamper,
            "SIGNATURE_INVALID",
        ),
        _gate(
            "algorithm_downgrade",
            downgrade.endswith("CORRUPT_ENVELOPE"),
            downgrade,
            "CORRUPT_ENVELOPE",
        ),
        _gate(
            "unknown_field",
            unknown_field.endswith("CORRUPT_ENVELOPE"),
            unknown_field,
            "CORRUPT_ENVELOPE",
        ),
        _gate(
            "dna_signature_tamper",
            invalid_signature.endswith("SIGNATURE_INVALID"),
            invalid_signature,
            "SIGNATURE_INVALID",
        ),
        _gate("clock_skew", clock_skew.endswith("CLOCK_SKEW"), clock_skew, "CLOCK_SKEW"),
        _gate("expiry", expired.endswith("ENVELOPE_EXPIRED"), expired, "ENVELOPE_EXPIRED"),
        _gate("rotation_continuity", rotation_continuity, rotation_continuity, True),
        _gate(
            "restart_continuity",
            restart_old and restart_current,
            {"old": restart_old, "current": restart_current},
            True,
        ),
        _gate(
            "revocation",
            revoked.endswith("KEY_REVOKED") and active_after_revoke,
            {"code": revoked, "active": active_after_revoke},
            True,
        ),
        _gate(
            "wrong_secret", wrong_secret.endswith("AUDIT_CORRUPT"), wrong_secret, "AUDIT_CORRUPT"
        ),
        _gate("keyed_state_tamper", all_tamper_codes, tamper, "all rejected"),
        _gate(
            "unsupported_storage_schema",
            tamper["schema"].endswith("STORAGE_SCHEMA_UNSUPPORTED"),
            tamper["schema"],
            "STORAGE_SCHEMA_UNSUPPORTED",
        ),
        _gate(
            "local_recovery_drill",
            tamper["recovery_restored"] == "READY",
            tamper["recovery_restored"],
            "READY",
        ),
        _gate(
            "signer_failure_stable",
            str(providers["signer"]).endswith("ATTESTATION_UNAVAILABLE")
            and providers["signer_state_ready"] is True,
            providers["signer"],
            "ATTESTATION_UNAVAILABLE",
        ),
        _gate(
            "verifier_failure_stable",
            str(providers["verifier"]).endswith("ATTESTATION_UNAVAILABLE"),
            providers["verifier"],
            "ATTESTATION_UNAVAILABLE",
        ),
        _gate(
            "nonce_provider_failure_stable",
            str(providers["nonce"]).endswith("NONCE_UNAVAILABLE")
            and providers["nonce_state_ready"] is True,
            providers["nonce"],
            "NONCE_UNAVAILABLE",
        ),
        _gate(
            "clock_provider_failure_stable",
            str(providers["clock"]).endswith("CLOCK_UNAVAILABLE"),
            providers["clock"],
            "CLOCK_UNAVAILABLE",
        ),
        _gate(
            "storage_timeout_bounded",
            str(providers["storage"]).endswith("STORAGE_ERROR")
            and float(providers["storage_elapsed_seconds"]) < 1.0,
            providers,
            "STORAGE_ERROR <1s",
        ),
        _gate(
            "concurrent_writers",
            concurrency["operations"] == concurrency["unique_nonces"]
            and concurrency["ready_after_restart"] is True,
            concurrency,
            "all unique and ready",
        ),
        _gate(
            "capsule_all_kinds",
            all(capsule["kind_results"].values()) and capsule["scope_rejected"] is True,
            capsule,
            "four kinds scoped",
        ),
        _gate(
            "secure_backup_consumer",
            capsule["backup_restored"] is True and capsule["backup_plaintext_absent"] is True,
            capsule,
            "encrypted restore",
        ),
        _gate(
            "canonical_launcher_dependencies",
            all(
                launcher.get(key) is True
                for key in (
                    "roundtrip",
                    "runtime_ready",
                    "privacy_ready",
                    "zero_trust_ready",
                    "cryptographic_skin_ready",
                    "state_authenticated",
                )
            ),
            launcher,
            "P11/P18/P20/P13 ready",
        ),
        _gate(
            "production_path_demo",
            all(
                demo["result"].get(key) is True
                for key in (
                    "restart_restored",
                    "plaintext_absent",
                    "rotation_continuity",
                    "old_key_revoked",
                    "audit_chain_valid",
                    "state_authenticated",
                    "wrong_secret_rejected",
                )
            ),
            demo["result"],
            "all true",
        ),
        _gate("workload_count", len(latencies) == operations, len(latencies), operations),
        _gate(
            "minimum_elapsed",
            workload_elapsed >= float(config["minimum_elapsed_seconds"]),
            workload_elapsed,
            config["minimum_elapsed_seconds"],
        ),
        _gate(
            "mean_latency",
            mean_latency <= float(config["max_mean_latency_ms"]),
            mean_latency,
            config["max_mean_latency_ms"],
        ),
        _gate(
            "p95_latency",
            p95 <= float(config["max_p95_latency_ms"]),
            p95,
            config["max_p95_latency_ms"],
        ),
        _gate(
            "throughput",
            throughput >= float(config["min_operations_per_second"]),
            throughput,
            config["min_operations_per_second"],
        ),
        _gate(
            "full_audit",
            audit_valid and full_audit_seconds <= float(config["max_full_audit_seconds"]),
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
        _gate(
            "envelope_overhead",
            max_overhead <= int(config["max_envelope_overhead_bytes"]),
            max_overhead,
            config["max_envelope_overhead_bytes"],
        ),
        _gate(
            "health_before_restart",
            status_before_restart["ready"] is True
            and status_before_restart["state_authenticated"] is True,
            status_before_restart,
            "ready/authenticated",
        ),
        _gate(
            "health_after_restart",
            status_after_restart["ready"] is True
            and status_after_restart["state_authenticated"] is True,
            status_after_restart,
            "ready/authenticated",
        ),
        _gate("secret_leak_scan", not leak_scan["matches"], leak_scan, "no matches"),
        _gate(
            "hardware_anti_rollback_truth_boundary",
            True,
            "BLOCKED_EXTERNAL",
            "must remain outside representative claim",
        ),
    ]
    failed = [gate["name"] for gate in gates if not gate["passed"]]
    if failed:
        raise CryptographicSkinVerificationError(
            "GATE_FAILED", f"P13 representative gates failed: {', '.join(failed)}"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE",
        "pillar": "P013",
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
        "authority_lifecycle": {
            "rotation_continuity": rotation_continuity,
            "restart_old": restart_old,
            "restart_current": restart_current,
            "revoked_code": revoked,
            "wrong_secret_code": wrong_secret,
            "status_before_restart": status_before_restart,
            "status_after_restart": status_after_restart,
        },
        "failure_paths": {
            "purpose": purpose_tamper,
            "subject": subject_tamper,
            "content_type": content_tamper,
            "ciphertext": ciphertext_tamper,
            "nonce": nonce_tamper,
            "downgrade": downgrade,
            "unknown_field": unknown_field,
            "signature": invalid_signature,
            "clock_skew": clock_skew,
            "expiry": expired,
            "storage_tamper": tamper,
            "provider_failures": providers,
        },
        "capsule_boundaries": capsule,
        "concurrency": concurrency,
        "canonical_launcher": launcher,
        "production_path_demo": demo,
        "workload": {
            "operations": operations,
            "payload_bytes": payload_size,
            "elapsed_seconds": workload_elapsed,
            "operations_per_second": throughput,
            "mean_latency_ms": mean_latency,
            "p95_latency_ms": p95,
            "full_audit_seconds": full_audit_seconds,
            "rss_growth_bytes": rss_growth,
            "storage_bytes": storage_bytes,
            "storage_bytes_per_operation": storage_per_operation,
            "max_envelope_overhead_bytes": max_overhead,
        },
        "leak_scan": leak_scan,
        "gates": gates,
        "limitations": [
            "Encrypted-file DNA identity and injected process secret are not an OS secret manager, TPM, or HSM.",
            "A valid older database snapshot cannot be distinguished without an external monotonic counter or hardware anti-rollback authority.",
            "The profile covers one Windows workstation and bounded local SQLite workload, not sustained production deployment.",
            "P13-only capsules are classically authenticated; quantum-resistant claims require the separately verified and available P16 provider.",
        ],
        "rollback": "Restore the last authenticated SQLite backup and prior compatible source bundle; never delete the state authenticator or silently downgrade schema.",
    }
    report_path = run_root / "verified-cryptographic-skin-report.json"
    report_raw = json.dumps(report, ensure_ascii=False, indent=2).encode()
    report_path.write_bytes(report_raw)
    report_path.with_suffix(report_path.suffix + ".sha256").write_text(
        _digest(report_raw) + "\n", encoding="utf-8"
    )
    return report_path, report


__all__ = [
    "CryptographicSkinVerificationError",
    "verify_cryptographic_skin",
]
