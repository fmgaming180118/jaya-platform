"""Functional canary implementations for promoted model artifacts."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ..evolution_manifest_v1 import digest_file
from .base import CanaryResult, CanaryRunner, create_canary_result

InferenceProbe = Callable[[Path, Mapping[str, Any]], Mapping[str, Any]]
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ZERO_DIGEST = f"sha256:{'0' * 64}"


def _expected_artifact_digest(manifest: Any) -> str | None:
    direct = getattr(manifest, "artifact_digest", None)
    if isinstance(direct, str):
        return direct
    if isinstance(manifest, Mapping):
        candidate = manifest.get("candidate")
        if isinstance(candidate, Mapping):
            artifact = candidate.get("artifact")
            if isinstance(artifact, Mapping):
                digest = artifact.get("digest")
                if isinstance(digest, str):
                    return digest
    return None


def _probe_context(manifest: Any, check_id: str, digest: str) -> dict[str, Any]:
    return {
        "candidate_id": getattr(manifest, "candidate_id", ""),
        "manifest_digest": getattr(manifest, "manifest_digest", ""),
        "check_id": check_id,
        "expected_artifact_digest": digest,
    }


class QLoRAAdapterCanary(CanaryRunner):
    """Require a SafeTensors artifact and an injected real inference probe."""

    DEFAULT_CHECK_ID = "qlora-adapter-inference-v1"

    def __init__(
        self,
        inference_probe: InferenceProbe | None = None,
        *,
        check_id: str = DEFAULT_CHECK_ID,
    ) -> None:
        self._inference_probe = inference_probe
        self._check_id = check_id

    @property
    def check_id(self) -> str:
        return self._check_id

    def validate_environment(self) -> tuple[bool, str]:
        if not callable(self._inference_probe):
            return False, "a real inference probe must be injected"
        return True, "real inference probe injected"

    def run(self, artifact_path: Path, manifest: Any) -> CanaryResult:
        path = Path(artifact_path)
        if path.is_symlink() or not path.is_file():
            return create_canary_result(
                False,
                {"code": "ARTIFACT_INVALID", "error": "adapter must be a regular file"},
            )
        if path.suffix.casefold() != ".safetensors":
            return create_canary_result(
                False,
                {
                    "code": "UNSAFE_MODEL_FORMAT",
                    "error": "only .safetensors adapter artifacts are accepted",
                },
            )
        expected_digest = _expected_artifact_digest(manifest)
        if (
            not isinstance(expected_digest, str)
            or not _DIGEST_RE.fullmatch(expected_digest)
            or expected_digest == _ZERO_DIGEST
        ):
            return create_canary_result(
                False,
                {
                    "code": "CHECKSUM_REQUIRED",
                    "error": "signed artifact digest is required",
                },
            )
        observed_before = digest_file(path)
        if observed_before != expected_digest:
            return create_canary_result(
                False,
                {"code": "CHECKSUM_MISMATCH", "error": "adapter checksum mismatch"},
            )
        if not callable(self._inference_probe):
            return create_canary_result(
                False,
                {
                    "code": "PROBE_REQUIRED",
                    "error": "no real inference probe was injected",
                },
            )
        try:
            raw_result = self._inference_probe(
                path,
                _probe_context(manifest, self.check_id, expected_digest),
            )
        except Exception:
            return create_canary_result(
                False,
                {"code": "PROBE_FAILED", "error": "inference probe raised an error"},
            )
        if not isinstance(raw_result, Mapping):
            return create_canary_result(
                False,
                {"code": "PROBE_INVALID", "error": "probe result must be an object"},
            )
        prohibited_flags = ("placeholder", "simulated", "structure_only")
        if any(raw_result.get(flag) is True for flag in prohibited_flags):
            return create_canary_result(
                False,
                {
                    "code": "PLACEHOLDER_PROBE",
                    "error": "placeholder probes are forbidden",
                },
            )
        required = {
            "passed",
            "mode",
            "probe_id",
            "model_loaded",
            "adapter_applied",
            "tokens_generated",
            "inference_time_ms",
            "output_digest",
        }
        if not required.issubset(raw_result):
            return create_canary_result(
                False,
                {
                    "code": "PROBE_INCOMPLETE",
                    "error": "real inference fields are missing",
                },
            )
        tokens = raw_result.get("tokens_generated")
        latency = raw_result.get("inference_time_ms")
        output_digest = raw_result.get("output_digest")
        valid = (
            raw_result.get("passed") is True
            and raw_result.get("mode") == "real-inference"
            and isinstance(raw_result.get("probe_id"), str)
            and bool(raw_result.get("probe_id"))
            and raw_result.get("model_loaded") is True
            and raw_result.get("adapter_applied") is True
            and isinstance(tokens, int)
            and not isinstance(tokens, bool)
            and tokens > 0
            and isinstance(latency, (int, float))
            and not isinstance(latency, bool)
            and math.isfinite(float(latency))
            and float(latency) > 0
            and isinstance(output_digest, str)
            and bool(_DIGEST_RE.fullmatch(output_digest))
            and output_digest != _ZERO_DIGEST
        )
        if not valid:
            return create_canary_result(
                False,
                {"code": "PROBE_INVALID", "error": "real inference proof is invalid"},
            )
        observed_after = digest_file(path)
        if observed_after != expected_digest:
            return create_canary_result(
                False,
                {"code": "CANARY_MUTATION", "error": "probe mutated the adapter"},
            )
        return create_canary_result(
            True,
            {
                "probe_id": raw_result["probe_id"],
                "mode": "real-inference",
                "model_loaded": True,
                "adapter_applied": True,
                "tokens_generated": tokens,
                "output_digest": output_digest,
                "artifact_digest": observed_after,
            },
            {"inference_time_ms": float(latency)},
        )


class GenericCanary(CanaryRunner):
    """Compatibility class that always rejects structural/readability checks."""

    @property
    def check_id(self) -> str:
        return "generic-readability-v1"

    def validate_environment(self) -> tuple[bool, str]:
        return False, "generic readability checks are not functional canaries"

    def run(self, artifact_path: Path, manifest: Any) -> CanaryResult:
        del artifact_path, manifest
        return create_canary_result(
            False,
            {
                "code": "GENERIC_CANARY_FORBIDDEN",
                "error": "a type-specific functional canary is required",
            },
        )
