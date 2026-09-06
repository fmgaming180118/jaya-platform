"""Unified CPU compute contract with reference and first-party C++ providers."""

from __future__ import annotations

import ctypes
import os
import platform
from functools import lru_cache
from typing import Any, cast

import numpy as np

from .loader import NativeProviderError, load_first_party_library

_ABI_VERSION = 1
_SELECTIONS = frozenset({"auto", "python-reference", "native-cpu"})
_STATUS_CODES = {
    -1: "NULL_POINTER",
    -2: "INVALID_SIZE",
    -3: "INVALID_VALUE",
    -4: "RESOURCE_LIMIT_EXCEEDED",
}


class ComputeProvider:
    """Execute bounded compute without exposing vendor libraries to pillars."""

    def __init__(self, selection: str = "auto") -> None:
        requested = str(selection).strip().casefold()
        if requested not in _SELECTIONS:
            raise NativeProviderError(
                "INVALID_PROVIDER",
                f"compute provider must be one of: {', '.join(sorted(_SELECTIONS))}",
            )
        self.requested = requested
        self._loaded = None
        self._provider_id = "numpy-reference-v1"
        if requested != "python-reference":
            self._loaded = load_first_party_library(
                "jaya_compute", specific_env="JAYA_COMPUTE_LIBRARY"
            )
        if self._loaded is not None:
            self._bind_native()
        elif requested == "native-cpu":
            raise NativeProviderError(
                "PROVIDER_UNAVAILABLE",
                "the required C++ CPU provider could not be loaded",
            )

    @property
    def native_available(self) -> bool:
        return self._loaded is not None

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def _bind_native(self) -> None:
        assert self._loaded is not None
        library = self._loaded.library
        library.jaya_compute_abi_version.argtypes = []
        library.jaya_compute_abi_version.restype = ctypes.c_uint32
        if int(library.jaya_compute_abi_version()) != _ABI_VERSION:
            raise NativeProviderError("ABI_MISMATCH", "the C++ compute provider ABI is unsupported")
        library.jaya_compute_provider_id.argtypes = []
        library.jaya_compute_provider_id.restype = ctypes.c_char_p
        raw_provider = library.jaya_compute_provider_id()
        if not raw_provider:
            raise NativeProviderError("ABI_INVALID", "the C++ provider ID is unavailable")
        try:
            self._provider_id = raw_provider.decode("ascii")
        except UnicodeDecodeError as exc:
            raise NativeProviderError("ABI_INVALID", "the C++ provider ID is not ASCII") from exc

        int8_pointer = ctypes.POINTER(ctypes.c_int8)
        uint8_pointer = ctypes.POINTER(ctypes.c_uint8)
        float_pointer = ctypes.POINTER(ctypes.c_float)
        library.jaya_binary_dot_i8.argtypes = [
            int8_pointer,
            int8_pointer,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int64),
            ctypes.POINTER(ctypes.c_uint64),
        ]
        library.jaya_binary_dot_i8.restype = ctypes.c_int32
        library.jaya_binary_pack_i8.argtypes = [
            int8_pointer,
            ctypes.c_size_t,
            uint8_pointer,
            ctypes.c_size_t,
        ]
        library.jaya_binary_pack_i8.restype = ctypes.c_int32
        library.jaya_binary_dot_packed.argtypes = [
            uint8_pointer,
            uint8_pointer,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int64),
            ctypes.POINTER(ctypes.c_uint64),
        ]
        library.jaya_binary_dot_packed.restype = ctypes.c_int32
        library.jaya_ternary_gemm_f32_i8.argtypes = [
            float_pointer,
            int8_pointer,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
            float_pointer,
        ]
        library.jaya_ternary_gemm_f32_i8.restype = ctypes.c_int32

    @staticmethod
    def _raise_status(operation: str, status: int) -> None:
        if status == 0:
            return
        code = _STATUS_CODES.get(status, "PROVIDER_FAILURE")
        raise NativeProviderError(code, f"native {operation} failed with status {status}")

    def profile(self) -> dict[str, Any]:
        return {
            "contract_version": _ABI_VERSION,
            "requested_provider": self.requested,
            "selected_provider": self.provider_id,
            "native_available": self.native_available,
            "library_path": (str(self._loaded.path) if self._loaded is not None else None),
            "hardware_accelerated": False,
            "accelerator_provider": None,
            "machine": platform.machine() or "UNKNOWN",
        }

    def binary_dot(self, left: Any, right: Any) -> tuple[int, int]:
        left_values = np.ascontiguousarray(left, dtype=np.int8)
        right_values = np.ascontiguousarray(right, dtype=np.int8)
        if left_values.ndim != 1 or right_values.ndim != 1:
            raise NativeProviderError("INVALID_SIZE", "binary vectors must be one-dimensional")
        if left_values.shape != right_values.shape or left_values.size == 0:
            raise NativeProviderError("INVALID_SIZE", "binary vector shapes must match")
        if self._loaded is None:
            if not np.all(np.isin(left_values, (-1, 1))) or not np.all(
                np.isin(right_values, (-1, 1))
            ):
                raise NativeProviderError("INVALID_VALUE", "binary values must be -1 or +1")
            matches = int(np.count_nonzero(left_values == right_values))
            return matches, 2 * matches - int(left_values.size)

        result = ctypes.c_int64()
        native_matches = ctypes.c_uint64()
        status = self._loaded.library.jaya_binary_dot_i8(
            left_values.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
            right_values.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
            left_values.size,
            ctypes.byref(result),
            ctypes.byref(native_matches),
        )
        self._raise_status("binary dot", int(status))
        return int(native_matches.value), int(result.value)

    def binary_pack(self, values: Any) -> bytes:
        normalized = np.ascontiguousarray(values, dtype=np.int8)
        if normalized.ndim != 1 or normalized.size == 0:
            raise NativeProviderError("INVALID_SIZE", "binary vector must be one-dimensional")
        if self._loaded is None:
            if not np.all(np.isin(normalized, (-1, 1))):
                raise NativeProviderError("INVALID_VALUE", "binary values must be -1 or +1")
            positive = (normalized == 1).astype(np.uint8)
            return bytes(np.packbits(positive, bitorder="little").tobytes())
        output = np.empty((normalized.size + 7) // 8, dtype=np.uint8)
        status = self._loaded.library.jaya_binary_pack_i8(
            normalized.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
            normalized.size,
            output.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
            output.size,
        )
        self._raise_status("binary packing", int(status))
        return bytes(output.tobytes())

    def binary_dot_packed(self, left: bytes, right: bytes, bit_length: int) -> tuple[int, int]:
        if not isinstance(left, bytes) or not isinstance(right, bytes):
            raise NativeProviderError("INVALID_VALUE", "packed vectors must be bytes")
        expected_bytes = (bit_length + 7) // 8
        if bit_length <= 0 or len(left) != expected_bytes or len(right) != expected_bytes:
            raise NativeProviderError("INVALID_SIZE", "packed binary vector size is invalid")
        if self._loaded is None:
            left_bits = int.from_bytes(left, "little")
            right_bits = int.from_bytes(right, "little")
            mask = (1 << bit_length) - 1
            matches = (~(left_bits ^ right_bits) & mask).bit_count()
            return matches, 2 * matches - bit_length

        left_values = np.frombuffer(left, dtype=np.uint8)
        right_values = np.frombuffer(right, dtype=np.uint8)
        result = ctypes.c_int64()
        native_matches = ctypes.c_uint64()
        status = self._loaded.library.jaya_binary_dot_packed(
            left_values.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
            right_values.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
            bit_length,
            ctypes.byref(result),
            ctypes.byref(native_matches),
        )
        self._raise_status("packed binary dot", int(status))
        return int(native_matches.value), int(result.value)

    def ternary_linear(self, inputs: Any, weights: Any) -> np.ndarray[Any, np.dtype[np.float32]]:
        input_values = np.ascontiguousarray(inputs, dtype=np.float32)
        weight_values = np.ascontiguousarray(weights, dtype=np.int8)
        was_vector = input_values.ndim == 1
        if was_vector:
            input_values = input_values.reshape(1, -1)
        if input_values.ndim != 2 or weight_values.ndim != 2:
            raise NativeProviderError("INVALID_SIZE", "ternary linear inputs must be matrices")
        rows, inner = input_values.shape
        weight_inner, columns = weight_values.shape
        if rows == 0 or inner == 0 or columns == 0 or inner != weight_inner:
            raise NativeProviderError("INVALID_SIZE", "ternary linear shapes are incompatible")
        if not np.all(np.isfinite(input_values)):
            raise NativeProviderError("INVALID_VALUE", "ternary input contains non-finite values")
        if self._loaded is None and not np.all(np.isin(weight_values, (-1, 0, 1))):
            raise NativeProviderError("INVALID_VALUE", "ternary weights must be -1, 0, or +1")
        if self._loaded is None:
            positive = (weight_values == 1).astype(np.float32)
            negative = (weight_values == -1).astype(np.float32)
            output = np.dot(input_values, positive) - np.dot(input_values, negative)
        else:
            output = np.empty((rows, columns), dtype=np.float32)
            status = self._loaded.library.jaya_ternary_gemm_f32_i8(
                input_values.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                weight_values.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
                rows,
                inner,
                columns,
                output.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            )
            self._raise_status("ternary linear", int(status))
        return cast(
            np.ndarray[Any, np.dtype[np.float32]],
            output[0] if was_vector else output,
        )


@lru_cache(maxsize=8)
def _cached_compute_provider(
    selection: str, library_dir: str, library_file: str
) -> ComputeProvider:
    del library_dir, library_file
    return ComputeProvider(selection)


def get_compute_provider(selection: str | None = None) -> ComputeProvider:
    requested = selection or os.getenv("JAYA_COMPUTE_PROVIDER", "auto")
    return _cached_compute_provider(
        requested,
        os.getenv("JAYA_NATIVE_LIBRARY_DIR", ""),
        os.getenv("JAYA_COMPUTE_LIBRARY", ""),
    )
