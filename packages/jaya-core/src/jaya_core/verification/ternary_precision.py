"""Representative verification runner for the Pillar 22 vertical slice."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from jaya_core.brain_v2.model.ternary_transition import (
    TernaryModelError,
    TrainedTernaryTransitionModel,
    evaluate_ternary_transition_model,
    train_ternary_transition_model,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars import DynamicPillarRegistry, PillarRuntimeView
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.ternary_capability import TERNARY_CAPABILITY_ID

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_EXPECTED_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "training_glob",
    "training_exclude",
    "evaluation_glob",
    "training",
    "evaluation_gates",
    "runtime_benchmark",
    "soak",
    "artifact_max_bytes",
    "source_files",
}


class TernaryVerificationError(RuntimeError):
    """Stable verification failure carrying the failed gate."""

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


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _load_profile(path: Path) -> dict[str, Any]:
    try:
        raw = path.expanduser().resolve().read_bytes()
        profile = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TernaryVerificationError("PROFILE_INVALID", "verification profile is invalid") from exc
    if not isinstance(profile, dict) or set(profile) != _EXPECTED_PROFILE_FIELDS:
        raise TernaryVerificationError("PROFILE_INVALID", "verification profile fields are invalid")
    if profile["schema_version"] != 1 or not _PROFILE_ID.fullmatch(
        str(profile["profile_id"])
    ):
        raise TernaryVerificationError("PROFILE_INVALID", "verification profile contract is invalid")
    if not isinstance(profile["scope"], str) or not profile["scope"].strip():
        raise TernaryVerificationError("PROFILE_INVALID", "verification scope is missing")
    for field in ("training_glob", "evaluation_glob"):
        value = profile[field]
        if not isinstance(value, str) or Path(value).is_absolute() or ".." in Path(value).parts:
            raise TernaryVerificationError("PROFILE_INVALID", f"{field} must stay inside repository")
    if (
        not isinstance(profile["training_exclude"], list)
        or any(not isinstance(item, str) or Path(item).name != item for item in profile["training_exclude"])
        or not isinstance(profile["source_files"], list)
        or not profile["source_files"]
    ):
        raise TernaryVerificationError("PROFILE_INVALID", "profile source selection is invalid")
    for section in ("training", "evaluation_gates", "runtime_benchmark", "soak"):
        if not isinstance(profile[section], dict):
            raise TernaryVerificationError("PROFILE_INVALID", f"{section} must be an object")
    return {**profile, "profile_sha256": _digest_bytes(raw)}


def _resolve_profile_files(root: Path, profile: dict[str, Any]) -> tuple[list[Path], list[Path]]:
    training = sorted(root.glob(profile["training_glob"]))
    excluded = set(profile["training_exclude"])
    training = [item.resolve() for item in training if item.is_file() and item.name not in excluded]
    evaluation = sorted(item.resolve() for item in root.glob(profile["evaluation_glob"]) if item.is_file())
    if not training or not evaluation:
        raise TernaryVerificationError("CORPUS_MISSING", "verification corpus selection is empty")
    if set(training) & set(evaluation):
        raise TernaryVerificationError("CORPUS_OVERLAP", "training and evaluation files overlap")
    return training, evaluation


def _source_bundle_sha256(root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
            raw = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise TernaryVerificationError(
                "SOURCE_UNAVAILABLE", "verification source bundle is unavailable"
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
            raise TernaryVerificationError("GIT_UNAVAILABLE", "git version could not be read") from exc
        if completed.returncode != 0:
            raise TernaryVerificationError("GIT_UNAVAILABLE", "git version could not be read")
        return completed.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD"),
        "worktree_dirty": bool(run("status", "--porcelain")),
    }


def _cpu_name() -> str:
    if platform.system() == "Windows":
        try:
            import winreg

            key_path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        except OSError:
            return platform.processor() or "UNKNOWN"
    return platform.processor() or "UNKNOWN"


def _host_fingerprint() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "cpu": _cpu_name(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "ram_bytes": psutil.virtual_memory().total,
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "psutil": psutil.__version__,
    }


def _expect_local_error(
    runtime: JayaCoreRuntime, request: dict[str, Any], expected_code: str
) -> dict[str, Any]:
    try:
        runtime.execute_local_pillar(TERNARY_CAPABILITY_ID, request)
    except LocalPillarError as exc:
        if exc.code != expected_code:
            raise TernaryVerificationError(
                "FAULT_DRILL_FAILED", "runtime returned an unexpected failure code"
            ) from exc
        return exc.to_dict()
    raise TernaryVerificationError("FAULT_DRILL_FAILED", "runtime accepted an invalid request")


def _corruption_drill(artifact_path: Path, artifact_sha256: str, run_root: Path) -> str:
    with tempfile.TemporaryDirectory(dir=run_root) as temporary:
        corrupt = Path(temporary) / "corrupt-model.json"
        corrupt.write_bytes(artifact_path.read_bytes() + b"x")
        try:
            TrainedTernaryTransitionModel.load(corrupt, expected_sha256=artifact_sha256)
        except TernaryModelError as exc:
            if exc.code != "CHECKSUM_MISMATCH":
                raise TernaryVerificationError(
                    "FAULT_DRILL_FAILED", "corrupt artifact returned an unexpected error"
                ) from exc
            return exc.code
    raise TernaryVerificationError("FAULT_DRILL_FAILED", "corrupt artifact was accepted")


def _soak_and_energy(
    model: TrainedTernaryTransitionModel, config: dict[str, Any]
) -> dict[str, Any]:
    text = str(config["text"])
    top_k = int(config["top_k"])
    iterations = int(config["iterations"])
    if not 10_000 <= iterations <= 1_000_000:
        raise TernaryVerificationError("PROFILE_INVALID", "soak iterations are out of range")
    meter = WindowsEmiEnergyMeter()
    try:
        energy_start = meter.sample()
    except EnergyMeterError as exc:
        raise TernaryVerificationError("ENERGY_REQUIRED", "host energy counter is unavailable") from exc
    process = psutil.Process()
    rss_before = process.memory_info().rss
    started = time.perf_counter()
    expected_digest: str | None = None
    errors = 0
    for _ in range(iterations):
        try:
            prediction = model.predict(text, top_k=top_k)
            prediction_digest = _digest_bytes(_canonical_json(prediction))
            if expected_digest is None:
                expected_digest = prediction_digest
            elif prediction_digest != expected_digest:
                errors += 1
        except TernaryModelError:
            errors += 1
    elapsed = time.perf_counter() - started
    rss_after = process.memory_info().rss
    try:
        energy = meter.measure(energy_start, meter.sample())
    except EnergyMeterError as exc:
        raise TernaryVerificationError("ENERGY_REQUIRED", "energy measurement failed") from exc
    energy_payload = {
        **energy.to_dict(),
        "joules_per_inference": energy.joules / iterations,
    }
    return {
        "iterations": iterations,
        "errors": errors,
        "elapsed_seconds": elapsed,
        "mean_latency_ms": elapsed * 1_000.0 / iterations,
        "inferences_per_second": iterations / elapsed,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "rss_growth_bytes": max(0, rss_after - rss_before),
        "prediction_sha256": expected_digest,
        "energy": energy_payload,
    }


def _gate(name: str, passed: bool, actual: Any, limit: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "limit": limit}


def verify_ternary_precision(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Run the real P22 verification profile and persist checksum-bound evidence."""

    normalized_approver = " ".join(str(approver).strip().split())
    if not 3 <= len(normalized_approver) <= 160:
        raise TernaryVerificationError("APPROVAL_REQUIRED", "an approver role is required")
    root = repository_root.expanduser().resolve()
    profile = _load_profile(profile_path)
    host = _host_fingerprint()
    if host["os"] != profile["supported_os"]:
        raise TernaryVerificationError("HOST_UNSUPPORTED", "host does not match verification profile")
    training_files, evaluation_files = _resolve_profile_files(root, profile)
    run_id = f"p22-verified-{uuid.uuid4().hex}"
    run_root = output_directory.expanduser().resolve() / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    artifact_path = run_root / "p22-ternary-transition.json"
    training_config = profile["training"]
    training = train_ternary_transition_model(
        training_files,
        artifact_path,
        max_vocab=int(training_config["max_vocab"]),
        holdout_ratio=float(training_config["holdout_ratio"]),
        smoothing=float(training_config["smoothing"]),
        max_perplexity_ratio=float(training_config["max_perplexity_ratio"]),
        max_top1_accuracy_drop=float(training_config["max_top1_accuracy_drop"]),
        run_id=run_id,
    )
    model = TrainedTernaryTransitionModel.load(
        artifact_path, expected_sha256=training.artifact_sha256
    )
    evaluation_config = profile["evaluation_gates"]
    evaluation = evaluate_ternary_transition_model(
        model,
        training_files,
        evaluation_files,
        max_perplexity_ratio=float(evaluation_config["max_perplexity_ratio"]),
        max_top1_accuracy_drop=float(evaluation_config["max_top1_accuracy_drop"]),
    )

    baseline_manifest = (
        root / "packages" / "jaya-core" / "src" / "jaya_core" / "contracts" / "40_pillars.yaml"
    )
    registry = DynamicPillarRegistry(
        database_path=run_root / "pillar_registry.sqlite3",
        manifest_paths=(baseline_manifest,),
    )
    runtime = JayaCoreRuntime(
        db_path=run_root / "core.sqlite3",
        local_pillar_data_dir=run_root / "pillar-capabilities",
        pillar_registry=registry,
        ternary_model_path=artifact_path,
        ternary_model_sha256=training.artifact_sha256,
    )
    runtime.pillar_runtime_view = PillarRuntimeView(registry, runtime.capability_registry)
    benchmark_config = profile["runtime_benchmark"]
    benchmark_request_id = f"verification-benchmark-{uuid.uuid4().hex}"
    try:
        prediction = runtime.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {
                "action": "predict",
                "text": benchmark_config["text"],
                "top_k": int(benchmark_config["top_k"]),
            },
        )
        benchmark = runtime.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {
                "action": "benchmark",
                "request_id": benchmark_request_id,
                "text": benchmark_config["text"],
                "top_k": int(benchmark_config["top_k"]),
                "iterations": int(benchmark_config["iterations"]),
                "timeout_seconds": float(benchmark_config["timeout_seconds"]),
                "measure_energy": True,
            },
        )
        invalid_input = _expect_local_error(
            runtime,
            {"action": "predict", "text": "", "top_k": 5},
            "INVALID_INPUT",
        )
        unknown_field = _expect_local_error(
            runtime,
            {"action": "predict", "text": "ternary", "unexpected": True},
            "UNKNOWN_FIELD",
        )
        timeout = _expect_local_error(
            runtime,
            {
                "action": "benchmark",
                "request_id": f"verification-timeout-{uuid.uuid4().hex}",
                "text": "ternary runtime",
                "iterations": 10_000,
                "timeout_seconds": 0.01,
            },
            "TIMEOUT",
        )
        p22_runtime = next(
            item
            for item in runtime.operational_snapshot()["pillars"]["pillars"]
            if item["pillar_id"] == "P022"
        )
    finally:
        runtime.close()

    restarted = JayaCoreRuntime(
        db_path=run_root / "core.sqlite3",
        local_pillar_data_dir=run_root / "pillar-capabilities",
        ternary_model_path=artifact_path,
        ternary_model_sha256=training.artifact_sha256,
    )
    try:
        receipt = restarted.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {"action": "receipt", "request_id": benchmark_request_id},
        )
    finally:
        restarted.close()

    soak = _soak_and_energy(model, profile["soak"])
    corruption_code = _corruption_drill(artifact_path, training.artifact_sha256, run_root)
    soak_config = profile["soak"]
    gates = [
        _gate("training_quality", training.metrics["quality_gate_passed"] is True, True, True),
        _gate(
            "evaluation_quality",
            evaluation.metrics["quality_gate_passed"] is True,
            evaluation.metrics["quality_gate_passed"],
            True,
        ),
        _gate(
            "evaluation_sources",
            evaluation.source_count >= int(evaluation_config["minimum_sources"]),
            evaluation.source_count,
            {"minimum": int(evaluation_config["minimum_sources"])},
        ),
        _gate(
            "evaluation_pairs",
            evaluation.pair_count >= int(evaluation_config["minimum_pairs"]),
            evaluation.pair_count,
            {"minimum": int(evaluation_config["minimum_pairs"])},
        ),
        _gate(
            "artifact_size",
            artifact_path.stat().st_size <= int(profile["artifact_max_bytes"]),
            artifact_path.stat().st_size,
            {"maximum": int(profile["artifact_max_bytes"])},
        ),
        _gate("runtime_available", p22_runtime["runtime_available"] is True, True, True),
        _gate(
            "runtime_energy",
            benchmark.data["energy_measurement"]["status"] == "MEASURED_HOST_PACKAGE",
            benchmark.data["energy_measurement"]["status"],
            "MEASURED_HOST_PACKAGE",
        ),
        _gate("restart_receipt", receipt.data["artifact_sha256"] == training.artifact_sha256, True, True),
        _gate("fault_paths", corruption_code == "CHECKSUM_MISMATCH", corruption_code, "CHECKSUM_MISMATCH"),
        _gate("soak_errors", soak["errors"] == 0, soak["errors"], 0),
        _gate(
            "soak_duration",
            soak["elapsed_seconds"] >= float(soak_config["minimum_elapsed_seconds"]),
            soak["elapsed_seconds"],
            {"minimum": float(soak_config["minimum_elapsed_seconds"])},
        ),
        _gate(
            "soak_latency",
            soak["mean_latency_ms"] <= float(soak_config["max_mean_latency_ms"]),
            soak["mean_latency_ms"],
            {"maximum": float(soak_config["max_mean_latency_ms"])},
        ),
        _gate(
            "soak_rss_growth",
            soak["rss_growth_bytes"] <= int(soak_config["max_rss_growth_bytes"]),
            soak["rss_growth_bytes"],
            {"maximum": int(soak_config["max_rss_growth_bytes"])},
        ),
        _gate(
            "package_energy_per_inference",
            soak["energy"]["joules_per_inference"]
            <= float(soak_config["max_package_joules_per_inference"]),
            soak["energy"]["joules_per_inference"],
            {"maximum": float(soak_config["max_package_joules_per_inference"])},
        ),
    ]
    verified = all(item["passed"] for item in gates)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE" if verified else "FAILED",
        "pillar": "P022",
        "scope": profile["scope"],
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "verified_at": datetime.now(UTC).isoformat(),
        "approval": {
            "approver": normalized_approver,
            "basis": "explicit repository-owner request to execute representative verification",
        },
        "version": {
            **_git_version(root),
            "source_bundle_sha256": _source_bundle_sha256(root, profile["source_files"]),
        },
        "environment": host,
        "corpora": {
            "training_files": [path.relative_to(root).as_posix() for path in training_files],
            "evaluation_files": [path.relative_to(root).as_posix() for path in evaluation_files],
            "disjoint": True,
        },
        "training": {
            "artifact_path": artifact_path.name,
            "artifact_sha256": training.artifact_sha256,
            "tokenizer_sha256": training.tokenizer_sha256,
            "dataset_sha256": training.dataset_sha256,
            "source_count": training.source_count,
            "train_sequences": training.train_sequences,
            "holdout_sequences": training.holdout_sequences,
            "metrics": training.metrics,
        },
        "independent_evaluation": {
            "dataset_sha256": evaluation.evaluation_dataset_sha256,
            "source_count": evaluation.source_count,
            "sequence_count": evaluation.sequence_count,
            "pair_count": evaluation.pair_count,
            "metrics": evaluation.metrics,
        },
        "runtime": {
            "prediction": prediction.to_dict(),
            "benchmark": benchmark.to_dict(),
            "restart_receipt": receipt.to_dict(),
            "pillar": p22_runtime,
        },
        "fault_drills": {
            "invalid_input": invalid_input,
            "unknown_field": unknown_field,
            "timeout": timeout,
            "corrupt_artifact": corruption_code,
        },
        "soak": soak,
        "gates": gates,
        "limitations": [
            "verified only for the named Windows CPU and JAYA engineering-document profile",
            "package energy includes the complete CPU package and is not process-attributed",
            "evaluation files are project documents, not an external general-language benchmark",
            "the model is a statistical transition model, not a neural or generative language model",
            "the worktree source is bound by digest because verification may run before commit",
        ],
        "rollback": {
            "action": "restore P022 manifest status to INTEGRATED and remove ternary model environment configuration",
            "data_compatibility": "benchmark receipts and model artifacts remain readable",
        },
    }
    report_path = run_root / "verified-ternary-report.json"
    raw_report = _canonical_json(report)
    report_path.write_bytes(raw_report)
    Path(f"{report_path}.sha256").write_text(f"{_digest_bytes(raw_report)}\n", encoding="ascii")
    if not verified:
        failed = ", ".join(item["name"] for item in gates if not item["passed"])
        raise TernaryVerificationError("VERIFICATION_FAILED", f"verification gates failed: {failed}")
    return report_path, report


__all__ = ["TernaryVerificationError", "verify_ternary_precision"]
