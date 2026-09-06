"""Representative verification runner for Pillar 26 Semantic Bridge."""

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
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.semantic_bridge import (
    SEMANTIC_CAPABILITY_ID,
    ModelSemanticProviderAdapter,
    SemanticBridgeCapability,
)

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


class SemanticVerificationError(RuntimeError):
    """Stable P26 verification failure."""

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
        raise SemanticVerificationError(
            "PROFILE_NOT_FOUND", f"profile does not exist: {path}"
        )
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SemanticVerificationError(
            "PROFILE_CORRUPT", f"profile JSON is corrupt: {exc}"
        ) from exc
    if not isinstance(profile, dict):
        raise SemanticVerificationError(
            "PROFILE_INVALID", "profile must be a JSON object"
        )
    if set(profile) != _PROFILE_FIELDS:
        raise SemanticVerificationError(
            "PROFILE_SCHEMA_INVALID",
            f"profile fields mismatch: {sorted(profile)} vs {sorted(_PROFILE_FIELDS)}",
        )
    if profile.get("schema_version") != 1:
        raise SemanticVerificationError(
            "PROFILE_SCHEMA_UNSUPPORTED",
            f"unsupported profile schema_version: {profile.get('schema_version')}",
        )
    if not _PROFILE_ID.match(str(profile.get("profile_id", ""))):
        raise SemanticVerificationError(
            "PROFILE_ID_INVALID", "profile_id is invalid"
        )
    return profile


def run_semantic_bridge_verification(
    profile_path: Path,
    *,
    base_dir: Path | None = None,
    approver: str = "Audit-Agent-P26",
) -> dict[str, Any]:
    """Execute canonical verification of P26 Semantic Bridge."""
    root_dir = base_dir or Path.cwd()
    profile = _load_profile(profile_path)

    system_name = platform.system()
    expected_os = profile["supported_os"]
    if expected_os != "Any" and system_name.lower() != expected_os.lower():
        raise SemanticVerificationError(
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
            raise SemanticVerificationError(
                "GATE_FAILED",
                f"Gate '{name}' failed: expected {expected}, got {actual}",
            )

    with tempfile.TemporaryDirectory(prefix="jaya-p26-verif-", ignore_cleanup_errors=True) as tmp:
        work_path = Path(tmp)
        db_path = work_path / "semantic_verification.sqlite3"
        bridge = SemanticBridgeCapability(db_path)

        # Gate 1: Health check
        _record_gate("health_check", bridge.health_check(), bridge.health_check(), True)

        # Gate 2: Schema & typed entity, relation, claim extraction
        corpus_text = (
            "model:JayaTransformer -trained_on-> dataset:VerifiedTokens and "
            "evaluated_by person:AdaLovelace"
        )
        ingest_res = bridge.execute(
            {
                "action": "ingest",
                "source_ref": "doc:verification-1",
                "content": corpus_text,
                "namespace": "verification",
            }
        )
        _record_gate(
            "method_label",
            ingest_res.data.get("method") == "RULE_BASED_TYPED_GRAMMAR",
            ingest_res.data.get("method"),
            "RULE_BASED_TYPED_GRAMMAR",
        )
        _record_gate(
            "entity_count",
            len(ingest_res.data.get("entities", [])) == 3,
            len(ingest_res.data.get("entities", [])),
            3,
        )
        _record_gate(
            "relation_count",
            len(ingest_res.data.get("relations", [])) == 1,
            len(ingest_res.data.get("relations", [])),
            1,
        )
        _record_gate(
            "claim_count",
            len(ingest_res.data.get("claims", [])) == 1,
            len(ingest_res.data.get("claims", [])),
            1,
        )

        # Gate 3: Epistemic status partitioning
        bridge.execute(
            {
                "action": "ingest",
                "source_ref": "doc:hypo-1",
                "content": "hypothesis: concept:AGI -requires-> concept:Consciousness",
            }
        )
        bridge.execute(
            {
                "action": "ingest",
                "source_ref": "doc:inf-1",
                "content": "implies: model:Transformer -enables-> concept:Planning",
            }
        )
        claims_fact = bridge.execute({"action": "query_claims", "epistemic_status": "FACT"})
        claims_hypo = bridge.execute({"action": "query_claims", "epistemic_status": "UNVERIFIED"})
        claims_inf = bridge.execute({"action": "query_claims", "epistemic_status": "INFERENCE"})

        _record_gate("epistemic_fact", claims_fact.data["count"] >= 1, claims_fact.data["count"], ">=1")
        _record_gate("epistemic_unverified", claims_hypo.data["count"] >= 1, claims_hypo.data["count"], ">=1")
        _record_gate("epistemic_inference", claims_inf.data["count"] >= 1, claims_inf.data["count"], ">=1")

        # Gate 4: Exact citation span and SHA-256 provenance
        prov_res = bridge.execute({"action": "verify_provenance", "source_ref": "doc:verification-1"})
        _record_gate(
            "provenance_verified",
            prov_res.data.get("verified") is True,
            prov_res.data.get("verified"),
            True,
        )

        # Gate 5: Cross-source linking and ambiguity resolution
        bridge.execute(
            {
                "action": "ingest",
                "source_ref": "doc:cross-1",
                "content": "person:Newton discovered concept:Gravity",
            }
        )
        bridge.execute(
            {
                "action": "ingest",
                "source_ref": "doc:cross-2",
                "content": "organization:Newton funded artifact:Telescope",
            }
        )
        ambig_query = bridge.execute({"action": "query", "value": "newton"})
        _record_gate(
            "ambiguity_detected",
            ambig_query.data.get("ambiguous") is True,
            ambig_query.data.get("ambiguous"),
            True,
        )
        _record_gate(
            "candidate_types",
            set(ambig_query.data.get("candidate_types", [])) == {"organization", "person"},
            ambig_query.data.get("candidate_types"),
            ["organization", "person"],
        )

        # Gate 6: Fault Drills
        # 6a. Empty input rejection
        try:
            bridge.execute({"action": "ingest", "source_ref": "doc:empty", "content": ""})
            empty_pass = False
        except LocalPillarError as err:
            empty_pass = err.code == "INVALID_INPUT"
        _record_gate("fault_empty_input", empty_pass, empty_pass, True)

        # 6b. Oversized input rejection (> 1 MiB)
        try:
            bridge.execute({"action": "ingest", "source_ref": "doc:huge", "content": "concept:A " * 200_000})
            huge_pass = False
        except LocalPillarError as err:
            huge_pass = err.code == "RESOURCE_LIMIT"
        _record_gate("fault_oversized_input", huge_pass, huge_pass, True)

        # 6c. Non-text media rejection
        try:
            bridge.execute(
                {
                    "action": "ingest",
                    "source_ref": "doc:media",
                    "content": "model:A",
                    "media_type": "image/png",
                }
            )
            media_pass = False
        except LocalPillarError as err:
            media_pass = err.code == "UNSUPPORTED_MEDIA_TYPE"
        _record_gate("fault_unsupported_media", media_pass, media_pass, True)

        # 6d. Citation tampering detection
        conn = sqlite3.connect(db_path)
        try:
            with conn:
                conn.execute(
                    "UPDATE semantic_mentions SET raw_text='tampered:Text' WHERE source_ref='doc:verification-1'"
                )
        finally:
            conn.close()
        try:
            bridge.execute({"action": "verify_provenance", "source_ref": "doc:verification-1"})
            tamper_detected = False
        except LocalPillarError as err:
            tamper_detected = err.code == "CITATION_MISMATCH"
        _record_gate("fault_citation_mismatch", tamper_detected, tamper_detected, True)

        # 6e. Model provider fail-closed when unconfigured
        adapter = ModelSemanticProviderAdapter(model_path=None)
        try:
            adapter.parse("model:X", "test", "src:fail")
            model_fail_closed = False
        except LocalPillarError as err:
            model_fail_closed = err.code == "PROVIDER_UNAVAILABLE"
        _record_gate("fault_provider_unavailable", model_fail_closed, model_fail_closed, True)

        # Gate 7: Soak & Latency Benchmark
        soak_config = profile["soak"]
        iterations = soak_config["iterations"]
        soak_db = work_path / "soak.sqlite3"
        soak_bridge = SemanticBridgeCapability(soak_db)

        process = psutil.Process()
        rss_start = process.memory_info().rss
        ingest_latencies_ms: list[float] = []

        start_soak = time.perf_counter()
        for i in range(iterations):
            content_str = f"model:Model_{i % 50} -refines-> concept:Task_{i % 25}"
            t0 = time.perf_counter()
            soak_bridge.execute(
                {
                    "action": "ingest",
                    "source_ref": f"soak:doc-{i}",
                    "content": content_str,
                    "namespace": "soak",
                }
            )
            ingest_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        elapsed_soak = time.perf_counter() - start_soak

        # Query latency test
        t_query_0 = time.perf_counter()
        soak_bridge.execute({"action": "query", "value": "model_10", "namespace": "soak"})
        query_latency_ms = (time.perf_counter() - t_query_0) * 1000.0

        rss_end = process.memory_info().rss
        rss_growth = max(0, rss_end - rss_start)
        mean_ingest_latency = sum(ingest_latencies_ms) / len(ingest_latencies_ms)
        db_size_bytes = soak_db.stat().st_size
        bytes_per_record = db_size_bytes / iterations

        _record_gate(
            "soak_mean_ingest_latency",
            mean_ingest_latency <= soak_config["max_mean_ingest_latency_ms"],
            round(mean_ingest_latency, 3),
            {"max": soak_config["max_mean_ingest_latency_ms"]},
        )
        _record_gate(
            "soak_query_latency",
            query_latency_ms <= soak_config["max_query_latency_ms"],
            round(query_latency_ms, 3),
            {"max": soak_config["max_query_latency_ms"]},
        )
        _record_gate(
            "soak_rss_growth",
            rss_growth <= soak_config["max_rss_growth_bytes"],
            rss_growth,
            {"max": soak_config["max_rss_growth_bytes"]},
        )
        _record_gate(
            "soak_database_density",
            bytes_per_record <= soak_config["max_database_bytes_per_record"],
            round(bytes_per_record, 1),
            {"max": soak_config["max_database_bytes_per_record"]},
        )

        # Gate 8: Canonical Vertical Slice Integration (P26 -> P27 -> P08)
        core_db = work_path / "runtime_core.sqlite3"
        pillar_dir = work_path / "pillars"
        runtime = JayaCoreRuntime(db_path=core_db, local_pillar_data_dir=pillar_dir)
        now = time.time()
        try:
            cycle_result = runtime.execute_integrated_memory_cycle(
                {
                    "source_ref": "slice:verification-source",
                    "content": "artifact:TestEvidence -supports-> concept:RobustVerification",
                    "namespace": "verif-slice",
                    "record_id": "temporal-verif-record-1",
                    "event_id": "memory-verif-event-1",
                    "session_id": "session-verif",
                    "goal_id": "goal-verif",
                    "owner_id": "owner-verif",
                    "policy": "internal",
                    "base_score": 0.95,
                    "confidence": 0.9,
                    "observed_at": now,
                    "evaluated_at": now,
                    "decay_rate": 0.01,
                    "sequence_number": 1,
                }
            )
            cycle_ok = (
                cycle_result.get("status") == "INTEGRATED_MEMORY_CYCLE_COMPLETED"
                and "P026" in cycle_result.get("pillars", [])
                and "P027" in cycle_result.get("pillars", [])
                and "P008" in cycle_result.get("pillars", [])
            )
        finally:
            runtime.close()

        _record_gate("vertical_slice_integration", cycle_ok, cycle_ok, True)

    # Calculate source bundle digests
    source_digests: dict[str, str] = {}
    for rel_path in profile["source_files"]:
        abs_path = root_dir / rel_path
        if abs_path.is_file():
            source_digests[rel_path] = _digest(abs_path.read_bytes())
        else:
            source_digests[rel_path] = "MISSING"

    verified = all(g["passed"] for g in gates)
    receipt = {
        "receipt_id": f"p26-verif-{uuid.uuid4().hex[:12]}",
        "profile_id": profile["profile_id"],
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "status": "VERIFIED" if verified else "FAILED",
        "capability_id": SEMANTIC_CAPABILITY_ID,
        "approval": {
            "approver": approver,
            "basis": "explicit repository-owner request to continue pillar verification",
        },
        "metrics": {
            "soak_iterations": iterations,
            "soak_elapsed_seconds": round(elapsed_soak, 3),
            "mean_ingest_latency_ms": round(mean_ingest_latency, 3),
            "query_latency_ms": round(query_latency_ms, 3),
            "rss_growth_bytes": rss_growth,
            "bytes_per_record": round(bytes_per_record, 1),
            "method": "RULE_BASED_TYPED_GRAMMAR",
            "epistemic_statuses_tested": ["FACT", "INFERENCE", "UNVERIFIED"],
        },
        "environment": {
            "os": system_name,
            "python_version": sys.version.split()[0],
            "cpu_count": psutil.cpu_count(logical=True),
        },
        "gates": gates,
        "source_digests": source_digests,
    }
    return receipt


__all__ = ["SemanticVerificationError", "run_semantic_bridge_verification"]
