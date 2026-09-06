"""Trusted P20 privacy-scope decisions with Rust or Python providers."""

from __future__ import annotations

import ctypes
import os
import re
import struct
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .loader import NativeProviderError, load_first_party_library

_ABI_VERSION = 1
_CAPABILITY_PRIVACY_SCOPE = 1 << 1
_SELECTIONS = frozenset({"auto", "python-reference", "trusted-rust"})
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}")
_MAX_CONTRACT_BYTES = 1024 * 1024
_REASONS = {
    1: "OWNER_MISMATCH",
    2: "OWNER_LOCAL_PURPOSE_ALLOWED",
    3: "PUBLIC_EXTERNAL_USE_ALLOWED",
    4: "SIGNED_CONSENT_ALLOWED",
    5: "SIGNED_CONSENT_REQUIRED",
    6: "CONSENT_SCOPE_INVALID",
}
_STATUS_CODES = {
    -1: "NULL_POINTER",
    -2: "INVALID_SIZE",
    -3: "INVALID_VALUE",
    -4: "RESOURCE_LIMIT_EXCEEDED",
}


@dataclass(frozen=True, slots=True)
class PrivacyUseContract:
    """Normalized P20 request without payload or secret material."""

    actor_id: str
    owner_id: str
    subject_id: str
    provider_id: str
    classification_code: int
    purpose_code: int
    destination_code: int


@dataclass(frozen=True, slots=True)
class VerifiedConsentScope:
    """Scope from a consent whose signature/status/expiry Python verified."""

    owner_id: str
    subject_id: str
    classification_mask: int
    purpose_mask: int
    provider_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrustedPrivacyDecision:
    """Stable P20 effect and reason returned by a trusted provider."""

    effect: int
    reason_code: str


def _identifier(value: str) -> bytes:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise NativeProviderError("INVALID_VALUE", "privacy identifier is invalid")
    return value.encode("ascii")


def _append_identifier(output: bytearray, value: str) -> None:
    encoded = _identifier(value)
    output.extend(struct.pack("<H", len(encoded)))
    output.extend(encoded)


def _encode_contract(
    request: PrivacyUseContract,
    consent: VerifiedConsentScope | None,
) -> bytes:
    if not isinstance(request, PrivacyUseContract):
        raise NativeProviderError("INVALID_VALUE", "privacy request contract is invalid")
    if (
        not 0 <= request.classification_code < 4
        or not 0 <= request.purpose_code < 6
        or not 0 <= request.destination_code < 3
    ):
        raise NativeProviderError("INVALID_VALUE", "privacy request enum is invalid")
    output = bytearray(b"JPV1")
    for value in (
        request.actor_id,
        request.owner_id,
        request.subject_id,
        request.provider_id,
    ):
        _append_identifier(output, value)
    output.extend(
        (
            request.classification_code,
            request.purpose_code,
            request.destination_code,
            int(consent is not None),
        )
    )
    if consent is not None:
        if not isinstance(consent, VerifiedConsentScope):
            raise NativeProviderError("INVALID_VALUE", "privacy consent scope is invalid")
        if (
            not 0 < consent.classification_mask <= 0b0000_1111
            or not 0 < consent.purpose_mask <= 0b0011_1111
            or not consent.provider_ids
            or len(consent.provider_ids) > (1 << 16) - 1
        ):
            raise NativeProviderError("INVALID_VALUE", "privacy consent mask is invalid")
        _append_identifier(output, consent.owner_id)
        _append_identifier(output, consent.subject_id)
        output.extend((consent.classification_mask, consent.purpose_mask))
        output.extend(struct.pack("<H", len(consent.provider_ids)))
        for provider_id in consent.provider_ids:
            _append_identifier(output, provider_id)
    if len(output) > _MAX_CONTRACT_BYTES:
        raise NativeProviderError("RESOURCE_LIMIT_EXCEEDED", "privacy contract is too large")
    return bytes(output)


class TrustedPrivacyGate:
    """Evaluate P20 scope without receiving plaintext, keys, or signatures."""

    def __init__(self, selection: str = "auto") -> None:
        requested = str(selection).strip().casefold()
        if requested not in _SELECTIONS:
            raise NativeProviderError(
                "INVALID_PROVIDER",
                f"privacy provider must be one of: {', '.join(sorted(_SELECTIONS))}",
            )
        self.requested = requested
        self._loaded = None
        self._provider_id = "python-privacy-reference-v1"
        if requested != "python-reference":
            self._loaded = load_first_party_library(
                "jaya_trusted", specific_env="JAYA_TRUSTED_LIBRARY"
            )
        if self._loaded is not None:
            try:
                self._bind_native()
            except (AttributeError, NativeProviderError):
                self._loaded = None
                self._provider_id = "python-privacy-reference-v1"
                if requested == "trusted-rust":
                    raise NativeProviderError(
                        "PROVIDER_UNAVAILABLE",
                        "the Rust provider does not expose privacy evaluation",
                    ) from None
        elif requested == "trusted-rust":
            raise NativeProviderError(
                "PROVIDER_UNAVAILABLE", "the required Rust privacy provider could not be loaded"
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
            raise NativeProviderError("ABI_MISMATCH", "the Rust privacy ABI is unsupported")
        library.jaya_trusted_capabilities.argtypes = []
        library.jaya_trusted_capabilities.restype = ctypes.c_uint64
        if int(library.jaya_trusted_capabilities()) & _CAPABILITY_PRIVACY_SCOPE == 0:
            raise NativeProviderError(
                "CAPABILITY_UNAVAILABLE", "the Rust privacy capability is unavailable"
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
        pointer = ctypes.POINTER(ctypes.c_uint8)
        library.jaya_trusted_evaluate_privacy.argtypes = [
            pointer,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_uint8),
        ]
        library.jaya_trusted_evaluate_privacy.restype = ctypes.c_int32

    def profile(self) -> dict[str, Any]:
        return {
            "contract_version": _ABI_VERSION,
            "requested_provider": self.requested,
            "selected_provider": self.provider_id,
            "native_available": self.native_available,
            "library_path": str(self._loaded.path) if self._loaded is not None else None,
            "receives_plaintext": False,
            "receives_secret_material": False,
        }

    def evaluate(
        self,
        request: PrivacyUseContract,
        consent: VerifiedConsentScope | None = None,
    ) -> TrustedPrivacyDecision:
        encoded = _encode_contract(request, consent)
        if self._loaded is None:
            if request.actor_id != request.owner_id:
                return TrustedPrivacyDecision(2, _REASONS[1])
            if request.destination_code in {0, 2}:
                return TrustedPrivacyDecision(1, _REASONS[2])
            if request.classification_code == 0:
                return TrustedPrivacyDecision(1, _REASONS[3])
            if consent is None:
                return TrustedPrivacyDecision(2, _REASONS[5])
            scope_matches = (
                consent.owner_id == request.owner_id
                and consent.subject_id == request.subject_id
                and consent.classification_mask & (1 << request.classification_code) != 0
                and consent.purpose_mask & (1 << request.purpose_code) != 0
                and request.provider_id in consent.provider_ids
            )
            return TrustedPrivacyDecision(
                1 if scope_matches else 2,
                _REASONS[4 if scope_matches else 6],
            )

        buffer = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
        output_effect = ctypes.c_uint8()
        output_reason = ctypes.c_uint8()
        status = self._loaded.library.jaya_trusted_evaluate_privacy(
            buffer,
            len(encoded),
            ctypes.byref(output_effect),
            ctypes.byref(output_reason),
        )
        if int(status) != 0:
            code = _STATUS_CODES.get(int(status), "PROVIDER_FAILURE")
            raise NativeProviderError(
                code, f"trusted privacy evaluation failed with status {status}"
            )
        reason = _REASONS.get(int(output_reason.value))
        if int(output_effect.value) not in {1, 2} or reason is None:
            raise NativeProviderError("ABI_INVALID", "privacy provider returned invalid output")
        return TrustedPrivacyDecision(int(output_effect.value), reason)


@lru_cache(maxsize=8)
def _cached_privacy_gate(selection: str, library_dir: str, library_file: str) -> TrustedPrivacyGate:
    del library_dir, library_file
    return TrustedPrivacyGate(selection)


def get_trusted_privacy_gate(selection: str | None = None) -> TrustedPrivacyGate:
    requested = (
        selection
        or os.getenv("JAYA_PRIVACY_PROVIDER")
        or os.getenv("JAYA_TRUSTED_PROVIDER", "auto")
    )
    return _cached_privacy_gate(
        requested,
        os.getenv("JAYA_NATIVE_LIBRARY_DIR", ""),
        os.getenv("JAYA_TRUSTED_LIBRARY", ""),
    )


__all__ = [
    "PrivacyUseContract",
    "TrustedPrivacyDecision",
    "TrustedPrivacyGate",
    "VerifiedConsentScope",
    "get_trusted_privacy_gate",
]
