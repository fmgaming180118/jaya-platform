"""Signed local numeric mixture-of-experts runtime for Pillar 34."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import sqlite3
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np

from .local_capabilities import LocalPillarError, LocalPillarResult

MOE_CAPABILITY_ID = "core.model.sparse_moe"
_FIELDS = frozenset(
    {
        "schema_version",
        "expert_id",
        "version",
        "task_kinds",
        "input_dimension",
        "output_dimension",
        "weight_matrix",
        "bias",
        "routing_vector",
        "capacity",
    }
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class DynamicSparsityMoECapability:
    """Verify, route, and execute signed expert weight artifacts."""

    def __init__(self, *, expert_root: Path, database_path: Path, signing_key: bytes | None) -> None:
        self.expert_root = expert_root.resolve()
        self.expert_root.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path.resolve()
        self.signing_key = signing_key
        self._expert_load: dict[str, int] = {}

        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS moe_schema(
                        schema_version INTEGER PRIMARY KEY,
                        applied_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS expert_utilization(
                        expert_id TEXT PRIMARY KEY,
                        selected_count INTEGER NOT NULL,
                        execution_count INTEGER NOT NULL,
                        overflow_count INTEGER NOT NULL DEFAULT 0,
                        last_latency_ns INTEGER NOT NULL,
                        last_used_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS moe_runs(
                        run_id TEXT PRIMARY KEY,
                        task_kind TEXT NOT NULL,
                        selected_json TEXT NOT NULL,
                        result_digest TEXT NOT NULL,
                        quality_regression REAL NOT NULL,
                        latency_ns INTEGER NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS moe_audit_log(
                        audit_id TEXT PRIMARY KEY,
                        run_id TEXT,
                        action TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS moe_receipts(
                        receipt_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        task_kind TEXT NOT NULL,
                        result_digest TEXT NOT NULL,
                        selected_experts_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    """
                )
                # Ensure column overflow_count exists if migrating an existing table
                cols = [row["name"] for row in connection.execute("PRAGMA table_info(expert_utilization)").fetchall()]
                if "overflow_count" not in cols:
                    connection.execute("ALTER TABLE expert_utilization ADD COLUMN overflow_count INTEGER NOT NULL DEFAULT 0")

                run_cols = [row["name"] for row in connection.execute("PRAGMA table_info(moe_runs)").fetchall()]
                if "quality_regression" not in run_cols:
                    connection.execute("ALTER TABLE moe_runs ADD COLUMN quality_regression REAL NOT NULL DEFAULT 0.0")
                if "latency_ns" not in run_cols:
                    connection.execute("ALTER TABLE moe_runs ADD COLUMN latency_ns INTEGER NOT NULL DEFAULT 0")

                row = connection.execute("SELECT schema_version FROM moe_schema LIMIT 1").fetchone()
                if row is None:
                    connection.execute("INSERT INTO moe_schema VALUES(?,?)", (2, time.time()))
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "MoE store unavailable") from exc

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _log_audit(
        self,
        connection: sqlite3.Connection,
        run_id: str | None,
        action: str,
        details: Mapping[str, Any],
    ) -> None:
        audit_id = f"aud-{uuid.uuid4().hex[:16]}"
        connection.execute(
            "INSERT INTO moe_audit_log VALUES(?,?,?,?,?)",
            (audit_id, run_id, action, _canonical(details).decode("utf-8"), time.time()),
        )

    def _save_receipt(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        task_kind: str,
        result_digest: str,
        selected_experts: list[str],
    ) -> str:
        receipt_id = f"rcpt-{uuid.uuid4().hex[:16]}"
        connection.execute(
            "INSERT INTO moe_receipts VALUES(?,?,?,?,?,?)",
            (receipt_id, run_id, task_kind, result_digest, json.dumps(selected_experts), time.time()),
        )
        return receipt_id

    def _verify(self, path: Path) -> dict[str, Any]:
        if self.signing_key is None or len(self.signing_key) < 32:
            raise LocalPillarError("SIGNING_KEY_UNAVAILABLE", "expert signing key is unavailable")
        try:
            raw = path.read_bytes()
            if not 1 <= len(raw) <= 4 * 1024 * 1024:
                raise LocalPillarError("RESOURCE_LIMIT", "expert artifact size is invalid")
            wrapper = json.loads(raw)
        except LocalPillarError:
            raise
        except (OSError, ValueError, TypeError) as exc:
            raise LocalPillarError("CORRUPT_EXPERT", "expert artifact cannot be parsed") from exc
        if not isinstance(wrapper, Mapping) or set(wrapper) != {"manifest", "signature"}:
            raise LocalPillarError("CORRUPT_EXPERT", "expert wrapper schema is invalid")
        manifest = wrapper["manifest"]
        signature = wrapper["signature"]
        if not isinstance(manifest, Mapping) or set(manifest) != _FIELDS or not isinstance(signature, str):
            raise LocalPillarError("CORRUPT_EXPERT", "expert manifest schema is invalid")
        expected = hmac.new(self.signing_key, _canonical(manifest), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise LocalPillarError("EXPERT_SIGNATURE_INVALID", "expert signature is invalid")
        if manifest["schema_version"] != 1:
            raise LocalPillarError("EXPERT_SCHEMA_UNSUPPORTED", "expert schema is unsupported")
        expert_id = manifest["expert_id"]
        if not isinstance(expert_id, str) or not 1 <= len(expert_id.strip()) <= 128:
            raise LocalPillarError("CORRUPT_EXPERT", "expert_id is invalid")
        task_kinds = manifest["task_kinds"]
        if not isinstance(task_kinds, list) or not 1 <= len(task_kinds) <= 32:
            raise LocalPillarError("CORRUPT_EXPERT", "task_kinds are invalid")
        try:
            input_dimension = int(manifest["input_dimension"])
            output_dimension = int(manifest["output_dimension"])
            capacity = int(manifest["capacity"])
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("CORRUPT_EXPERT", "expert dimensions are invalid") from exc
        if not 1 <= input_dimension <= 4096 or not 1 <= output_dimension <= 4096 or not 1 <= capacity <= 1_000_000:
            raise LocalPillarError("CORRUPT_EXPERT", "expert dimension or capacity is invalid")
        try:
            weights = np.asarray(manifest["weight_matrix"], dtype=np.float64)
            bias = np.asarray(manifest["bias"], dtype=np.float64)
            routing = np.asarray(manifest["routing_vector"], dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("CORRUPT_EXPERT", "expert weights are invalid") from exc
        if weights.shape != (output_dimension, input_dimension) or bias.shape != (output_dimension,) or routing.shape != (input_dimension,):
            raise LocalPillarError("CORRUPT_EXPERT", "expert tensor shape is invalid")
        if not all(np.all(np.isfinite(item)) for item in (weights, bias, routing)):
            raise LocalPillarError("CORRUPT_EXPERT", "expert weights must be finite")
        return {
            "expert_id": expert_id,
            "version": str(manifest["version"]),
            "task_kinds": {str(item).upper() for item in task_kinds},
            "input_dimension": input_dimension,
            "output_dimension": output_dimension,
            "capacity": capacity,
            "weights": weights,
            "bias": bias,
            "routing": routing,
            "artifact_digest": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        }

    def experts(self) -> list[dict[str, Any]]:
        experts = []
        seen: set[str] = set()
        for path in sorted(self.expert_root.glob("*.expert.json")):
            expert = self._verify(path)
            if expert["expert_id"] in seen:
                raise LocalPillarError("DUPLICATE_EXPERT", "expert_id is duplicated")
            seen.add(expert["expert_id"])
            experts.append(expert)
        return experts

    def health_check(self) -> bool:
        try:
            experts = self.experts()
        except LocalPillarError:
            return False
        groups: dict[tuple[int, int, str], int] = {}
        for expert in experts:
            for task in expert["task_kinds"]:
                key = (expert["input_dimension"], expert["output_dimension"], task)
                groups[key] = groups.get(key, 0) + 1
        return any(count >= 2 for count in groups.values())

    def set_expert_load(self, expert_id: str, load: int) -> None:
        """Explicitly set simulated/active load for an expert."""
        self._expert_load[expert_id] = max(0, int(load))

    def run(self, request: Mapping[str, Any]) -> LocalPillarResult:
        allowed = {
            "action",
            "task_kind",
            "vector",
            "top_k",
            "maximum_quality_regression",
            "temperature",
            "timeout_seconds",
            "active_loads",
        }
        if set(request) - allowed:
            raise LocalPillarError("UNKNOWN_FIELD", "MoE request contains unsupported fields")
        if not {"action", "task_kind", "vector", "top_k"} <= set(request):
            raise LocalPillarError("MISSING_FIELD", "MoE request is incomplete")

        task_kind = str(request["task_kind"]).strip().upper()
        values = request["vector"]
        top_k = request["top_k"]

        try:
            maximum_regression = float(request.get("maximum_quality_regression", 0.1))
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "quality budget must be numeric") from exc
        if type(top_k) is not int or top_k < 2:
            raise LocalPillarError("INVALID_INPUT", "top_k must select at least two experts")
        if not math.isfinite(maximum_regression) or not 0 <= maximum_regression <= 1:
            raise LocalPillarError("INVALID_INPUT", "quality budget must be within 0-1")

        try:
            temperature = float(request.get("temperature", 1.0))
            if not math.isfinite(temperature) or temperature <= 0:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "temperature must be positive numeric") from exc

        try:
            vector = np.asarray(values, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise LocalPillarError("INVALID_INPUT", "vector must be numeric") from exc
        if vector.ndim != 1 or not 1 <= vector.size <= 4096 or not np.all(np.isfinite(vector)):
            raise LocalPillarError("INVALID_INPUT", "vector must be finite and one-dimensional")

        # Update loads if provided in request
        if "active_loads" in request and isinstance(request["active_loads"], Mapping):
            for eid, l in request["active_loads"].items():
                self._expert_load[str(eid)] = max(0, int(l))

        started_total = time.perf_counter_ns()
        compatible = [
            expert
            for expert in self.experts()
            if task_kind in expert["task_kinds"] and expert["input_dimension"] == vector.size
        ]
        if len(compatible) < 2 or top_k > len(compatible):
            raise LocalPillarError("EXPERT_UNAVAILABLE", "not enough compatible signed experts")
        output_dimensions = {item["output_dimension"] for item in compatible}
        if len(output_dimensions) != 1:
            raise LocalPillarError("EXPERT_INCOMPATIBLE", "expert output dimensions differ")

        # Compute cosine similarity routing score for all compatible experts
        scored = []
        vector_norm = max(float(np.linalg.norm(vector)), 1e-12)
        for expert in compatible:
            routing_norm = max(float(np.linalg.norm(expert["routing"])), 1e-12)
            score = float(np.dot(expert["routing"], vector) / (routing_norm * vector_norm))
            scored.append((score, expert))
        scored.sort(key=lambda item: (-item[0], item[1]["expert_id"]))

        # Dynamic capacity constraint and overflow rerouting
        selected: list[tuple[float, dict[str, Any]]] = []
        overflows_occurred: list[dict[str, Any]] = []

        for score, expert in scored:
            eid = expert["expert_id"]
            capacity = expert["capacity"]
            current_load = self._expert_load.get(eid, 0)

            if current_load >= capacity:
                # Capacity exceeded for this candidate, track overflow
                overflows_occurred.append({"expert_id": eid, "capacity": capacity, "load": current_load})
                continue

            selected.append((score, expert))
            if len(selected) == top_k:
                break

        if len(selected) < top_k:
            raise LocalPillarError(
                "CAPACITY_EXCEEDED",
                f"available experts exceeded capacity: needed {top_k}, available {len(selected)}",
            )

        def execute(group: list[tuple[float, dict[str, Any]]]):
            route_scores = np.asarray([item[0] for item in group], dtype=np.float64)
            scaled = (route_scores - np.max(route_scores)) / max(temperature, 1e-4)
            route_weights = np.exp(scaled)
            route_weights /= np.sum(route_weights)
            outputs = []
            metrics = []
            for weight, (_, expert) in zip(route_weights, group, strict=True):
                started = time.perf_counter_ns()
                value = expert["weights"] @ vector + expert["bias"]
                latency = max(1, time.perf_counter_ns() - started)
                outputs.append(weight * value)
                metrics.append((expert, float(weight), latency))
            return np.sum(outputs, axis=0), metrics

        sparse_output, metrics = execute(selected)
        dense_output, _ = execute(scored)
        regression = float(
            np.linalg.norm(sparse_output - dense_output)
            / max(float(np.linalg.norm(dense_output)), 1e-12)
        )
        if regression > maximum_regression:
            raise LocalPillarError("QUALITY_BUDGET_EXCEEDED", "top-k output exceeds dense baseline budget")

        run_latency_ns = time.perf_counter_ns() - started_total
        result_digest = hashlib.sha256(sparse_output.tobytes()).hexdigest()
        run_id = hashlib.sha256(
            _canonical({"task": task_kind, "vector": vector.tolist(), "at": time.time_ns(), "nonce": uuid.uuid4().hex})
        ).hexdigest()

        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                for expert, _, latency in metrics:
                    eid = expert["expert_id"]
                    connection.execute(
                        """
                        INSERT INTO expert_utilization(expert_id, selected_count, execution_count, overflow_count, last_latency_ns, last_used_at)
                        VALUES(?,1,1,0,?,?)
                        ON CONFLICT(expert_id) DO UPDATE SET
                        selected_count=selected_count+1,execution_count=execution_count+1,
                        last_latency_ns=excluded.last_latency_ns,last_used_at=excluded.last_used_at
                        """,
                        (eid, latency, time.time()),
                    )
                for of in overflows_occurred:
                    eid = of["expert_id"]
                    connection.execute(
                        """
                        INSERT INTO expert_utilization(expert_id, selected_count, execution_count, overflow_count, last_latency_ns, last_used_at)
                        VALUES(?,0,0,1,0,?)
                        ON CONFLICT(expert_id) DO UPDATE SET
                        overflow_count=overflow_count+1,last_used_at=excluded.last_used_at
                        """,
                        (eid, time.time()),
                    )
                selected_ids = [item[0]["expert_id"] for item in metrics]
                connection.execute(
                    "INSERT INTO moe_runs VALUES(?,?,?,?,?,?,?)",
                    (run_id, task_kind, json.dumps(selected_ids), result_digest, regression, run_latency_ns, time.time()),
                )
                receipt_id = self._save_receipt(connection, run_id, task_kind, result_digest, selected_ids)
                self._log_audit(
                    connection,
                    run_id,
                    "MOE_ROUTED_AND_EXECUTED",
                    {
                        "task_kind": task_kind,
                        "selected_experts": selected_ids,
                        "overflows": overflows_occurred,
                        "quality_regression": regression,
                        "latency_ns": run_latency_ns,
                    },
                )
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "MoE metrics were not stored") from exc

        return LocalPillarResult(
            "P034",
            "SIGNED_EXPERTS_EXECUTED",
            {
                "run_id": run_id,
                "task_kind": task_kind,
                "selected_experts": [
                    {
                        "expert_id": expert["expert_id"],
                        "version": expert["version"],
                        "artifact_digest": expert["artifact_digest"],
                        "routing_weight": float(weight),
                        "latency_ns": latency,
                    }
                    for expert, weight, latency in metrics
                ],
                "output": sparse_output.tolist(),
                "dense_baseline": dense_output.tolist(),
                "quality_regression": float(regression),
                "experts_available": len(compatible),
                "experts_executed": len(selected),
                "input_bytes": int(vector.nbytes),
                "receipt_id": receipt_id,
                "result_digest": result_digest,
                "overflows": overflows_occurred,
            },
        )

    def utilization(self) -> list[dict[str, Any]]:
        """Read all expert utilization records."""
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM expert_utilization ORDER BY selected_count DESC"
                ).fetchall()
                return [
                    {
                        "expert_id": row["expert_id"],
                        "selected_count": row["selected_count"],
                        "execution_count": row["execution_count"],
                        "overflow_count": row["overflow_count"],
                        "last_latency_ns": row["last_latency_ns"],
                        "last_used_at": row["last_used_at"],
                    }
                    for row in rows
                ]
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "failed to read utilization") from exc

    def history(self, limit: int = 50) -> dict[str, Any]:
        """Read recent MoE runs, receipts, and audit trail."""
        try:
            with self._connect() as connection:
                runs = connection.execute(
                    "SELECT * FROM moe_runs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
                receipts = connection.execute(
                    "SELECT * FROM moe_receipts ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
                audits = connection.execute(
                    "SELECT * FROM moe_audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
                return {
                    "runs": [
                        {
                            "run_id": r["run_id"],
                            "task_kind": r["task_kind"],
                            "selected_experts": json.loads(r["selected_json"]),
                            "result_digest": r["result_digest"],
                            "quality_regression": r["quality_regression"],
                            "latency_ns": r["latency_ns"],
                            "created_at": r["created_at"],
                        }
                        for r in runs
                    ],
                    "receipts": [
                        {
                            "receipt_id": rc["receipt_id"],
                            "run_id": rc["run_id"],
                            "task_kind": rc["task_kind"],
                            "result_digest": rc["result_digest"],
                            "selected_experts": json.loads(rc["selected_experts_json"]),
                            "created_at": rc["created_at"],
                        }
                        for rc in receipts
                    ],
                    "audit_events": [
                        {
                            "audit_id": a["audit_id"],
                            "run_id": a["run_id"],
                            "action": a["action"],
                            "details": json.loads(a["details_json"]),
                            "created_at": a["created_at"],
                        }
                        for a in audits
                    ],
                }
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "failed to read history") from exc

    def verify_integrity(self) -> LocalPillarResult:
        """Verify SQLite integrity and validate receipt digests."""
        try:
            with self._connect() as connection:
                check = connection.execute("PRAGMA quick_check").fetchone()
                if not check or check[0] != "ok":
                    raise LocalPillarError("STORAGE_CORRUPT", "sqlite pragma quick_check failed")

                receipts = connection.execute("SELECT * FROM moe_receipts").fetchall()
                for rc in receipts:
                    run_row = connection.execute(
                        "SELECT result_digest FROM moe_runs WHERE run_id=?", (rc["run_id"],)
                    ).fetchone()
                    if run_row is None or run_row["result_digest"] != rc["result_digest"]:
                        raise LocalPillarError(
                            "STORAGE_CORRUPT", f"receipt digest mismatch for run {rc['run_id']}"
                        )
        except LocalPillarError:
            raise
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_CORRUPT", "storage verification error") from exc

        return LocalPillarResult(
            "P034",
            "INTEGRITY_VERIFIED",
            {"status": "HEALTHY", "receipts_checked": len(receipts)},
        )

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be a mapping")
        action = request.get("action")
        if action == "run":
            return self.run(request)
        if action == "experts":
            return LocalPillarResult(
                "P034",
                "EXPERTS_LISTED",
                {
                    "experts": [
                        {
                            "expert_id": e["expert_id"],
                            "version": e["version"],
                            "task_kinds": list(e["task_kinds"]),
                            "input_dimension": e["input_dimension"],
                            "output_dimension": e["output_dimension"],
                            "capacity": e["capacity"],
                            "artifact_digest": e["artifact_digest"],
                        }
                        for e in self.experts()
                    ]
                },
            )
        if action == "utilization":
            return LocalPillarResult("P034", "UTILIZATION_READ", {"utilization": self.utilization()})
        if action == "history":
            limit = int(request.get("limit", 50))
            return LocalPillarResult("P034", "HISTORY_READ", self.history(limit))
        if action == "set_load":
            self.set_expert_load(str(request["expert_id"]), int(request["load"]))
            return LocalPillarResult("P034", "LOAD_SET", {"expert_id": request["expert_id"], "load": request["load"]})
        if action == "verify_integrity":
            return self.verify_integrity()
        raise LocalPillarError("UNSUPPORTED_ACTION", "MoE action is unsupported")
