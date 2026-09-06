"""P29 Binary Cortex authenticated artifacts and bit-packed execution."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import platform
import re
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jaya_core.pillars.local_types import LocalPillarError, LocalPillarResult
from jaya_core.providers import (
    ComputeProvider,
    NativeProviderError,
    TrustedArtifactGate,
    get_compute_provider,
    get_trusted_artifact_gate,
)
from jaya_core.security.cryptographic_skin import (
    CryptographicSkin,
    CryptographicSkinError,
    SealedEnvelope,
)

_ARTIFACT_SCHEMA_VERSION = 1
_ARTIFACT_PURPOSE = "binary-cortex-artifact-v1"
_RECEIPT_PURPOSE = "binary-cortex-receipt-v1"
_ARTIFACT_CONTENT_TYPE = "application/vnd.jaya.binary-cortex+json"
_RECEIPT_CONTENT_TYPE = "application/vnd.jaya.binary-cortex-receipt+json"
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LocalPillarError("INVALID_INPUT", "binary payload is not canonical JSON") from exc


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > 16 * 1024 * 1024:
        raise LocalPillarError("ARTIFACT_CORRUPT", "binary row encoding is invalid")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise LocalPillarError("ARTIFACT_CORRUPT", "binary row encoding is invalid") from exc


@dataclass(frozen=True, slots=True)
class LoadedBinaryArtifact:
    """Authenticated in-memory representation of one binary weight matrix."""

    artifact_id: str
    input_features: int
    output_units: int
    packed_rows: tuple[bytes, ...]
    row_bits: tuple[int, ...]
    weights_sha256: str
    payload_sha256: str
    envelope_sha256: str


class BinaryCortexService:
    """Bounded binary inference with P13-authenticated persistent artifacts."""

    MAX_VECTOR_LENGTH = 65_536
    MAX_OUTPUT_UNITS = 4_096
    MAX_TOTAL_WEIGHT_BITS = 16_777_216
    MAX_BENCHMARK_ITERATIONS = 10_000
    MAX_BENCHMARK_SCALAR_OPERATIONS = 20_000_000
    MAX_ENVELOPE_BYTES = 32 * 1024 * 1024

    def __init__(
        self,
        *,
        artifact_root: Path | str | None = None,
        cryptographic_skin: CryptographicSkin | None = None,
        kernel_timeout_seconds: float = 2.0,
        kernel_probe: Callable[[], bool] | None = None,
        monotonic: Callable[[], float] = time.perf_counter,
        compute_provider: ComputeProvider | None = None,
        trusted_gate: TrustedArtifactGate | None = None,
    ) -> None:
        if (
            isinstance(kernel_timeout_seconds, bool)
            or not isinstance(kernel_timeout_seconds, (int, float))
            or not 0.001 <= float(kernel_timeout_seconds) <= 30.0
        ):
            raise LocalPillarError(
                "INVALID_CONFIG", "binary kernel timeout must be between 0.001 and 30 seconds"
            )
        if kernel_probe is not None and not callable(kernel_probe):
            raise LocalPillarError("INVALID_CONFIG", "binary kernel probe must be callable")
        if not callable(monotonic):
            raise LocalPillarError("INVALID_CONFIG", "binary monotonic clock must be callable")
        self._artifact_root = (
            Path(artifact_root).expanduser().resolve() if artifact_root is not None else None
        )
        self._skin = cryptographic_skin
        self._kernel_timeout_seconds = float(kernel_timeout_seconds)
        self._kernel_probe = kernel_probe or (lambda: callable(getattr(int, "bit_count", None)))
        self._monotonic = monotonic
        self._lock = threading.RLock()
        try:
            self._compute = compute_provider or get_compute_provider()
            self._trusted = trusted_gate or get_trusted_artifact_gate()
        except NativeProviderError as exc:
            raise LocalPillarError(exc.code, str(exc)) from exc

    @classmethod
    def _normalize(cls, vector: object, field: str) -> tuple[int, ...]:
        if not isinstance(vector, Sequence) or isinstance(vector, (str, bytes, bytearray)):
            raise LocalPillarError("INVALID_INPUT", f"{field} must be a sequence")
        if not 1 <= len(vector) <= cls.MAX_VECTOR_LENGTH:
            raise LocalPillarError(
                "RESOURCE_LIMIT", f"{field} length must be 1-{cls.MAX_VECTOR_LENGTH}"
            )
        normalized: list[int] = []
        for value in vector:
            if value is True or (type(value) is int and value == 1):
                normalized.append(1)
            elif value is False or (type(value) is int and value == -1):
                normalized.append(-1)
            else:
                raise LocalPillarError("INVALID_INPUT", f"{field} values must be -1/+1 or bool")
        return tuple(normalized)

    @staticmethod
    def _pack(vector: tuple[int, ...]) -> bytes:
        packed = bytearray((len(vector) + 7) // 8)
        for index, value in enumerate(vector):
            if value == 1:
                packed[index // 8] |= 1 << (index % 8)
        return bytes(packed)

    @staticmethod
    def _dot_bits(left_bits: int, right_bits: int, length: int) -> tuple[int, int]:
        mask = (1 << length) - 1
        matches = (~(left_bits ^ right_bits) & mask).bit_count()
        return matches, 2 * matches - length

    def _calculate(self, lhs: tuple[int, ...], rhs: tuple[int, ...]) -> tuple[int, int]:
        if self._compute.native_available:
            try:
                return self._compute.binary_dot(lhs, rhs)
            except NativeProviderError as exc:
                raise LocalPillarError(exc.code, str(exc)) from exc
        left_bits = int.from_bytes(self._pack(lhs), "little")
        right_bits = int.from_bytes(self._pack(rhs), "little")
        return self._dot_bits(left_bits, right_bits, len(lhs))

    def _selected_pack(self, vector: tuple[int, ...]) -> bytes:
        if not self._compute.native_available:
            return self._pack(vector)
        try:
            return self._compute.binary_pack(vector)
        except NativeProviderError as exc:
            raise LocalPillarError(exc.code, str(exc)) from exc

    def _selected_packed_dot(
        self, left: bytes, right: bytes, length: int
    ) -> tuple[int, int]:
        if not self._compute.native_available:
            return self._dot_bits(
                int.from_bytes(left, "little"), int.from_bytes(right, "little"), length
            )
        try:
            return self._compute.binary_dot_packed(left, right, length)
        except NativeProviderError as exc:
            raise LocalPillarError(exc.code, str(exc)) from exc

    def _kernel_label(self) -> str:
        return (
            "CPP20_XNOR_POPCOUNT"
            if self._compute.native_available
            else "PYTHON_INT_XNOR_POPCOUNT"
        )

    @staticmethod
    def _require_fields(
        request: Mapping[str, Any], *, allowed: frozenset[str], required: frozenset[str]
    ) -> None:
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

    def _validated_id(self, value: object, field: str) -> str:
        if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
            raise LocalPillarError("INVALID_INPUT", f"{field} is invalid")
        try:
            self._trusted.validate_identifier(value)
        except NativeProviderError as exc:
            raise LocalPillarError("INVALID_INPUT", f"{field} is invalid") from exc
        return value

    @staticmethod
    def _validated_timeout(value: object, default: float) -> float:
        selected = default if value is None else value
        if (
            isinstance(selected, bool)
            or not isinstance(selected, (int, float))
            or not 0.001 <= float(selected) <= 30.0
        ):
            raise LocalPillarError("INVALID_INPUT", "timeout_seconds must be between 0.001 and 30")
        return float(selected)

    def _kernel_available(self) -> bool:
        try:
            return bool(self._kernel_probe()) and callable(getattr(int, "bit_count", None))
        except Exception:  # noqa: BLE001 - provider capability boundary
            return False

    def kernel_profile(self) -> dict[str, Any]:
        """Return a truthful local kernel capability profile."""

        return {
            "provider_id": self._compute.provider_id,
            "available": self._kernel_available(),
            "binary_execution": True,
            "hardware_accelerated": False,
            "runtime": platform.python_implementation(),
            "python": platform.python_version(),
            "machine": platform.machine() or "UNKNOWN",
            "processor": platform.processor() or "UNKNOWN",
            "instruction_claim": (
                "CPP20_PORTABLE_POPCOUNT"
                if self._compute.native_available
                else "PYTHON_INT_BIT_COUNT_NO_SIMD_CLAIM"
            ),
            "compute": self._compute.profile(),
            "trusted_artifact_gate": self._trusted.profile(),
        }

    def dot(self, left: object, right: object) -> LocalPillarResult:
        lhs = self._normalize(left, "left")
        rhs = self._normalize(right, "right")
        if len(lhs) != len(rhs):
            raise LocalPillarError("SHAPE_MISMATCH", "binary vectors must have equal length")
        if not self._kernel_available():
            raise LocalPillarError("KERNEL_UNAVAILABLE", "binary bit-count kernel is unavailable")
        try:
            matches, dot_product = self._calculate(lhs, rhs)
        except MemoryError as exc:
            raise LocalPillarError(
                "RESOURCE_UNAVAILABLE", "binary kernel memory allocation failed"
            ) from exc
        return LocalPillarResult(
            pillar_id="P029",
            code="BINARY_DOT_EXECUTED",
            data={
                "length": len(lhs),
                "matches": matches,
                "dot_product": dot_product,
                "packed_bytes": (len(lhs) + 7) // 8,
                "kernel": self._kernel_label(),
                "compute_provider": self._compute.provider_id,
                "fallback_used": False,
            },
        )

    def benchmark(self, left: object, right: object, *, iterations: int = 100) -> LocalPillarResult:
        if type(iterations) is not int or not 1 <= iterations <= self.MAX_BENCHMARK_ITERATIONS:
            raise LocalPillarError(
                "RESOURCE_LIMIT", f"iterations must be 1-{self.MAX_BENCHMARK_ITERATIONS}"
            )
        lhs = self._normalize(left, "left")
        rhs = self._normalize(right, "right")
        if len(lhs) != len(rhs):
            raise LocalPillarError("SHAPE_MISMATCH", "binary vectors must have equal length")
        if len(lhs) * iterations > self.MAX_BENCHMARK_SCALAR_OPERATIONS:
            raise LocalPillarError("RESOURCE_LIMIT", "benchmark scalar work limit exceeded")
        if not self._kernel_available():
            raise LocalPillarError("KERNEL_UNAVAILABLE", "binary bit-count kernel is unavailable")

        pack_started = time.perf_counter_ns()
        left_packed = self._selected_pack(lhs)
        right_packed = self._selected_pack(rhs)
        packing_elapsed_ns = max(1, time.perf_counter_ns() - pack_started)

        binary_started = time.perf_counter_ns()
        actual = 0
        for _ in range(iterations):
            _, actual = self._selected_packed_dot(left_packed, right_packed, len(lhs))
        binary_elapsed_ns = max(1, time.perf_counter_ns() - binary_started)

        dense_started = time.perf_counter_ns()
        expected = 0
        for _ in range(iterations):
            expected = sum(a * b for a, b in zip(lhs, rhs, strict=True))
        dense_elapsed_ns = max(1, time.perf_counter_ns() - dense_started)
        if actual != expected:
            raise LocalPillarError("KERNEL_MISMATCH", "binary kernel failed scalar verification")
        binary_storage = len(left_packed) + len(right_packed)
        dense_fp32_storage = len(lhs) * 2 * 4
        return LocalPillarResult(
            pillar_id="P029",
            code="BINARY_KERNEL_BENCHMARKED",
            data={
                "length": len(lhs),
                "iterations": iterations,
                "elapsed_ns": binary_elapsed_ns,
                "binary_elapsed_ns": binary_elapsed_ns,
                "dense_elapsed_ns": dense_elapsed_ns,
                "packing_elapsed_ns": packing_elapsed_ns,
                "operations_per_second": iterations * 1_000_000_000 / binary_elapsed_ns,
                "dense_operations_per_second": iterations * 1_000_000_000 / dense_elapsed_ns,
                "kernel_speedup_excluding_pack": dense_elapsed_ns / binary_elapsed_ns,
                "dot_product": actual,
                "verified_against": "PYTHON_SCALAR_DOT",
                "kernel": self._kernel_label(),
                "compute_provider": self._compute.provider_id,
                "binary_storage_bytes": binary_storage,
                "dense_fp32_storage_bytes": dense_fp32_storage,
                "storage_compression_ratio": dense_fp32_storage / binary_storage,
                "fallback_used": False,
            },
        )

    def _artifact_path(self, artifact_id: str) -> Path:
        if self._artifact_root is None:
            raise LocalPillarError(
                "ARTIFACT_STORAGE_UNAVAILABLE", "binary artifact root is not configured"
            )
        return self._artifact_root / "artifacts" / f"{artifact_id}.jaya-binary-envelope.json"

    def _receipt_path(self, receipt_id: str) -> Path:
        if self._artifact_root is None:
            raise LocalPillarError(
                "ARTIFACT_STORAGE_UNAVAILABLE", "binary artifact root is not configured"
            )
        return self._artifact_root / "receipts" / f"{receipt_id}.jaya-binary-receipt.json"

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise LocalPillarError(
                "ARTIFACT_STORAGE_UNAVAILABLE", "binary artifact could not be persisted"
            ) from exc

    def _require_skin(self) -> CryptographicSkin:
        if self._skin is None:
            raise LocalPillarError(
                "ARTIFACT_SECURITY_UNAVAILABLE", "P13 Cryptographic Skin is not configured"
            )
        return self._skin

    @classmethod
    def _normalized_matrix(cls, weights: object) -> tuple[tuple[int, ...], ...]:
        if not isinstance(weights, Sequence) or isinstance(weights, (str, bytes, bytearray)):
            raise LocalPillarError("INVALID_INPUT", "weights must be a matrix")
        if not 1 <= len(weights) <= cls.MAX_OUTPUT_UNITS:
            raise LocalPillarError(
                "RESOURCE_LIMIT", f"weights must contain 1-{cls.MAX_OUTPUT_UNITS} rows"
            )
        rows = tuple(cls._normalize(row, "weights row") for row in weights)
        features = len(rows[0])
        if any(len(row) != features for row in rows):
            raise LocalPillarError("SHAPE_MISMATCH", "binary weight rows must have equal length")
        if features * len(rows) > cls.MAX_TOTAL_WEIGHT_BITS:
            raise LocalPillarError("RESOURCE_LIMIT", "binary weight matrix exceeds bit limit")
        return rows

    def install_artifact(
        self, artifact_id: object, weights: object, *, ttl_seconds: int = 31_536_000
    ) -> LocalPillarResult:
        artifact = self._validated_id(artifact_id, "artifact_id")
        if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 31_536_000:
            raise LocalPillarError(
                "INVALID_INPUT", "artifact ttl_seconds must be between 60 and 31536000"
            )
        rows = self._normalized_matrix(weights)
        try:
            packed_rows = tuple(self._pack(row) for row in rows)
        except MemoryError as exc:
            raise LocalPillarError(
                "RESOURCE_UNAVAILABLE", "binary artifact packing exhausted memory"
            ) from exc
        try:
            self._trusted.validate_binary_layout(
                packed_rows,
                input_features=len(rows[0]),
                max_features=self.MAX_VECTOR_LENGTH,
                max_outputs=self.MAX_OUTPUT_UNITS,
                max_total_bits=self.MAX_TOTAL_WEIGHT_BITS,
            )
        except NativeProviderError as exc:
            raise LocalPillarError("INVALID_INPUT", "binary artifact layout is invalid") from exc
        encoded_rows = [_encode(row) for row in packed_rows]
        weight_material = b"".join(len(row).to_bytes(8, "big") + row for row in packed_rows)
        material: dict[str, Any] = {
            "schema_version": _ARTIFACT_SCHEMA_VERSION,
            "artifact_id": artifact,
            "input_features": len(rows[0]),
            "output_units": len(rows),
            "bit_order": "LSB0",
            "value_mapping": {"zero": -1, "one": 1},
            "packed_rows": encoded_rows,
            "weights_sha256": _sha256(weight_material),
        }
        payload = {**material, "payload_sha256": _sha256(_canonical(material))}
        skin = self._require_skin()
        try:
            envelope = skin.seal(
                _canonical(payload),
                purpose=_ARTIFACT_PURPOSE,
                subject=f"binary-artifact:{artifact}",
                content_type=_ARTIFACT_CONTENT_TYPE,
                ttl_seconds=ttl_seconds,
            )
        except CryptographicSkinError as exc:
            raise LocalPillarError(
                "ARTIFACT_SECURITY_FAILED", "binary artifact could not be authenticated"
            ) from exc
        envelope_bytes = json.dumps(
            envelope.to_dict(), ensure_ascii=False, sort_keys=True, indent=2
        ).encode("utf-8")
        with self._lock:
            self._atomic_write(self._artifact_path(artifact), envelope_bytes)
            loaded = self._load_artifact(artifact)
        dense_fp32_bytes = loaded.input_features * loaded.output_units * 4
        packed_bytes = sum(len(row) for row in loaded.packed_rows)
        return LocalPillarResult(
            pillar_id="P029",
            code="BINARY_ARTIFACT_INSTALLED",
            data={
                "artifact_id": artifact,
                "input_features": loaded.input_features,
                "output_units": loaded.output_units,
                "weights_sha256": loaded.weights_sha256,
                "payload_sha256": loaded.payload_sha256,
                "envelope_sha256": loaded.envelope_sha256,
                "packed_weight_bytes": packed_bytes,
                "dense_fp32_weight_bytes": dense_fp32_bytes,
                "storage_compression_ratio": dense_fp32_bytes / packed_bytes,
                "artifact_path": str(self._artifact_path(artifact)),
                "security": "P13_AES_256_GCM_DNA_ATTESTED",
                "trusted_provider": self._trusted.provider_id,
            },
        )

    def _load_artifact(self, artifact_id: str) -> LoadedBinaryArtifact:
        path = self._artifact_path(artifact_id)
        try:
            envelope_bytes = path.read_bytes()
        except FileNotFoundError as exc:
            raise LocalPillarError("ARTIFACT_NOT_FOUND", "binary artifact does not exist") from exc
        except OSError as exc:
            raise LocalPillarError(
                "ARTIFACT_STORAGE_UNAVAILABLE", "binary artifact cannot be read"
            ) from exc
        if not envelope_bytes or len(envelope_bytes) > self.MAX_ENVELOPE_BYTES:
            raise LocalPillarError("ARTIFACT_CORRUPT", "binary artifact size is invalid")
        try:
            envelope_value = json.loads(envelope_bytes)
            envelope = SealedEnvelope.from_dict(envelope_value)
        except (json.JSONDecodeError, CryptographicSkinError, TypeError) as exc:
            raise LocalPillarError("ARTIFACT_CORRUPT", "binary envelope is invalid") from exc
        if (
            envelope.purpose != _ARTIFACT_PURPOSE
            or envelope.subject != f"binary-artifact:{artifact_id}"
            or envelope.content_type != _ARTIFACT_CONTENT_TYPE
        ):
            raise LocalPillarError("ARTIFACT_SCOPE_INVALID", "binary envelope scope is invalid")
        try:
            plaintext = self._require_skin().open(envelope)
        except CryptographicSkinError as exc:
            raise LocalPillarError(
                "ARTIFACT_AUTHENTICATION_FAILED", "binary artifact authentication failed"
            ) from exc
        try:
            payload = json.loads(plaintext)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise LocalPillarError("ARTIFACT_CORRUPT", "binary payload is invalid") from exc
        expected = {
            "schema_version",
            "artifact_id",
            "input_features",
            "output_units",
            "bit_order",
            "value_mapping",
            "packed_rows",
            "weights_sha256",
            "payload_sha256",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise LocalPillarError("ARTIFACT_CORRUPT", "binary payload schema is invalid")
        if (
            payload["schema_version"] != _ARTIFACT_SCHEMA_VERSION
            or payload["artifact_id"] != artifact_id
            or payload["bit_order"] != "LSB0"
            or payload["value_mapping"] != {"zero": -1, "one": 1}
            or type(payload["input_features"]) is not int
            or type(payload["output_units"]) is not int
            or not 1 <= payload["input_features"] <= self.MAX_VECTOR_LENGTH
            or not 1 <= payload["output_units"] <= self.MAX_OUTPUT_UNITS
            or not isinstance(payload["packed_rows"], list)
            or len(payload["packed_rows"]) != payload["output_units"]
        ):
            raise LocalPillarError("ARTIFACT_CORRUPT", "binary payload values are invalid")
        material = {key: payload[key] for key in expected - {"payload_sha256"}}
        if payload["payload_sha256"] != _sha256(_canonical(material)):
            raise LocalPillarError("ARTIFACT_CORRUPT", "binary payload digest is invalid")
        packed_rows = tuple(_decode(row) for row in payload["packed_rows"])
        row_bytes = (payload["input_features"] + 7) // 8
        if any(len(row) != row_bytes for row in packed_rows):
            raise LocalPillarError("ARTIFACT_CORRUPT", "binary row width is invalid")
        remainder = payload["input_features"] % 8
        if remainder and any(row[-1] & ~((1 << remainder) - 1) for row in packed_rows):
            raise LocalPillarError("ARTIFACT_CORRUPT", "binary row padding is non-zero")
        try:
            self._trusted.validate_binary_layout(
                packed_rows,
                input_features=payload["input_features"],
                max_features=self.MAX_VECTOR_LENGTH,
                max_outputs=self.MAX_OUTPUT_UNITS,
                max_total_bits=self.MAX_TOTAL_WEIGHT_BITS,
            )
        except NativeProviderError as exc:
            raise LocalPillarError("ARTIFACT_CORRUPT", "binary layout gate rejected artifact") from exc
        weight_material = b"".join(len(row).to_bytes(8, "big") + row for row in packed_rows)
        if payload["weights_sha256"] != _sha256(weight_material):
            raise LocalPillarError("ARTIFACT_CORRUPT", "binary weights digest is invalid")
        return LoadedBinaryArtifact(
            artifact_id=artifact_id,
            input_features=payload["input_features"],
            output_units=payload["output_units"],
            packed_rows=packed_rows,
            row_bits=tuple(int.from_bytes(row, "little") for row in packed_rows),
            weights_sha256=payload["weights_sha256"],
            payload_sha256=payload["payload_sha256"],
            envelope_sha256=_sha256(envelope_bytes),
        )

    def inspect_artifact(self, artifact_id: object) -> LocalPillarResult:
        artifact = self._validated_id(artifact_id, "artifact_id")
        with self._lock:
            loaded = self._load_artifact(artifact)
        return LocalPillarResult(
            pillar_id="P029",
            code="BINARY_ARTIFACT_VERIFIED",
            data={
                "artifact_id": artifact,
                "input_features": loaded.input_features,
                "output_units": loaded.output_units,
                "weights_sha256": loaded.weights_sha256,
                "payload_sha256": loaded.payload_sha256,
                "envelope_sha256": loaded.envelope_sha256,
            },
        )

    def _persist_receipt(self, material: dict[str, Any]) -> tuple[str, str]:
        receipt_id = f"receipt-{uuid.uuid4().hex}"
        payload = {"schema_version": 1, "receipt_id": receipt_id, **material}
        try:
            envelope = self._require_skin().seal(
                _canonical(payload),
                purpose=_RECEIPT_PURPOSE,
                subject=f"binary-receipt:{receipt_id}",
                content_type=_RECEIPT_CONTENT_TYPE,
                ttl_seconds=31_536_000,
            )
        except CryptographicSkinError as exc:
            raise LocalPillarError(
                "RECEIPT_SECURITY_FAILED", "binary execution receipt could not be authenticated"
            ) from exc
        receipt_bytes = json.dumps(
            envelope.to_dict(), ensure_ascii=False, sort_keys=True, indent=2
        ).encode("utf-8")
        self._atomic_write(self._receipt_path(receipt_id), receipt_bytes)
        return receipt_id, _sha256(receipt_bytes)

    def infer(
        self,
        artifact_id: object,
        input_vector: object,
        *,
        allow_dense_fallback: bool = False,
        timeout_seconds: object = None,
    ) -> LocalPillarResult:
        artifact = self._validated_id(artifact_id, "artifact_id")
        if type(allow_dense_fallback) is not bool:
            raise LocalPillarError("INVALID_INPUT", "allow_dense_fallback must be boolean")
        timeout = self._validated_timeout(timeout_seconds, self._kernel_timeout_seconds)
        started = self._monotonic()
        deadline = started + timeout
        with self._lock:
            loaded = self._load_artifact(artifact)
        vector = self._normalize(input_vector, "input")
        if len(vector) != loaded.input_features:
            raise LocalPillarError("SHAPE_MISMATCH", "input does not match artifact features")

        kernel_available = self._kernel_available()
        if not kernel_available and not allow_dense_fallback:
            raise LocalPillarError("KERNEL_UNAVAILABLE", "binary kernel is unavailable")
        try:
            if self._monotonic() > deadline:
                raise LocalPillarError("EXECUTION_TIMEOUT", "binary execution exceeded timeout")
            outputs: list[int] = []
            if kernel_available:
                input_packed = self._selected_pack(vector)
                for packed in loaded.packed_rows:
                    if self._monotonic() > deadline:
                        raise LocalPillarError(
                            "EXECUTION_TIMEOUT", "binary execution exceeded timeout"
                        )
                    outputs.append(
                        self._selected_packed_dot(
                            input_packed, packed, loaded.input_features
                        )[1]
                    )
                kernel = self._kernel_label()
                fallback_used = False
                code = "BINARY_INFERENCE_EXECUTED"
            else:
                for packed in loaded.packed_rows:
                    if self._monotonic() > deadline:
                        raise LocalPillarError(
                            "EXECUTION_TIMEOUT", "dense fallback exceeded timeout"
                        )
                    outputs.append(
                        sum(
                            value * (1 if packed[index // 8] & (1 << (index % 8)) else -1)
                            for index, value in enumerate(vector)
                        )
                    )
                kernel = "PYTHON_DENSE_REFERENCE_FALLBACK"
                fallback_used = True
                code = "DENSE_FALLBACK_EXECUTED"
        except MemoryError as exc:
            raise LocalPillarError(
                "RESOURCE_UNAVAILABLE", "binary inference exhausted memory"
            ) from exc
        elapsed_seconds = max(0.0, self._monotonic() - started)
        output_sha256 = _sha256(_canonical({"outputs": outputs}))
        receipt_id, receipt_sha256 = self._persist_receipt(
            {
                "artifact_id": artifact,
                "artifact_payload_sha256": loaded.payload_sha256,
                "input_sha256": _sha256(_canonical({"input": list(vector)})),
                "output_sha256": output_sha256,
                "kernel": kernel,
                "fallback_used": fallback_used,
                "compute_provider": self._compute.provider_id,
                "trusted_provider": self._trusted.provider_id,
                "input_features": loaded.input_features,
                "output_units": loaded.output_units,
            }
        )
        return LocalPillarResult(
            pillar_id="P029",
            code=code,
            data={
                "artifact_id": artifact,
                "outputs": outputs,
                "output_sha256": output_sha256,
                "kernel": kernel,
                "fallback_used": fallback_used,
                "compute_provider": self._compute.provider_id,
                "trusted_provider": self._trusted.provider_id,
                "elapsed_seconds": elapsed_seconds,
                "binary_kernel_operations": loaded.output_units * 2,
                "dense_reference_multiply_adds": (loaded.output_units * loaded.input_features),
                "receipt_id": receipt_id,
                "receipt_sha256": receipt_sha256,
            },
        )

    def verify_receipt(self, receipt_id: object) -> LocalPillarResult:
        receipt = self._validated_id(receipt_id, "receipt_id")
        path = self._receipt_path(receipt)
        try:
            raw = path.read_bytes()
            envelope = SealedEnvelope.from_dict(json.loads(raw))
        except FileNotFoundError as exc:
            raise LocalPillarError("RECEIPT_NOT_FOUND", "binary receipt does not exist") from exc
        except (OSError, json.JSONDecodeError, CryptographicSkinError, TypeError) as exc:
            raise LocalPillarError("RECEIPT_CORRUPT", "binary receipt is invalid") from exc
        if (
            envelope.purpose != _RECEIPT_PURPOSE
            or envelope.subject != f"binary-receipt:{receipt}"
            or envelope.content_type != _RECEIPT_CONTENT_TYPE
        ):
            raise LocalPillarError("RECEIPT_SCOPE_INVALID", "binary receipt scope is invalid")
        try:
            payload = json.loads(self._require_skin().open(envelope))
        except (CryptographicSkinError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise LocalPillarError(
                "RECEIPT_AUTHENTICATION_FAILED", "binary receipt authentication failed"
            ) from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != 1
            or payload.get("receipt_id") != receipt
        ):
            raise LocalPillarError("RECEIPT_CORRUPT", "binary receipt payload is invalid")
        return LocalPillarResult(
            pillar_id="P029",
            code="BINARY_RECEIPT_VERIFIED",
            data=payload,
        )

    def health_check(self) -> bool:
        try:
            result = self.dot((1, -1, 1, -1, 1), (1, 1, -1, -1, 1))
        except LocalPillarError:
            return False
        return result.data["dot_product"] == 1 and result.data["packed_bytes"] == 1

    def execute(self, request: Mapping[str, Any]) -> LocalPillarResult:
        if not isinstance(request, Mapping):
            raise LocalPillarError("INVALID_INPUT", "request must be an object")
        action = request.get("action", "dot")
        if action == "dot":
            self._require_fields(
                request,
                allowed=frozenset({"action", "left", "right"}),
                required=frozenset({"left", "right"}),
            )
            return self.dot(request["left"], request["right"])
        if action == "benchmark":
            self._require_fields(
                request,
                allowed=frozenset({"action", "left", "right", "iterations"}),
                required=frozenset({"action", "left", "right"}),
            )
            return self.benchmark(
                request["left"], request["right"], iterations=request.get("iterations", 100)
            )
        if action == "profile":
            self._require_fields(
                request, allowed=frozenset({"action"}), required=frozenset({"action"})
            )
            return LocalPillarResult(
                pillar_id="P029",
                code="BINARY_KERNEL_PROFILED",
                data=self.kernel_profile(),
            )
        if action == "install":
            self._require_fields(
                request,
                allowed=frozenset({"action", "artifact_id", "weights", "ttl_seconds"}),
                required=frozenset({"action", "artifact_id", "weights"}),
            )
            return self.install_artifact(
                request["artifact_id"],
                request["weights"],
                ttl_seconds=request.get("ttl_seconds", 31_536_000),
            )
        if action == "inspect":
            self._require_fields(
                request,
                allowed=frozenset({"action", "artifact_id"}),
                required=frozenset({"action", "artifact_id"}),
            )
            return self.inspect_artifact(request["artifact_id"])
        if action == "infer":
            self._require_fields(
                request,
                allowed=frozenset(
                    {
                        "action",
                        "artifact_id",
                        "input",
                        "allow_dense_fallback",
                        "timeout_seconds",
                    }
                ),
                required=frozenset({"action", "artifact_id", "input"}),
            )
            return self.infer(
                request["artifact_id"],
                request["input"],
                allow_dense_fallback=request.get("allow_dense_fallback", False),
                timeout_seconds=request.get("timeout_seconds"),
            )
        if action == "verify_receipt":
            self._require_fields(
                request,
                allowed=frozenset({"action", "receipt_id"}),
                required=frozenset({"action", "receipt_id"}),
            )
            return self.verify_receipt(request["receipt_id"])
        raise LocalPillarError("UNSUPPORTED_ACTION", "binary cortex action is unsupported")
