"""Real training, artifact, runtime, failure, and persistence coverage for P22."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np
import pytest

from jaya_core.brain_v2.model.ternary_transition import (
    TernaryModelError,
    TernaryTrainingResult,
    TrainedTernaryTransitionModel,
    evaluate_ternary_transition_model,
    train_ternary_transition_model,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.core_config import ConfigurationError, CoreConfig
from jaya_core.observability.energy_meter import EnergySample, WindowsEmiEnergyMeter
from jaya_core.pillars import DynamicPillarRegistry, PillarRuntimeView, load_manifest
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.ternary_capability import TERNARY_CAPABILITY_ID

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "packages" / "jaya-core" / "src" / "jaya_core" / "contracts" / "40_pillars.yaml"


@pytest.fixture(scope="module")
def trained_artifact(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, TernaryTrainingResult]:
    root = tmp_path_factory.mktemp("trained-ternary")
    corpus = root / "corpus.txt"
    patterns = (
        "model ternary menghemat memori saat inferensi lokal.",
        "model ternary menggunakan bobot minus satu nol dan satu.",
        "runtime lokal memuat artifact dengan checksum yang terikat.",
        "benchmark mengukur latency memori ukuran dan kualitas.",
        "penelitian membutuhkan bukti pengukuran dan provenance.",
        "input nyata menghasilkan prediksi token dari bobot terlatih.",
    )
    corpus.write_text("\n".join(patterns * 24), encoding="utf-8")
    artifact = root / "model.ternary.json"
    result = train_ternary_transition_model(
        (corpus,),
        artifact,
        max_vocab=128,
        max_perplexity_ratio=10.0,
        max_top1_accuracy_drop=1.0,
        run_id="pytest-real-training",
    )
    assert result.metrics["quality_gate_passed"] is True
    return artifact, result


def test_p22_manifest_is_bound_to_integrated_runtime_capability() -> None:
    p22 = {item.pillar_id: item for item in load_manifest(BASELINE)}["P022"]

    assert p22.initial_status.value == "VERIFIED"
    assert p22.capability_id == TERNARY_CAPABILITY_ID
    assert p22.dependencies == ("P002", "P005", "P021")


def test_real_training_binds_corpus_tokenizer_weights_and_quality_metrics(
    trained_artifact: tuple[Path, TernaryTrainingResult],
) -> None:
    artifact, result = trained_artifact
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    model = TrainedTernaryTransitionModel.load(
        artifact, expected_sha256=result.artifact_sha256
    )

    assert payload["weight_origin"] == "trained_from_explicit_corpus"
    assert payload["schema_version"] == 2
    assert payload["training_provenance"]["holdout_ratio"] == 0.2
    assert payload["training_provenance"]["dataset_sha256"] == result.dataset_sha256
    assert payload["tokenizer"]["sha256"] == result.tokenizer_sha256
    assert set(np.unique(model.weights)).issubset({-1, 0, 1})
    assert payload["metrics"]["holdout_pairs"] > 0
    assert payload["metrics"]["baseline_perplexity"] > 0
    assert payload["metrics"]["ternary_perplexity"] > 0
    first = model.predict("model ternary", top_k=3)
    second = model.predict("bukti pengukuran", top_k=3)
    assert first["context_token"] == "ternary"
    assert second["context_token"] == "pengukuran"
    assert first["predictions"]
    assert second["predictions"]
    assert all(item["ternary_weight"] in {-1, 0, 1} for item in first["predictions"])


def test_independent_evaluation_reconstructs_baseline_and_rejects_overlap(
    tmp_path: Path, trained_artifact: tuple[Path, TernaryTrainingResult]
) -> None:
    artifact, training = trained_artifact
    training_corpus = artifact.parent / "corpus.txt"
    evaluation_corpus = tmp_path / "evaluation.txt"
    evaluation_corpus.write_text(
        "model ternary menjalankan inferensi.\n"
        "artifact checksum menjaga integritas runtime.\n"
        "benchmark mengukur kualitas dan sumber daya.\n" * 16,
        encoding="utf-8",
    )
    model = TrainedTernaryTransitionModel.load(
        artifact, expected_sha256=training.artifact_sha256
    )

    evaluation = evaluate_ternary_transition_model(
        model,
        (training_corpus,),
        (evaluation_corpus,),
        max_perplexity_ratio=10.0,
        max_top1_accuracy_drop=1.0,
    )

    assert evaluation.source_count == 1
    assert evaluation.pair_count > 0
    assert evaluation.metrics["quality_gate_passed"] is True
    with pytest.raises(TernaryModelError) as overlap:
        evaluate_ternary_transition_model(
            model,
            (training_corpus,),
            (training_corpus,),
            max_perplexity_ratio=10.0,
            max_top1_accuracy_drop=1.0,
        )
    assert overlap.value.code == "CORPUS_OVERLAP"


def test_windows_emi_conversion_uses_picowatt_hour_package_delta() -> None:
    start = EnergySample(
        captured_at="2026-08-29T00:00:00+00:00",
        monotonic_ns=1_000_000_000,
        energy_picowatt_hours=5_000_000_000,
        channels=("RAPL_Package0_PKG",),
    )
    end = EnergySample(
        captured_at="2026-08-29T00:00:02+00:00",
        monotonic_ns=3_000_000_000,
        energy_picowatt_hours=6_000_000_000,
        channels=("RAPL_Package0_PKG",),
    )

    measurement = WindowsEmiEnergyMeter.measure(start, end)

    assert measurement.joules == pytest.approx(3.6)
    assert measurement.average_package_watts == pytest.approx(1.8)


def test_loader_rejects_corruption_and_failed_quality_gate(
    tmp_path: Path, trained_artifact: tuple[Path, TernaryTrainingResult]
) -> None:
    source, _ = trained_artifact
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_bytes(source.read_bytes() + b"x")
    Path(f"{corrupt}.sha256").write_text(
        Path(f"{source}.sha256").read_text(encoding="ascii"), encoding="ascii"
    )
    with pytest.raises(TernaryModelError) as checksum:
        TrainedTernaryTransitionModel.load(corrupt)
    assert checksum.value.code == "CHECKSUM_MISMATCH"

    rejected = tmp_path / "quality-rejected.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["metrics"]["quality_gate_passed"] = False
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    rejected.write_bytes(raw)
    Path(f"{rejected}.sha256").write_text(
        f"sha256:{hashlib.sha256(raw).hexdigest()}\n", encoding="ascii"
    )
    with pytest.raises(TernaryModelError) as quality:
        TrainedTernaryTransitionModel.load(rejected)
    assert quality.value.code == "QUALITY_GATE_FAILED"


def test_runtime_executes_benchmark_and_persists_receipt_after_restart(
    tmp_path: Path, trained_artifact: tuple[Path, TernaryTrainingResult]
) -> None:
    artifact, training = trained_artifact
    registry = DynamicPillarRegistry(
        database_path=tmp_path / "pillar-registry.sqlite3",
        manifest_paths=(BASELINE,),
    )
    first = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
        pillar_registry=registry,
        ternary_model_path=artifact,
        ternary_model_sha256=training.artifact_sha256,
    )
    first.pillar_runtime_view = PillarRuntimeView(registry, first.capability_registry)
    try:
        predicted = first.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {"action": "predict", "text": "model ternary", "top_k": 4},
        )
        benchmark = first.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {
                "action": "benchmark",
                "request_id": "p22-benchmark-001",
                "text": "runtime lokal",
                "iterations": 20,
                "timeout_seconds": 5.0,
            },
        )
        p22 = next(
            item
            for item in first.operational_snapshot()["pillars"]["pillars"]
            if item["pillar_id"] == "P022"
        )
        assert predicted.code == "TERNARY_PREDICTION_COMPLETED"
        assert benchmark.data["mean_latency_ms"] > 0
        assert benchmark.data["inferences_per_second"] > 0
        assert benchmark.data["artifact_size_bytes"] == artifact.stat().st_size
        assert benchmark.data["energy_measurement"]["status"] == "NOT_REQUESTED"
        assert p22["runtime_available"] is True
        with pytest.raises(LocalPillarError) as duplicate:
            first.execute_local_pillar(
                TERNARY_CAPABILITY_ID,
                {
                    "action": "benchmark",
                    "request_id": "p22-benchmark-001",
                    "text": "different request material",
                    "iterations": 20,
                    "timeout_seconds": 5.0,
                },
            )
        assert duplicate.value.code == "IDEMPOTENCY_CONFLICT"
    finally:
        first.close()

    restarted = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
        ternary_model_path=artifact,
        ternary_model_sha256=training.artifact_sha256,
    )
    try:
        receipt = restarted.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {"action": "receipt", "request_id": "p22-benchmark-001"},
        )
        replay = restarted.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {
                "action": "benchmark",
                "request_id": "p22-benchmark-001",
                "text": "runtime lokal",
                "iterations": 20,
                "timeout_seconds": 5.0,
            },
        )
        assert receipt.data["artifact_sha256"] == training.artifact_sha256
        assert replay.code == "TERNARY_BENCHMARK_REPLAYED"
        assert replay.data["replayed"] is True
    finally:
        restarted.close()

    receipt_database = (
        tmp_path / "pillars" / "ternary-precision" / "benchmark_receipts.sqlite3"
    )
    with closing(sqlite3.connect(receipt_database)) as connection, connection:
        connection.execute(
            "UPDATE ternary_benchmark_receipts SET result_json = ? WHERE request_id = ?",
            ("not-json", "p22-benchmark-001"),
        )
    corrupted = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
        ternary_model_path=artifact,
        ternary_model_sha256=training.artifact_sha256,
    )
    try:
        with pytest.raises(LocalPillarError) as corruption:
            corrupted.execute_local_pillar(
                TERNARY_CAPABILITY_ID,
                {"action": "receipt", "request_id": "p22-benchmark-001"},
            )
        assert corruption.value.code == "STORAGE_CORRUPT"
    finally:
        corrupted.close()

    moved_database = receipt_database.with_suffix(".closed.sqlite3")
    receipt_database.replace(moved_database)
    assert moved_database.is_file()


def test_runtime_fails_closed_without_model_and_validates_failure_paths(
    tmp_path: Path, trained_artifact: tuple[Path, TernaryTrainingResult]
) -> None:
    unavailable = JayaCoreRuntime(
        db_path=tmp_path / "unavailable-core.sqlite3",
        local_pillar_data_dir=tmp_path / "unavailable-pillars",
    )
    try:
        assert unavailable.capability_registry.lookup(
            TERNARY_CAPABILITY_ID
        ).health_status == "UNHEALTHY"
        with pytest.raises(LocalPillarError) as missing:
            unavailable.execute_local_pillar(
                TERNARY_CAPABILITY_ID, {"action": "predict", "text": "model"}
            )
        assert missing.value.code == "CAPABILITY_UNAVAILABLE"
    finally:
        unavailable.close()

    artifact, training = trained_artifact
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "failure-core.sqlite3",
        local_pillar_data_dir=tmp_path / "failure-pillars",
        ternary_model_path=artifact,
        ternary_model_sha256=training.artifact_sha256,
    )
    try:
        with pytest.raises(LocalPillarError) as unknown:
            runtime.execute_local_pillar(
                TERNARY_CAPABILITY_ID,
                {"action": "predict", "text": "model", "unexpected": True},
            )
        assert unknown.value.code == "UNKNOWN_FIELD"
        with pytest.raises(LocalPillarError) as timeout:
            runtime.execute_local_pillar(
                TERNARY_CAPABILITY_ID,
                {
                    "action": "benchmark",
                    "request_id": "timeout-benchmark",
                    "text": "model ternary",
                    "iterations": 10_000,
                    "timeout_seconds": 0.01,
                },
            )
        assert timeout.value.code == "TIMEOUT"
    finally:
        runtime.close()


def test_core_config_validates_and_redacts_ternary_artifact_configuration(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "model.json"
    digest = "sha256:" + "a" * 64
    config = CoreConfig.from_env(
        {
            "JAYA_ENVIRONMENT": "test",
            "JAYA_CORE_DATA_DIR": str(tmp_path),
            "JAYA_TERNARY_MODEL_PATH": str(artifact),
            "JAYA_TERNARY_MODEL_SHA256": digest,
        },
        core_dir=ROOT,
    )

    assert config.ternary_model_path == artifact.resolve()
    assert config.ternary_model_sha256 == digest
    assert config.to_safe_dict()["ternary_model_configured"] is True
    assert config.to_safe_dict()["ternary_model_checksum_configured"] is True
    with pytest.raises(ConfigurationError) as invalid:
        CoreConfig.from_env(
            {
                "JAYA_ENVIRONMENT": "test",
                "JAYA_CORE_DATA_DIR": str(tmp_path),
                "JAYA_TERNARY_MODEL_SHA256": "not-a-digest",
            },
            core_dir=ROOT,
        )
    assert "invalid:JAYA_TERNARY_MODEL_SHA256" in invalid.value.issues


def test_canonical_launcher_wires_configured_ternary_artifact(
    tmp_path: Path,
    trained_artifact: tuple[Path, TernaryTrainingResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import run_jaya_core_server

    artifact, training = trained_artifact
    monkeypatch.delenv("JAYA_PILLAR_MANIFEST_PATHS", raising=False)
    monkeypatch.delenv("JAYA_PILLAR_REGISTRY_DB", raising=False)
    config = CoreConfig.from_env(
        {
            "JAYA_ENVIRONMENT": "test",
            "JAYA_CORE_DATA_DIR": str(tmp_path),
            "JAYA_NODE_ID": "ternary-launcher-test",
            "JAYA_TERNARY_MODEL_PATH": str(artifact),
            "JAYA_TERNARY_MODEL_SHA256": training.artifact_sha256,
        },
        core_dir=ROOT,
    )
    runtime = run_jaya_core_server._build_runtime(config)
    try:
        result = runtime.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {"action": "predict", "text": "model ternary", "top_k": 3},
        )
        p22 = next(
            item
            for item in runtime.operational_snapshot()["pillars"]["pillars"]
            if item["pillar_id"] == "P022"
        )
        assert result.data["artifact_sha256"] == training.artifact_sha256
        assert p22["runtime_available"] is True
    finally:
        runtime.close()
