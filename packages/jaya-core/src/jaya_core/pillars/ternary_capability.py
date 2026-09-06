"""Canonical Pillar 22 capability backed by a trained ternary artifact."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psutil

from jaya_core.brain_v2.model.ternary_transition import (
    TernaryModelError,
    TrainedTernaryTransitionModel,
)
from jaya_core.capabilities.manifest import CapabilityManifest
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter

from .local_capabilities import LocalPillarError, LocalPillarResult

TERNARY_CAPABILITY_ID = "core.model.ternary-transition"
INTEGRATED_TERNARY_PILLARS = ("P022",)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _strict(request: Mapping[str, Any], allowed: set[str], required: set[str]) -> None:
    unknown = set(request) - allowed
    missing = required - set(request)
    if unknown:
        raise LocalPillarError("UNKNOWN_FIELD", f"unsupported fields: {', '.join(sorted(unknown))}")
    if missing:
        raise LocalPillarError("MISSING_FIELD", f"required fields: {', '.join(sorted(missing))}")


def _text(value: object, field: str, *, maximum: int, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be text")
    normalized = " ".join(value.strip().split())
    if not minimum <= len(normalized) <= maximum:
        raise LocalPillarError(
            "INVALID_INPUT", f"{field} must contain {minimum}-{maximum} characters"
        )
    return normalized


def _integer(value: object, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise LocalPillarError(
            "INVALID_INPUT", f"{field} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _number(value: object, field: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be numeric")
    normalized = float(value)
    if not minimum <= normalized <= maximum:
        raise LocalPillarError(
            "INVALID_INPUT", f"{field} must be in [{minimum}, {maximum}]"
        )
    return normalized


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise LocalPillarError("INVALID_INPUT", f"{field} must be boolean")
    return value


class TernaryPrecisionCapabilityService:
    """Load, execute, benchmark, and audit one trained local ternary model."""

    def __init__(
        self,
        data_dir: Path,
        *,
        artifact_path: Path | str | None,
        expected_sha256: str | None = None,
    ) -> None:
        root = data_dir.expanduser().resolve() / "ternary-precision"
        root.mkdir(parents=True, exist_ok=True)
        self._database = root / "benchmark_receipts.sqlite3"
        self._artifact_path = (
            Path(artifact_path).expanduser().resolve() if artifact_path is not None else None
        )
        self._load_error: str | None = None
        self.model: TrainedTernaryTransitionModel | None = None
        self._initialize_database()
        if self._artifact_path is None:
            self._load_error = "MODEL_NOT_CONFIGURED"
        else:
            try:
                self.model = TrainedTernaryTransitionModel.load(
                    self._artifact_path, expected_sha256=expected_sha256
                )
            except TernaryModelError as exc:
                self._load_error = exc.code

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(self._database, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "benchmark storage is unavailable") from exc
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize_database(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version not in (0, 1):
                    raise LocalPillarError(
                        "STORAGE_VERSION_UNSUPPORTED", "benchmark schema is unsupported"
                    )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ternary_benchmark_receipts(
                        request_id TEXT PRIMARY KEY,
                        request_sha256 TEXT NOT NULL,
                        artifact_sha256 TEXT NOT NULL,
                        result_json TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ternary_receipts_artifact "
                    "ON ternary_benchmark_receipts(artifact_sha256)"
                )
                connection.execute("PRAGMA user_version = 1")
        except LocalPillarError:
            raise
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "benchmark storage is unavailable") from exc

    def health_check(self) -> bool:
        if self.model is None:
            return False
        try:
            with self._connect() as connection:
                return connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except (LocalPillarError, sqlite3.Error):
            return False

    def manifest(self) -> CapabilityManifest:
        return CapabilityManifest(
            capability_id=TERNARY_CAPABILITY_ID,
            version="1.0",
            provider="trained_numpy_ternary_transition_model",
            execution_location="local",
            min_memory_mb=16,
            permissions_required=["persistent_storage", "model_artifact_read"],
            offline_available=True,
            health_status="HEALTHY" if self.health_check() else "UNHEALTHY",
        )

    def status(self) -> dict[str, Any]:
        if self.model is None:
            return {
                "ready": False,
                "code": self._load_error or "MODEL_UNAVAILABLE",
                "model_type": None,
            }
        return {
            "ready": self.health_check(),
            "code": "READY" if self.health_check() else "STORAGE_UNAVAILABLE",
            "model_type": "STATISTICAL_TERNARY_TRANSITION_LM",
            "artifact_sha256": self.model.artifact_sha256,
            "tokenizer_sha256": self.model.tokenizer_sha256,
            "dataset_sha256": self.model.dataset_sha256,
            "training_run_id": self.model.run_id,
            "vocab_size": len(self.model.vocabulary),
            "metrics": dict(self.model.metrics),
        }

    def _require_model(self) -> TrainedTernaryTransitionModel:
        if self.model is None:
            raise LocalPillarError(
                self._load_error or "MODEL_UNAVAILABLE", "trained ternary model is unavailable"
            )
        if not self.health_check():
            raise LocalPillarError("STORAGE_UNAVAILABLE", "ternary capability is unhealthy")
        return self.model

    def _predict(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "text", "top_k"}, {"action", "text"})
        text = _text(request["text"], "text", maximum=32_768)
        top_k = _integer(request.get("top_k", 5), "top_k", minimum=1, maximum=20)
        try:
            result = self._require_model().predict(text, top_k=top_k)
        except TernaryModelError as exc:
            raise LocalPillarError(exc.code, str(exc)) from exc
        return LocalPillarResult("P022", "TERNARY_PREDICTION_COMPLETED", result)

    def _existing_receipt(self, request_id: str, request_sha256: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT request_sha256, result_json FROM ternary_benchmark_receipts "
                    "WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "benchmark storage is unavailable") from exc
        if row is None:
            return None
        if row["request_sha256"] != request_sha256:
            raise LocalPillarError(
                "IDEMPOTENCY_CONFLICT", "request_id is already bound to another benchmark"
            )
        try:
            result = json.loads(row["result_json"])
        except json.JSONDecodeError as exc:
            raise LocalPillarError("STORAGE_CORRUPT", "benchmark receipt is corrupt") from exc
        result["replayed"] = True
        return result

    def _benchmark(self, request: Mapping[str, Any]) -> LocalPillarResult:
        allowed = {
            "action",
            "request_id",
            "text",
            "top_k",
            "iterations",
            "timeout_seconds",
            "measure_energy",
        }
        _strict(request, allowed, {"action", "request_id", "text"})
        request_id = _text(request["request_id"], "request_id", maximum=160)
        text = _text(request["text"], "text", maximum=32_768)
        top_k = _integer(request.get("top_k", 5), "top_k", minimum=1, maximum=20)
        iterations = _integer(
            request.get("iterations", 100), "iterations", minimum=1, maximum=10_000
        )
        timeout_seconds = _number(
            request.get("timeout_seconds", 10.0),
            "timeout_seconds",
            minimum=0.01,
            maximum=120.0,
        )
        measure_energy = _boolean(request.get("measure_energy", False), "measure_energy")
        model = self._require_model()
        request_material = {
            "text": text,
            "top_k": top_k,
            "iterations": iterations,
            "timeout_seconds": timeout_seconds,
            "measure_energy": measure_energy,
            "artifact_sha256": model.artifact_sha256,
        }
        request_sha256 = hashlib.sha256(
            _canonical_json(request_material).encode("utf-8")
        ).hexdigest()
        existing = self._existing_receipt(request_id, request_sha256)
        if existing is not None:
            return LocalPillarResult("P022", "TERNARY_BENCHMARK_REPLAYED", existing)

        energy_meter = WindowsEmiEnergyMeter() if measure_energy else None
        energy_start = None
        energy_error: EnergyMeterError | None = None
        if energy_meter is not None:
            try:
                energy_start = energy_meter.sample()
            except EnergyMeterError as exc:
                energy_error = exc
        process = psutil.Process()
        rss_before = process.memory_info().rss
        started = time.perf_counter()
        prediction: dict[str, Any] | None = None
        for index in range(iterations):
            prediction = model.predict(text, top_k=top_k)
            if index % 32 == 0 and time.perf_counter() - started > timeout_seconds:
                raise LocalPillarError("TIMEOUT", "ternary benchmark exceeded its timeout")
        elapsed = time.perf_counter() - started
        if elapsed > timeout_seconds:
            raise LocalPillarError("TIMEOUT", "ternary benchmark exceeded its timeout")
        rss_after = process.memory_info().rss
        energy_measurement: dict[str, Any] = {
            "status": "NOT_REQUESTED",
            "joules": None,
        }
        if energy_meter is not None and energy_start is not None:
            try:
                measured = energy_meter.measure(energy_start, energy_meter.sample())
                energy_measurement = {
                    **measured.to_dict(),
                    "joules_per_inference": measured.joules / iterations,
                }
            except EnergyMeterError as exc:
                energy_error = exc
        if energy_meter is not None and energy_error is not None:
            energy_measurement = {
                "status": energy_error.code,
                "joules": None,
            }
        if prediction is None:
            raise LocalPillarError("BENCHMARK_FAILED", "benchmark executed no inference")
        prediction_sha256 = hashlib.sha256(
            _canonical_json(prediction).encode("utf-8")
        ).hexdigest()
        try:
            artifact_size = self._artifact_path.stat().st_size if self._artifact_path else 0
        except OSError as exc:
            raise LocalPillarError("ARTIFACT_MISSING", "ternary artifact became unavailable") from exc
        result = {
            "request_id": request_id,
            "request_sha256": request_sha256,
            "artifact_sha256": model.artifact_sha256,
            "dataset_sha256": model.dataset_sha256,
            "prediction_sha256": prediction_sha256,
            "iterations": iterations,
            "elapsed_seconds": elapsed,
            "mean_latency_ms": elapsed * 1_000.0 / iterations,
            "inferences_per_second": iterations / elapsed,
            "rss_before_bytes": rss_before,
            "rss_after_bytes": rss_after,
            "rss_delta_bytes": rss_after - rss_before,
            "artifact_size_bytes": artifact_size,
            "quality_metrics": dict(model.metrics),
            "energy_measurement": energy_measurement,
            "prediction": prediction,
            "replayed": False,
        }
        result_json = _canonical_json(result)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO ternary_benchmark_receipts("
                    "request_id, request_sha256, artifact_sha256, result_json"
                    ") VALUES (?, ?, ?, ?)",
                    (request_id, request_sha256, model.artifact_sha256, result_json),
                )
        except sqlite3.IntegrityError as exc:
            replay = self._existing_receipt(request_id, request_sha256)
            if replay is None:
                raise LocalPillarError("STORAGE_CONFLICT", "benchmark receipt conflicted") from exc
            return LocalPillarResult("P022", "TERNARY_BENCHMARK_REPLAYED", replay)
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "benchmark receipt could not be stored") from exc
        return LocalPillarResult("P022", "TERNARY_BENCHMARK_COMPLETED", result)

    def _receipt(self, request: Mapping[str, Any]) -> LocalPillarResult:
        _strict(request, {"action", "request_id"}, {"action", "request_id"})
        request_id = _text(request["request_id"], "request_id", maximum=160)
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT result_json FROM ternary_benchmark_receipts WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise LocalPillarError("STORAGE_UNAVAILABLE", "benchmark storage is unavailable") from exc
        if row is None:
            raise LocalPillarError("RECEIPT_NOT_FOUND", "benchmark receipt was not found")
        try:
            result = json.loads(row["result_json"])
        except json.JSONDecodeError as exc:
            raise LocalPillarError("STORAGE_CORRUPT", "benchmark receipt is corrupt") from exc
        return LocalPillarResult("P022", "TERNARY_BENCHMARK_RECEIPT", result)

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        action = request.get("action")
        if action == "predict":
            return self._predict(request)
        if action == "benchmark":
            return self._benchmark(request)
        if action == "receipt":
            return self._receipt(request)
        if action == "status":
            _strict(request, {"action"}, {"action"})
            return LocalPillarResult("P022", "TERNARY_MODEL_STATUS", self.status())
        raise LocalPillarError("UNSUPPORTED_ACTION", "ternary capability action is unsupported")


__all__ = [
    "INTEGRATED_TERNARY_PILLARS",
    "TERNARY_CAPABILITY_ID",
    "TernaryPrecisionCapabilityService",
]
