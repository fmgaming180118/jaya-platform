"""Representative verification runner for Pillar 08: Holographic Memory."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.memory.episodic import EpisodicMemoryStore
from jaya_core.pillars.foundation_capabilities import (
    MEMORY_CAPABILITY_ID,
    FoundationPillarCapabilityService,
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


class HolographicVerificationError(RuntimeError):
    """Stable P08 verification failure."""

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
        raise HolographicVerificationError(
            "PROFILE_NOT_FOUND", f"profile does not exist: {path}"
        )
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HolographicVerificationError(
            "PROFILE_CORRUPT", f"profile JSON is corrupt: {exc}"
        ) from exc
    if not isinstance(profile, dict):
        raise HolographicVerificationError(
            "PROFILE_INVALID", "profile must be a JSON object"
        )
    if set(profile) != _PROFILE_FIELDS:
        raise HolographicVerificationError(
            "PROFILE_SCHEMA_INVALID",
            f"profile fields mismatch: {sorted(profile)} vs {sorted(_PROFILE_FIELDS)}",
        )
    if profile.get("schema_version") != 1:
        raise HolographicVerificationError(
            "PROFILE_SCHEMA_UNSUPPORTED",
            f"unsupported profile schema_version: {profile.get('schema_version')}",
        )
    if not _PROFILE_ID.match(str(profile.get("profile_id", ""))):
        raise HolographicVerificationError(
            "PROFILE_ID_INVALID", "profile_id is invalid"
        )
    return profile


def run_holographic_memory_verification(
    profile_path: Path,
    *,
    base_dir: Path | None = None,
    approver: str = "Audit-Agent-P08",
) -> dict[str, Any]:
    """Execute canonical verification of P08 Holographic Memory."""
    root_dir = base_dir or Path.cwd()
    profile = _load_profile(profile_path)

    system_name = platform.system()
    expected_os = profile["supported_os"]
    if expected_os != "Any" and system_name.lower() != expected_os.lower():
        raise HolographicVerificationError(
            "UNSUPPORTED_OS",
            f"profile requires {expected_os}, running on {system_name}",
        )

    gates: list[dict[str, Any]] = []

    def _record_gate(name: str, passed: bool, actual: Any, expected: Any) -> None:
        gates.append(
            {
                "name": name,
                "passed": bool(passed),
                "actual": actual,
                "expected": expected,
            }
        )
        if not passed:
            raise HolographicVerificationError(
                "GATE_FAILED",
                f"verification gate failed: {name} (actual={actual!r}, expected={expected!r})",
            )

    # 1. Source files check
    manifest: dict[str, str] = {}
    for rel_path in profile["source_files"]:
        abs_path = root_dir / rel_path
        if not abs_path.is_file():
            raise HolographicVerificationError(
                "SOURCE_FILE_MISSING", f"required source file missing: {rel_path}"
            )
        manifest[rel_path] = _digest(abs_path.read_bytes())
    _record_gate(
        "source_manifest_verified",
        len(manifest) == len(profile["source_files"]),
        len(manifest),
        len(profile["source_files"]),
    )

    # Setup temporary directory for verification runs
    temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    temp_dir = Path(temp_dir_obj.name)

    try:
        db_path = temp_dir / "holographic_store.sqlite3"
        pillar_dir = temp_dir / "pillars"
        store = EpisodicMemoryStore(db_path)
        service = FoundationPillarCapabilityService(
            data_dir=pillar_dir,
            episodic_memory=store,
        )

        try:
            # 2. Database schema & version check
            with store._get_connection() as conn:
                version_row = conn.execute(
                    "SELECT value FROM holographic_meta WHERE key='schema_version';"
                ).fetchone()
                schema_version = str(version_row["value"]) if version_row else None
                meta_cols = [
                    r[1]
                    for r in conn.execute("PRAGMA table_info(holographic_metadata);").fetchall()
                ]
            _record_gate(
                "database_schema_and_version_verified",
                schema_version == "1" and "raw_indexes_json" in meta_cols,
                {"version": schema_version, "has_raw_indexes": "raw_indexes_json" in meta_cols},
                {"version": "1", "has_raw_indexes": True},
            )

            # 3. Capability registration & health check
            manifests = {m.capability_id: m for m in service.manifests()}
            cap_manifest = manifests.get(MEMORY_CAPABILITY_ID)
            _record_gate(
                "capability_registration_verified",
                cap_manifest is not None and cap_manifest.health_status == "HEALTHY",
                cap_manifest.health_status if cap_manifest else None,
                "HEALTHY",
            )

            # 4. Append episodic event with provenance and multi-indexes
            source_digest = "sha256:" + hashlib.sha256(b"canonical-evidence-01").hexdigest()
            test_provenance = {
                "source_digest": source_digest,
                "confidence": 0.99,
                "owner_id": "auditor-08",
                "policy": "INTERNAL",
                "observed_at": time.time(),
            }
            test_indexes = {
                "semantic": ["quantum_teleportation", "bell_state"],
                "entity": ["qubit_pair_alpha", "detector_01"],
                "task": ["entangle_qubits"],
                "procedure": ["bell_measurement_v2"],
            }
            append_req = {
                "action": "append",
                "event_id": "event-holo-001",
                "event_type": "QUANTUM_TELEMETRY",
                "session_id": "sess-quantum-main",
                "goal_id": "goal-teleport-01",
                "payload": {"fidelity": 0.994, "loss_db": 0.02},
                "sequence_number": 1,
                "provenance": test_provenance,
                "indexes": test_indexes,
            }
            append_res = service.execute(MEMORY_CAPABILITY_ID, append_req)
            _record_gate(
                "episodic_append_and_provenance_verified",
                append_res.code == "MEMORY_EVENT_APPENDED" and append_res.data.get("inserted") is True,
                append_res.code,
                "MEMORY_EVENT_APPENDED",
            )

            # 5. Multi-index retrieval for all 7 supported index types
            all_types = profile["matrix"]["index_types"]
            index_samples = {
                "session": "sess-quantum-main",
                "goal": "goal-teleport-01",
                "event_type": "quantum_telemetry",
                "semantic": "quantum_teleportation",
                "entity": "detector_01",
                "task": "entangle_qubits",
                "procedure": "bell_measurement_v2",
            }
            indexed_types_ok = True
            for idx_type, idx_val in index_samples.items():
                q_res = service.execute(
                    MEMORY_CAPABILITY_ID,
                    {"action": "query", "index_type": idx_type, "index_value": idx_val},
                )
                events = q_res.data.get("events", [])
                if not events or events[0]["event_id"] != "event-holo-001":
                    indexed_types_ok = False
                    break
                # Check provenance fields attached
                prov = events[0]["provenance"]
                if prov["source_digest"] != source_digest or prov["confidence"] != 0.99:
                    indexed_types_ok = False
                    break

            _record_gate(
                "multi_index_retrieval_all_types_verified",
                indexed_types_ok,
                indexed_types_ok,
                True,
            )

            # 6. Duplicate event idempotency
            dup_res = service.execute(MEMORY_CAPABILITY_ID, append_req)
            _record_gate(
                "duplicate_event_idempotency_verified",
                dup_res.code == "MEMORY_EVENT_DUPLICATE" and dup_res.data.get("inserted") is False,
                dup_res.code,
                "MEMORY_EVENT_DUPLICATE",
            )

            # 7. Memory conflict detection on differing payload/provenance/indexes
            conflict_detected = False
            try:
                service.execute(
                    MEMORY_CAPABILITY_ID,
                    {**append_req, "payload": {"fidelity": 0.50}},
                )
            except LocalPillarError as exc:
                if exc.code == "MEMORY_CONFLICT":
                    conflict_detected = True

            _record_gate(
                "memory_conflict_detection_verified",
                conflict_detected,
                conflict_detected,
                True,
            )

            # 8. Index reconstruction / self-healing after table corruption
            with store._get_connection() as conn:
                conn.execute("DELETE FROM holographic_indexes;")
            empty_res = service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "query", "index_type": "semantic", "index_value": "quantum_teleportation"},
            )
            rebuild_res = service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "rebuild_indexes"},
            )
            restored_res = service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "query", "index_type": "semantic", "index_value": "quantum_teleportation"},
            )
            _record_gate(
                "index_reconstruction_self_healing_verified",
                len(empty_res.data["events"]) == 0
                and rebuild_res.code == "INDEXES_REBUILT"
                and len(restored_res.data["events"]) == 1,
                len(restored_res.data["events"]),
                1,
            )

            # 9. Compaction and retention pruning
            t_now = time.time()
            service.execute(
                MEMORY_CAPABILITY_ID,
                {
                    "action": "append",
                    "event_id": "event-stale-002",
                    "event_type": "CACHE_HIT",
                    "session_id": "sess-transient",
                    "goal_id": "goal-cleanup",
                    "payload": {"temp": True},
                    "sequence_number": 2,
                    "provenance": test_provenance,
                    "indexes": {"task": ["temporary_cache"]},
                },
            )
            store.revoke_holographic("event-stale-002", "pruned by retention", t_now - 500.0)
            compact_res = service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "compact", "retention_seconds": 60.0},
            )
            _record_gate(
                "compaction_retention_prune_verified",
                compact_res.code == "MEMORY_COMPACTED"
                and "event-stale-002" in compact_res.data.get("pruned_event_ids", []),
                compact_res.data.get("pruned_events_count"),
                1,
            )

            # 10. Export portability
            exp_res = service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "export", "session_id": "sess-quantum-main"},
            )
            _record_gate(
                "export_portability_verified",
                exp_res.code == "MEMORY_EXPORTED"
                and exp_res.data.get("count", 0) >= 1
                and exp_res.data["events"][0]["event"]["event_id"] == "event-holo-001",
                exp_res.data.get("count"),
                1,
            )

            # 11. Sovereign privacy deletion
            del_unauth_caught = False
            try:
                service.execute(
                    MEMORY_CAPABILITY_ID,
                    {"action": "delete", "event_id": "event-holo-001", "owner_id": "unauthorized-hacker"},
                )
            except LocalPillarError as exc:
                if exc.code == "MEMORY_NOT_FOUND_OR_DENIED":
                    del_unauth_caught = True

            del_auth_res = service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "delete", "event_id": "event-holo-001", "owner_id": "auditor-08"},
            )
            _record_gate(
                "sovereign_privacy_deletion_verified",
                del_unauth_caught and del_auth_res.code == "MEMORY_EVENT_DELETED",
                del_auth_res.code,
                "MEMORY_EVENT_DELETED",
            )

            # 12. Durability across store restart
            restart_event = {
                "action": "append",
                "event_id": "event-durability-003",
                "event_type": "CHECKPOINT",
                "session_id": "sess-durability",
                "goal_id": "goal-restart",
                "payload": {"state": "committed"},
                "sequence_number": 3,
                "provenance": test_provenance,
                "indexes": {"semantic": ["restart_verification"]},
            }
            service.execute(MEMORY_CAPABILITY_ID, restart_event)
        finally:
            store.close()

        # Reopen store from the same SQLite file
        restarted_store = EpisodicMemoryStore(db_path)
        restarted_service = FoundationPillarCapabilityService(
            data_dir=pillar_dir,
            episodic_memory=restarted_store,
        )
        try:
            read_res = restarted_service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "query", "index_type": "semantic", "index_value": "restart_verification"},
            )
            _record_gate(
                "restart_durability_verified",
                len(read_res.data.get("events", [])) == 1
                and read_res.data["events"][0]["payload"]["state"] == "committed",
                len(read_res.data.get("events", [])),
                1,
            )

            # 13. Resource limits and strict validation
            limits_ok = True
            try:
                restarted_service.execute(
                    MEMORY_CAPABILITY_ID,
                    {
                        "action": "append",
                        "event_id": "oversized-event",
                        "event_type": "OVERSIZED",
                        "session_id": "s",
                        "goal_id": "g",
                        "payload": {"huge": "x" * (300 * 1024)},
                        "sequence_number": 1,
                        "provenance": test_provenance,
                        "indexes": {"task": ["oversized_task"]},
                    },
                )
                limits_ok = False
            except LocalPillarError as exc:
                if exc.code != "RESOURCE_LIMIT":
                    limits_ok = False

            _record_gate(
                "resource_limits_and_validation_verified",
                limits_ok,
                limits_ok,
                True,
            )

            # 14. Cognitive runtime dispatch integration
            runtime = JayaCoreRuntime(
                db_path=str(temp_dir / "cognitive_runtime.sqlite3"),
                local_pillar_data_dir=str(temp_dir / "cognitive_pillars"),
            )
            try:
                rt_manifest = runtime.capability_registry.lookup(MEMORY_CAPABILITY_ID)
                rt_res = runtime.foundation_pillar_capabilities.execute(
                    MEMORY_CAPABILITY_ID,
                    {
                        "action": "append",
                        "event_id": "runtime-integrated-001",
                        "event_type": "COGNITIVE_OBSERVATION",
                        "session_id": "session-cognitive",
                        "goal_id": "goal-runtime",
                        "payload": {"layer": "foundation"},
                        "sequence_number": 1,
                        "provenance": test_provenance,
                        "indexes": {"semantic": ["runtime_integration"]},
                    },
                )
                _record_gate(
                    "runtime_dispatch_verified",
                    rt_manifest is not None and rt_res.code == "MEMORY_EVENT_APPENDED",
                    rt_res.code,
                    "MEMORY_EVENT_APPENDED",
                )
            finally:
                runtime.close()

            # 15. Soak and performance measurement
            soak_cfg = profile["soak"]
            iterations = soak_cfg["iterations"]
            proc = psutil.Process()
            rss_start = proc.memory_info().rss
            t_soak_start = time.perf_counter()

            append_times: list[float] = []
            for i in range(iterations):
                t_app0 = time.perf_counter()
                restarted_service.execute(
                    MEMORY_CAPABILITY_ID,
                    {
                        "action": "append",
                        "event_id": f"soak-evt-{i:05d}",
                        "event_type": "SOAK_TEST",
                        "session_id": f"sess-soak-{i % 10}",
                        "goal_id": f"goal-soak-{i % 5}",
                        "payload": {"iteration": i, "data": f"soak_data_payload_{i}"},
                        "sequence_number": i,
                        "provenance": test_provenance,
                        "indexes": {
                            "semantic": [f"topic_{i % 20}"],
                            "entity": [f"agent_{i % 8}"],
                            "task": [f"task_{i % 4}"],
                        },
                    },
                )
                append_times.append(time.perf_counter() - t_app0)

            t_query0 = time.perf_counter()
            soak_query = restarted_service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "query", "index_type": "entity", "index_value": "agent_3", "limit": 100},
            )
            query_time_ms = (time.perf_counter() - t_query0) * 1000.0

            total_soak_elapsed = time.perf_counter() - t_soak_start
            rss_growth = max(0, proc.memory_info().rss - rss_start)
            mean_append_ms = (sum(append_times) / len(append_times)) * 1000.0
            db_size = db_path.stat().st_size
            bytes_per_record = db_size / (iterations + 10)

            soak_passed = (
                mean_append_ms <= soak_cfg["max_mean_append_latency_ms"]
                and query_time_ms <= soak_cfg["max_query_latency_ms"]
                and rss_growth <= soak_cfg["max_rss_growth_bytes"]
                and bytes_per_record <= soak_cfg["max_database_bytes_per_record"]
                and len(soak_query.data.get("events", [])) > 0
            )

            metrics = {
                "iterations": iterations,
                "elapsed_seconds": round(total_soak_elapsed, 4),
                "mean_append_latency_ms": round(mean_append_ms, 3),
                "query_latency_ms": round(query_time_ms, 3),
                "rss_growth_bytes": rss_growth,
                "database_size_bytes": db_size,
                "bytes_per_record": round(bytes_per_record, 1),
            }

            _record_gate(
                "soak_and_performance_verified",
                soak_passed,
                metrics,
                soak_cfg,
            )

        finally:
            restarted_store.close()

    finally:
        temp_dir_obj.cleanup()

    # Build signature and receipt
    verified_at = datetime.now(UTC).isoformat()
    receipt_data = {
        "schema_version": 1,
        "capability_id": MEMORY_CAPABILITY_ID,
        "profile_id": profile["profile_id"],
        "status": "VERIFIED",
        "verified_at": verified_at,
        "approver": approver,
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "source_manifest": manifest,
        "gates": gates,
        "metrics": metrics,
    }
    receipt_bytes = _canonical_json(receipt_data)
    receipt_data["receipt_digest"] = _digest(receipt_bytes)
    return receipt_data
