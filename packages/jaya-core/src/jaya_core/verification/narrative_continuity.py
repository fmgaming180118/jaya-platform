"""Representative verification for Pillar 31 signed narrative continuity."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import secrets
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from jaya_core.brain_v2.engine.narrative_continuity import (
    DNAAnchorNarrativeSigner,
    NarrativeContinuity,
    NarrativeContinuityError,
    NarrativeFailureCode,
)
from jaya_core.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "soak",
    "source_files",
}


class NarrativeVerificationError(RuntimeError):
    """Stable P31 verification failure carrying the failed boundary."""

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
        raise NarrativeVerificationError("PROFILE_INVALID", "P31 profile is invalid") from exc
    if not isinstance(profile, dict) or set(profile) != _PROFILE_FIELDS:
        raise NarrativeVerificationError("PROFILE_INVALID", "P31 profile fields are invalid")
    soak = profile["soak"]
    if (
        profile["schema_version"] != 1
        or not _PROFILE_ID.fullmatch(str(profile["profile_id"]))
        or not isinstance(profile["scope"], str)
        or not profile["scope"].strip()
        or not isinstance(profile["supported_os"], str)
        or not isinstance(soak, dict)
        or set(soak)
        != {
            "iterations",
            "minimum_elapsed_seconds",
            "max_mean_append_latency_ms",
            "max_full_integrity_seconds",
            "max_rss_growth_bytes",
            "max_database_bytes_per_event",
            "max_package_joules_per_event",
        }
        or not isinstance(profile["source_files"], list)
        or not profile["source_files"]
    ):
        raise NarrativeVerificationError("PROFILE_INVALID", "P31 profile values are invalid")
    iterations = soak["iterations"]
    if type(iterations) is not int or not 1_000 <= iterations <= 100_000:
        raise NarrativeVerificationError("PROFILE_INVALID", "P31 soak iterations invalid")
    return {**profile, "profile_sha256": _digest(raw)}


def _source_bundle_sha256(root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
            raw = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise NarrativeVerificationError(
                "SOURCE_UNAVAILABLE", "P31 verification source bundle is unavailable"
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
            raise NarrativeVerificationError("GIT_UNAVAILABLE", "git version unavailable") from exc
        if completed.returncode != 0:
            raise NarrativeVerificationError("GIT_UNAVAILABLE", "git version unavailable")
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
        "psutil": psutil.__version__,
    }


def _anchor(runtime_root: Path, secret: str, *, enroll: bool) -> DNAAnchor:
    anchor = DNAAnchor(
        runtime_root / "identity",
        EncryptedFileKeyStore(runtime_root / "keystore", secret),
    )
    try:
        if enroll:
            anchor.enroll()
        else:
            anchor.load_identity()
    except Exception:
        anchor.close()
        raise
    return anchor


def _runtime(runtime_root: Path, secret: str, *, enroll: bool) -> JayaCoreRuntime:
    anchor = _anchor(runtime_root, secret, enroll=enroll)
    try:
        return JayaCoreRuntime(
            db_path=runtime_root / "core.sqlite3",
            local_pillar_data_dir=runtime_root / "pillars",
            identity_anchor=anchor,
            identity_required=True,
            narrative_db_path=runtime_root / "narrative.sqlite3",
            narrative_required=True,
            node_id="p31-verification-node",
        )
    except Exception:
        anchor.close()
        raise


def _expect_narrative_error(call: Any, code: NarrativeFailureCode) -> str:
    try:
        call()
    except NarrativeContinuityError as exc:
        if exc.code is not code:
            raise NarrativeVerificationError(
                "FAULT_DRILL_FAILED", "P31 returned an unexpected failure code"
            ) from exc
        return exc.code.value
    raise NarrativeVerificationError("FAULT_DRILL_FAILED", "P31 accepted invalid input")


def _scenario(ledger: NarrativeContinuity) -> dict[str, Any]:
    evidence_alpha = ledger.register_evidence(
        content=b"release=alpha; source=calibration-run-a",
        source_uri="memory://p31/calibration-run-a",
        media_type="text/plain",
    )
    evidence_beta = ledger.register_evidence(
        content=b"release=beta; source=calibration-run-b",
        source_uri="memory://p31/calibration-run-b",
        media_type="text/plain",
    )
    evidence_commitment = ledger.register_evidence(
        content=b"operator requested a signed review commitment",
        source_uri="memory://p31/operator-request",
        media_type="text/plain",
    )
    raw = ledger.remember_turn(
        "Generated prose says release gamma without evidence",
        response_text="release gamma",
        request_id="scenario-raw-turn",
    )
    fact_alpha = ledger.record_verified_fact(
        request_id="scenario-fact-alpha",
        subject="project.release",
        value="alpha",
        evidence_refs=(evidence_alpha,),
    )
    ledger.record_verified_fact(
        request_id="scenario-fact-beta",
        subject="project.release",
        value="beta",
        evidence_refs=(evidence_beta,),
    )
    conflict_snapshot = ledger.snapshot(limit=20, max_chars=20_000)
    commitment = ledger.record_commitment(
        request_id="scenario-commitment",
        commitment_id="commitment:review",
        subject="project.review",
        details={"owner_role": "operator", "state": "requested"},
        evidence_refs=(evidence_commitment,),
    )
    correction = ledger.record_correction(
        request_id="scenario-correction",
        correction_of=fact_alpha.event_id,
        subject="project.release",
        corrected_value="beta",
        evidence_refs=(evidence_beta,),
    )
    inference = ledger.record_inference(
        request_id="scenario-inference",
        subject="project.risk",
        inference={"label": "requires-review", "confidence": 0.75},
        evidence_refs=(evidence_commitment,),
        causation_id=commitment.event_id,
    )
    corrected_snapshot = ledger.snapshot(limit=20, max_chars=20_000)
    rollback = ledger.record_rollback(
        request_id="scenario-rollback",
        target_snapshot_version=int(conflict_snapshot["snapshot_version"]),
        reason="record a logical rollback receipt without deleting later evidence",
    )
    final_snapshot = ledger.snapshot(limit=20, max_chars=20_000)
    duplicate = _expect_narrative_error(
        lambda: ledger.remember_turn("different material", request_id="scenario-raw-turn"),
        NarrativeFailureCode.DUPLICATE_REQUEST,
    )
    missing_evidence = _expect_narrative_error(
        lambda: ledger.record_verified_fact(
            request_id="scenario-unregistered-evidence",
            subject="invalid.fact",
            value="not-accepted",
            evidence_refs=("evidence:" + "0" * 64,),
        ),
        NarrativeFailureCode.INVALID_INPUT,
    )
    nonfinite = _expect_narrative_error(
        lambda: ledger.record_inference(
            request_id="scenario-nonfinite",
            subject="invalid.score",
            inference={"score": float("nan")},
        ),
        NarrativeFailureCode.INVALID_INPUT,
    )
    return {
        "evidence_refs": [evidence_alpha, evidence_beta, evidence_commitment],
        "raw_event_id": raw["event_id"],
        "fact_alpha_event_id": fact_alpha.event_id,
        "commitment_event_id": commitment.event_id,
        "correction_event_id": correction.event_id,
        "inference_event_id": inference.event_id,
        "rollback_event_id": rollback.event_id,
        "conflict_snapshot": conflict_snapshot,
        "corrected_snapshot": corrected_snapshot,
        "final_snapshot": final_snapshot,
        "faults": {
            "duplicate_request": duplicate,
            "unregistered_evidence": missing_evidence,
            "nonfinite_payload": nonfinite,
        },
    }


def _append_only_faults(database: Path) -> dict[str, bool]:
    results = {"update_rejected": False, "delete_rejected": False}
    for name, statement in (
        (
            "update_rejected",
            "UPDATE narrative_events SET subject='tampered' WHERE request_id='scenario-raw-turn'",
        ),
        (
            "delete_rejected",
            "DELETE FROM narrative_events WHERE request_id='scenario-raw-turn'",
        ),
    ):
        with closing(sqlite3.connect(database)) as connection:
            try:
                connection.execute(statement)
                connection.commit()
            except sqlite3.DatabaseError:
                results[name] = True
    return results


def _soak(
    ledger: NarrativeContinuity,
    database: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    iterations = int(config["iterations"])
    meter = WindowsEmiEnergyMeter(timeout_seconds=20.0)
    try:
        energy_start = meter.sample()
    except EnergyMeterError as exc:
        raise NarrativeVerificationError("ENERGY_REQUIRED", "P31 energy counter unavailable") from exc
    process = psutil.Process()
    rss_before = process.memory_info().rss
    bytes_before = database.stat().st_size
    started = time.perf_counter()
    errors = 0
    for index in range(iterations):
        try:
            ledger.remember_turn(
                f"bounded signed soak event {index}",
                runtime_result={"ok": True, "status": "RECORDED"},
                request_id=f"soak-{index}",
            )
        except NarrativeContinuityError:
            errors += 1
    append_elapsed = time.perf_counter() - started
    integrity_started = time.perf_counter()
    integrity_ok = ledger.verify_integrity()
    snapshot = ledger.snapshot(limit=100, max_chars=20_000)
    integrity_elapsed = time.perf_counter() - integrity_started
    rss_after = process.memory_info().rss
    bytes_after = database.stat().st_size
    try:
        energy = meter.measure(energy_start, meter.sample())
    except EnergyMeterError as exc:
        raise NarrativeVerificationError("ENERGY_REQUIRED", "P31 energy measurement failed") from exc
    return {
        "iterations": iterations,
        "errors": errors,
        "append_elapsed_seconds": append_elapsed,
        "mean_append_latency_ms": append_elapsed * 1_000.0 / iterations,
        "appends_per_second": iterations / append_elapsed,
        "full_integrity_seconds": integrity_elapsed,
        "integrity_ok": integrity_ok,
        "snapshot_version": snapshot["snapshot_version"],
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "total_events": snapshot["total_events"],
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "rss_growth_bytes": max(0, rss_after - rss_before),
        "database_bytes_before": bytes_before,
        "database_bytes_after": bytes_after,
        "database_bytes_per_event": max(0, bytes_after - bytes_before) / iterations,
        "energy": {
            **energy.to_dict(),
            "joules_per_event": energy.joules / iterations,
        },
    }


def _corruption_and_migration(
    run_root: Path,
    runtime_root: Path,
    secret: str,
) -> dict[str, Any]:
    source = runtime_root / "narrative.sqlite3"
    corrupt = run_root / "corrupt-narrative.sqlite3"
    with closing(sqlite3.connect(source)) as source_connection, closing(
        sqlite3.connect(corrupt)
    ) as destination_connection:
        source_connection.backup(destination_connection)
    with closing(sqlite3.connect(corrupt)) as connection, connection:
        connection.execute("DROP TRIGGER narrative_events_no_update")
        connection.execute(
            "UPDATE narrative_events SET payload_json=? WHERE request_id=?",
            ('{"tampered":true}', "scenario-raw-turn"),
        )

    anchor = _anchor(runtime_root, secret, enroll=False)
    signer = DNAAnchorNarrativeSigner(anchor)
    corruption_code = _expect_narrative_error(
        lambda: NarrativeContinuity(corrupt, signer),
        NarrativeFailureCode.LEDGER_CORRUPT,
    )
    legacy = run_root / "legacy-narrative.json"
    legacy.write_text(
        json.dumps(
            {
                "events": [
                    {"kind": "turn", "user": "legacy observation one"},
                    {"kind": "feedback", "task": "legacy observation two"},
                ],
                "summary": "This generated summary must never become a verified fact.",
            }
        ),
        encoding="utf-8",
    )
    migrated = NarrativeContinuity(persist_path=legacy, signer=signer)
    try:
        snapshot = migrated.snapshot(limit=10, max_chars=10_000)
        migration = {
            "events": snapshot["total_events"],
            "verified_facts": snapshot["summary"]["verified_facts"],
            "truth_classes": sorted({item["truth_class"] for item in snapshot["recent"]}),
            "legacy_sha256_present": hashlib.sha256(legacy.read_bytes()).hexdigest()
            in json.dumps(snapshot["recent"], sort_keys=True),
        }
    finally:
        migrated.close()
        anchor.close()
    return {"corruption_code": corruption_code, "migration": migration}


def _gate(name: str, passed: bool, actual: Any, limit: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "limit": limit}


def verify_narrative_continuity(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Execute the approved P31 profile through the production runtime and signer."""

    normalized_approver = " ".join(str(approver).strip().split())
    if not 3 <= len(normalized_approver) <= 160:
        raise NarrativeVerificationError("APPROVAL_REQUIRED", "P31 approver role required")
    root = repository_root.expanduser().resolve()
    profile = _load_profile(profile_path)
    host = _host()
    if host["os"] != profile["supported_os"]:
        raise NarrativeVerificationError("HOST_UNSUPPORTED", "P31 host profile differs")
    run_id = f"p31-verified-{uuid.uuid4().hex}"
    run_root = output_directory.expanduser().resolve() / run_id
    runtime_root = run_root / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=False)
    secret = secrets.token_urlsafe(48)

    first = _runtime(runtime_root, secret, enroll=True)
    try:
        ledger = first.narrative_continuity
        if ledger is None:
            raise NarrativeVerificationError("RUNTIME_UNAVAILABLE", "P31 runtime is unavailable")
        capability = first.capability_registry.lookup("core.narrative.context")
        scenario = _scenario(ledger)
        append_only = _append_only_faults(runtime_root / "narrative.sqlite3")
        before_restart = ledger.boot_context()
        status = ledger.status()
        runtime_health = capability.health_status if capability is not None else "MISSING"
    finally:
        first.close()

    restarted = _runtime(runtime_root, secret, enroll=False)
    try:
        ledger = restarted.narrative_continuity
        if ledger is None:
            raise NarrativeVerificationError("RUNTIME_UNAVAILABLE", "P31 restart unavailable")
        after_restart = ledger.boot_context()
        soak = _soak(ledger, runtime_root / "narrative.sqlite3", profile["soak"])
    finally:
        restarted.close()

    drills = _corruption_and_migration(run_root, runtime_root, secret)
    moved_root = run_root / "runtime-closed-probe"
    try:
        runtime_root.replace(moved_root)
        moved_root.replace(runtime_root)
        clean_shutdown = runtime_root.is_dir()
    except OSError:
        clean_shutdown = False

    conflict_summary = scenario["conflict_snapshot"]["summary"]
    corrected_summary = scenario["corrected_snapshot"]["summary"]
    final_summary = scenario["final_snapshot"]["summary"]
    soak_config = profile["soak"]
    gates = [
        _gate("runtime_health", runtime_health == "HEALTHY", runtime_health, "HEALTHY"),
        _gate(
            "signed_append_only",
            status["signed"] is True and status["append_only"] is True,
            {"signed": status["signed"], "append_only": status["append_only"]},
            {"signed": True, "append_only": True},
        ),
        _gate(
            "conflict_detected",
            len(conflict_summary["conflicts"]) == 1,
            conflict_summary["conflicts"],
            {"count": 1},
        ),
        _gate(
            "correction_resolved",
            corrected_summary["conflicts"] == []
            and corrected_summary["verified_facts"][0]["value"] == "beta",
            {
                "conflicts": corrected_summary["conflicts"],
                "verified_facts": corrected_summary["verified_facts"],
            },
            {"conflicts": [], "release": "beta"},
        ),
        _gate(
            "generated_prose_not_fact",
            all(item["value"] != "gamma" for item in final_summary["verified_facts"]),
            final_summary["verified_facts"],
            "no gamma verified fact",
        ),
        _gate(
            "commitment_persisted",
            final_summary["active_commitments"][0]["commitment_id"]
            == "commitment:review",
            final_summary["active_commitments"],
            "commitment:review",
        ),
        _gate(
            "rollback_is_append_only_receipt",
            scenario["rollback_event_id"]
            in {item["event_id"] for item in scenario["final_snapshot"]["recent"]}
            and final_summary["conflicts"] == [],
            {"rollback_event_id": scenario["rollback_event_id"], "conflicts": final_summary["conflicts"]},
            {"receipt_present": True, "history_mutated": False},
        ),
        _gate(
            "restart_snapshot",
            before_restart["snapshot_sha256"] == after_restart["snapshot_sha256"]
            and after_restart["conflicts"] == [],
            {
                "before": before_restart["snapshot_sha256"],
                "after": after_restart["snapshot_sha256"],
                "conflicts": after_restart["conflicts"],
            },
            {"same_digest": True, "conflicts": []},
        ),
        _gate(
            "duplicate_request",
            scenario["faults"]["duplicate_request"] == "DUPLICATE_REQUEST",
            scenario["faults"]["duplicate_request"],
            "DUPLICATE_REQUEST",
        ),
        _gate(
            "unregistered_evidence",
            scenario["faults"]["unregistered_evidence"] == "INVALID_INPUT",
            scenario["faults"]["unregistered_evidence"],
            "INVALID_INPUT",
        ),
        _gate(
            "nonfinite_payload",
            scenario["faults"]["nonfinite_payload"] == "INVALID_INPUT",
            scenario["faults"]["nonfinite_payload"],
            "INVALID_INPUT",
        ),
        _gate("append_only_update", append_only["update_rejected"], append_only["update_rejected"], True),
        _gate("append_only_delete", append_only["delete_rejected"], append_only["delete_rejected"], True),
        _gate(
            "partial_corruption",
            drills["corruption_code"] == "LEDGER_CORRUPT",
            drills["corruption_code"],
            "LEDGER_CORRUPT",
        ),
        _gate(
            "legacy_migration_truth_boundary",
            drills["migration"]["events"] == 2
            and drills["migration"]["verified_facts"] == []
            and drills["migration"]["truth_classes"] == ["RAW_EVENT"]
            and drills["migration"]["legacy_sha256_present"] is True,
            drills["migration"],
            {"events": 2, "verified_facts": [], "truth_classes": ["RAW_EVENT"]},
        ),
        _gate("soak_errors", soak["errors"] == 0, soak["errors"], 0),
        _gate("soak_integrity", soak["integrity_ok"] is True, soak["integrity_ok"], True),
        _gate(
            "soak_duration",
            soak["append_elapsed_seconds"] >= float(soak_config["minimum_elapsed_seconds"]),
            soak["append_elapsed_seconds"],
            {"minimum": float(soak_config["minimum_elapsed_seconds"])},
        ),
        _gate(
            "soak_latency",
            soak["mean_append_latency_ms"] <= float(soak_config["max_mean_append_latency_ms"]),
            soak["mean_append_latency_ms"],
            {"maximum": float(soak_config["max_mean_append_latency_ms"])},
        ),
        _gate(
            "full_integrity_latency",
            soak["full_integrity_seconds"] <= float(soak_config["max_full_integrity_seconds"]),
            soak["full_integrity_seconds"],
            {"maximum": float(soak_config["max_full_integrity_seconds"])},
        ),
        _gate(
            "soak_rss_growth",
            soak["rss_growth_bytes"] <= int(soak_config["max_rss_growth_bytes"]),
            soak["rss_growth_bytes"],
            {"maximum": int(soak_config["max_rss_growth_bytes"])},
        ),
        _gate(
            "storage_growth",
            soak["database_bytes_per_event"] <= float(soak_config["max_database_bytes_per_event"]),
            soak["database_bytes_per_event"],
            {"maximum": float(soak_config["max_database_bytes_per_event"])},
        ),
        _gate(
            "package_energy_per_event",
            soak["energy"]["joules_per_event"] <= float(soak_config["max_package_joules_per_event"]),
            soak["energy"]["joules_per_event"],
            {"maximum": float(soak_config["max_package_joules_per_event"])},
        ),
        _gate("clean_shutdown", clean_shutdown, clean_shutdown, True),
    ]
    verified = all(item["passed"] for item in gates)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE" if verified else "FAILED",
        "pillar": "P031",
        "scope": profile["scope"],
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "verified_at": datetime.now(UTC).isoformat(),
        "approval": {
            "approver": normalized_approver,
            "basis": "explicit repository-owner request to verify remaining pillars",
        },
        "version": {
            **_git_version(root),
            "source_bundle_sha256": _source_bundle_sha256(root, profile["source_files"]),
        },
        "environment": host,
        "runtime": {
            "health": runtime_health,
            "status": status,
            "before_restart": before_restart,
            "after_restart": after_restart,
        },
        "scenario": scenario,
        "fault_drills": {**scenario["faults"], **append_only, **drills},
        "soak": soak,
        "gates": gates,
        "limitations": [
            "verified on one Windows workstation and one local SQLite ledger profile",
            "DNA Anchor uses the encrypted file keystore in this profile, not an HSM or TPM",
            "energy is CPU-package total and is not process-attributed",
            "rollback is an immutable receipt and does not rewrite or delete historical events",
            "semantic truth still depends on registered evidence and upstream validation",
            "worktree source is bound by digest because verification may precede commit",
        ],
        "rollback": {
            "action": "restore P031 manifest status to INTEGRATED",
            "data_impact": "none; signed narrative ledger remains readable",
        },
    }
    report_path = run_root / "verified-narrative-report.json"
    raw_report = _canonical_json(report)
    report_path.write_bytes(raw_report)
    Path(f"{report_path}.sha256").write_text(f"{_digest(raw_report)}\n", encoding="ascii")
    if not verified:
        failures = ", ".join(item["name"] for item in gates if not item["passed"])
        raise NarrativeVerificationError("VERIFICATION_FAILED", f"P31 gates failed: {failures}")
    return report_path, report


__all__ = ["NarrativeVerificationError", "verify_narrative_continuity"]
