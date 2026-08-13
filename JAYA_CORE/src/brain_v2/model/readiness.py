"""Typed, redacted model-readiness contracts shared by JAYA_CORE runtimes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


class ModelReadinessState(str, Enum):
    """Operational state of an inference model."""

    UNAVAILABLE = "UNAVAILABLE"
    DEGRADED = "DEGRADED"
    READY = "READY"


class ModelFailureCode(str, Enum):
    """Stable failure codes that are safe to expose through readiness APIs."""

    READY = "ready"
    NOT_LOADED = "not_loaded"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_INVALID = "artifact_invalid"
    CHECKSUM_MISSING = "checksum_missing"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    CONFIG_INVALID = "config_invalid"
    WEIGHTS_INVALID = "weights_invalid"
    RANDOM_WEIGHTS = "random_weights"
    TOKENIZER_MISSING = "tokenizer_missing"
    TOKENIZER_INVALID = "tokenizer_invalid"
    DEPENDENCY_MISSING = "dependency_missing"
    PROBE_FAILED = "probe_failed"
    EMPTY_OUTPUT = "empty_output"
    LOAD_FAILED = "load_failed"
    GENERATION_FAILED = "generation_failed"
    UNVERIFIED_MUTATION = "unverified_mutation"
    READINESS_CONTRACT_MISSING = "readiness_contract_missing"


def normalize_sha256(value: str | None) -> str | None:
    """Return a canonical ``sha256:<hex>`` digest or ``None``."""

    candidate = (value or "").strip().lower()
    if not _SHA256_RE.fullmatch(candidate):
        return None
    return "sha256:" + candidate.removeprefix("sha256:")


@dataclass(frozen=True, slots=True)
class ModelReadinessReport:
    """Sanitized model state; never contains paths, secrets, or raw exceptions."""

    state: ModelReadinessState
    code: ModelFailureCode
    artifact_sha256: str | None = None
    tokenizer_sha256: str | None = None

    @property
    def ready(self) -> bool:
        return self.state is ModelReadinessState.READY

    def as_dict(self) -> dict[str, str | bool | None]:
        return {
            "state": self.state.value,
            "code": self.code.value,
            "ready": self.ready,
            "artifact_sha256": self.artifact_sha256,
            "tokenizer_sha256": self.tokenizer_sha256,
        }


class ModelUnavailableError(RuntimeError):
    """Typed, redacted failure raised instead of returning fabricated text."""

    def __init__(self, code: ModelFailureCode) -> None:
        self.code = code
        super().__init__(f"model unavailable: {code.value}")


__all__ = [
    "ModelFailureCode",
    "ModelReadinessReport",
    "ModelReadinessState",
    "ModelUnavailableError",
    "normalize_sha256",
]
