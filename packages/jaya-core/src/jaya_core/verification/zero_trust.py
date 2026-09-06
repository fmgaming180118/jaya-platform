"""Representative verification runner for Pillar 18 Zero Trust."""

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
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psutil

from jaya_core.brain_v2.protection.dna_anchor import (
    DNAAnchor,
    DNAAnchorError,
    DNAFailureCode,
    EncryptedFileKeyStore,
)
from jaya_core.brain_v2.protection.zero_trust import (
    TrustEffect,
    TrustEnvelope,
    TrustError,
    TrustFailureCode,
    ZeroTrustAuthority,
    create_trust_envelope,
)
from jaya_core.capabilities.puzzle import CapabilityPuzzleRegistry
from jaya_core.core_config import CoreConfig

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
    "authorizations",
    "replay_attempts",
    "max_clock_skew_seconds",
    "minimum_elapsed_seconds",
    "max_mean_latency_ms",
    "max_p95_latency_ms",
    "max_full_audit_seconds",
    "max_rss_growth_bytes",
    "max_storage_bytes_per_decision",
    "min_replay_attempts_per_second",
}
_NODE = "p18-representative-node"
_CAPABILITY = "core.logic.evaluate"


class ZeroTrustVerificationError(RuntimeError):
    """Stable P18 representative verification failure."""

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
        raise ZeroTrustVerificationError(
            "PROFILE_INVALID",
            "P18 verification profile is invalid",
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
        raise ZeroTrustVerificationError(
            "PROFILE_INVALID",
            "P18 verification profile fields are invalid",
        )
    for field in ("authorizations", "replay_attempts"):
        value = workload[field]
        if type(value) is not int or not 10 <= value <= 10_000:
            raise ZeroTrustVerificationError(
                "PROFILE_INVALID",
                "P18 workload count is invalid",
            )
    if type(workload["max_rss_growth_bytes"]) is not int or workload["max_rss_growth_bytes"] <= 0:
        raise ZeroTrustVerificationError(
            "PROFILE_INVALID",
            "P18 RSS threshold is invalid",
        )
    for field in _WORKLOAD_FIELDS - {
        "authorizations",
        "replay_attempts",
        "max_rss_growth_bytes",
    }:
        value = workload[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ZeroTrustVerificationError(
                "PROFILE_INVALID",
                "P18 workload threshold is invalid",
            )
    if not 0 < float(workload["max_clock_skew_seconds"]) <= 300:
        raise ZeroTrustVerificationError(
            "PROFILE_INVALID",
            "P18 clock skew threshold is invalid",
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
            raise ZeroTrustVerificationError(
                "GIT_UNAVAILABLE",
                "P18 git version is unavailable",
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
            raise ZeroTrustVerificationError(
                "SOURCE_UNAVAILABLE",
                "P18 verification source bundle is unavailable",
            ) from exc
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "little"))
        digest.update(raw)
    return f"sha256:{digest.hexdigest()}"


def _anchor(root: Path, secret: str) -> DNAAnchor:
    return DNAAnchor(root, EncryptedFileKeyStore(root / "keystore", secret))


def _principal_state(anchor: DNAAnchor):
    def resolve(principal_id: str) -> dict[str, object] | None:
        try:
            record = anchor.load_identity()
        except DNAAnchorError as exc:
            if exc.code is DNAFailureCode.IDENTITY_REVOKED:
                return {"active": False, "key_version": 0}
            raise
        if record.brain_id != principal_id:
            return None
        return {"active": True, "key_version": record.key_version}

    return resolve


def _envelope(
    anchor: DNAAnchor,
    principal_id: str,
    payload: dict[str, object],
    *,
    now: datetime,
    node_id: str = _NODE,
    capability_id: str = _CAPABILITY,
) -> TrustEnvelope:
    return create_trust_envelope(
        principal_id=principal_id,
        node_id=node_id,
        capability_id=capability_id,
        payload=payload,
        policy_receipt_sha256="a" * 64,
        privacy_receipt_sha256="b" * 64,
        signer=lambda purpose, digest: anchor.sign_attestation(
            purpose,
            digest,
        ).to_dict(),
        now=now,
    )


def _expect_trust_error(function: Any, code: TrustFailureCode) -> str:
    try:
        function()
    except TrustError as exc:
        if exc.code is not code:
            raise ZeroTrustVerificationError(
                "UNEXPECTED_FAILURE",
                f"expected {code.value}, received {exc.code.value}",
            ) from exc
        return exc.code.value
    raise ZeroTrustVerificationError(
        "EXPECTED_FAILURE_MISSING",
        f"expected {code.value}",
    )


def _expect_corrupt(
    database: Path,
    verifier: Any,
) -> str:
    return _expect_trust_error(
        lambda: ZeroTrustAuthority(database, attestation_verifier=verifier),
        TrustFailureCode.CORRUPT_AUDIT,
    )


def _run_demo(root: Path, workspace: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(root / "scripts" / "demo_zero_trust.py"),
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
        raise ZeroTrustVerificationError(
            "DEMO_FAILED",
            "P18 production-path demo returned invalid output",
        ) from exc
    if completed.returncode != 0:
        raise ZeroTrustVerificationError(
            "DEMO_FAILED",
            "P18 production-path demo failed",
        )
    return {"command": command, "result": value, "stderr": completed.stderr.strip()}


def _launcher_probe(root: Path, workspace: Path) -> dict[str, object]:
    from scripts.run_jaya_core_server import _build_runtime

    data_dir = workspace / "data"
    identity_dir = data_dir / "identity"
    data_dir.mkdir(parents=True)
    identity_secret = secrets.token_urlsafe(48)
    privacy_secret = secrets.token_urlsafe(48)
    anchor = _anchor(identity_dir, identity_secret)
    anchor.enroll()
    anchor.close()
    config = CoreConfig.from_env(
        {
            "JAYA_ENVIRONMENT": "test",
            "JAYA_SOUL_PASSWORD": "soul-" + secrets.token_urlsafe(40),
            "JAYA_CORE_API_KEY": "api-" + secrets.token_urlsafe(40),
            "JAYA_CORE_DATA_DIR": str(data_dir),
            "JAYA_NODE_ID": "p18-launcher-node",
            "JAYA_REQUIRE_IDENTITY": "true",
            "JAYA_IDENTITY_KEY_SECRET": identity_secret,
            "JAYA_IDENTITY_DIR": str(identity_dir),
            "JAYA_REQUIRE_PRIVACY": "true",
            "JAYA_PRIVACY_KEY_SECRET": privacy_secret,
            "JAYA_REQUIRE_ZERO_TRUST": "true",
        },
        core_dir=root,
    )
    runtime = _build_runtime(config)
    try:
        result = runtime.reason_logic_ir(
            request_id="p18-representative-launcher",
            facts=["trust.required"],
            rules=[],
            query="trust.required",
        )
        snapshot = runtime.operational_snapshot()
    finally:
        runtime.close()
    return {
        "ok": result.get("ok"),
        "logic_status": result.get("result", {}).get("status"),
        "zero_trust_ready": snapshot.get("zero_trust", {}).get("ready"),
        "principal_state_source": snapshot.get("zero_trust", {}).get("principal_state_source"),
        "privacy_ready": snapshot.get("sovereign_privacy", {}).get("ready"),
    }


def _artifact_probe(workspace: Path) -> dict[str, object]:
    puzzle_dir = workspace / "puzzles" / "tampered"
    puzzle_dir.mkdir(parents=True)
    marker = workspace / "artifact-imported.txt"
    artifact = puzzle_dir / "adapter.py"
    artifact.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\n",
        encoding="utf-8",
    )
    (puzzle_dir / "puzzle.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "puzzle_id": "p18.tampered",
                "capability_id": "p18.tampered",
                "version": "1.0.0",
                "artifact": "adapter.py",
                "artifact_sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    registry = CapabilityPuzzleRegistry((workspace / "puzzles",))
    try:
        refresh = registry.refresh()
    finally:
        registry.close()
    return {
        "refresh": next(iter(refresh.values())),
        "artifact_imported": marker.exists(),
    }


def _leak_scan(root: Path, needles: tuple[str, ...]) -> dict[str, object]:
    matches: list[str] = []
    scanned_files = 0
    scanned_bytes = 0
    encoded = tuple(item.encode("utf-8") for item in needles if item)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ZeroTrustVerificationError(
                "LEAK_SCAN_FAILED",
                "P18 verification artifact could not be scanned",
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


def verify_zero_trust(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Execute the approved P18 profile against production authority code."""

    normalized_approver = " ".join(str(approver).strip().split())
    if not 3 <= len(normalized_approver) <= 160:
        raise ZeroTrustVerificationError(
            "APPROVAL_REQUIRED",
            "P18 approver role is required",
        )
    root = repository_root.expanduser().resolve()
    profile = _load_profile(profile_path)
    host = _host()
    if host["os"] != profile["supported_os"]:
        raise ZeroTrustVerificationError(
            "HOST_UNSUPPORTED",
            "P18 host does not match the approved profile",
        )
    run_id = f"p18-verified-{uuid.uuid4().hex}"
    run_root = output_directory.expanduser().resolve() / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    identity_secret = secrets.token_urlsafe(48)
    private_needle = f"P18-PRIVATE-{secrets.token_hex(24)}"
    current_time = datetime.now(UTC)
    config = profile["workload"]
    identity_root = run_root / "identity"
    database = run_root / "zero-trust.db"
    anchor = _anchor(identity_root, identity_secret)
    record, _ = anchor.enroll()
    authority = ZeroTrustAuthority(
        database,
        attestation_verifier=anchor.verify_attestation,
        principal_state_resolver=_principal_state(anchor),
        clock=lambda: current_time,
        max_clock_skew_seconds=float(config["max_clock_skew_seconds"]),
    )
    authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    payload = {"query": "trust.required", "private_marker": private_needle}
    allowed_envelope = _envelope(anchor, record.brain_id, payload, now=current_time)
    allowed = authority.authorize(allowed_envelope, payload)
    validated = authority.validates(_CAPABILITY, payload, allowed)
    replay = authority.authorize(allowed_envelope, payload)
    payload_mismatch = authority.authorize(
        _envelope(anchor, record.brain_id, payload, now=current_time),
        {"query": "changed"},
    )
    unknown = authority.authorize(
        _envelope(
            anchor,
            f"brain-unknown-{uuid.uuid4()}",
            payload,
            now=current_time,
        ),
        payload,
    )
    wrong_node = authority.authorize(
        _envelope(
            anchor,
            record.brain_id,
            payload,
            now=current_time,
            node_id="p18-spoofed-node",
        ),
        payload,
    )
    unscoped = authority.authorize(
        _envelope(
            anchor,
            record.brain_id,
            payload,
            now=current_time,
            capability_id="filesystem.erase",
        ),
        payload,
    )
    malformed_policy_envelope = replace(
        _envelope(anchor, record.brain_id, payload, now=current_time),
        policy_receipt_sha256="invalid",
    )
    malformed_policy = authority.authorize(malformed_policy_envelope, payload)
    malformed_privacy_envelope = replace(
        _envelope(anchor, record.brain_id, payload, now=current_time),
        privacy_receipt_sha256="invalid",
    )
    malformed_privacy = authority.authorize(malformed_privacy_envelope, payload)
    within_skew = authority.authorize(
        _envelope(
            anchor,
            record.brain_id,
            payload,
            now=current_time + timedelta(seconds=float(config["max_clock_skew_seconds"]) - 1),
        ),
        payload,
    )
    outside_skew = authority.authorize(
        _envelope(
            anchor,
            record.brain_id,
            payload,
            now=current_time + timedelta(seconds=float(config["max_clock_skew_seconds"]) + 1),
        ),
        payload,
    )
    expired = authority.authorize(
        _envelope(
            anchor,
            record.brain_id,
            payload,
            now=current_time - timedelta(minutes=2),
        ),
        payload,
    )

    stale_candidate = _envelope(anchor, record.brain_id, payload, now=current_time)
    rotated_record, _ = anchor.rotate_key()
    stale_key = authority.authorize(stale_candidate, payload)
    current_envelope = _envelope(anchor, record.brain_id, payload, now=current_time)
    current_key = authority.authorize(current_envelope, payload)
    revocation_candidate = _envelope(
        anchor,
        record.brain_id,
        payload,
        now=current_time,
    )

    process = psutil.Process()
    rss_before = process.memory_info().rss
    decision_count_before = authority.decision_count()
    workload_envelopes: list[tuple[TrustEnvelope, dict[str, object]]] = []
    latencies: list[float] = []
    workload_started = time.perf_counter()
    for index in range(int(config["authorizations"])):
        workload_payload: dict[str, object] = {
            "sequence": index,
            "value": hashlib.sha256(f"{run_id}:{index}".encode()).hexdigest(),
        }
        envelope = _envelope(
            anchor,
            record.brain_id,
            workload_payload,
            now=current_time,
        )
        started = time.perf_counter()
        decision = authority.authorize(envelope, workload_payload)
        accepted = authority.validates(_CAPABILITY, workload_payload, decision)
        latencies.append((time.perf_counter() - started) * 1_000)
        if decision.effect is not TrustEffect.ALLOW or accepted is not True:
            raise ZeroTrustVerificationError(
                "WORKLOAD_INVARIANT",
                "P18 workload authorization was not accepted",
            )
        workload_envelopes.append((envelope, workload_payload))
    workload_elapsed = time.perf_counter() - workload_started
    decision_count_after_authorize = authority.decision_count()
    replay_started = time.perf_counter()
    replay_failures = 0
    for envelope, workload_payload in workload_envelopes[: int(config["replay_attempts"])]:
        replay_decision = authority.authorize(envelope, workload_payload)
        if replay_decision.reason_code == TrustFailureCode.REPLAY_DETECTED.value:
            replay_failures += 1
    replay_elapsed = time.perf_counter() - replay_started
    replay_throughput = replay_failures / max(replay_elapsed, 0.000001)
    audit_started = time.perf_counter()
    full_audit_valid = authority.audit_chain_valid()
    full_audit_seconds = time.perf_counter() - audit_started
    status_before_restart = authority.status()
    decision_count_after_replay = authority.decision_count()
    authority.close()
    anchor.close()
    rss_after = process.memory_info().rss

    restarted_anchor = _anchor(identity_root, identity_secret)
    restarted = ZeroTrustAuthority(
        database,
        attestation_verifier=restarted_anchor.verify_attestation,
        principal_state_resolver=_principal_state(restarted_anchor),
        clock=lambda: current_time,
        max_clock_skew_seconds=float(config["max_clock_skew_seconds"]),
    )
    restart_replay = restarted.authorize(current_envelope, payload)
    restarted.revoke_principal(record.brain_id)
    revoked_after_restart = restarted.authorize(revocation_candidate, payload)
    restart_audit = restarted.audit_chain_valid()
    status_after_restart = restarted.status()
    restarted.close()
    restarted_anchor.close()

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    tamper_anchor = _anchor(identity_root, identity_secret)
    envelope_tamper_db = run_root / "tamper-envelope.db"
    shutil.copy2(database, envelope_tamper_db)
    with sqlite3.connect(envelope_tamper_db) as connection:
        row = connection.execute(
            "SELECT decision_id, envelope_json FROM trust_decisions "
            "WHERE effect = 'ALLOW' ORDER BY decision_id LIMIT 1"
        ).fetchone()
        value = json.loads(row[1])
        value["capability_id"] = "filesystem.erase"
        connection.execute(
            "UPDATE trust_decisions SET envelope_json = ? WHERE decision_id = ?",
            (json.dumps(value, sort_keys=True), row[0]),
        )
    envelope_tamper = _expect_corrupt(
        envelope_tamper_db,
        tamper_anchor.verify_attestation,
    )

    acl_tamper_db = run_root / "tamper-acl.db"
    shutil.copy2(database, acl_tamper_db)
    with sqlite3.connect(acl_tamper_db) as connection:
        connection.execute(
            "UPDATE trust_principals SET capabilities_json = ?",
            ('["core.logic.evaluate","filesystem.erase"]',),
        )
    acl_tamper = _expect_corrupt(acl_tamper_db, tamper_anchor.verify_attestation)

    nonce_tamper_db = run_root / "tamper-nonce.db"
    shutil.copy2(database, nonce_tamper_db)
    with sqlite3.connect(nonce_tamper_db) as connection:
        connection.execute("DELETE FROM trust_nonces")
    nonce_tamper = _expect_corrupt(
        nonce_tamper_db,
        tamper_anchor.verify_attestation,
    )

    schema_db = run_root / "unsupported-schema.db"
    schema_authority = ZeroTrustAuthority(
        schema_db,
        attestation_verifier=tamper_anchor.verify_attestation,
    )
    schema_authority.close()
    with sqlite3.connect(schema_db) as connection:
        connection.execute("UPDATE trust_metadata SET value = '999' WHERE key = 'schema_version'")
    schema_failure = _expect_trust_error(
        lambda: ZeroTrustAuthority(
            schema_db,
            attestation_verifier=tamper_anchor.verify_attestation,
        ),
        TrustFailureCode.STORAGE_SCHEMA_UNSUPPORTED,
    )

    clock_value: list[object] = [current_time]
    clock_authority = ZeroTrustAuthority(
        run_root / "clock-failure.db",
        attestation_verifier=tamper_anchor.verify_attestation,
        clock=lambda: clock_value[0],  # type: ignore[return-value]
    )
    clock_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    clock_value[0] = None
    clock_failure = _expect_trust_error(
        lambda: clock_authority.authorize(
            _envelope(tamper_anchor, record.brain_id, payload, now=current_time),
            payload,
        ),
        TrustFailureCode.CLOCK_UNAVAILABLE,
    )
    clock_authority.close()

    def unavailable_state(_: str) -> dict[str, object] | None:
        raise RuntimeError("principal state unavailable")

    state_authority = ZeroTrustAuthority(
        run_root / "state-failure.db",
        attestation_verifier=tamper_anchor.verify_attestation,
        principal_state_resolver=unavailable_state,
        clock=lambda: current_time,
    )
    state_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    state_failure = state_authority.authorize(
        _envelope(tamper_anchor, record.brain_id, payload, now=current_time),
        payload,
    ).reason_code
    state_authority.close()

    def unavailable_verifier(_: object) -> bool:
        raise RuntimeError("attestation verifier unavailable")

    verifier_authority = ZeroTrustAuthority(
        run_root / "verifier-failure.db",
        attestation_verifier=unavailable_verifier,  # type: ignore[arg-type]
        clock=lambda: current_time,
    )
    verifier_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    verifier_failure = verifier_authority.authorize(
        _envelope(tamper_anchor, record.brain_id, payload, now=current_time),
        payload,
    ).reason_code
    verifier_audit = verifier_authority.audit_chain_valid()
    verifier_authority.close()

    payload_authority = ZeroTrustAuthority(
        run_root / "payload-limit.db",
        attestation_verifier=tamper_anchor.verify_attestation,
        clock=lambda: current_time,
        max_payload_bytes=1_024,
    )
    payload_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    large_payload = {"value": "x" * 2_048}
    payload_limit = payload_authority.authorize(
        _envelope(
            tamper_anchor,
            record.brain_id,
            large_payload,
            now=current_time,
        ),
        large_payload,
    ).reason_code
    payload_authority.close()

    lock_db = run_root / "storage-lock.db"
    lock_authority = ZeroTrustAuthority(
        lock_db,
        attestation_verifier=tamper_anchor.verify_attestation,
        clock=lambda: current_time,
        storage_timeout_seconds=0.05,
    )
    lock_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    blocker = sqlite3.connect(lock_db, timeout=1.0)
    blocker.execute("BEGIN IMMEDIATE")
    lock_started = time.perf_counter()
    try:
        storage_failure = _expect_trust_error(
            lambda: lock_authority.authorize(
                _envelope(
                    tamper_anchor,
                    record.brain_id,
                    payload,
                    now=current_time,
                ),
                payload,
            ),
            TrustFailureCode.STORAGE_ERROR,
        )
    finally:
        blocker.rollback()
        blocker.close()
        lock_authority.close()
    lock_elapsed = time.perf_counter() - lock_started

    artifact_probe = _artifact_probe(run_root / "artifact-probe")
    launcher_probe = _launcher_probe(root, run_root / "launcher-probe")
    demo = _run_demo(root, run_root / "production-path-demo")

    dna_db = run_root / "dna-revocation.db"
    dna_authority = ZeroTrustAuthority(
        dna_db,
        attestation_verifier=tamper_anchor.verify_attestation,
        principal_state_resolver=_principal_state(tamper_anchor),
        clock=lambda: current_time,
    )
    dna_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    dna_revocation_candidate = _envelope(
        tamper_anchor,
        record.brain_id,
        payload,
        now=current_time,
    )
    tamper_anchor.revoke("representative P18 DNA revocation drill")
    dna_revoked = dna_authority.authorize(dna_revocation_candidate, payload)
    dna_revoke_audit = dna_authority.audit_chain_valid()
    dna_authority.close()
    tamper_anchor.close()

    sorted_latencies = sorted(latencies)
    p95_index = max(0, int(len(sorted_latencies) * 0.95) - 1)
    storage_bytes = sum(path.stat().st_size for path in run_root.rglob("*") if path.is_file())
    total_decisions = decision_count_after_replay
    workload = {
        "authorizations": int(config["authorizations"]),
        "replay_attempts": int(config["replay_attempts"]),
        "elapsed_seconds": workload_elapsed,
        "mean_latency_ms": sum(latencies) / len(latencies),
        "p95_latency_ms": sorted_latencies[p95_index],
        "replay_elapsed_seconds": replay_elapsed,
        "replay_attempts_per_second": replay_throughput,
        "full_audit_seconds": full_audit_seconds,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "rss_growth_bytes": max(0, rss_after - rss_before),
        "storage_bytes": storage_bytes,
        "storage_bytes_per_decision": storage_bytes / total_decisions,
        "decision_count_before": decision_count_before,
        "decision_count_after_authorize": decision_count_after_authorize,
        "decision_count_after_replay": decision_count_after_replay,
    }
    leak_scan = _leak_scan(run_root, (identity_secret, private_needle))
    demo_result = demo["result"]
    gates = [
        _gate(
            "signed_allow_and_validation",
            allowed.effect is TrustEffect.ALLOW and validated is True,
            {"effect": allowed.effect.value, "validated": validated},
            {"effect": "ALLOW", "validated": True},
        ),
        _gate(
            "persistent_replay_denial",
            replay.reason_code == TrustFailureCode.REPLAY_DETECTED.value
            and restart_replay.reason_code == TrustFailureCode.REPLAY_DETECTED.value,
            {"immediate": replay.reason_code, "restart": restart_replay.reason_code},
            TrustFailureCode.REPLAY_DETECTED.value,
        ),
        _gate(
            "payload_binding",
            payload_mismatch.reason_code == TrustFailureCode.PAYLOAD_MISMATCH.value,
            payload_mismatch.reason_code,
            TrustFailureCode.PAYLOAD_MISMATCH.value,
        ),
        _gate(
            "principal_and_node_identity",
            unknown.reason_code == TrustFailureCode.PRINCIPAL_UNKNOWN.value
            and wrong_node.reason_code == TrustFailureCode.NODE_MISMATCH.value,
            {"unknown": unknown.reason_code, "wrong_node": wrong_node.reason_code},
            {
                "unknown": TrustFailureCode.PRINCIPAL_UNKNOWN.value,
                "wrong_node": TrustFailureCode.NODE_MISMATCH.value,
            },
        ),
        _gate(
            "least_privilege_acl",
            unscoped.reason_code == TrustFailureCode.CAPABILITY_DENIED.value,
            unscoped.reason_code,
            TrustFailureCode.CAPABILITY_DENIED.value,
        ),
        _gate(
            "upstream_receipt_format",
            malformed_policy.reason_code == TrustFailureCode.INVALID_INPUT.value
            and malformed_privacy.reason_code == TrustFailureCode.INVALID_INPUT.value,
            {"policy": malformed_policy.reason_code, "privacy": malformed_privacy.reason_code},
            TrustFailureCode.INVALID_INPUT.value,
        ),
        _gate(
            "bounded_clock_skew",
            within_skew.effect is TrustEffect.ALLOW
            and outside_skew.reason_code == TrustFailureCode.EXPIRED.value,
            {"within": within_skew.effect.value, "outside": outside_skew.reason_code},
            {"within": "ALLOW", "outside": TrustFailureCode.EXPIRED.value},
        ),
        _gate(
            "expired_envelope",
            expired.reason_code == TrustFailureCode.EXPIRED.value,
            expired.reason_code,
            TrustFailureCode.EXPIRED.value,
        ),
        _gate(
            "dna_key_rotation",
            rotated_record.key_version == 2
            and stale_key.reason_code == TrustFailureCode.PRINCIPAL_KEY_STALE.value
            and current_key.effect is TrustEffect.ALLOW,
            {
                "version": rotated_record.key_version,
                "stale": stale_key.reason_code,
                "current": current_key.effect.value,
            },
            {"version": 2, "stale": TrustFailureCode.PRINCIPAL_KEY_STALE.value, "current": "ALLOW"},
        ),
        _gate(
            "registry_revocation_after_restart",
            revoked_after_restart.reason_code == TrustFailureCode.PRINCIPAL_REVOKED.value
            and restart_audit,
            {"reason": revoked_after_restart.reason_code, "audit": restart_audit},
            {"reason": TrustFailureCode.PRINCIPAL_REVOKED.value, "audit": True},
        ),
        _gate(
            "dna_revocation",
            dna_revoked.reason_code == TrustFailureCode.PRINCIPAL_REVOKED.value
            and dna_revoke_audit,
            {"reason": dna_revoked.reason_code, "audit": dna_revoke_audit},
            {"reason": TrustFailureCode.PRINCIPAL_REVOKED.value, "audit": True},
        ),
        _gate(
            "dynamic_principal_state",
            status_before_restart["principal_state_source"] == "dynamic_resolver"
            and status_after_restart["principal_state_source"] == "dynamic_resolver",
            {
                "before": status_before_restart["principal_state_source"],
                "after": status_after_restart["principal_state_source"],
            },
            "dynamic_resolver",
        ),
        _gate(
            "envelope_storage_tamper",
            envelope_tamper == TrustFailureCode.CORRUPT_AUDIT.value,
            envelope_tamper,
            TrustFailureCode.CORRUPT_AUDIT.value,
        ),
        _gate(
            "acl_storage_tamper",
            acl_tamper == TrustFailureCode.CORRUPT_AUDIT.value,
            acl_tamper,
            TrustFailureCode.CORRUPT_AUDIT.value,
        ),
        _gate(
            "nonce_storage_tamper",
            nonce_tamper == TrustFailureCode.CORRUPT_AUDIT.value,
            nonce_tamper,
            TrustFailureCode.CORRUPT_AUDIT.value,
        ),
        _gate(
            "storage_schema",
            schema_failure == TrustFailureCode.STORAGE_SCHEMA_UNSUPPORTED.value,
            schema_failure,
            TrustFailureCode.STORAGE_SCHEMA_UNSUPPORTED.value,
        ),
        _gate(
            "clock_failure",
            clock_failure == TrustFailureCode.CLOCK_UNAVAILABLE.value,
            clock_failure,
            TrustFailureCode.CLOCK_UNAVAILABLE.value,
        ),
        _gate(
            "principal_state_failure",
            state_failure == TrustFailureCode.PRINCIPAL_STATE_UNAVAILABLE.value,
            state_failure,
            TrustFailureCode.PRINCIPAL_STATE_UNAVAILABLE.value,
        ),
        _gate(
            "attestation_failure",
            verifier_failure == TrustFailureCode.ATTESTATION_UNAVAILABLE.value and verifier_audit,
            {"reason": verifier_failure, "audit": verifier_audit},
            {"reason": TrustFailureCode.ATTESTATION_UNAVAILABLE.value, "audit": True},
        ),
        _gate(
            "payload_resource_limit",
            payload_limit == TrustFailureCode.PAYLOAD_TOO_LARGE.value,
            payload_limit,
            TrustFailureCode.PAYLOAD_TOO_LARGE.value,
        ),
        _gate(
            "storage_timeout",
            storage_failure == TrustFailureCode.STORAGE_ERROR.value and lock_elapsed < 1.0,
            {"reason": storage_failure, "elapsed_seconds": lock_elapsed},
            {"reason": TrustFailureCode.STORAGE_ERROR.value, "maximum_seconds": 1.0},
        ),
        _gate(
            "artifact_integrity_before_import",
            artifact_probe["refresh"] == "ARTIFACT_INTEGRITY_FAILED"
            and artifact_probe["artifact_imported"] is False,
            artifact_probe,
            {"refresh": "ARTIFACT_INTEGRITY_FAILED", "artifact_imported": False},
        ),
        _gate(
            "canonical_launcher",
            launcher_probe
            == {
                "ok": True,
                "logic_status": "PROVED",
                "zero_trust_ready": True,
                "principal_state_source": "dynamic_resolver",
                "privacy_ready": True,
            },
            launcher_probe,
            "CANONICAL_DUAL_GATE_READY",
        ),
        _gate(
            "production_path_demo",
            demo_result.get("status") == "VERIFIED_LOCAL"
            and demo_result.get("allow") == "ALLOW"
            and demo_result.get("stale_key") == TrustFailureCode.PRINCIPAL_KEY_STALE.value
            and demo_result.get("revoked_after_restart") == TrustFailureCode.PRINCIPAL_REVOKED.value
            and demo_result.get("audit_chain_valid") is True,
            demo_result,
            "VERIFIED_LOCAL_ROTATION_REPLAY_REVOCATION",
        ),
        _gate(
            "workload_authorizations",
            decision_count_after_authorize - decision_count_before == int(config["authorizations"]),
            decision_count_after_authorize - decision_count_before,
            int(config["authorizations"]),
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
            "replay_throughput",
            replay_failures == int(config["replay_attempts"])
            and replay_throughput >= float(config["min_replay_attempts_per_second"]),
            {"denied": replay_failures, "per_second": replay_throughput},
            {
                "denied": int(config["replay_attempts"]),
                "minimum_per_second": float(config["min_replay_attempts_per_second"]),
            },
        ),
        _gate(
            "full_audit",
            full_audit_valid and full_audit_seconds <= float(config["max_full_audit_seconds"]),
            {"valid": full_audit_valid, "seconds": full_audit_seconds},
            {"valid": True, "maximum_seconds": float(config["max_full_audit_seconds"])},
        ),
        _gate(
            "workload_rss_growth",
            workload["rss_growth_bytes"] <= int(config["max_rss_growth_bytes"]),
            workload["rss_growth_bytes"],
            {"maximum": int(config["max_rss_growth_bytes"])},
        ),
        _gate(
            "storage_per_decision",
            workload["storage_bytes_per_decision"]
            <= float(config["max_storage_bytes_per_decision"]),
            workload["storage_bytes_per_decision"],
            {"maximum": float(config["max_storage_bytes_per_decision"])},
        ),
        _gate("secret_leak_scan", not leak_scan["matches"], leak_scan, {"matches": []}),
    ]
    verified = all(item["passed"] for item in gates)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE" if verified else "FAILED",
        "pillar": "P018",
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
        "authority_lifecycle": {
            "before_restart": status_before_restart,
            "after_restart": status_after_restart,
            "rotation_version": rotated_record.key_version,
            "stale_key_failure": stale_key.reason_code,
            "registry_revocation_failure": revoked_after_restart.reason_code,
            "dna_revocation_failure": dna_revoked.reason_code,
        },
        "failure_paths": {
            "unknown_principal": unknown.reason_code,
            "wrong_node": wrong_node.reason_code,
            "unscoped_capability": unscoped.reason_code,
            "payload_mismatch": payload_mismatch.reason_code,
            "clock": clock_failure,
            "principal_state": state_failure,
            "attestation": verifier_failure,
            "payload_limit": payload_limit,
            "storage": storage_failure,
            "envelope_tamper": envelope_tamper,
            "acl_tamper": acl_tamper,
            "nonce_tamper": nonce_tamper,
            "schema": schema_failure,
        },
        "artifact_integrity": artifact_probe,
        "canonical_launcher": launcher_probe,
        "production_path_demo": demo,
        "leak_scan": leak_scan,
        "workload": workload,
        "gates": gates,
        "limitations": [
            "verified only for the named single-workstation Windows profile",
            "DNA private material uses an encrypted-file keystore, not TPM, HSM, or a remote CA",
            "revocation is verified in one local SQLite authority; distributed propagation and partition behavior remain outside scope",
            "the clock tolerance is tested with an injected local clock; signed distributed time and NTP failure operations remain outside scope",
            "multi-day telemetry, operator alert delivery, cross-node recovery, and live CA rotation remain outside this representative profile",
            "worktree source is bound by digest because verification may precede commit",
        ],
        "rollback": {
            "action": "restore P018 manifest status to INTEGRATED",
            "data": "retain authority and identity databases for forensic review; revoke active principals before disabling the dynamic state resolver",
        },
    }
    report_path = run_root / "verified-zero-trust-report.json"
    raw_report = _canonical(report)
    report_path.write_bytes(raw_report)
    Path(f"{report_path}.sha256").write_text(
        f"{_digest(raw_report)}\n",
        encoding="ascii",
    )
    if not verified:
        failures = ", ".join(item["name"] for item in gates if not item["passed"])
        raise ZeroTrustVerificationError(
            "VERIFICATION_FAILED",
            f"P18 gates failed: {failures}",
        )
    return report_path, report


__all__ = ["ZeroTrustVerificationError", "verify_zero_trust"]
