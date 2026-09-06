"""Fail-closed loader for checksum-bound JAYA Nano inference artifacts."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jaya_core.brain_v2.format.packer import unpack_state_dict
from jaya_core.brain_v2.model.readiness import ModelFailureCode, normalize_sha256

_HEADER_SIZE = 128
_SECTION_HEADER_SIZE = 24
_FOOTER_SIZE = 32
_PACKED_WEIGHTS = 1 << 42
_NANO_PROFILE = 1 << 43
_PACKED_WEIGHTS_SECTION = 6
_MODEL_CONFIG_SECTION = 4
_MAX_TOKENIZER_BYTES = 16 * 1024 * 1024
_REQUIRED_SPECIAL_TOKENS = {
    "<PAD>": 0,
    "<UNK>": 1,
    "<BOS>": 2,
    "<EOS>": 3,
}


class NanoArtifactError(RuntimeError):
    """Artifact failure whose public message never includes paths or raw data."""

    def __init__(self, code: ModelFailureCode) -> None:
        self.code = code
        super().__init__(f"nano artifact rejected: {code.value}")


class VerifiedNanoTokenizer:
    """Small tokenizer loaded from a digest-bound JSON sidecar."""

    __slots__ = ("_id_to_token", "_token_to_id", "merges", "vocab_size")

    def __init__(
        self,
        token_to_id: dict[str, int],
        merges: tuple[tuple[str, str], ...],
        vocab_size: int,
    ) -> None:
        self._token_to_id = token_to_id
        self._id_to_token = {value: key for key, value in token_to_id.items()}
        self.merges = merges
        self.vocab_size = vocab_size

    def encode(self, text: str) -> list[int]:
        if not isinstance(text, str) or not text.strip():
            return []
        unknown = self._token_to_id["<UNK>"]
        token_ids = [self._token_to_id["<BOS>"]]
        for word in text.casefold().split():
            token_ids.append(self._token_to_id.get(word, unknown))
        token_ids.append(self._token_to_id["<EOS>"])
        return token_ids

    def decode(self, token_ids: list[int]) -> str:
        special = frozenset(_REQUIRED_SPECIAL_TOKENS)
        tokens = [
            self._id_to_token.get(int(token_id), "<UNK>")
            for token_id in token_ids
        ]
        return " ".join(token for token in tokens if token not in special).strip()


@dataclass(frozen=True, slots=True)
class LoadedNanoArtifact:
    state_dict: dict[str, Any]
    config: dict[str, Any]
    tokenizer: VerifiedNanoTokenizer
    artifact_sha256: str
    tokenizer_sha256: str
    nano_profile: bool


def _digest_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _read_expected_digest(path: Path, explicit: str | None) -> str:
    expected = normalize_sha256(explicit)
    if expected is not None:
        return expected
    sidecar = Path(f"{path}.sha256")
    try:
        if not sidecar.is_file() or sidecar.stat().st_size > 256:
            raise NanoArtifactError(ModelFailureCode.CHECKSUM_MISSING)
        first_token = sidecar.read_text(encoding="ascii").strip().split(maxsplit=1)[0]
    except NanoArtifactError:
        raise
    except (OSError, UnicodeError, IndexError) as exc:
        raise NanoArtifactError(ModelFailureCode.CHECKSUM_MISSING) from exc
    expected = normalize_sha256(first_token)
    if expected is None:
        raise NanoArtifactError(ModelFailureCode.CHECKSUM_MISSING)
    return expected


def _verify_container(raw: bytes) -> tuple[int, dict[int, bytes]]:
    if len(raw) < _HEADER_SIZE + _FOOTER_SIZE:
        raise NanoArtifactError(ModelFailureCode.ARTIFACT_INVALID)
    if raw[:4] != b"JAYA":
        raise NanoArtifactError(ModelFailureCode.ARTIFACT_INVALID)
    major = struct.unpack_from("<H", raw, 4)[0]
    if major != 18:
        raise NanoArtifactError(ModelFailureCode.ARTIFACT_INVALID)

    sealed = raw[:-_FOOTER_SIZE]
    expected_crc = struct.unpack_from("<I", raw, len(raw) - _FOOTER_SIZE)[0]
    expected_hash = raw[-28:]
    if (
        (zlib.crc32(sealed) & 0xFFFFFFFF) != expected_crc
        or hashlib.sha256(sealed).digest()[:28] != expected_hash
    ):
        raise NanoArtifactError(ModelFailureCode.ARTIFACT_INVALID)

    flags = struct.unpack_from("<Q", raw, 8)[0]
    if not flags & _PACKED_WEIGHTS:
        raise NanoArtifactError(ModelFailureCode.ARTIFACT_INVALID)

    sections: dict[int, bytes] = {}
    intervals: list[tuple[int, int]] = []
    cursor = _HEADER_SIZE
    first_payload_offset = len(sealed)
    while cursor + _SECTION_HEADER_SIZE <= first_payload_offset:
        section_type, reserved, section_size, section_offset = struct.unpack_from(
            "<IIqq",
            sealed,
            cursor,
        )
        if section_type == reserved == section_size == section_offset == 0:
            break
        if (
            reserved != 0
            or section_type <= 0
            or section_size <= 0
            or section_offset < _HEADER_SIZE
            or section_offset + section_size > len(sealed)
            or section_type in sections
        ):
            raise NanoArtifactError(ModelFailureCode.ARTIFACT_INVALID)
        first_payload_offset = min(first_payload_offset, section_offset)
        intervals.append((section_offset, section_offset + section_size))
        sections[section_type] = sealed[
            section_offset : section_offset + section_size
        ]
        cursor += _SECTION_HEADER_SIZE

    ordered = sorted(intervals)
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise NanoArtifactError(ModelFailureCode.ARTIFACT_INVALID)
    if (
        _PACKED_WEIGHTS_SECTION not in sections
        or _MODEL_CONFIG_SECTION not in sections
    ):
        raise NanoArtifactError(ModelFailureCode.ARTIFACT_INVALID)
    return flags, sections


def _load_config(payload: bytes) -> dict[str, Any]:
    try:
        config = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise NanoArtifactError(ModelFailureCode.CONFIG_INVALID) from exc
    if not isinstance(config, dict):
        raise NanoArtifactError(ModelFailureCode.CONFIG_INVALID)
    if config.get("weight_origin") != "trained_artifact":
        raise NanoArtifactError(ModelFailureCode.RANDOM_WEIGHTS)
    provenance = config.get("training_provenance")
    if (
        not isinstance(provenance, dict)
        or not isinstance(provenance.get("run_id"), str)
        or not provenance["run_id"].strip()
        or normalize_sha256(provenance.get("dataset_sha256")) is None
    ):
        raise NanoArtifactError(ModelFailureCode.CONFIG_INVALID)
    return config


def _load_tokenizer(
    path: Path,
    config: dict[str, Any],
    tokenizer_path: str | Path | None,
) -> tuple[VerifiedNanoTokenizer, str]:
    metadata = config.get("tokenizer")
    if not isinstance(metadata, dict):
        raise NanoArtifactError(ModelFailureCode.TOKENIZER_MISSING)
    expected_digest = normalize_sha256(metadata.get("sha256"))
    if expected_digest is None:
        raise NanoArtifactError(ModelFailureCode.TOKENIZER_INVALID)
    candidate = (
        Path(tokenizer_path)
        if tokenizer_path is not None
        else Path(f"{path}.tokenizer.json")
    )
    try:
        if (
            not candidate.is_file()
            or candidate.stat().st_size <= 0
            or candidate.stat().st_size > _MAX_TOKENIZER_BYTES
        ):
            raise NanoArtifactError(ModelFailureCode.TOKENIZER_MISSING)
        raw = candidate.read_bytes()
    except NanoArtifactError:
        raise
    except OSError as exc:
        raise NanoArtifactError(ModelFailureCode.TOKENIZER_MISSING) from exc
    observed_digest = _digest_bytes(raw)
    if observed_digest != expected_digest:
        raise NanoArtifactError(ModelFailureCode.TOKENIZER_INVALID)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise NanoArtifactError(ModelFailureCode.TOKENIZER_INVALID) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise NanoArtifactError(ModelFailureCode.TOKENIZER_INVALID)
    token_to_id = payload.get("token_to_id")
    merges_raw = payload.get("merges")
    vocab_size = payload.get("vocab_size")
    if (
        not isinstance(token_to_id, dict)
        or not isinstance(merges_raw, list)
        or isinstance(vocab_size, bool)
        or not isinstance(vocab_size, int)
        or vocab_size <= 0
        or vocab_size != config.get("vocab_size")
        or vocab_size != metadata.get("vocab_size")
    ):
        raise NanoArtifactError(ModelFailureCode.TOKENIZER_INVALID)
    if (
        len(token_to_id) != vocab_size
        or any(
            not isinstance(token, str)
            or not token
            or isinstance(token_id, bool)
            or not isinstance(token_id, int)
            or not 0 <= token_id < vocab_size
            for token, token_id in token_to_id.items()
        )
        or len(set(token_to_id.values())) != vocab_size
        or any(token_to_id.get(token) != token_id for token, token_id in _REQUIRED_SPECIAL_TOKENS.items())
    ):
        raise NanoArtifactError(ModelFailureCode.TOKENIZER_INVALID)
    merges: list[tuple[str, str]] = []
    for item in merges_raw:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(part, str) and part for part in item)
        ):
            raise NanoArtifactError(ModelFailureCode.TOKENIZER_INVALID)
        merges.append((item[0], item[1]))
    return (
        VerifiedNanoTokenizer(token_to_id, tuple(merges), vocab_size),
        observed_digest,
    )


def load_verified_nano_artifact(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    tokenizer_path: str | Path | None = None,
) -> LoadedNanoArtifact:
    """Load and bind a Nano model, tokenizer, provenance, and checksums."""

    artifact_path = Path(path)
    try:
        if not artifact_path.is_file() or artifact_path.stat().st_size <= 0:
            raise NanoArtifactError(ModelFailureCode.ARTIFACT_MISSING)
        raw = artifact_path.read_bytes()
    except NanoArtifactError:
        raise
    except OSError as exc:
        raise NanoArtifactError(ModelFailureCode.ARTIFACT_MISSING) from exc

    expected_digest = _read_expected_digest(artifact_path, expected_sha256)
    observed_digest = _digest_bytes(raw)
    if observed_digest != expected_digest:
        raise NanoArtifactError(ModelFailureCode.CHECKSUM_MISMATCH)
    flags, sections = _verify_container(raw)
    config = _load_config(sections[_MODEL_CONFIG_SECTION])
    tokenizer, tokenizer_digest = _load_tokenizer(
        artifact_path,
        config,
        tokenizer_path,
    )
    try:
        state_dict = unpack_state_dict(sections[_PACKED_WEIGHTS_SECTION])
    except Exception as exc:
        raise NanoArtifactError(ModelFailureCode.WEIGHTS_INVALID) from exc
    return LoadedNanoArtifact(
        state_dict=state_dict,
        config=config,
        tokenizer=tokenizer,
        artifact_sha256=observed_digest,
        tokenizer_sha256=tokenizer_digest,
        nano_profile=bool(flags & _NANO_PROFILE),
    )


__all__ = [
    "LoadedNanoArtifact",
    "NanoArtifactError",
    "VerifiedNanoTokenizer",
    "load_verified_nano_artifact",
]
