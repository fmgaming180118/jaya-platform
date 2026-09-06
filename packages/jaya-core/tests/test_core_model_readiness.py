from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
from jaya_core.brain_v2.engine.runtime import IronEngine
from jaya_core.brain_v2.engine.slm_engine import SLMEngine, digest_model_artifact
from jaya_core.brain_v2.format.packer import pack_state_dict
from jaya_core.brain_v2.model.nano_inference import NANO_CONFIG, NanoModel
from jaya_core.brain_v2.model.readiness import (
    ModelFailureCode,
    ModelReadinessState,
    ModelUnavailableError,
)
from jaya_core.core_service import RuntimeDependency


def _state_dict() -> dict[str, object]:
    rng = np.random.default_rng(42)
    d = NANO_CONFIG["d_model"]

    def ternary(*shape: int) -> np.ndarray:
        return rng.integers(-1, 2, size=shape, dtype=np.int8)

    return {
        "embeddings": ternary(NANO_CONFIG["vocab_size"], d),
        "layers": [
            {
                "Wq": ternary(d, d),
                "Wk": ternary(d, d),
                "Wv": ternary(d, d),
                "Wo": ternary(d, d),
                "W1": ternary(d, d * 4),
                "W2": ternary(d * 4, d),
            }
            for _ in range(NANO_CONFIG["n_layers"])
        ],
        "output_head": ternary(d, NANO_CONFIG["vocab_size"]),
    }


def _write_verified_artifact(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    tokenizer_path = tmp_path / "brain.jay.tokenizer.json"
    tokens = {
        "<PAD>": 0,
        "<UNK>": 1,
        "<BOS>": 2,
        "<EOS>": 3,
        "jaya": 4,
        "readiness": 5,
        "probe": 6,
    }
    tokens.update(
        {f"token-{index}": index for index in range(7, NANO_CONFIG["vocab_size"])}
    )
    tokenizer_raw = json.dumps(
        {
            "schema_version": 1,
            "vocab_size": NANO_CONFIG["vocab_size"],
            "token_to_id": tokens,
            "merges": [],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    tokenizer_path.write_bytes(tokenizer_raw)
    tokenizer_digest = f"sha256:{hashlib.sha256(tokenizer_raw).hexdigest()}"

    weights = pack_state_dict(_state_dict())
    config = {
        **NANO_CONFIG,
        "weight_origin": "trained_artifact",
        "training_provenance": {
            "run_id": "fixture-training-run",
            "dataset_sha256": "sha256:" + ("a" * 64),
        },
        "tokenizer": {
            "sha256": tokenizer_digest,
            "vocab_size": NANO_CONFIG["vocab_size"],
        },
    }
    config_raw = json.dumps(config, sort_keys=True).encode()
    header_size, section_size, page = 128, 24, 4096

    def align(value: int) -> int:
        return (value + page - 1) & ~(page - 1)

    weight_offset = align(header_size + (2 * section_size))
    config_offset = align(weight_offset + len(weights))
    flags = (1 << 42) | (1 << 43)
    header = struct.pack("<4sHHQ", b"JAYA", 18, 0, flags)
    header = (header + (b"\0" * header_size))[:header_size]
    sections = (
        struct.pack("<IIqq", 6, 0, len(weights), weight_offset)
        + struct.pack("<IIqq", 4, 0, len(config_raw), config_offset)
    )
    body = bytearray(header + sections)
    body.extend(b"\0" * (weight_offset - len(body)))
    body.extend(weights)
    body.extend(b"\0" * (config_offset - len(body)))
    body.extend(config_raw)
    seal = struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)
    seal += hashlib.sha256(body).digest()[:28]
    artifact = tmp_path / "brain.jay"
    artifact.write_bytes(body + seal)
    artifact_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    Path(f"{artifact}.sha256").write_text(artifact_digest, encoding="ascii")
    return artifact


def test_nano_never_initializes_random_weights_implicitly() -> None:
    model = NanoModel()

    with pytest.raises(ModelUnavailableError) as captured:
        model.forward([1])

    assert captured.value.code is ModelFailureCode.NOT_LOADED
    model.random_init()
    assert model.readiness.state is ModelReadinessState.DEGRADED
    assert model.readiness.code is ModelFailureCode.RANDOM_WEIGHTS


def test_runtime_requires_checksum_tokenizer_and_real_probe(tmp_path: Path) -> None:
    artifact = _write_verified_artifact(tmp_path)
    probe_calls: list[tuple[int, ...]] = []
    engine = IronEngine(
        str(artifact),
        "test-password",
        model_probe=lambda _model, _tokenizer, logits: (
            probe_calls.append(logits.shape) or True
        ),
    )

    engine._try_load_nano_model()

    assert engine.model_readiness.state is ModelReadinessState.READY
    assert engine.nano_mode is True
    assert probe_calls == [(5, NANO_CONFIG["vocab_size"])]


def test_runtime_rejects_checksum_and_tokenizer_corruption(tmp_path: Path) -> None:
    artifact = _write_verified_artifact(tmp_path)
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    engine = IronEngine(str(artifact), "test-password")
    engine._try_load_nano_model()
    assert engine.model_readiness.code is ModelFailureCode.CHECKSUM_MISMATCH
    assert engine.nano_mode is False

    artifact = _write_verified_artifact(tmp_path / "second")
    Path(f"{artifact}.tokenizer.json").write_text("{}", encoding="utf-8")
    engine = IronEngine(str(artifact), "test-password")
    engine._try_load_nano_model()
    assert engine.model_readiness.code is ModelFailureCode.TOKENIZER_INVALID
    assert engine.nano_mode is False


class _FakeTokenizer:
    eos_token_id = 3

    def __call__(self, *_args: object, **_kwargs: object) -> dict[str, list[list[int]]]:
        return {"input_ids": [[2, 4, 3]]}

    def decode(self, _ids: object, **_kwargs: object) -> str:
        return "verified output"


class _FakeModel:
    def generate(self, input_ids: list[list[int]], **_kwargs: object) -> list[list[int]]:
        return [list(input_ids[0]) + [4]]


def test_slm_requires_local_digest_and_runs_injected_probe(tmp_path: Path) -> None:
    artifact = tmp_path / "model"
    artifact.mkdir()
    (artifact / "weights.bin").write_bytes(b"verified local model")
    engine = SLMEngine(
        enable_moe=False,
        model_artifact_path=str(artifact),
        expected_artifact_sha256=digest_model_artifact(artifact),
        component_loader=lambda _path, _device: (_FakeModel(), _FakeTokenizer()),
    )

    assert engine.load() is True
    assert engine.readiness.state is ModelReadinessState.READY


def test_slm_missing_model_raises_typed_error_not_apology() -> None:
    engine = SLMEngine(enable_moe=False)

    with pytest.raises(ModelUnavailableError) as captured:
        engine.generate("halo")

    assert captured.value.code is ModelFailureCode.ARTIFACT_MISSING
    assert "Maaf" not in str(captured.value)


@pytest.mark.asyncio
async def test_service_readiness_never_accepts_is_awake_only() -> None:
    runtime = type("AwakeOnly", (), {"is_awake": True})()

    status = await RuntimeDependency(runtime).check()

    assert status.ready is False
    assert status.code == "readiness_contract_missing"
