"""Trainable and checksum-bound ternary transition language model.

This module intentionally implements a small statistical language model rather
than pretending that randomly initialized NanoModel weights are trained.  Its
transition matrix is learned from an explicit corpus, quantized to {-1, 0, 1},
packed with the existing Pillar 22 codec, and used directly during inference.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import struct
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from jaya_core.brain_v2.format.packer import pack_ternary, unpack_ternary
from jaya_core.providers import NativeProviderError, get_trusted_artifact_gate

_SPECIAL_TOKENS = ("<PAD>", "<UNK>", "<BOS>", "<EOS>")
_TOKEN_RE = re.compile(r"[\w]+|[^\w\s]", re.UNICODE)
_ALLOWED_CORPUS_SUFFIXES = frozenset({".md", ".txt"})
_SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_CORPUS_BYTES = 64 * 1024 * 1024
_MODEL_TYPE = "STATISTICAL_TERNARY_TRANSITION_LM"


class TernaryModelError(RuntimeError):
    """Stable, path-redacted failure raised by the ternary model boundary."""

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


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _normalize_sha256(value: object) -> str | None:
    normalized = str(value or "").strip().casefold()
    if not _SHA256_RE.fullmatch(normalized):
        return None
    return f"sha256:{normalized.removeprefix('sha256:')}"


def tokenize(text: str) -> list[str]:
    """Tokenize Unicode text with a deterministic word-and-punctuation rule."""

    return [token.casefold() for token in _TOKEN_RE.findall(text)]


@dataclass(frozen=True, slots=True)
class CorpusDocument:
    source_ref: str
    text: str


@dataclass(frozen=True, slots=True)
class TernaryTrainingResult:
    artifact_path: Path
    artifact_sha256: str
    tokenizer_sha256: str
    dataset_sha256: str
    metrics: dict[str, float | int | bool]
    source_count: int
    train_sequences: int
    holdout_sequences: int


@dataclass(frozen=True, slots=True)
class TernaryEvaluationResult:
    evaluation_dataset_sha256: str
    source_count: int
    sequence_count: int
    pair_count: int
    metrics: dict[str, float | int | bool]


def load_corpus(paths: Sequence[str | Path]) -> tuple[list[CorpusDocument], str]:
    """Load an explicit bounded corpus and return documents plus its digest."""

    if not paths:
        raise TernaryModelError("CORPUS_MISSING", "at least one corpus path is required")
    candidates: list[tuple[Path, str]] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if path.is_file():
            if path.suffix.casefold() not in _ALLOWED_CORPUS_SUFFIXES:
                raise TernaryModelError(
                    "CORPUS_TYPE_UNSUPPORTED", "corpus files must be Markdown or text"
                )
            candidates.append((path, path.name))
            continue
        if path.is_dir():
            nested = sorted(
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix.casefold() in _ALLOWED_CORPUS_SUFFIXES
            )
            candidates.extend((item, item.relative_to(path).as_posix()) for item in nested)
            continue
        raise TernaryModelError("CORPUS_MISSING", "a configured corpus path is unavailable")
    if not candidates:
        raise TernaryModelError("CORPUS_EMPTY", "the configured corpus has no supported files")
    if len(candidates) > 10_000:
        raise TernaryModelError("RESOURCE_LIMIT", "corpus contains more than 10000 files")

    documents: list[CorpusDocument] = []
    digest = hashlib.sha256()
    total_bytes = 0
    for path, source_ref in candidates:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise TernaryModelError("CORPUS_UNAVAILABLE", "a corpus file could not be read") from exc
        total_bytes += len(raw)
        if total_bytes > _MAX_CORPUS_BYTES:
            raise TernaryModelError("RESOURCE_LIMIT", "corpus exceeds 64 MiB")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            raise TernaryModelError("CORPUS_INVALID", "corpus must be valid UTF-8") from exc
        digest.update(len(source_ref.encode("utf-8")).to_bytes(4, "little"))
        digest.update(source_ref.encode("utf-8"))
        digest.update(len(raw).to_bytes(8, "little"))
        digest.update(raw)
        documents.append(CorpusDocument(source_ref=source_ref, text=text))
    if not any(tokenize(document.text) for document in documents):
        raise TernaryModelError("CORPUS_EMPTY", "corpus contains no usable tokens")
    return documents, f"sha256:{digest.hexdigest()}"


def _sequences(
    documents: Sequence[CorpusDocument], dataset_sha256: str, holdout_ratio: float
) -> tuple[list[list[str]], list[list[str]]]:
    train: list[list[str]] = []
    holdout: list[list[str]] = []
    boundary = int(holdout_ratio * 10_000)
    for document in documents:
        for line_number, line in enumerate(document.text.splitlines(), start=1):
            tokens = tokenize(line)
            if not tokens:
                continue
            material = (
                f"{dataset_sha256}\n{document.source_ref}\n{line_number}\n{line}"
            ).encode()
            bucket = int.from_bytes(hashlib.sha256(material).digest()[:4], "big") % 10_000
            (holdout if bucket < boundary else train).append(tokens)
    if len(train) < 2 or not holdout:
        combined = train + holdout
        if len(combined) < 3:
            raise TernaryModelError(
                "CORPUS_TOO_SMALL", "corpus requires at least three non-empty sequences"
            )
        split_at = max(2, len(combined) - max(1, len(combined) // 5))
        train, holdout = combined[:split_at], combined[split_at:]
    return train, holdout


def _build_vocabulary(sequences: Iterable[Sequence[str]], max_vocab: int) -> list[str]:
    frequencies: dict[str, int] = {}
    for sequence in sequences:
        for token in sequence:
            frequencies[token] = frequencies.get(token, 0) + 1
    ordered = sorted(frequencies, key=lambda token: (-frequencies[token], token))
    vocabulary = [*_SPECIAL_TOKENS, *ordered[: max_vocab - len(_SPECIAL_TOKENS)]]
    if len(vocabulary) < 8:
        raise TernaryModelError("CORPUS_TOO_SMALL", "corpus vocabulary is too small")
    return vocabulary


def _pair_ids(sequences: Iterable[Sequence[str]], token_to_id: dict[str, int]) -> np.ndarray:
    pairs: list[tuple[int, int]] = []
    unknown = token_to_id["<UNK>"]
    bos = token_to_id["<BOS>"]
    eos = token_to_id["<EOS>"]
    for sequence in sequences:
        ids = [bos, *(token_to_id.get(token, unknown) for token in sequence), eos]
        pairs.extend(pairwise(ids))
    if not pairs:
        raise TernaryModelError("CORPUS_TOO_SMALL", "corpus contains no transition pairs")
    return np.asarray(pairs, dtype=np.int32)


def _softmax_rows(scores: np.ndarray) -> np.ndarray:
    shifted = scores - np.max(scores, axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / np.sum(exponentials, axis=1, keepdims=True)


def _evaluate_probabilities(probabilities: np.ndarray, pairs: np.ndarray) -> tuple[float, float]:
    selected = probabilities[pairs[:, 0], pairs[:, 1]]
    nll = float(-np.log(np.clip(selected, 1e-12, 1.0)).mean())
    predictions = np.argmax(probabilities[pairs[:, 0]], axis=1)
    accuracy = float(np.mean(predictions == pairs[:, 1]))
    return float(math.exp(min(nll, 50.0))), accuracy


def train_ternary_transition_model(
    corpus_paths: Sequence[str | Path],
    artifact_path: str | Path,
    *,
    max_vocab: int = 512,
    holdout_ratio: float = 0.2,
    smoothing: float = 0.5,
    max_perplexity_ratio: float = 2.0,
    max_top1_accuracy_drop: float = 0.2,
    run_id: str | None = None,
) -> TernaryTrainingResult:
    """Train, calibrate, benchmark, and persist one ternary model artifact."""

    if isinstance(max_vocab, bool) or not 16 <= max_vocab <= 2_048:
        raise TernaryModelError("INVALID_CONFIG", "max_vocab must be in [16, 2048]")
    if not 0.05 <= holdout_ratio <= 0.5:
        raise TernaryModelError("INVALID_CONFIG", "holdout_ratio must be in [0.05, 0.5]")
    if not 0.01 <= smoothing <= 10.0:
        raise TernaryModelError("INVALID_CONFIG", "smoothing must be in [0.01, 10]")
    if not 1.0 <= max_perplexity_ratio <= 10.0:
        raise TernaryModelError(
            "INVALID_CONFIG", "max_perplexity_ratio must be in [1, 10]"
        )
    if not 0.0 <= max_top1_accuracy_drop <= 1.0:
        raise TernaryModelError(
            "INVALID_CONFIG", "max_top1_accuracy_drop must be in [0, 1]"
        )
    normalized_run_id = str(run_id or uuid.uuid4().hex).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", normalized_run_id):
        raise TernaryModelError("INVALID_CONFIG", "run_id has an invalid format")

    started = time.perf_counter()
    documents, dataset_sha256 = load_corpus(corpus_paths)
    train_sequences, holdout_sequences = _sequences(
        documents, dataset_sha256, holdout_ratio
    )
    vocabulary = _build_vocabulary(train_sequences, max_vocab)
    token_to_id = {token: index for index, token in enumerate(vocabulary)}
    train_pairs = _pair_ids(train_sequences, token_to_id)
    holdout_pairs = _pair_ids(holdout_sequences, token_to_id)
    vocab_size = len(vocabulary)

    counts = np.zeros((vocab_size, vocab_size), dtype=np.float64)
    np.add.at(counts, (train_pairs[:, 0], train_pairs[:, 1]), 1.0)
    dense_probabilities = (counts + smoothing) / (
        counts.sum(axis=1, keepdims=True) + smoothing * vocab_size
    )
    baseline_perplexity, baseline_accuracy = _evaluate_probabilities(
        dense_probabilities, holdout_pairs
    )
    centered_logits = np.log(dense_probabilities)
    centered_logits -= centered_logits.mean(axis=1, keepdims=True)
    row_mean_magnitude = np.mean(np.abs(centered_logits), axis=1, keepdims=True)
    threshold_factors = (0.0, 0.2, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0, 1.1, 1.25)
    temperatures = (0.4, 0.5, 0.6, 0.75, 0.85, 1.0, 1.25, 1.5, 2.0)
    best: tuple[tuple[int, float, float], float, float, float, float, np.ndarray, np.ndarray] | None = None
    for threshold_factor in threshold_factors:
        threshold = row_mean_magnitude * threshold_factor
        weights = np.where(
            centered_logits > threshold,
            1,
            np.where(centered_logits < -threshold, -1, 0),
        ).astype(np.int8)
        scale_denominator = np.sum(np.square(weights, dtype=np.float64), axis=1)
        row_scales = np.divide(
            np.sum(centered_logits * weights, axis=1),
            scale_denominator,
            out=np.zeros(vocab_size, dtype=np.float64),
            where=scale_denominator > 0,
        )
        for temperature in temperatures:
            probabilities = _softmax_rows(
                weights.astype(np.float64) * row_scales[:, None] / temperature
            )
            perplexity, accuracy = _evaluate_probabilities(probabilities, holdout_pairs)
            ratio = perplexity / baseline_perplexity
            drop = max(0.0, baseline_accuracy - accuracy)
            passes = ratio <= max_perplexity_ratio and drop <= max_top1_accuracy_drop
            sort_key = (0 if passes else 1, perplexity, -accuracy)
            candidate = (
                sort_key,
                perplexity,
                -accuracy,
                threshold_factor,
                temperature,
                weights,
                row_scales,
            )
            if best is None or candidate[0] < best[0]:
                best = candidate
    if best is None:
        raise TernaryModelError("TRAINING_FAILED", "ternary calibration produced no candidate")
    (
        _,
        ternary_perplexity,
        negative_accuracy,
        threshold_factor,
        temperature,
        weights,
        row_scales,
    ) = best
    ternary_accuracy = -negative_accuracy
    perplexity_ratio = ternary_perplexity / baseline_perplexity
    top1_accuracy_drop = max(0.0, baseline_accuracy - ternary_accuracy)
    quality_gate_passed = (
        perplexity_ratio <= max_perplexity_ratio
        and top1_accuracy_drop <= max_top1_accuracy_drop
    )
    tokenizer_payload = {"schema_version": 1, "tokens": vocabulary}
    tokenizer_sha256 = _sha256(_canonical_json(tokenizer_payload))
    packed_weights = pack_ternary(weights)
    metrics: dict[str, float | int | bool] = {
        "baseline_perplexity": baseline_perplexity,
        "baseline_top1_accuracy": baseline_accuracy,
        "ternary_perplexity": ternary_perplexity,
        "ternary_top1_accuracy": ternary_accuracy,
        "perplexity_ratio": perplexity_ratio,
        "max_perplexity_ratio": max_perplexity_ratio,
        "top1_accuracy_drop": top1_accuracy_drop,
        "max_top1_accuracy_drop": max_top1_accuracy_drop,
        "quality_gate_passed": quality_gate_passed,
        "holdout_pairs": len(holdout_pairs),
        "train_pairs": len(train_pairs),
    }
    artifact = {
        "schema_version": 2,
        "model_type": _MODEL_TYPE,
        "weight_origin": "trained_from_explicit_corpus",
        "training_provenance": {
            "run_id": normalized_run_id,
            "dataset_sha256": dataset_sha256,
            "source_refs": [document.source_ref for document in documents],
            "train_sequences": len(train_sequences),
            "holdout_sequences": len(holdout_sequences),
            "holdout_ratio": holdout_ratio,
            "trained_at": datetime.now(UTC).isoformat(),
            "duration_seconds": time.perf_counter() - started,
        },
        "tokenizer": {**tokenizer_payload, "sha256": tokenizer_sha256},
        "weights": {
            "encoding": "ternary-2bit-base64",
            "shape": [vocab_size, vocab_size],
            "values": [-1, 0, 1],
            "data": base64.b64encode(packed_weights).decode("ascii"),
        },
        "calibration": {
            "threshold_factor": threshold_factor,
            "temperature": temperature,
            "smoothing": smoothing,
            "row_scales": row_scales.tolist(),
        },
        "metrics": metrics,
    }
    raw_artifact = _canonical_json(artifact)
    destination = Path(artifact_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.write_bytes(raw_artifact)
        artifact_sha256 = _sha256(raw_artifact)
        Path(f"{destination}.sha256").write_text(
            f"{artifact_sha256}\n", encoding="ascii"
        )
    except OSError as exc:
        raise TernaryModelError("ARTIFACT_WRITE_FAILED", "model artifact could not be written") from exc
    return TernaryTrainingResult(
        artifact_path=destination,
        artifact_sha256=artifact_sha256,
        tokenizer_sha256=tokenizer_sha256,
        dataset_sha256=dataset_sha256,
        metrics=metrics,
        source_count=len(documents),
        train_sequences=len(train_sequences),
        holdout_sequences=len(holdout_sequences),
    )


@dataclass(frozen=True, slots=True)
class TrainedTernaryTransitionModel:
    vocabulary: tuple[str, ...]
    weights: np.ndarray
    row_scales: np.ndarray
    temperature: float
    artifact_sha256: str
    tokenizer_sha256: str
    dataset_sha256: str
    run_id: str
    source_refs: tuple[str, ...]
    holdout_ratio: float | None
    smoothing: float
    metrics: dict[str, float | int | bool]

    @classmethod
    def load(
        cls, path: str | Path, *, expected_sha256: str | None = None
    ) -> TrainedTernaryTransitionModel:
        artifact_path = Path(path).expanduser().resolve()
        try:
            if not artifact_path.is_file():
                raise TernaryModelError("ARTIFACT_MISSING", "ternary artifact is unavailable")
            if not 0 < artifact_path.stat().st_size <= _MAX_ARTIFACT_BYTES:
                raise TernaryModelError("ARTIFACT_INVALID", "ternary artifact size is invalid")
            raw = artifact_path.read_bytes()
        except TernaryModelError:
            raise
        except OSError as exc:
            raise TernaryModelError("ARTIFACT_MISSING", "ternary artifact is unavailable") from exc
        expected = _normalize_sha256(expected_sha256)
        if expected_sha256 is not None and expected is None:
            raise TernaryModelError("CHECKSUM_INVALID", "configured artifact checksum is invalid")
        if expected is None:
            sidecar = Path(f"{artifact_path}.sha256")
            try:
                if not sidecar.is_file() or sidecar.stat().st_size > 256:
                    raise TernaryModelError("CHECKSUM_MISSING", "artifact checksum is required")
                expected = _normalize_sha256(sidecar.read_text(encoding="ascii").strip())
            except TernaryModelError:
                raise
            except (OSError, UnicodeError) as exc:
                raise TernaryModelError("CHECKSUM_MISSING", "artifact checksum is required") from exc
        observed = _sha256(raw)
        if expected != observed:
            raise TernaryModelError("CHECKSUM_MISMATCH", "ternary artifact checksum differs")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise TernaryModelError("ARTIFACT_INVALID", "ternary artifact is invalid JSON") from exc
        required = {
            "schema_version", "model_type", "weight_origin", "training_provenance",
            "tokenizer", "weights", "calibration", "metrics",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise TernaryModelError("ARTIFACT_INVALID", "ternary artifact fields are invalid")
        if (
            payload["schema_version"] not in (1, 2)
            or payload["model_type"] != _MODEL_TYPE
            or payload["weight_origin"] != "trained_from_explicit_corpus"
        ):
            raise TernaryModelError("ARTIFACT_INVALID", "ternary artifact contract is unsupported")
        provenance = payload["training_provenance"]
        tokenizer_payload = payload["tokenizer"]
        weights_payload = payload["weights"]
        calibration = payload["calibration"]
        metrics = payload["metrics"]
        if not all(isinstance(item, dict) for item in (
            provenance, tokenizer_payload, weights_payload, calibration, metrics
        )):
            raise TernaryModelError("ARTIFACT_INVALID", "ternary artifact sections are invalid")
        schema_version = int(payload["schema_version"])
        required_provenance = {
            "run_id", "dataset_sha256", "source_refs", "train_sequences",
            "holdout_sequences", "trained_at", "duration_seconds",
        }
        if schema_version == 2:
            required_provenance.add("holdout_ratio")
        if set(provenance) != required_provenance:
            raise TernaryModelError("PROVENANCE_INVALID", "training provenance fields are invalid")
        dataset_sha256 = _normalize_sha256(provenance.get("dataset_sha256"))
        run_id = provenance.get("run_id")
        source_refs = provenance.get("source_refs")
        train_sequences = provenance.get("train_sequences")
        holdout_sequences = provenance.get("holdout_sequences")
        duration_seconds = provenance.get("duration_seconds")
        holdout_ratio = provenance.get("holdout_ratio")
        if (
            dataset_sha256 is None
            or not isinstance(run_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", run_id)
            or not isinstance(source_refs, list)
            or not 1 <= len(source_refs) <= 10_000
            or any(not isinstance(ref, str) or not ref or len(ref) > 1_024 for ref in source_refs)
            or isinstance(train_sequences, bool)
            or not isinstance(train_sequences, int)
            or train_sequences < 2
            or isinstance(holdout_sequences, bool)
            or not isinstance(holdout_sequences, int)
            or holdout_sequences < 1
            or isinstance(duration_seconds, bool)
            or not isinstance(duration_seconds, (int, float))
            or not math.isfinite(float(duration_seconds))
            or float(duration_seconds) < 0
            or not isinstance(provenance.get("trained_at"), str)
            or (
                schema_version == 2
                and (
                    isinstance(holdout_ratio, bool)
                    or not isinstance(holdout_ratio, (int, float))
                    or not 0.05 <= float(holdout_ratio) <= 0.5
                )
            )
        ):
            raise TernaryModelError("PROVENANCE_INVALID", "training provenance is incomplete")
        tokens = tokenizer_payload.get("tokens")
        tokenizer_sha256 = _normalize_sha256(tokenizer_payload.get("sha256"))
        if (
            set(tokenizer_payload) != {"schema_version", "tokens", "sha256"}
            or
            tokenizer_payload.get("schema_version") != 1
            or not isinstance(tokens, list)
            or len(tokens) < 8
            or len(tokens) > 2_048
            or any(not isinstance(token, str) or not token for token in tokens)
            or len(set(tokens)) != len(tokens)
            or tuple(tokens[:4]) != _SPECIAL_TOKENS
            or tokenizer_sha256
            != _sha256(_canonical_json({"schema_version": 1, "tokens": tokens}))
        ):
            raise TernaryModelError("TOKENIZER_INVALID", "artifact tokenizer is invalid")
        if (
            set(weights_payload) != {"encoding", "shape", "values", "data"}
            or weights_payload.get("encoding") != "ternary-2bit-base64"
            or weights_payload.get("shape") != [len(tokens), len(tokens)]
            or weights_payload.get("values") != [-1, 0, 1]
            or not isinstance(weights_payload.get("data"), str)
        ):
            raise TernaryModelError("WEIGHTS_INVALID", "ternary weights metadata is invalid")
        try:
            packed = base64.b64decode(weights_payload["data"], validate=True)
            expected_values = len(tokens) * len(tokens)
            expected_packed_bytes = 8 + math.ceil(expected_values / 4)
            if (
                len(packed) != expected_packed_bytes
                or packed[:4] != b"T2BV"
                or struct.unpack("<I", packed[4:8])[0] != expected_values
            ):
                raise ValueError("packed ternary length differs from metadata")
            weights = unpack_ternary(packed, len(tokens) * len(tokens)).reshape(
                len(tokens), len(tokens)
            )
        except (ValueError, TypeError, IndexError, struct.error, binascii.Error) as exc:
            raise TernaryModelError("WEIGHTS_INVALID", "ternary weights could not be decoded") from exc
        if not np.isin(weights, (-1, 0, 1)).all():
            raise TernaryModelError("WEIGHTS_INVALID", "weights are not ternary")
        try:
            get_trusted_artifact_gate().validate_ternary_values(
                weights, max_length=64 * 1024 * 1024
            )
        except NativeProviderError as exc:
            code = (
                "PROVIDER_UNAVAILABLE"
                if exc.code == "PROVIDER_UNAVAILABLE"
                else "WEIGHTS_INVALID"
            )
            raise TernaryModelError(code, "trusted ternary artifact validation failed") from exc
        if set(calibration) != {
            "threshold_factor", "temperature", "smoothing", "row_scales"
        }:
            raise TernaryModelError("CALIBRATION_INVALID", "calibration fields are invalid")
        threshold_factor = calibration.get("threshold_factor")
        smoothing = calibration.get("smoothing")
        temperature = calibration.get("temperature")
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in (threshold_factor, smoothing, temperature)
        ):
            raise TernaryModelError("CALIBRATION_INVALID", "temperature must be numeric")
        temperature = float(temperature)
        if (
            not math.isfinite(temperature)
            or not 0.05 <= temperature <= 10.0
            or not math.isfinite(float(threshold_factor))
            or not 0.0 <= float(threshold_factor) <= 2.0
            or not math.isfinite(float(smoothing))
            or not 0.01 <= float(smoothing) <= 10.0
        ):
            raise TernaryModelError("CALIBRATION_INVALID", "temperature is out of range")
        row_scales_payload = calibration.get("row_scales")
        if (
            not isinstance(row_scales_payload, list)
            or len(row_scales_payload) != len(tokens)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 100.0
                for value in row_scales_payload
            )
        ):
            raise TernaryModelError("CALIBRATION_INVALID", "row scales are invalid")
        row_scales = np.asarray(row_scales_payload, dtype=np.float64)
        required_metrics = {
            "baseline_perplexity", "baseline_top1_accuracy", "ternary_perplexity",
            "ternary_top1_accuracy", "perplexity_ratio", "max_perplexity_ratio",
            "top1_accuracy_drop", "max_top1_accuracy_drop", "quality_gate_passed",
            "holdout_pairs", "train_pairs",
        }
        if set(metrics) != required_metrics or metrics.get("quality_gate_passed") is not True:
            raise TernaryModelError("QUALITY_GATE_FAILED", "artifact quality gate did not pass")
        numeric_metrics = required_metrics - {"quality_gate_passed"}
        if any(
            isinstance(metrics[key], bool)
            or not isinstance(metrics[key], (int, float))
            or not math.isfinite(float(metrics[key]))
            or float(metrics[key]) < 0
            for key in numeric_metrics
        ):
            raise TernaryModelError("METRICS_INVALID", "artifact metrics are invalid")
        if (
            float(metrics["baseline_perplexity"]) <= 0
            or float(metrics["ternary_perplexity"]) <= 0
            or not 0 <= float(metrics["baseline_top1_accuracy"]) <= 1
            or not 0 <= float(metrics["ternary_top1_accuracy"]) <= 1
            or not 0 <= float(metrics["top1_accuracy_drop"]) <= 1
            or not 0 <= float(metrics["max_top1_accuracy_drop"]) <= 1
            or not 1 <= float(metrics["max_perplexity_ratio"]) <= 10
            or isinstance(metrics["holdout_pairs"], bool)
            or not isinstance(metrics["holdout_pairs"], int)
            or metrics["holdout_pairs"] <= 0
            or isinstance(metrics["train_pairs"], bool)
            or not isinstance(metrics["train_pairs"], int)
            or metrics["train_pairs"] <= 0
        ):
            raise TernaryModelError("METRICS_INVALID", "artifact metrics are out of range")
        observed_ratio = float(metrics["ternary_perplexity"]) / float(
            metrics["baseline_perplexity"]
        )
        if (
            not math.isclose(observed_ratio, float(metrics["perplexity_ratio"]), rel_tol=1e-9)
            or observed_ratio > float(metrics["max_perplexity_ratio"])
            or not math.isclose(
                max(
                    0.0,
                    float(metrics["baseline_top1_accuracy"])
                    - float(metrics["ternary_top1_accuracy"]),
                ),
                float(metrics["top1_accuracy_drop"]),
                rel_tol=1e-9,
                abs_tol=1e-12,
            )
            or float(metrics["top1_accuracy_drop"])
            > float(metrics["max_top1_accuracy_drop"])
        ):
            raise TernaryModelError("METRICS_INVALID", "artifact quality metrics are inconsistent")
        return cls(
            vocabulary=tuple(tokens),
            weights=weights.astype(np.int8, copy=False),
            row_scales=row_scales,
            temperature=temperature,
            artifact_sha256=observed,
            tokenizer_sha256=tokenizer_sha256,
            dataset_sha256=dataset_sha256,
            run_id=run_id,
            source_refs=tuple(source_refs),
            holdout_ratio=float(holdout_ratio) if schema_version == 2 else None,
            smoothing=float(smoothing),
            metrics={key: metrics[key] for key in sorted(metrics)},
        )

    def predict(self, text: str, *, top_k: int = 5) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise TernaryModelError("INVALID_INPUT", "text must be non-empty")
        encoded = tokenize(text)
        if not encoded:
            raise TernaryModelError("INVALID_INPUT", "text contains no supported tokens")
        if len(text.encode("utf-8")) > 32_768 or len(encoded) > 4_096:
            raise TernaryModelError("RESOURCE_LIMIT", "input exceeds the model limits")
        if isinstance(top_k, bool) or not 1 <= top_k <= 20:
            raise TernaryModelError("INVALID_INPUT", "top_k must be in [1, 20]")
        token_to_id = {token: index for index, token in enumerate(self.vocabulary)}
        context_token = encoded[-1]
        context_id = token_to_id.get(context_token, token_to_id["<UNK>"])
        scores = (
            self.weights[context_id].astype(np.float64)
            * self.row_scales[context_id]
            / self.temperature
        )
        shifted = scores - np.max(scores)
        probabilities = np.exp(shifted)
        probabilities /= probabilities.sum()
        candidates = [
            index
            for index in np.argsort(-probabilities, kind="stable")
            if self.vocabulary[int(index)] not in _SPECIAL_TOKENS
        ][:top_k]
        return {
            "model_type": _MODEL_TYPE,
            "context_token": context_token,
            "context_token_known": context_token in token_to_id,
            "predictions": [
                {
                    "token": self.vocabulary[int(index)],
                    "probability": float(probabilities[int(index)]),
                    "ternary_weight": int(self.weights[context_id, int(index)]),
                }
                for index in candidates
            ],
            "artifact_sha256": self.artifact_sha256,
            "tokenizer_sha256": self.tokenizer_sha256,
            "dataset_sha256": self.dataset_sha256,
        }


def _resolved_corpus_files(paths: Sequence[str | Path]) -> set[Path]:
    files: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if path.is_file():
            files.add(path)
        elif path.is_dir():
            files.update(
                item.resolve()
                for item in path.rglob("*")
                if item.is_file() and item.suffix.casefold() in _ALLOWED_CORPUS_SUFFIXES
            )
    return files


def evaluate_ternary_transition_model(
    model: TrainedTernaryTransitionModel,
    training_corpus_paths: Sequence[str | Path],
    evaluation_corpus_paths: Sequence[str | Path],
    *,
    max_perplexity_ratio: float,
    max_top1_accuracy_drop: float,
) -> TernaryEvaluationResult:
    """Evaluate a trained artifact on a disjoint, explicit corpus."""

    if model.holdout_ratio is None:
        raise TernaryModelError(
            "PROVENANCE_UNSUPPORTED",
            "artifact does not record the split ratio required for independent evaluation",
        )
    if not 1.0 <= max_perplexity_ratio <= 10.0:
        raise TernaryModelError("INVALID_CONFIG", "max_perplexity_ratio must be in [1, 10]")
    if not 0.0 <= max_top1_accuracy_drop <= 1.0:
        raise TernaryModelError(
            "INVALID_CONFIG", "max_top1_accuracy_drop must be in [0, 1]"
        )
    training_files = _resolved_corpus_files(training_corpus_paths)
    evaluation_files = _resolved_corpus_files(evaluation_corpus_paths)
    if training_files & evaluation_files:
        raise TernaryModelError(
            "CORPUS_OVERLAP", "evaluation corpus must be disjoint from training corpus"
        )

    training_documents, training_sha256 = load_corpus(training_corpus_paths)
    if training_sha256 != model.dataset_sha256:
        raise TernaryModelError(
            "DATASET_MISMATCH", "training corpus differs from artifact provenance"
        )
    train_sequences, _ = _sequences(
        training_documents, training_sha256, model.holdout_ratio
    )
    token_to_id = {token: index for index, token in enumerate(model.vocabulary)}
    train_pairs = _pair_ids(train_sequences, token_to_id)
    if len(train_pairs) != int(model.metrics["train_pairs"]):
        raise TernaryModelError(
            "PROVENANCE_MISMATCH", "reconstructed training pairs differ from artifact metrics"
        )

    evaluation_documents, evaluation_sha256 = load_corpus(evaluation_corpus_paths)
    evaluation_sequences = [
        tokens
        for document in evaluation_documents
        for line in document.text.splitlines()
        if (tokens := tokenize(line))
    ]
    evaluation_pairs = _pair_ids(evaluation_sequences, token_to_id)
    vocab_size = len(model.vocabulary)
    counts = np.zeros((vocab_size, vocab_size), dtype=np.float64)
    np.add.at(counts, (train_pairs[:, 0], train_pairs[:, 1]), 1.0)
    dense_probabilities = (counts + model.smoothing) / (
        counts.sum(axis=1, keepdims=True) + model.smoothing * vocab_size
    )
    ternary_probabilities = _softmax_rows(
        model.weights.astype(np.float64)
        * model.row_scales[:, None]
        / model.temperature
    )
    dense_perplexity, dense_accuracy = _evaluate_probabilities(
        dense_probabilities, evaluation_pairs
    )
    ternary_perplexity, ternary_accuracy = _evaluate_probabilities(
        ternary_probabilities, evaluation_pairs
    )
    perplexity_ratio = ternary_perplexity / dense_perplexity
    top1_accuracy_drop = max(0.0, dense_accuracy - ternary_accuracy)
    gate_passed = (
        perplexity_ratio <= max_perplexity_ratio
        and top1_accuracy_drop <= max_top1_accuracy_drop
    )
    return TernaryEvaluationResult(
        evaluation_dataset_sha256=evaluation_sha256,
        source_count=len(evaluation_documents),
        sequence_count=len(evaluation_sequences),
        pair_count=len(evaluation_pairs),
        metrics={
            "baseline_perplexity": dense_perplexity,
            "baseline_top1_accuracy": dense_accuracy,
            "ternary_perplexity": ternary_perplexity,
            "ternary_top1_accuracy": ternary_accuracy,
            "perplexity_ratio": perplexity_ratio,
            "max_perplexity_ratio": max_perplexity_ratio,
            "top1_accuracy_drop": top1_accuracy_drop,
            "max_top1_accuracy_drop": max_top1_accuracy_drop,
            "quality_gate_passed": gate_passed,
        },
    )


__all__ = [
    "CorpusDocument",
    "TernaryEvaluationResult",
    "TernaryModelError",
    "TernaryTrainingResult",
    "TrainedTernaryTransitionModel",
    "evaluate_ternary_transition_model",
    "load_corpus",
    "tokenize",
    "train_ternary_transition_model",
]
