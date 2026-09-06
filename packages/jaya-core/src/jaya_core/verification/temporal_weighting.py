"""Representative verification runner for Pillar 27 temporal weighting."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars.foundation_capabilities import TEMPORAL_CAPABILITY_ID
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


class TemporalVerificationError(RuntimeError):
    """Stable P27 verification failure carrying the failed boundary."""

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
        raise TemporalVerificationError("PROFILE_INVALID", "P27 profile is invalid") from exc
    if not isinstance(profile, dict) or set(profile) != _PROFILE_FIELDS:
        raise TemporalVerificationError("PROFILE_INVALID", "P27 profile fields are invalid")
    if profile["schema_version"] != 1 or not _PROFILE_ID.fullmatch(
        str(profile["profile_id"])
    ):
        raise TemporalVerificationError("PROFILE_INVALID", "P27 profile contract is invalid")
    matrix = profile["matrix"]
    soak = profile["soak"]
    if (
        not isinstance(profile["scope"], str)
        or not profile["scope"].strip()
        or not isinstance(matrix, dict)
        or set(matrix) != {"domains", "decay_rate"}
        or not isinstance(matrix["domains"], list)
        or len(matrix["domains"]) < 3
        or len(set(matrix["domains"])) != len(matrix["domains"])
        or any(not isinstance(item, str) or not item.strip() for item in matrix["domains"])
        or isinstance(matrix["decay_rate"], bool)
        or not isinstance(matrix["decay_rate"], (int, float))
        or not 0 <= float(matrix["decay_rate"]) <= 100
        or not isinstance(soak, dict)
        or set(soak)
        != {
            "iterations",
            "minimum_elapsed_seconds",
            "max_mean_add_latency_ms",
            "max_rank_latency_ms",
            "max_rss_growth_bytes",
            "max_database_bytes_per_record",
            "max_package_joules_per_record",
        }
        or not isinstance(profile["source_files"], list)
        or not profile["source_files"]
    ):
        raise TemporalVerificationError("PROFILE_INVALID", "P27 profile values are invalid")
    return {**profile, "profile_sha256": _digest(raw)}


def _source_bundle_sha256(root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
            raw = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise TemporalVerificationError(
                "SOURCE_UNAVAILABLE", "P27 verification source bundle is unavailable"
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
            raise TemporalVerificationError(
                "GIT_UNAVAILABLE", "git version unavailable"
            ) from exc
        if completed.returncode != 0:
            raise TemporalVerificationError("GIT_UNAVAILABLE", "git version unavailable")
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
        "psutil": psutil.__version__,
    }


def _runtime(root: Path) -> JayaCoreRuntime:
    return JayaCoreRuntime(
        db_path=root / "core.sqlite3",
        local_pillar_data_dir=root / "pillars",
        node_id=f"{root.name}-node",
    )


def _expect_error(
    runtime: JayaCoreRuntime, request: dict[str, Any], code: str
) -> dict[str, Any]:
    try:
        runtime.execute_local_pillar(TEMPORAL_CAPABILITY_ID, request)
    except LocalPillarError as exc:
        if exc.code != code:
            raise TemporalVerificationError(
                "FAULT_DRILL_FAILED", "P27 returned an unexpected failure code"
            ) from exc
        return exc.to_dict()
    raise TemporalVerificationError("FAULT_DRILL_FAILED", "P27 accepted invalid input")


def _evidence_payload(domain: str, version: int) -> dict[str, Any]:
    material = {"domain": domain, "version": version}
    return {**material, "evidence_digest": _digest(_canonical_json(material))}


def _matrix(
    runtime: JayaCoreRuntime, profile: dict[str, Any], evaluated_at: float
) -> dict[str, Any]:
    decay_rate = float(profile["matrix"]["decay_rate"])
    domains = list(profile["matrix"]["domains"])
    requests: dict[str, dict[str, Any]] = {}
    policy_requests: dict[str, dict[str, Any]] = {}
    for index, domain in enumerate(domains):
        old_id = f"{domain}-v1"
        current_id = f"{domain}-v2"
        expired_id = f"{domain}-expired"
        old_request = {
            "action": "add",
            "record_id": old_id,
            "source_ref": f"evidence:{domain}:v1",
            "base_score": 0.95,
            "observed_at": evaluated_at - 7_200 - index,
            "valid_until": evaluated_at + 3_600,
            "retention_until": evaluated_at + 7_200,
            "clock_source": "EXTERNAL_SIGNED",
            "payload": _evidence_payload(domain, 1),
        }
        current_request = {
            "action": "add",
            "record_id": current_id,
            "source_ref": f"evidence:{domain}:v2",
            "base_score": 0.8,
            "observed_at": evaluated_at - 60 - index,
            "supersedes": old_id,
            "valid_until": evaluated_at + 3_600,
            "retention_until": evaluated_at + 7_200,
            "clock_source": "EXTERNAL_SIGNED",
            "payload": _evidence_payload(domain, 2),
        }
        expired_request = {
            "action": "add",
            "record_id": expired_id,
            "source_ref": f"evidence:{domain}:expired",
            "base_score": 1.0,
            "observed_at": evaluated_at - 3_600 - index,
            "valid_until": evaluated_at - 1_800,
            "retention_until": evaluated_at - 30,
            "clock_source": "SOURCE_REPORTED",
            "payload": _evidence_payload(domain, 0),
        }
        hold_request = {
            "action": "set_legal_hold",
            "event_id": f"hold-{expired_id}",
            "record_id": expired_id,
            "enabled": True,
            "reason": "retain expired evidence for representative verification",
            "changed_at": evaluated_at - 10,
        }
        for temporal_request in (old_request, current_request, expired_request):
            runtime.execute_local_pillar(TEMPORAL_CAPABILITY_ID, temporal_request)
        runtime.execute_local_pillar(TEMPORAL_CAPABILITY_ID, hold_request)
        requests[domain] = current_request
        policy_requests[domain] = hold_request

    ranked = runtime.execute_local_pillar(
        TEMPORAL_CAPABILITY_ID,
        {"action": "rank", "decay_rate": decay_rate, "now": evaluated_at},
    )
    history = runtime.execute_local_pillar(
        TEMPORAL_CAPABILITY_ID,
        {"action": "history", "as_of": evaluated_at, "limit": 1_000},
    )
    historical = runtime.execute_local_pillar(
        TEMPORAL_CAPABILITY_ID,
        {"action": "history", "as_of": evaluated_at - 120, "limit": 1_000},
    )
    duplicate = runtime.execute_local_pillar(
        TEMPORAL_CAPABILITY_ID, requests[domains[0]]
    )
    policy_duplicate = runtime.execute_local_pillar(
        TEMPORAL_CAPABILITY_ID, policy_requests[domains[0]]
    )
    fault_drills = {
        "record_conflict": _expect_error(
            runtime,
            {**requests[domains[0]], "base_score": 0.7},
            "TEMPORAL_CONFLICT",
        ),
        "policy_conflict": _expect_error(
            runtime,
            {**policy_requests[domains[0]], "enabled": False},
            "TEMPORAL_CONFLICT",
        ),
        "missing_parent": _expect_error(
            runtime,
            {
                "action": "add",
                "record_id": "missing-parent-child",
                "source_ref": "evidence:missing-parent",
                "base_score": 0.5,
                "observed_at": evaluated_at,
                "supersedes": "absent-parent",
                "payload": {"evidence_digest": _digest(b"missing-parent")},
            },
            "SUPERSESSION_NOT_FOUND",
        ),
        "future_clock": _expect_error(
            runtime,
            {
                "action": "add",
                "record_id": "future-clock",
                "source_ref": "evidence:future-clock",
                "base_score": 0.5,
                "observed_at": time.time() + 600,
                "payload": {"evidence_digest": _digest(b"future-clock")},
            },
            "CLOCK_SKEW",
        ),
        "invalid_window": _expect_error(
            runtime,
            {
                "action": "add",
                "record_id": "invalid-window",
                "source_ref": "evidence:invalid-window",
                "base_score": 0.5,
                "observed_at": evaluated_at,
                "valid_until": evaluated_at - 1,
                "payload": {"evidence_digest": _digest(b"invalid-window")},
            },
            "INVALID_INPUT",
        ),
        "nonfinite": _expect_error(
            runtime,
            {
                "action": "add",
                "record_id": "nonfinite-score",
                "source_ref": "evidence:nonfinite",
                "base_score": "nan",
                "observed_at": evaluated_at,
                "payload": {"evidence_digest": _digest(b"nonfinite")},
            },
            "INVALID_INPUT",
        ),
        "unknown_field": _expect_error(
            runtime,
            {"action": "history", "unexpected": True},
            "UNKNOWN_FIELD",
        ),
    }
    return {
        "domains": domains,
        "evaluated_at": evaluated_at,
        "decay_rate": decay_rate,
        "ranked": ranked.to_dict(),
        "history": history.to_dict(),
        "historical": historical.to_dict(),
        "duplicate": duplicate.to_dict(),
        "policy_duplicate": policy_duplicate.to_dict(),
        "fault_drills": fault_drills,
    }


def _migration_drill(root: Path) -> dict[str, Any]:
    runtime_root = root / "migration-runtime"
    pillar_root = runtime_root / "pillars"
    pillar_root.mkdir(parents=True, exist_ok=False)
    database = pillar_root / "temporal_weighting.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE temporal_records(
                record_id TEXT PRIMARY KEY,
                source_ref TEXT NOT NULL,
                base_score REAL NOT NULL,
                observed_at REAL NOT NULL,
                supersedes TEXT,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY(supersedes) REFERENCES temporal_records(record_id)
            );
            INSERT INTO temporal_records VALUES(
                'legacy-record','evidence:legacy',0.5,1.0,NULL,
                '{"evidence_digest":"sha256:legacy"}',1.0
            );
            """
        )
    runtime = _runtime(runtime_root)
    try:
        history = runtime.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID, {"action": "history", "as_of": 2.0}
        )
    finally:
        runtime.close()
    record = history.data["records"][0]
    with sqlite3.connect(database) as connection:
        schema_version = connection.execute(
            "SELECT value FROM temporal_meta WHERE key='schema_version'"
        ).fetchone()[0]
    return {
        "record_id": record["record_id"],
        "clock_source": record["clock_source"],
        "schema_version": schema_version,
    }


def _corruption_drill(root: Path, evaluated_at: float) -> dict[str, Any]:
    runtime_root = root / "corruption-runtime"
    runtime = _runtime(runtime_root)
    request = {
        "action": "add",
        "record_id": "corrupt-record",
        "source_ref": "evidence:corrupt",
        "base_score": 0.5,
        "observed_at": evaluated_at,
        "payload": {"evidence_digest": _digest(b"corrupt")},
    }
    try:
        runtime.execute_local_pillar(TEMPORAL_CAPABILITY_ID, request)
        database = runtime_root / "pillars" / "temporal_weighting.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE temporal_records SET payload_json='invalid-json' "
                "WHERE record_id='corrupt-record'"
            )
        return _expect_error(
            runtime,
            {"action": "rank", "decay_rate": 0.1, "now": evaluated_at},
            "STORAGE_CORRUPT",
        )
    finally:
        runtime.close()


def _soak(root: Path, config: dict[str, Any], evaluated_at: float) -> dict[str, Any]:
    iterations = int(config["iterations"])
    if not 1_000 <= iterations <= 100_000:
        raise TemporalVerificationError("PROFILE_INVALID", "P27 soak iterations invalid")
    runtime_root = root / "soak-runtime"
    runtime = _runtime(runtime_root)
    meter = WindowsEmiEnergyMeter(timeout_seconds=20.0)
    process = psutil.Process()
    try:
        energy_start = meter.sample()
    except EnergyMeterError as exc:
        runtime.close()
        raise TemporalVerificationError(
            "ENERGY_REQUIRED", "P27 energy counter unavailable"
        ) from exc
    rss_before = process.memory_info().rss
    started = time.perf_counter()
    errors = 0
    for index in range(iterations):
        try:
            runtime.execute_local_pillar(
                TEMPORAL_CAPABILITY_ID,
                {
                    "action": "add",
                    "record_id": f"soak-{index}",
                    "source_ref": f"soak:evidence:{index}",
                    "base_score": (index % 101) / 100,
                    "observed_at": evaluated_at - (index % 3_600),
                    "retention_until": evaluated_at + 86_400,
                    "payload": {
                        "sequence": index,
                        "evidence_digest": _digest(str(index).encode("ascii")),
                    },
                },
            )
        except LocalPillarError:
            errors += 1
    elapsed = time.perf_counter() - started
    rank_started = time.perf_counter()
    ranked = runtime.execute_local_pillar(
        TEMPORAL_CAPABILITY_ID,
        {
            "action": "rank",
            "decay_rate": 0.05,
            "now": evaluated_at,
            "limit": 1_000,
            "timeout_seconds": 30.0,
        },
    )
    rank_latency_ms = (time.perf_counter() - rank_started) * 1_000.0
    history = runtime.execute_local_pillar(
        TEMPORAL_CAPABILITY_ID,
        {
            "action": "history",
            "as_of": evaluated_at,
            "limit": 1_000,
            "timeout_seconds": 30.0,
        },
    )
    timeout = _expect_error(
        runtime,
        {
            "action": "history",
            "as_of": evaluated_at,
            "timeout_seconds": 0.000001,
        },
        "TIMEOUT",
    )
    rss_after = process.memory_info().rss
    try:
        energy = meter.measure(energy_start, meter.sample())
    except EnergyMeterError as exc:
        runtime.close()
        raise TemporalVerificationError(
            "ENERGY_REQUIRED", "P27 energy measurement failed"
        ) from exc
    runtime.close()
    database = runtime_root / "pillars" / "temporal_weighting.sqlite3"
    database_bytes = sum(
        path.stat().st_size
        for path in database.parent.glob(f"{database.name}*")
        if path.is_file()
    )
    closed_probe = database.with_name(f"{database.name}.closed-probe")
    clean_shutdown = False
    for _ in range(20):
        try:
            if closed_probe.exists() and not database.exists():
                closed_probe.replace(database)
            database.replace(closed_probe)
            closed_probe.replace(database)
        except PermissionError:
            time.sleep(0.05)
            continue
        clean_shutdown = True
        break
    return {
        "iterations": iterations,
        "errors": errors,
        "elapsed_seconds": elapsed,
        "mean_add_latency_ms": elapsed * 1_000.0 / iterations,
        "rank_latency_ms": rank_latency_ms,
        "ranked_records": len(ranked.data["records"]),
        "history_records": len(history.data["records"]),
        "history_has_more": history.data["has_more"],
        "timeout": timeout,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "rss_growth_bytes": max(0, rss_after - rss_before),
        "database_bytes": database_bytes,
        "database_bytes_per_record": database_bytes / iterations,
        "clean_shutdown": clean_shutdown,
        "energy": {
            **energy.to_dict(),
            "joules_per_record": energy.joules / iterations,
        },
    }


def _gate(name: str, passed: bool, actual: Any, limit: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "limit": limit}


def verify_temporal_weighting(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Execute the approved P27 profile through the production Core runtime."""

    normalized_approver = " ".join(str(approver).strip().split())
    if not 3 <= len(normalized_approver) <= 160:
        raise TemporalVerificationError("APPROVAL_REQUIRED", "P27 approver role required")
    root = repository_root.expanduser().resolve()
    profile = _load_profile(profile_path)
    host = _host()
    if host["os"] != profile["supported_os"]:
        raise TemporalVerificationError("HOST_UNSUPPORTED", "P27 host profile differs")
    run_id = f"p27-verified-{uuid.uuid4().hex}"
    run_root = output_directory.expanduser().resolve() / run_id
    runtime_root = run_root / "functional-runtime"
    runtime_root.mkdir(parents=True, exist_ok=False)
    evaluated_at = time.time()
    runtime = _runtime(runtime_root)
    try:
        matrix = _matrix(runtime, profile, evaluated_at)
    finally:
        runtime.close()

    restarted = _runtime(runtime_root)
    try:
        restart_rank = restarted.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID,
            {
                "action": "rank",
                "decay_rate": matrix["decay_rate"],
                "now": evaluated_at,
            },
        )
        restart_history = restarted.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID,
            {"action": "history", "as_of": evaluated_at, "limit": 1_000},
        )
    finally:
        restarted.close()
    migration = _migration_drill(run_root)
    corruption = _corruption_drill(run_root, evaluated_at)
    soak = _soak(run_root, profile["soak"], evaluated_at)

    domains = matrix["domains"]
    ranked_records = matrix["ranked"]["data"]["records"]
    ranked_ids = {item["record_id"] for item in ranked_records}
    history_records = matrix["history"]["data"]["records"]
    history_by_id = {item["record_id"]: item for item in history_records}
    historical_by_id = {
        item["record_id"]: item for item in matrix["historical"]["data"]["records"]
    }
    current_ids = {f"{domain}-v2" for domain in domains}
    old_ids = {f"{domain}-v1" for domain in domains}
    expired_ids = {f"{domain}-expired" for domain in domains}
    evidence_bound = all(
        isinstance(item["payload"].get("evidence_digest"), str)
        and item["payload"]["evidence_digest"].startswith("sha256:")
        for item in history_records
    )
    historical_old_active = all(
        historical_by_id[f"{domain}-v1"]["status"] == "ACTIVE"
        and f"{domain}-v2" not in historical_by_id
        for domain in domains
    )
    faults = matrix["fault_drills"]
    soak_config = profile["soak"]
    gates = [
        _gate("domain_matrix", len(domains) >= 3, len(domains), {"minimum": 3}),
        _gate("new_facts_ranked", ranked_ids == current_ids, sorted(ranked_ids), sorted(current_ids)),
        _gate("old_facts_superseded", all(history_by_id[item]["status"] == "SUPERSEDED" for item in old_ids), sorted(old_ids), "SUPERSEDED"),
        _gate("expired_facts_excluded", ranked_ids.isdisjoint(expired_ids), sorted(ranked_ids & expired_ids), []),
        _gate("expired_history_retained", all(history_by_id[item]["status"] == "EXPIRED" for item in expired_ids), sorted(expired_ids), "EXPIRED"),
        _gate("legal_hold_audited", all(history_by_id[item]["retention_status"] == "LEGAL_HOLD" for item in expired_ids), sorted(expired_ids), "LEGAL_HOLD"),
        _gate("explicit_as_of", historical_old_active, historical_old_active, True),
        _gate("evidence_binding", evidence_bound, evidence_bound, True),
        _gate("record_idempotency", matrix["duplicate"]["code"] == "TEMPORAL_RECORD_DUPLICATE", matrix["duplicate"]["code"], "TEMPORAL_RECORD_DUPLICATE"),
        _gate("policy_idempotency", matrix["policy_duplicate"]["code"] == "TEMPORAL_POLICY_EVENT_DUPLICATE", matrix["policy_duplicate"]["code"], "TEMPORAL_POLICY_EVENT_DUPLICATE"),
        *[
            _gate(name, value["code"] == expected, value["code"], expected)
            for name, value, expected in (
                ("record_conflict", faults["record_conflict"], "TEMPORAL_CONFLICT"),
                ("policy_conflict", faults["policy_conflict"], "TEMPORAL_CONFLICT"),
                ("missing_parent", faults["missing_parent"], "SUPERSESSION_NOT_FOUND"),
                ("future_clock", faults["future_clock"], "CLOCK_SKEW"),
                ("invalid_window", faults["invalid_window"], "INVALID_INPUT"),
                ("nonfinite", faults["nonfinite"], "INVALID_INPUT"),
                ("unknown_field", faults["unknown_field"], "UNKNOWN_FIELD"),
            )
        ],
        _gate("restart_rank", restart_rank.to_dict() == matrix["ranked"], restart_rank.to_dict() == matrix["ranked"], True),
        _gate("restart_history", restart_history.to_dict() == matrix["history"], restart_history.to_dict() == matrix["history"], True),
        _gate("v1_migration", migration == {"record_id": "legacy-record", "clock_source": "SYSTEM_UTC", "schema_version": "2"}, migration, "schema 2 with legacy record"),
        _gate("corruption_detection", corruption["code"] == "STORAGE_CORRUPT", corruption["code"], "STORAGE_CORRUPT"),
        _gate("deadline_enforcement", soak["timeout"]["code"] == "TIMEOUT", soak["timeout"]["code"], "TIMEOUT"),
        _gate("soak_errors", soak["errors"] == 0, soak["errors"], 0),
        _gate("soak_duration", soak["elapsed_seconds"] >= float(soak_config["minimum_elapsed_seconds"]), soak["elapsed_seconds"], {"minimum": float(soak_config["minimum_elapsed_seconds"])}),
        _gate("soak_add_latency", soak["mean_add_latency_ms"] <= float(soak_config["max_mean_add_latency_ms"]), soak["mean_add_latency_ms"], {"maximum": float(soak_config["max_mean_add_latency_ms"])}),
        _gate("rank_latency", soak["rank_latency_ms"] <= float(soak_config["max_rank_latency_ms"]), soak["rank_latency_ms"], {"maximum": float(soak_config["max_rank_latency_ms"])}),
        _gate("soak_rss_growth", soak["rss_growth_bytes"] <= int(soak_config["max_rss_growth_bytes"]), soak["rss_growth_bytes"], {"maximum": int(soak_config["max_rss_growth_bytes"])}),
        _gate("database_density", soak["database_bytes_per_record"] <= float(soak_config["max_database_bytes_per_record"]), soak["database_bytes_per_record"], {"maximum": float(soak_config["max_database_bytes_per_record"])}),
        _gate("package_energy_per_record", soak["energy"]["joules_per_record"] <= float(soak_config["max_package_joules_per_record"]), soak["energy"]["joules_per_record"], {"maximum": float(soak_config["max_package_joules_per_record"])}),
        _gate("clean_shutdown", soak["clean_shutdown"], soak["clean_shutdown"], True),
    ]
    verified = all(item["passed"] for item in gates)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE" if verified else "FAILED",
        "pillar": "P027",
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
        "matrix": matrix,
        "restart": {
            "rank": restart_rank.to_dict(),
            "history": restart_history.to_dict(),
        },
        "migration": migration,
        "corruption_drill": corruption,
        "soak": soak,
        "gates": gates,
        "limitations": [
            "verified on one Windows workstation with a local SQLite temporal store",
            "EXTERNAL_SIGNED identifies caller-declared clock provenance; signature validation belongs to the evidence provider",
            "retention eligibility is reported but physical deletion is intentionally outside this capability",
            "package energy includes the complete CPU package and is not process-attributed",
            "worktree source is bound by digest because verification may precede commit",
        ],
        "rollback": {
            "action": "restore P027 manifest status to INTEGRATED",
            "state_impact": "schema additions are non-destructive; keep temporal history and policy events",
        },
    }
    report_path = run_root / "verified-temporal-weighting-report.json"
    raw_report = _canonical_json(report)
    report_path.write_bytes(raw_report)
    Path(f"{report_path}.sha256").write_text(f"{_digest(raw_report)}\n", encoding="ascii")
    if not verified:
        failures = ", ".join(item["name"] for item in gates if not item["passed"])
        raise TemporalVerificationError("VERIFICATION_FAILED", f"P27 gates failed: {failures}")
    return report_path, report


__all__ = ["TemporalVerificationError", "verify_temporal_weighting"]
