"""Implemented-local foundation capabilities for the remaining JAYA pillars."""

from __future__ import annotations

import json
import math
import platform
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np

from jaya_core.capabilities.manifest import CapabilityManifest
from jaya_core.memory.events import MemoryEvent

from .activation_sparsity import SPARSE_CAPABILITY_ID, ActivationSparsityCapability
from .local_capabilities import LocalPillarError, LocalPillarResult
from .semantic_bridge import SEMANTIC_CAPABILITY_ID, SemanticBridgeCapability

MEMORY_CAPABILITY_ID = "core.memory.holographic"
SANDBOX_CAPABILITY_ID = "core.sandbox.expression"
TEMPORAL_CAPABILITY_ID = "core.memory.temporal"
INTEGRATED_MEMORY_PILLARS = ("P008", "P026", "P027")
FOUNDATION_CAPABILITY_IDS = frozenset(
    {
        MEMORY_CAPABILITY_ID,
        SANDBOX_CAPABILITY_ID,
        SEMANTIC_CAPABILITY_ID,
        TEMPORAL_CAPABILITY_ID,
        SPARSE_CAPABILITY_ID,
    }
)


@contextmanager
def _connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path, timeout=5.0)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _strict(
    request: Mapping[str, Any],
    *,
    allowed: frozenset[str],
    required: frozenset[str],
) -> None:
    unknown = set(request) - allowed
    missing = required - set(request)
    if unknown:
        raise LocalPillarError("UNKNOWN_FIELD", f"unsupported fields: {', '.join(sorted(unknown))}")
    if missing:
        raise LocalPillarError("MISSING_FIELD", f"required fields: {', '.join(sorted(missing))}")


def _text(value: object, field: str, maximum: int = 4_096) -> str:
    if not isinstance(value, str):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be text")
    normalized = " ".join(value.strip().split())
    if not 1 <= len(normalized) <= maximum:
        raise LocalPillarError("INVALID_INPUT", f"{field} must contain 1-{maximum} characters")
    return normalized


class HolographicMemoryCapability:
    """Strict runtime facade over Core's canonical episodic SQLite store."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def health_check(self) -> bool:
        return str(getattr(self.store, "db_path", ":memory:")) != ":memory:" and bool(
            self.store.health_check()
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        action = request.get("action")
        if action == "append":
            _strict(
                request,
                allowed=frozenset(
                    {
                        "action",
                        "event_id",
                        "event_type",
                        "session_id",
                        "goal_id",
                        "payload",
                        "provenance",
                        "indexes",
                        "node_id",
                        "sequence_number",
                    }
                ),
                required=frozenset(
                    {
                        "action",
                        "event_id",
                        "event_type",
                        "session_id",
                        "goal_id",
                        "payload",
                        "provenance",
                        "indexes",
                    }
                ),
            )
            payload = request["payload"]
            if not isinstance(payload, Mapping):
                raise LocalPillarError("INVALID_INPUT", "payload must be an object")
            serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            if len(serialized.encode("utf-8")) > 256 * 1024:
                raise LocalPillarError("RESOURCE_LIMIT", "memory payload exceeds 256 KiB")
            sequence = request.get("sequence_number", 0)
            if type(sequence) is not int or not 0 <= sequence <= 2**63 - 1:
                raise LocalPillarError("INVALID_INPUT", "sequence_number is invalid")
            provenance = request["provenance"]
            if not isinstance(provenance, Mapping):
                raise LocalPillarError("INVALID_INPUT", "provenance must be an object")
            _strict(
                provenance,
                allowed=frozenset(
                    {"source_digest", "confidence", "owner_id", "policy", "observed_at"}
                ),
                required=frozenset(
                    {"source_digest", "confidence", "owner_id", "policy", "observed_at"}
                ),
            )
            source_digest = _text(provenance["source_digest"], "source_digest", 80)
            if re.fullmatch(r"sha256:[0-9a-fA-F]{64}", source_digest) is None:
                raise LocalPillarError("INVALID_INPUT", "source_digest must be a SHA-256 digest")
            try:
                confidence = float(provenance["confidence"])
                observed_at = float(provenance["observed_at"])
            except (TypeError, ValueError) as exc:
                raise LocalPillarError(
                    "INVALID_INPUT", "confidence and observed_at must be numeric"
                ) from exc
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise LocalPillarError("INVALID_INPUT", "confidence must be finite and 0-1")
            if not math.isfinite(observed_at) or observed_at > time.time() + 300:
                raise LocalPillarError("CLOCK_SKEW", "observed_at exceeds allowed clock skew")
            owner_id = _text(provenance["owner_id"], "owner_id", 128)
            policy = _text(provenance["policy"], "policy", 32).upper()
            if policy not in {"PRIVATE", "RESTRICTED", "INTERNAL", "PUBLIC"}:
                raise LocalPillarError("INVALID_INPUT", "memory policy is unsupported")
            raw_indexes = request["indexes"]
            if not isinstance(raw_indexes, Mapping):
                raise LocalPillarError("INVALID_INPUT", "indexes must be an object")
            unknown_index = set(raw_indexes) - {"semantic", "entity", "task", "procedure"}
            if unknown_index:
                raise LocalPillarError("INVALID_INPUT", "memory index type is unsupported")
            indexes: dict[str, list[str]] = {
                "session": [_text(request["session_id"], "session_id", 128).casefold()],
                "goal": [_text(request["goal_id"], "goal_id", 128).casefold()],
                "event_type": [_text(request["event_type"], "event_type", 128).casefold()],
            }
            for index_type, raw_values in raw_indexes.items():
                if not isinstance(raw_values, list) or not 1 <= len(raw_values) <= 64:
                    raise LocalPillarError(
                        "RESOURCE_LIMIT", "each memory index must contain 1-64 values"
                    )
                indexes[index_type] = [
                    _text(value, f"indexes.{index_type}", 256).casefold()
                    for value in raw_values
                ]
                if len(set(indexes[index_type])) != len(indexes[index_type]):
                    raise LocalPillarError("INVALID_INPUT", "memory index values must be unique")
            event = MemoryEvent(
                event_id=_text(request["event_id"], "event_id", 128),
                event_type=_text(request["event_type"], "event_type", 128),
                session_id=_text(request["session_id"], "session_id", 128),
                goal_id=_text(request["goal_id"], "goal_id", 128),
                payload=dict(payload),
                node_id=_text(request.get("node_id", "local"), "node_id", 128),
                sequence_number=sequence,
            )
            metadata = {
                "source_digest": source_digest.lower(),
                "confidence": confidence,
                "owner_id": owner_id,
                "policy": policy,
                "observed_at": observed_at,
            }
            inserted = self.store.append_holographic(event, metadata, indexes)
            if not inserted:
                existing = self.store.holographic_record(event.event_id)
                expected_event = {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "session_id": event.session_id,
                    "goal_id": event.goal_id,
                    "payload": event.payload,
                    "node_id": event.node_id,
                    "sequence_number": event.sequence_number,
                }
                actual_event = (
                    {
                        key: existing["event"][key]
                        for key in expected_event
                    }
                    if existing is not None
                    else None
                )
                actual_provenance = existing["provenance"] if existing is not None else None
                expected_provenance = {
                    **metadata,
                    "revoked_at": None,
                    "revoke_reason": None,
                }
                expected_indexes = {
                    key: sorted(values) for key, values in indexes.items()
                }
                if (
                    actual_event != expected_event
                    or actual_provenance != expected_provenance
                    or existing is None
                    or existing["indexes"] != expected_indexes
                ):
                    raise LocalPillarError(
                        "MEMORY_CONFLICT", "event_id already identifies different memory data"
                    )
            return LocalPillarResult(
                "P008",
                "MEMORY_EVENT_APPENDED" if inserted else "MEMORY_EVENT_DUPLICATE",
                {"event_id": event.event_id, "inserted": inserted},
            )
        if action in {"query", "query_session", "query_goal"}:
            legacy = action != "query"
            id_field = "session_id" if action == "query_session" else "goal_id"
            if legacy:
                index_type = "session" if action == "query_session" else "goal"
                index_value = request.get(id_field)
            else:
                index_type = request.get("index_type")
                index_value = request.get("index_value")
            _strict(
                request,
                allowed=(
                    frozenset({"action", id_field, "limit", "include_revoked"})
                    if legacy
                    else frozenset(
                        {"action", "index_type", "index_value", "limit", "include_revoked"}
                    )
                ),
                required=(
                    frozenset({"action", id_field})
                    if legacy
                    else frozenset({"action", "index_type", "index_value"})
                ),
            )
            limit = request.get("limit", 50)
            if type(limit) is not int or not 1 <= limit <= 1_000:
                raise LocalPillarError("RESOURCE_LIMIT", "limit must be 1-1000")
            normalized_type = _text(index_type, "index_type", 32).casefold()
            if normalized_type not in {
                "session", "goal", "event_type", "semantic", "entity", "task", "procedure"
            }:
                raise LocalPillarError("INVALID_INPUT", "memory index type is unsupported")
            normalized_value = _text(index_value, "index_value", 256).casefold()
            include_revoked = request.get("include_revoked", False)
            if type(include_revoked) is not bool:
                raise LocalPillarError("INVALID_INPUT", "include_revoked must be boolean")
            events = self.store.query_holographic(
                normalized_type,
                normalized_value,
                limit,
                include_revoked=include_revoked,
            )
            return LocalPillarResult(
                "P008",
                "MEMORY_EVENTS_READ",
                {"events": events, "index_type": normalized_type},
            )
        if action == "revoke":
            _strict(
                request,
                allowed=frozenset({"action", "event_id", "reason"}),
                required=frozenset({"action", "event_id", "reason"}),
            )
            event_id = _text(request["event_id"], "event_id", 128)
            reason = _text(request["reason"], "reason", 1_024)
            if not self.store.revoke_holographic(event_id, reason, time.time()):
                raise LocalPillarError("MEMORY_NOT_FOUND_OR_REVOKED", "memory cannot be revoked")
            return LocalPillarResult(
                "P008", "MEMORY_EVENT_REVOKED", {"event_id": event_id, "revoked": True}
            )
        if action == "get_record":
            _strict(
                request,
                allowed=frozenset({"action", "event_id"}),
                required=frozenset({"action", "event_id"}),
            )
            event_id = _text(request["event_id"], "event_id", 128)
            rec = self.store.holographic_record(event_id)
            if rec is None:
                raise LocalPillarError("MEMORY_NOT_FOUND", "memory record not found")
            return LocalPillarResult("P008", "MEMORY_RECORD_READ", {"record": rec})
        if action == "rebuild_indexes":
            _strict(
                request,
                allowed=frozenset({"action"}),
                required=frozenset({"action"}),
            )
            count = self.store.rebuild_indexes()
            return LocalPillarResult(
                "P008", "INDEXES_REBUILT", {"indexed_events_count": count}
            )
        if action == "compact":
            _strict(
                request,
                allowed=frozenset({"action", "retention_seconds"}),
                required=frozenset({"action"}),
            )
            retention = request.get("retention_seconds", 86400.0)
            if not isinstance(retention, (int, float)) or retention < 0:
                raise LocalPillarError(
                    "INVALID_INPUT", "retention_seconds must be non-negative numeric"
                )
            result = self.store.compact(float(retention))
            return LocalPillarResult("P008", "MEMORY_COMPACTED", result)
        if action == "export":
            _strict(
                request,
                allowed=frozenset({"action", "session_id", "owner_id"}),
                required=frozenset({"action"}),
            )
            session_id = (
                _text(request["session_id"], "session_id", 128)
                if "session_id" in request
                else None
            )
            owner_id = (
                _text(request["owner_id"], "owner_id", 128)
                if "owner_id" in request
                else None
            )
            records = self.store.export_holographic(session_id, owner_id)
            return LocalPillarResult(
                "P008", "MEMORY_EXPORTED", {"events": records, "count": len(records)}
            )
        if action == "delete":
            _strict(
                request,
                allowed=frozenset({"action", "event_id", "owner_id"}),
                required=frozenset({"action", "event_id", "owner_id"}),
            )
            event_id = _text(request["event_id"], "event_id", 128)
            owner_id = _text(request["owner_id"], "owner_id", 128)
            deleted = self.store.delete_holographic(event_id, owner_id)
            if not deleted:
                raise LocalPillarError(
                    "MEMORY_NOT_FOUND_OR_DENIED",
                    "cannot delete memory: not found or unauthorized owner",
                )
            return LocalPillarResult(
                "P008", "MEMORY_EVENT_DELETED", {"event_id": event_id, "deleted": True}
            )
        raise LocalPillarError("UNSUPPORTED_ACTION", "memory action is unsupported")


_SANDBOX_WORKER = r"""
import ast, json, operator, sys
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
       ast.Mod: operator.mod, ast.Pow: operator.pow}
UOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.not_}
CMPS = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
        ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
def ev(node, depth=0):
    if depth > 32: raise ValueError('depth_limit')
    if isinstance(node, ast.Expression): return ev(node.body, depth + 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int,float,bool,str)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        left, right = ev(node.left, depth + 1), ev(node.right, depth + 1)
        if isinstance(node.op, ast.Pow):
            if not isinstance(right, (int, float)) or abs(right) > 12 or (isinstance(left, (int, float)) and abs(left) > 1000):
                raise ValueError('power_limit')
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ValueError('division_by_zero')
        return OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in UOPS:
        return UOPS[type(node.op)](ev(node.operand, depth + 1))
    if isinstance(node, ast.BoolOp):
        values = [bool(ev(value, depth + 1)) for value in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = ev(node.left, depth + 1)
        for op, comparator in zip(node.ops, node.comparators):
            right = ev(comparator, depth + 1)
            if type(op) not in CMPS or not CMPS[type(op)](left, right): return False
            left = right
        return True
    if isinstance(node, ast.List):
        if len(node.elts) > 64: raise ValueError('collection_limit')
        return [ev(elt, depth + 1) for elt in node.elts]
    if isinstance(node, ast.Dict):
        if len(node.keys) > 64: raise ValueError('collection_limit')
        return {ev(k, depth + 1): ev(v, depth + 1) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.Subscript):
        val = ev(node.value, depth + 1)
        idx = ev(node.slice, depth + 1)
        if isinstance(val, (list, tuple, str)) and isinstance(idx, int):
            if abs(idx) > 1024 or idx >= len(val) or idx < -len(val): raise IndexError('index_out_of_bounds')
            return val[idx]
        if isinstance(val, dict) and isinstance(idx, (str, int, float, bool)):
            return val[idx]
        raise ValueError('subscript_unsupported')
    raise ValueError('node_forbidden')
try:
    raw_input = sys.stdin.read()
    if len(raw_input.encode('utf-8')) > 8192: raise ValueError('input_limit')
    payload = json.loads(raw_input)
    expression = payload.get('expression')
    if not isinstance(expression, str) or not (1 <= len(expression) <= 4096): raise ValueError('input_limit')
    tree = ast.parse(expression, mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 256: raise ValueError('node_limit')
    result = ev(tree)
    encoded = json.dumps({'ok': True, 'result': result}, allow_nan=False)
    if len(encoded.encode('utf-8')) > 65536: raise ValueError('output_limit')
    sys.stdout.write(encoded)
except Exception as exc:
    err_code = str(exc) if str(exc) else type(exc).__name__
    sys.stdout.write(json.dumps({'ok': False, 'code': err_code}))
"""


class SandboxedImaginationCapability:
    """Execute a bounded declarative expression in an isolated Python worker."""

    def __init__(self, timeout_seconds: float = 2.0) -> None:
        if not 0.1 <= timeout_seconds <= 10.0:
            raise LocalPillarError("INVALID_CONFIG", "sandbox timeout must be 0.1-10 seconds")
        self.timeout_seconds = timeout_seconds

    def health_check(self) -> bool:
        try:
            return self.evaluate("2 + 3 * 4").data["result"] == 14
        except LocalPillarError:
            return False

    def evaluate(self, expression: object) -> LocalPillarResult:
        candidate = _text(expression, "expression", 4_096)
        started = time.perf_counter_ns()
        work_dir_cleaned = False
        try:
            with tempfile.TemporaryDirectory(prefix="jaya-sandbox-") as work_dir:
                completed = subprocess.run(
                    [sys.executable, "-I", "-S", "-c", _SANDBOX_WORKER],
                    input=json.dumps({"expression": candidate}),
                    text=True,
                    capture_output=True,
                    cwd=work_dir,
                    env={"PYTHONIOENCODING": "utf-8"},
                    timeout=self.timeout_seconds,
                    check=False,
                )
            work_dir_cleaned = True
        except subprocess.TimeoutExpired as exc:
            raise LocalPillarError("TIMEOUT", "sandbox evaluation timed out") from exc
        except OSError as exc:
            raise LocalPillarError("PROVIDER_UNAVAILABLE", "sandbox worker is unavailable") from exc
        if completed.returncode != 0 or len(completed.stdout.encode("utf-8")) > 65_536:
            raise LocalPillarError("SANDBOX_FAILED", "sandbox worker failed")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise LocalPillarError(
                "INVALID_PROVIDER_RESPONSE", "sandbox output is invalid"
            ) from exc
        if not payload.get("ok"):
            code = payload.get("code", "")
            if code in {"node_forbidden", "power_limit"}:
                raise LocalPillarError("SECURITY_VIOLATION", f"expression violates sandbox policy: {code}")
            if code in {"depth_limit", "node_limit", "input_limit", "output_limit", "collection_limit"}:
                raise LocalPillarError("RESOURCE_LIMIT", f"sandbox resource limit exceeded: {code}")
            if code == "division_by_zero":
                raise LocalPillarError("ARITHMETIC_ERROR", "division by zero in sandbox evaluation")
            raise LocalPillarError("SECURITY_VIOLATION", f"expression violates sandbox policy: {code}")
        return LocalPillarResult(
            "P023",
            "SANDBOX_EXPRESSION_EVALUATED",
            {
                "result": payload.get("result"),
                "duration_ns": time.perf_counter_ns() - started,
                "isolation": "PYTHON_ISOLATED_PROCESS_AST_ALLOWLIST",
                "epistemic_label": "SIMULATION",
                "epistemic_status": "UNVERIFIED",
                "cleanup_verified": work_dir_cleaned,
            },
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            allowed=frozenset({"action", "expression"}),
            required=frozenset({"action", "expression"}),
        )
        if request["action"] != "evaluate":
            raise LocalPillarError("UNSUPPORTED_ACTION", "sandbox action is unsupported")
        return self.evaluate(request["expression"])


class TemporalWeightingCapability:
    """Persistent provenance-aware temporal scoring with auditable policy history."""

    SCHEMA_VERSION = 2
    MAX_PAYLOAD_BYTES = 256 * 1024
    CLOCK_SOURCES = frozenset({"SYSTEM_UTC", "EXTERNAL_SIGNED", "SOURCE_REPORTED"})

    def __init__(self, database_path: Path, max_future_skew_seconds: float = 300.0) -> None:
        self.database_path = database_path.resolve()
        self.max_future_skew_seconds = max_future_skew_seconds
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with _connection(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS temporal_meta(
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS temporal_records(
                        record_id TEXT PRIMARY KEY,
                        source_ref TEXT NOT NULL,
                        base_score REAL NOT NULL,
                        observed_at REAL NOT NULL,
                        supersedes TEXT,
                        payload_json TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        FOREIGN KEY(supersedes) REFERENCES temporal_records(record_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_temporal_observed
                    ON temporal_records(observed_at DESC);
                    """
                )
                version_row = connection.execute(
                    "SELECT value FROM temporal_meta WHERE key='schema_version'"
                ).fetchone()
                version = 1 if version_row is None else int(version_row[0])
                if version > self.SCHEMA_VERSION:
                    raise LocalPillarError(
                        "STORAGE_SCHEMA_UNSUPPORTED",
                        "temporal store schema is newer than this runtime",
                    )
                columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(temporal_records)")
                }
                migrations = {
                    "valid_until": "ALTER TABLE temporal_records ADD COLUMN valid_until REAL",
                    "retention_until": (
                        "ALTER TABLE temporal_records ADD COLUMN retention_until REAL"
                    ),
                    "legal_hold": (
                        "ALTER TABLE temporal_records ADD COLUMN legal_hold INTEGER "
                        "NOT NULL DEFAULT 0 CHECK(legal_hold IN (0,1))"
                    ),
                    "clock_source": (
                        "ALTER TABLE temporal_records ADD COLUMN clock_source TEXT "
                        "NOT NULL DEFAULT 'SYSTEM_UTC'"
                    ),
                }
                for column, statement in migrations.items():
                    if column not in columns:
                        connection.execute(statement)
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS temporal_policy_events(
                        event_id TEXT PRIMARY KEY,
                        record_id TEXT NOT NULL,
                        enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                        reason TEXT NOT NULL,
                        changed_at REAL NOT NULL,
                        created_at REAL NOT NULL,
                        FOREIGN KEY(record_id) REFERENCES temporal_records(record_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_temporal_policy_record_time
                    ON temporal_policy_events(record_id, changed_at DESC, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_temporal_supersedes_observed
                    ON temporal_records(supersedes, observed_at DESC);
                    """
                )
                connection.execute(
                    "INSERT INTO temporal_meta(key,value) VALUES('schema_version',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(self.SCHEMA_VERSION),),
                )
        except LocalPillarError:
            raise
        except (TypeError, ValueError) as exc:
            raise LocalPillarError(
                "STORAGE_CORRUPT", "temporal store schema metadata is invalid"
            ) from exc
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "temporal store unavailable") from exc

    def health_check(self) -> bool:
        try:
            with _connection(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                version = connection.execute(
                    "SELECT value FROM temporal_meta WHERE key='schema_version'"
                ).fetchone()
                foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchone()
                return (
                    version is not None
                    and int(version[0]) == self.SCHEMA_VERSION
                    and foreign_key_errors is None
                    and connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                )
        except (sqlite3.Error, TypeError, ValueError):
            return False

    @staticmethod
    def _number(value: object, field: str) -> float:
        if isinstance(value, bool):
            raise LocalPillarError("INVALID_INPUT", f"{field} must be numeric")
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", f"{field} must be numeric") from exc
        if not math.isfinite(result):
            raise LocalPillarError("INVALID_INPUT", f"{field} must be finite")
        return result

    def _timestamp(self, value: object, field: str, *, future_allowed: bool = False) -> float:
        timestamp = self._number(value, field)
        if timestamp < 0:
            raise LocalPillarError("INVALID_INPUT", f"{field} must be a Unix timestamp")
        if not future_allowed and timestamp > time.time() + self.max_future_skew_seconds:
            raise LocalPillarError("CLOCK_SKEW", f"{field} exceeds allowed clock skew")
        return timestamp

    @staticmethod
    def _timeout(request: Mapping[str, Any]) -> tuple[float, float]:
        raw_timeout = request.get("timeout_seconds", 5.0)
        if isinstance(raw_timeout, bool):
            raise LocalPillarError("INVALID_INPUT", "timeout_seconds must be numeric")
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "timeout_seconds must be numeric") from exc
        if not math.isfinite(timeout) or not 0.000001 <= timeout <= 30.0:
            raise LocalPillarError(
                "RESOURCE_LIMIT", "timeout_seconds must be within 0.000001-30"
            )
        return timeout, time.perf_counter() + timeout

    @staticmethod
    def _install_deadline(connection: sqlite3.Connection, deadline: float) -> None:
        connection.set_progress_handler(
            lambda: 1 if time.perf_counter() >= deadline else 0,
            100,
        )

    @staticmethod
    def _payload(raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LocalPillarError(
                "STORAGE_CORRUPT", "temporal payload is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise LocalPillarError(
                "STORAGE_CORRUPT", "temporal payload is not an object"
            )
        return payload

    @staticmethod
    def _stored_number(
        value: object,
        field: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise LocalPillarError(
                "STORAGE_CORRUPT", f"stored {field} is not numeric"
            ) from exc
        if (
            not math.isfinite(result)
            or (minimum is not None and result < minimum)
            or (maximum is not None and result > maximum)
        ):
            raise LocalPillarError(
                "STORAGE_CORRUPT", f"stored {field} is outside its contract"
            )
        return result

    @classmethod
    def _stored_optional_timestamp(cls, value: object, field: str) -> float | None:
        if value is None:
            return None
        return cls._stored_number(value, field, minimum=0.0)

    @classmethod
    def _stored_clock_source(cls, value: object) -> str:
        if not isinstance(value, str) or value not in cls.CLOCK_SOURCES:
            raise LocalPillarError(
                "STORAGE_CORRUPT", "stored clock_source is outside its contract"
            )
        return value

    @staticmethod
    def _ensure_deadline(deadline: float) -> None:
        if time.perf_counter() >= deadline:
            raise LocalPillarError("TIMEOUT", "temporal operation exceeded its deadline")

    @staticmethod
    def _sqlite_read_error(exc: sqlite3.Error) -> LocalPillarError:
        if isinstance(exc, sqlite3.OperationalError) and "interrupt" in str(exc).lower():
            return LocalPillarError("TIMEOUT", "temporal operation exceeded its deadline")
        return LocalPillarError("STORAGE_UNAVAILABLE", "temporal records cannot be read")

    def add(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            allowed=frozenset(
                {
                    "action",
                    "record_id",
                    "source_ref",
                    "base_score",
                    "observed_at",
                    "supersedes",
                    "payload",
                    "valid_until",
                    "retention_until",
                    "legal_hold",
                    "clock_source",
                }
            ),
            required=frozenset(
                {"action", "record_id", "source_ref", "base_score", "observed_at", "payload"}
            ),
        )
        record_id = _text(request["record_id"], "record_id", 128)
        source_ref = _text(request["source_ref"], "source_ref", 512)
        score = self._number(request["base_score"], "base_score")
        observed = self._timestamp(request["observed_at"], "observed_at")
        if not 0.0 <= score <= 1.0:
            raise LocalPillarError("INVALID_INPUT", "base_score must be within 0-1")
        payload = request["payload"]
        if not isinstance(payload, Mapping):
            raise LocalPillarError("INVALID_INPUT", "payload must be an object")
        try:
            payload_json = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "payload must be finite JSON") from exc
        if len(payload_json.encode("utf-8")) > self.MAX_PAYLOAD_BYTES:
            raise LocalPillarError("RESOURCE_LIMIT", "temporal payload exceeds 256 KiB")
        supersedes = request.get("supersedes")
        if supersedes is not None:
            supersedes = _text(supersedes, "supersedes", 128)
            if supersedes == record_id:
                raise LocalPillarError("INVALID_INPUT", "record cannot supersede itself")
        valid_until = request.get("valid_until")
        if valid_until is not None:
            valid_until = self._timestamp(valid_until, "valid_until", future_allowed=True)
            if valid_until <= observed:
                raise LocalPillarError(
                    "INVALID_INPUT", "valid_until must be later than observed_at"
                )
        retention_until = request.get("retention_until")
        if retention_until is not None:
            retention_until = self._timestamp(
                retention_until, "retention_until", future_allowed=True
            )
            retention_floor = valid_until if valid_until is not None else observed
            if retention_until < retention_floor:
                raise LocalPillarError(
                    "INVALID_INPUT",
                    "retention_until must not precede the validity window",
                )
        legal_hold = request.get("legal_hold", False)
        if type(legal_hold) is not bool:
            raise LocalPillarError("INVALID_INPUT", "legal_hold must be boolean")
        clock_source = str(request.get("clock_source", "SYSTEM_UTC")).strip().upper()
        if clock_source not in self.CLOCK_SOURCES:
            raise LocalPillarError("INVALID_INPUT", "clock_source is unsupported")
        material = (
            source_ref,
            score,
            observed,
            supersedes,
            payload_json,
            valid_until,
            retention_until,
            int(legal_hold),
            clock_source,
        )
        try:
            with _connection(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT source_ref,base_score,observed_at,supersedes,payload_json,
                           valid_until,retention_until,legal_hold,clock_source
                    FROM temporal_records WHERE record_id=?
                    """,
                    (record_id,),
                ).fetchone()
                if existing is not None:
                    if tuple(existing) == material:
                        return LocalPillarResult(
                            "P027",
                            "TEMPORAL_RECORD_DUPLICATE",
                            {"record_id": record_id, "inserted": False},
                        )
                    raise LocalPillarError(
                        "TEMPORAL_CONFLICT",
                        "record_id is already bound to different temporal material",
                    )
                if supersedes is not None:
                    parent = connection.execute(
                        "SELECT observed_at FROM temporal_records WHERE record_id=?",
                        (supersedes,),
                    ).fetchone()
                    if parent is None:
                        raise LocalPillarError(
                            "SUPERSESSION_NOT_FOUND", "superseded record does not exist"
                        )
                    if observed < float(parent[0]):
                        raise LocalPillarError(
                            "INVALID_INPUT",
                            "superseding record cannot be older than its parent",
                        )
                connection.execute(
                    """
                    INSERT INTO temporal_records(
                        record_id,source_ref,base_score,observed_at,supersedes,
                        payload_json,created_at,valid_until,retention_until,
                        legal_hold,clock_source
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record_id,
                        source_ref,
                        score,
                        observed,
                        supersedes,
                        payload_json,
                        time.time(),
                        valid_until,
                        retention_until,
                        int(legal_hold),
                        clock_source,
                    ),
                )
        except LocalPillarError:
            raise
        except sqlite3.IntegrityError as exc:
            raise LocalPillarError("STORAGE_CORRUPT", "temporal constraint failed") from exc
        except sqlite3.Error as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "temporal record could not be stored"
            ) from exc
        return LocalPillarResult(
            "P027", "TEMPORAL_RECORD_STORED", {"record_id": record_id, "inserted": True}
        )

    def rank(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            allowed=frozenset(
                {"action", "decay_rate", "limit", "now", "timeout_seconds"}
            ),
            required=frozenset({"action", "decay_rate"}),
        )
        decay = self._number(request["decay_rate"], "decay_rate")
        now = self._timestamp(request.get("now", time.time()), "now", future_allowed=True)
        limit = request.get("limit", 50)
        if not 0.0 <= decay <= 100.0:
            raise LocalPillarError("INVALID_INPUT", "decay_rate must be 0-100")
        if type(limit) is not int or not 1 <= limit <= 1_000:
            raise LocalPillarError("RESOURCE_LIMIT", "limit must be 1-1000")
        _, deadline = self._timeout(request)
        try:
            with _connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                self._install_deadline(connection, deadline)
                rows = connection.execute(
                    """
                    SELECT t.*,
                           COALESCE(
                               (
                                   SELECT enabled FROM temporal_policy_events e
                                   WHERE e.record_id=t.record_id AND e.changed_at <= ?
                                   ORDER BY e.changed_at DESC,e.created_at DESC,e.event_id DESC
                                   LIMIT 1
                               ),
                               t.legal_hold
                           ) AS effective_legal_hold
                    FROM temporal_records t
                    WHERE t.observed_at <= ?
                      AND (t.valid_until IS NULL OR t.valid_until > ?)
                      AND
                      NOT EXISTS(
                        SELECT 1 FROM temporal_records newer
                        WHERE newer.supersedes=t.record_id AND newer.observed_at <= ?
                    )
                    """,
                    (now, now, now, now),
                ).fetchall()
        except sqlite3.Error as exc:
            raise self._sqlite_read_error(exc) from exc
        ranked = []
        for row in rows:
            self._ensure_deadline(deadline)
            observed_at = self._stored_number(
                row["observed_at"], "observed_at", minimum=0.0
            )
            base_score = self._stored_number(
                row["base_score"], "base_score", minimum=0.0, maximum=1.0
            )
            valid_until = self._stored_optional_timestamp(
                row["valid_until"], "valid_until"
            )
            retention_until = self._stored_optional_timestamp(
                row["retention_until"], "retention_until"
            )
            clock_source = self._stored_clock_source(row["clock_source"])
            age_hours = max(0.0, now - observed_at) / 3600.0
            weighted = base_score * math.exp(-decay * age_hours)
            ranked.append(
                {
                    "record_id": row["record_id"],
                    "source_ref": row["source_ref"],
                    "weighted_score": weighted,
                    "observed_at": observed_at,
                    "valid_until": valid_until,
                    "retention_until": retention_until,
                    "legal_hold": bool(row["effective_legal_hold"]),
                    "clock_source": clock_source,
                    "status": "ACTIVE",
                    "payload": self._payload(row["payload_json"]),
                }
            )
        ranked.sort(key=lambda item: (-item["weighted_score"], item["record_id"]))
        self._ensure_deadline(deadline)
        return LocalPillarResult(
            "P027",
            "TEMPORAL_RECORDS_RANKED",
            {"records": ranked[:limit], "evaluated_at": now, "decay_rate": decay},
        )

    def set_legal_hold(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            allowed=frozenset(
                {"action", "event_id", "record_id", "enabled", "reason", "changed_at"}
            ),
            required=frozenset(
                {"action", "event_id", "record_id", "enabled", "reason", "changed_at"}
            ),
        )
        event_id = _text(request["event_id"], "event_id", 128)
        record_id = _text(request["record_id"], "record_id", 128)
        enabled = request["enabled"]
        if type(enabled) is not bool:
            raise LocalPillarError("INVALID_INPUT", "enabled must be boolean")
        reason = _text(request["reason"], "reason", 1_024)
        changed_at = self._timestamp(request["changed_at"], "changed_at")
        material = (record_id, int(enabled), reason, changed_at)
        try:
            with _connection(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT record_id,enabled,reason,changed_at
                    FROM temporal_policy_events WHERE event_id=?
                    """,
                    (event_id,),
                ).fetchone()
                if existing is not None:
                    if tuple(existing) == material:
                        return LocalPillarResult(
                            "P027",
                            "TEMPORAL_POLICY_EVENT_DUPLICATE",
                            {"event_id": event_id, "record_id": record_id, "inserted": False},
                        )
                    raise LocalPillarError(
                        "TEMPORAL_CONFLICT",
                        "event_id is already bound to different policy material",
                    )
                record = connection.execute(
                    "SELECT observed_at FROM temporal_records WHERE record_id=?", (record_id,)
                ).fetchone()
                if record is None:
                    raise LocalPillarError("RECORD_NOT_FOUND", "temporal record does not exist")
                if changed_at < float(record[0]):
                    raise LocalPillarError(
                        "INVALID_INPUT", "policy event cannot precede its temporal record"
                    )
                connection.execute(
                    """
                    INSERT INTO temporal_policy_events(
                        event_id,record_id,enabled,reason,changed_at,created_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (event_id, record_id, int(enabled), reason, changed_at, time.time()),
                )
        except LocalPillarError:
            raise
        except sqlite3.IntegrityError as exc:
            raise LocalPillarError("STORAGE_CORRUPT", "temporal policy constraint failed") from exc
        except sqlite3.Error as exc:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE", "temporal policy event could not be stored"
            ) from exc
        return LocalPillarResult(
            "P027",
            "TEMPORAL_LEGAL_HOLD_RECORDED",
            {"event_id": event_id, "record_id": record_id, "inserted": True},
        )

    def history(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(
            request,
            allowed=frozenset(
                {"action", "record_id", "limit", "as_of", "timeout_seconds"}
            ),
            required=frozenset({"action"}),
        )
        record_id = request.get("record_id")
        if record_id is not None:
            record_id = _text(record_id, "record_id", 128)
        limit = request.get("limit", 100)
        if type(limit) is not int or not 1 <= limit <= 1_000:
            raise LocalPillarError("RESOURCE_LIMIT", "limit must be 1-1000")
        as_of = self._timestamp(
            request.get("as_of", time.time()), "as_of", future_allowed=True
        )
        _, deadline = self._timeout(request)
        where = "WHERE t.observed_at <= ?"
        where_parameters: list[object] = [as_of]
        if record_id is not None:
            where += " AND t.record_id=?"
            where_parameters.append(record_id)
        parameters = [as_of, as_of, as_of, *where_parameters, limit + 1]
        try:
            with _connection(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                self._install_deadline(connection, deadline)
                rows = connection.execute(
                    f"""
                    SELECT t.*,
                           EXISTS(
                               SELECT 1 FROM temporal_records newer
                               WHERE newer.supersedes=t.record_id
                                 AND newer.observed_at <= ?
                           ) AS is_superseded,
                           COALESCE(
                               (
                                   SELECT enabled FROM temporal_policy_events e
                                   WHERE e.record_id=t.record_id AND e.changed_at <= ?
                                   ORDER BY e.changed_at DESC,e.created_at DESC,e.event_id DESC
                                   LIMIT 1
                               ),
                               t.legal_hold
                           ) AS effective_legal_hold,
                           (
                               SELECT event_id FROM temporal_policy_events e
                               WHERE e.record_id=t.record_id AND e.changed_at <= ?
                               ORDER BY e.changed_at DESC,e.created_at DESC,e.event_id DESC
                               LIMIT 1
                           ) AS latest_policy_event_id
                    FROM temporal_records t
                    {where}
                    ORDER BY t.observed_at DESC,t.record_id
                    LIMIT ?
                    """,
                    tuple(parameters),
                ).fetchall()
        except sqlite3.Error as exc:
            raise self._sqlite_read_error(exc) from exc
        records: list[dict[str, Any]] = []
        has_more = len(rows) > limit
        for row in rows[:limit]:
            self._ensure_deadline(deadline)
            observed_at = self._stored_number(
                row["observed_at"], "observed_at", minimum=0.0
            )
            base_score = self._stored_number(
                row["base_score"], "base_score", minimum=0.0, maximum=1.0
            )
            valid_until = self._stored_optional_timestamp(
                row["valid_until"], "valid_until"
            )
            retention_until = self._stored_optional_timestamp(
                row["retention_until"], "retention_until"
            )
            clock_source = self._stored_clock_source(row["clock_source"])
            if bool(row["is_superseded"]):
                status = "SUPERSEDED"
            elif valid_until is not None and valid_until <= as_of:
                status = "EXPIRED"
            else:
                status = "ACTIVE"
            legal_hold = bool(row["effective_legal_hold"])
            if legal_hold:
                retention_status = "LEGAL_HOLD"
            elif retention_until is None:
                retention_status = "RETAINED_INDEFINITELY"
            elif retention_until <= as_of:
                retention_status = "ELIGIBLE_FOR_POLICY_DELETION"
            else:
                retention_status = "RETENTION_ACTIVE"
            records.append(
                {
                    "record_id": row["record_id"],
                    "source_ref": row["source_ref"],
                    "base_score": base_score,
                    "observed_at": observed_at,
                    "supersedes": row["supersedes"],
                    "valid_until": valid_until,
                    "retention_until": retention_until,
                    "legal_hold": legal_hold,
                    "latest_policy_event_id": row["latest_policy_event_id"],
                    "retention_status": retention_status,
                    "clock_source": clock_source,
                    "status": status,
                    "payload": self._payload(row["payload_json"]),
                }
            )
        self._ensure_deadline(deadline)
        return LocalPillarResult(
            "P027",
            "TEMPORAL_HISTORY_READ",
            {"records": records, "as_of": as_of, "has_more": has_more},
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        if request.get("action") == "add":
            return self.add(request)
        if request.get("action") == "rank":
            return self.rank(request)
        if request.get("action") == "set_legal_hold":
            return self.set_legal_hold(request)
        if request.get("action") == "history":
            return self.history(request)
        raise LocalPillarError("UNSUPPORTED_ACTION", "temporal action is unsupported")





class FoundationPillarCapabilityService:
    """Dispatch the local memory, sandbox, semantic, temporal, and sparse providers."""

    def __init__(
        self,
        *,
        data_dir: Path,
        episodic_memory: Any,
    ) -> None:
        root = data_dir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.memory = HolographicMemoryCapability(episodic_memory)
        self.sandbox = SandboxedImaginationCapability()
        self.semantic = SemanticBridgeCapability(root / "semantic_bridge.sqlite3")
        self.temporal = TemporalWeightingCapability(root / "temporal_weighting.sqlite3")
        self.sparse = ActivationSparsityCapability(root / "activation_sparsity.sqlite3")

    def _health(self, capability_id: str) -> bool:
        if capability_id == MEMORY_CAPABILITY_ID:
            return self.memory.health_check()
        if capability_id == SANDBOX_CAPABILITY_ID:
            return self.sandbox.health_check()
        if capability_id == SEMANTIC_CAPABILITY_ID:
            return self.semantic.health_check()
        if capability_id == TEMPORAL_CAPABILITY_ID:
            return self.temporal.health_check()
        if capability_id == SPARSE_CAPABILITY_ID:
            return self.sparse.health_check()
        return False

    def manifests(self) -> tuple[CapabilityManifest, ...]:
        specs = (
            (MEMORY_CAPABILITY_ID, 32, ["persistent_storage"]),
            (SANDBOX_CAPABILITY_ID, 32, ["process_execute"]),
            (SEMANTIC_CAPABILITY_ID, 32, ["persistent_storage"]),
            (TEMPORAL_CAPABILITY_ID, 16, ["persistent_storage"]),
            (SPARSE_CAPABILITY_ID, 32, ["persistent_storage"]),
        )
        return tuple(
            CapabilityManifest(
                capability_id=capability_id,
                version="1.0",
                provider="foundation_pillar_service",
                execution_location="local",
                min_memory_mb=memory,
                permissions_required=permissions,
                offline_available=True,
                health_status="HEALTHY" if self._health(capability_id) else "UNHEALTHY",
            )
            for capability_id, memory, permissions in specs
        )

    def execute(self, capability_id: str, request: Mapping[str, Any]) -> LocalPillarResult:
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        if capability_id == MEMORY_CAPABILITY_ID:
            return self.memory.execute(request)
        if capability_id == SANDBOX_CAPABILITY_ID:
            return self.sandbox.execute(request)
        if capability_id == SEMANTIC_CAPABILITY_ID:
            return self.semantic.execute(request)
        if capability_id == TEMPORAL_CAPABILITY_ID:
            return self.temporal.execute(request)
        if capability_id == SPARSE_CAPABILITY_ID:
            return self.sparse.execute(request)
        raise LocalPillarError("CAPABILITY_UNAVAILABLE", "foundation pillar is not registered")

    def integrated_memory_health(self) -> dict[str, bool]:
        """Probe persistent dependencies used by the semantic memory slice."""
        return {
            "P008_HOLOGRAPHIC_MEMORY": self.memory.health_check(),
            "P026_SEMANTIC_BRIDGE": self.semantic.health_check(),
            "P027_TEMPORAL_WEIGHTING": self.temporal.health_check(),
        }

    @staticmethod
    def _validate_memory_cycle_request(request: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {
            "source_ref",
            "content",
            "namespace",
            "record_id",
            "event_id",
            "session_id",
            "goal_id",
            "owner_id",
            "policy",
            "base_score",
            "confidence",
            "observed_at",
            "evaluated_at",
            "decay_rate",
            "sequence_number",
        }
        required = allowed - {"sequence_number"}
        unknown = set(request) - allowed
        missing = required - set(request)
        if unknown:
            raise LocalPillarError(
                "UNKNOWN_FIELD", f"unsupported fields: {', '.join(sorted(unknown))}"
            )
        if missing:
            raise LocalPillarError(
                "MISSING_FIELD", f"required fields: {', '.join(sorted(missing))}"
            )
        normalized = dict(request)
        text_limits = {
            "source_ref": 512,
            "content": SemanticBridgeCapability.MAX_SOURCE_BYTES,
            "namespace": 128,
            "record_id": 128,
            "event_id": 128,
            "session_id": 128,
            "goal_id": 128,
            "owner_id": 128,
            "policy": 32,
        }
        for field, maximum in text_limits.items():
            normalized[field] = _text(request[field], field, maximum)
        if len(normalized["content"].encode("utf-8")) > SemanticBridgeCapability.MAX_SOURCE_BYTES:
            raise LocalPillarError("RESOURCE_LIMIT", "content exceeds 1 MiB")
        if re.search(
            r"(?:model|dataset|artifact|person|organization|concept):"
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",
            normalized["content"],
            re.IGNORECASE,
        ) is None:
            raise LocalPillarError(
                "SEMANTIC_ENTITY_REQUIRED", "content must contain a typed semantic entity"
            )
        policy = normalized["policy"].upper()
        if policy not in {"PRIVATE", "RESTRICTED", "INTERNAL", "PUBLIC"}:
            raise LocalPillarError("INVALID_INPUT", "memory policy is unsupported")
        normalized["policy"] = policy
        try:
            base_score = float(request["base_score"])
            confidence = float(request["confidence"])
            observed_at = float(request["observed_at"])
            evaluated_at = float(request["evaluated_at"])
            decay_rate = float(request["decay_rate"])
        except (TypeError, ValueError) as exc:
            raise LocalPillarError(
                "INVALID_INPUT", "score, confidence, time, and decay must be numeric"
            ) from exc
        if not math.isfinite(base_score) or not 0 <= base_score <= 1:
            raise LocalPillarError("INVALID_INPUT", "base_score must be finite and 0-1")
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise LocalPillarError("INVALID_INPUT", "confidence must be finite and 0-1")
        if not math.isfinite(observed_at) or observed_at > time.time() + 300:
            raise LocalPillarError("CLOCK_SKEW", "observed_at exceeds allowed clock skew")
        if (
            not math.isfinite(evaluated_at)
            or evaluated_at < observed_at
            or evaluated_at > time.time() + 300
        ):
            raise LocalPillarError("CLOCK_SKEW", "evaluated_at is outside the valid window")
        if not math.isfinite(decay_rate) or not 0 <= decay_rate <= 100:
            raise LocalPillarError("INVALID_INPUT", "decay_rate must be finite and 0-100")
        sequence = request.get("sequence_number", 0)
        if type(sequence) is not int or not 0 <= sequence <= 2**63 - 1:
            raise LocalPillarError("INVALID_INPUT", "sequence_number is invalid")
        normalized.update(
            {
                "base_score": base_score,
                "confidence": confidence,
                "observed_at": observed_at,
                "evaluated_at": evaluated_at,
                "decay_rate": decay_rate,
                "sequence_number": sequence,
            }
        )
        return normalized

    def execute_integrated_memory_cycle(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Persist one source through semantic, temporal, and indexed memory layers."""
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        payload = self._validate_memory_cycle_request(request)
        health = self.integrated_memory_health()
        unavailable = [name for name, ready in health.items() if not ready]
        if unavailable:
            raise LocalPillarError(
                "STORAGE_UNAVAILABLE",
                f"integrated memory dependencies unavailable: {', '.join(unavailable)}",
            )

        semantic = self.semantic.execute(
            {
                "action": "ingest",
                "source_ref": payload["source_ref"],
                "content": payload["content"],
                "namespace": payload["namespace"],
            }
        )
        semantic_entities = list(semantic.data["entities"])
        semantic_indexes = list(
            dict.fromkeys(
                f"{item['entity_type']}:{item['canonical_value']}"
                for item in semantic_entities
            )
        )
        entity_indexes = list(
            dict.fromkeys(str(item["canonical_value"]) for item in semantic_entities)
        )
        temporal_request = {
            "action": "add",
            "record_id": payload["record_id"],
            "source_ref": semantic.data["source_ref"],
            "base_score": payload["base_score"],
            "observed_at": payload["observed_at"],
            "payload": {"source_digest": semantic.data["source_digest"]},
        }
        try:
            temporal = self.temporal.execute(temporal_request)
        except LocalPillarError as exc:
            if exc.code != "DUPLICATE_OR_INVALID_PARENT":
                raise
            temporal = LocalPillarResult(
                "P027",
                "TEMPORAL_RECORD_DUPLICATE",
                {"record_id": payload["record_id"]},
            )
        ranked = self.temporal.execute(
            {
                "action": "rank",
                "decay_rate": payload["decay_rate"],
                "now": payload["evaluated_at"],
            }
        )
        active_record = next(
            (
                item
                for item in ranked.data["records"]
                if item["record_id"] == payload["record_id"]
            ),
            None,
        )
        if (
            active_record is None
            or active_record["source_ref"] != payload["source_ref"]
            or active_record["payload"].get("source_digest")
            != semantic.data["source_digest"]
        ):
            raise LocalPillarError(
                "TEMPORAL_CONFLICT", "record_id identifies different temporal evidence"
            )
        memory = self.memory.execute(
            {
                "action": "append",
                "event_id": payload["event_id"],
                "event_type": "SEMANTIC_EVIDENCE_INDEXED",
                "session_id": payload["session_id"],
                "goal_id": payload["goal_id"],
                "sequence_number": payload["sequence_number"],
                "payload": {
                    "source_ref": semantic.data["source_ref"],
                    "source_digest": semantic.data["source_digest"],
                    "semantic_method": semantic.data["method"],
                    "temporal_record_id": active_record["record_id"],
                    "weighted_score": active_record["weighted_score"],
                    "evidence_status": "UNVERIFIED",
                },
                "provenance": {
                    "source_digest": semantic.data["source_digest"],
                    "confidence": payload["confidence"],
                    "owner_id": payload["owner_id"],
                    "policy": payload["policy"],
                    "observed_at": payload["observed_at"],
                },
                "indexes": {
                    "semantic": semantic_indexes,
                    "entity": entity_indexes,
                    "task": [payload["goal_id"]],
                },
            }
        )
        recalled = self.memory.execute(
            {
                "action": "query_session",
                "session_id": payload["session_id"],
                "limit": 50,
            }
        )
        if not any(
            item["event_id"] == payload["event_id"] for item in recalled.data["events"]
        ):
            raise LocalPillarError("MEMORY_WRITE_FAILED", "indexed event cannot be recalled")
        return {
            "cycle_id": payload["event_id"],
            "status": "INTEGRATED_MEMORY_CYCLE_COMPLETED",
            "pillars": list(INTEGRATED_MEMORY_PILLARS),
            "dependency_health": health,
            "semantic": semantic.data,
            "temporal": {**temporal.data, "ranked_record": active_record},
            "memory": {**memory.data, "recalled_events": len(recalled.data["events"])},
            "evidence_status": "UNVERIFIED",
        }
