"""Rust-backed trusted artifact validation with a labeled Python reference path."""

from __future__ import annotations

import ctypes
import os
import re
from functools import lru_cache
from typing import Any

import numpy as np

from .loader import NativeProviderError, load_first_party_library

_ABI_VERSION = 1
_SELECTIONS = frozenset({"auto", "python-reference", "trusted-rust"})
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_STATUS_CODES = {
    -1: "NULL_POINTER",
    -2: "INVALID_SIZE",
    -3: "INVALID_VALUE",
    -4: "RESOURCE_LIMIT_EXCEEDED",
}


class TrustedArtifactGate:
    """Validate artifact invariants across a memory-safe FFI boundary."""

    def __init__(self, selection: str = "auto") -> None:
        requested = str(selection).strip().casefold()
        if requested not in _SELECTIONS:
            raise NativeProviderError(
                "INVALID_PROVIDER",
                f"trusted provider must be one of: {', '.join(sorted(_SELECTIONS))}",
            )
        self.requested = requested
        self._loaded = None
        self._provider_id = "python-artifact-validation-v1"
        if requested != "python-reference":
            self._loaded = load_first_party_library(
                "jaya_trusted", specific_env="JAYA_TRUSTED_LIBRARY"
            )
        if self._loaded is not None:
            self._bind_native()
        elif requested == "trusted-rust":
            raise NativeProviderError(
                "PROVIDER_UNAVAILABLE", "the required Rust trusted provider could not be loaded"
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
        library.jaya_trusted_abi_version.argtypes = []
        library.jaya_trusted_abi_version.restype = ctypes.c_uint32
        if int(library.jaya_trusted_abi_version()) != _ABI_VERSION:
            raise NativeProviderError(
                "ABI_MISMATCH", "the Rust trusted provider ABI is unsupported"
            )
        library.jaya_trusted_provider_id.argtypes = []
        library.jaya_trusted_provider_id.restype = ctypes.c_char_p
        raw_provider = library.jaya_trusted_provider_id()
        if not raw_provider:
            raise NativeProviderError("ABI_INVALID", "the Rust provider ID is unavailable")
        try:
            self._provider_id = raw_provider.decode("ascii")
        except UnicodeDecodeError as exc:
            raise NativeProviderError("ABI_INVALID", "the Rust provider ID is not ASCII") from exc
        uint8_pointer = ctypes.POINTER(ctypes.c_uint8)
        int8_pointer = ctypes.POINTER(ctypes.c_int8)
        library.jaya_trusted_validate_identifier.argtypes = [uint8_pointer, ctypes.c_size_t]
        library.jaya_trusted_validate_identifier.restype = ctypes.c_int32
        library.jaya_trusted_validate_binary_layout.argtypes = [
            uint8_pointer,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        library.jaya_trusted_validate_binary_layout.restype = ctypes.c_int32
        library.jaya_trusted_validate_ternary_values.argtypes = [
            int8_pointer,
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        library.jaya_trusted_validate_ternary_values.restype = ctypes.c_int32

    @staticmethod
    def _raise_status(operation: str, status: int) -> None:
        if status == 0:
            return
        code = _STATUS_CODES.get(status, "PROVIDER_FAILURE")
        raise NativeProviderError(code, f"trusted {operation} failed with status {status}")

    def profile(self) -> dict[str, Any]:
        return {
            "contract_version": _ABI_VERSION,
            "requested_provider": self.requested,
            "selected_provider": self.provider_id,
            "native_available": self.native_available,
            "library_path": (str(self._loaded.path) if self._loaded is not None else None),
        }

    def validate_identifier(self, value: str) -> None:
        if not isinstance(value, str):
            raise NativeProviderError("INVALID_VALUE", "artifact identifier must be text")
        try:
            encoded = value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise NativeProviderError("INVALID_VALUE", "artifact identifier must be ASCII") from exc
        if self._loaded is None:
            if _SAFE_ID.fullmatch(value) is None:
                raise NativeProviderError("INVALID_VALUE", "artifact identifier is invalid")
            return
        values = np.frombuffer(encoded, dtype=np.uint8)
        status = self._loaded.library.jaya_trusted_validate_identifier(
            values.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), values.size
        )
        self._raise_status("identifier validation", int(status))

    def validate_binary_layout(
        self,
        packed_rows: tuple[bytes, ...],
        *,
        input_features: int,
        max_features: int,
        max_outputs: int,
        max_total_bits: int,
    ) -> None:
        output_units = len(packed_rows)
        row_bytes = (input_features + 7) // 8 if input_features > 0 else 0
        if (
            input_features <= 0
            or input_features > max_features
            or output_units <= 0
            or output_units > max_outputs
            or input_features * output_units > max_total_bits
            or any(len(row) != row_bytes for row in packed_rows)
        ):
            raise NativeProviderError("INVALID_SIZE", "binary artifact layout is invalid")
        data = b"".join(packed_rows)
        if self._loaded is None:
            remainder = input_features % 8
            if remainder and any(row[-1] & ~((1 << remainder) - 1) for row in packed_rows):
                raise NativeProviderError("INVALID_VALUE", "binary artifact padding must be zero")
            return
        values = np.frombuffer(data, dtype=np.uint8)
        status = self._loaded.library.jaya_trusted_validate_binary_layout(
            values.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
            values.size,
            input_features,
            output_units,
            max_features,
            max_outputs,
            max_total_bits,
        )
        self._raise_status("binary layout validation", int(status))

    def validate_ternary_values(self, values: Any, *, max_length: int) -> None:
        normalized = np.ascontiguousarray(values, dtype=np.int8).reshape(-1)
        if normalized.size == 0 or normalized.size > max_length:
            raise NativeProviderError("INVALID_SIZE", "ternary artifact size is invalid")
        if self._loaded is None:
            if not np.all(np.isin(normalized, (-1, 0, 1))):
                raise NativeProviderError("INVALID_VALUE", "ternary artifact values are invalid")
            return
        status = self._loaded.library.jaya_trusted_validate_ternary_values(
            normalized.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
            normalized.size,
            max_length,
        )
        self._raise_status("ternary artifact validation", int(status))


@lru_cache(maxsize=8)
def _cached_trusted_gate(
    selection: str, library_dir: str, library_file: str
) -> TrustedArtifactGate:
    del library_dir, library_file
    return TrustedArtifactGate(selection)


def get_trusted_artifact_gate(selection: str | None = None) -> TrustedArtifactGate:
    requested = selection or os.getenv("JAYA_TRUSTED_PROVIDER", "auto")
    return _cached_trusted_gate(
        requested,
        os.getenv("JAYA_NATIVE_LIBRARY_DIR", ""),
        os.getenv("JAYA_TRUSTED_LIBRARY", ""),
    )
