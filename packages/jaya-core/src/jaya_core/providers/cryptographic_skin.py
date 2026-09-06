"""Trusted P13 cryptographic-envelope admission with Rust or Python providers."""

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
_CAPABILITY_CRYPTOGRAPHIC_SKIN = 1 << 3
_SELECTIONS = frozenset({"auto", "python-reference", "trusted-rust"})
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}")
_SAFE_PURPOSE = re.compile(r"[a-z][a-z0-9_.:-]{0,127}")
_SAFE_CONTENT_TYPE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}/"
    r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}"
)
_MAX_CONTRACT_BYTES = 4 * 1024
_MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
_REASONS = {
    1: "CRYPTO_SKIN_CONTRACT_INVALID",
    2: "ATTESTATION_REQUIRED",
    3: "CRYPTO_SKIN_SIGNATURE_INVALID",
    4: "CRYPTO_SKIN_ATTESTATION_UNAVAILABLE",
    5: "CRYPTO_SKIN_KEY_STATE_INVALID",
    6: "CRYPTO_SKIN_KEY_REVOKED",
    7: "CRYPTO_SKIN_CLOCK_SKEW",
    8: "CRYPTO_SKIN_ENVELOPE_EXPIRED",
    9: "ENVELOPE_BYTES_REQUIRED",
    10: "CRYPTO_SKIN_NONCE_INVALID",
    11: "CRYPTO_SKIN_CIPHERTEXT_INVALID",
    12: "CRYPTO_SKIN_PAYLOAD_TOO_LARGE",
    13: "VERIFIED_CRYPTOGRAPHIC_ENVELOPE",
}
_STATUS_CODES = {
    -1: "NULL_POINTER",
    -2: "INVALID_SIZE",
    -3: "INVALID_VALUE",
    -4: "RESOURCE_LIMIT_EXCEEDED",
}


@dataclass(frozen=True, slots=True)
class CryptographicEnvelopeContract:
    """Normalized facts; raw payload, nonce, ciphertext, signature, and keys stay in Python."""

    envelope_id: str
    key_id: str
    purpose: str
    subject: str
    content_type: str
    schema_version: int
    algorithm_suite_code: int
    operation_code: int
    key_state: int
    attestation_state: int
    temporal_state: int
    nonce_size_bytes: int
    ciphertext_size_bytes: int
    max_payload_bytes: int


@dataclass(frozen=True, slots=True)
class TrustedCryptographicSkinDecision:
    """Stable P13 effect and reason returned by an envelope gate."""

    effect: int
    reason_code: str


def _field(value: str, pattern: re.Pattern[str], label: str) -> bytes:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise NativeProviderError("INVALID_VALUE", f"cryptographic {label} is invalid")
    return value.encode("ascii")


def _append_field(output: bytearray, value: bytes) -> None:
    output.extend(struct.pack("<H", len(value)))
    output.extend(value)


def _encode_contract(contract: CryptographicEnvelopeContract) -> bytes:
    if not isinstance(contract, CryptographicEnvelopeContract):
        raise NativeProviderError("INVALID_VALUE", "cryptographic envelope contract is invalid")
    integer_fields = (
        contract.schema_version,
        contract.algorithm_suite_code,
        contract.operation_code,
        contract.key_state,
        contract.attestation_state,
        contract.temporal_state,
        contract.nonce_size_bytes,
        contract.ciphertext_size_bytes,
        contract.max_payload_bytes,
    )
    if any(type(value) is not int for value in integer_fields):
        raise NativeProviderError("INVALID_VALUE", "cryptographic contract integer is invalid")
    if (
        not 0 <= contract.schema_version <= (1 << 16) - 1
        or not 0 <= contract.algorithm_suite_code <= 255
        or contract.operation_code not in {1, 2}
        or contract.key_state not in {0, 1, 2, 3}
        or contract.attestation_state not in {0, 1, 2, 3}
        or contract.temporal_state not in {0, 1, 2, 3}
        or not 0 <= contract.nonce_size_bytes <= (1 << 16) - 1
        or not 0 <= contract.ciphertext_size_bytes <= _MAX_PAYLOAD_BYTES + 16
        or not 1 <= contract.max_payload_bytes <= _MAX_PAYLOAD_BYTES
    ):
        raise NativeProviderError("INVALID_VALUE", "cryptographic contract value is invalid")
    if contract.attestation_state == 0 and any(
        (
            contract.key_state,
            contract.temporal_state,
            contract.nonce_size_bytes,
            contract.ciphertext_size_bytes,
        )
    ):
        raise NativeProviderError(
            "INVALID_VALUE", "pending attestation contains unverified envelope facts"
        )

    output = bytearray(b"JCS1")
    for value, pattern, label in (
        (contract.envelope_id, _SAFE_ID, "envelope ID"),
        (contract.key_id, _SAFE_ID, "key ID"),
        (contract.purpose, _SAFE_PURPOSE, "purpose"),
        (contract.subject, _SAFE_ID, "subject"),
        (contract.content_type, _SAFE_CONTENT_TYPE, "content type"),
    ):
        _append_field(output, _field(value, pattern, label))
    output.extend(struct.pack("<H", contract.schema_version))
    output.extend(
        (
            contract.algorithm_suite_code,
            contract.operation_code,
            contract.key_state,
            contract.attestation_state,
            contract.temporal_state,
        )
    )
    output.extend(
        struct.pack(
            "<HII",
            contract.nonce_size_bytes,
            contract.ciphertext_size_bytes,
            contract.max_payload_bytes,
        )
    )
    if len(output) > _MAX_CONTRACT_BYTES:
        raise NativeProviderError(
            "RESOURCE_LIMIT_EXCEEDED", "cryptographic envelope contract is too large"
        )
    return bytes(output)


def _evaluate_reference(
    contract: CryptographicEnvelopeContract,
) -> TrustedCryptographicSkinDecision:
    if contract.schema_version != 1 or contract.algorithm_suite_code != 1:
        return TrustedCryptographicSkinDecision(2, _REASONS[1])
    if contract.attestation_state == 0:
        return TrustedCryptographicSkinDecision(3, _REASONS[2])
    if contract.attestation_state == 3:
        return TrustedCryptographicSkinDecision(2, _REASONS[4])
    if contract.attestation_state == 2:
        return TrustedCryptographicSkinDecision(2, _REASONS[3])
    if contract.key_state == 3:
        return TrustedCryptographicSkinDecision(2, _REASONS[6])
    if contract.key_state == 0 or (contract.operation_code == 1 and contract.key_state != 1):
        return TrustedCryptographicSkinDecision(2, _REASONS[5])
    if contract.temporal_state == 2:
        return TrustedCryptographicSkinDecision(2, _REASONS[7])
    if contract.temporal_state == 3:
        return TrustedCryptographicSkinDecision(2, _REASONS[8])
    if contract.temporal_state == 0:
        return TrustedCryptographicSkinDecision(2, _REASONS[1])
    if contract.nonce_size_bytes == 0 and contract.ciphertext_size_bytes == 0:
        return TrustedCryptographicSkinDecision(3, _REASONS[9])
    if contract.nonce_size_bytes != 12:
        return TrustedCryptographicSkinDecision(2, _REASONS[10])
    if contract.ciphertext_size_bytes < 16:
        return TrustedCryptographicSkinDecision(2, _REASONS[11])
    if contract.ciphertext_size_bytes > contract.max_payload_bytes + 16:
        return TrustedCryptographicSkinDecision(2, _REASONS[12])
    return TrustedCryptographicSkinDecision(1, _REASONS[13])


class TrustedCryptographicSkinGate:
    """Evaluate P13 envelope admission without receiving cryptographic material."""

    def __init__(self, selection: str = "auto") -> None:
        requested = str(selection).strip().casefold()
        if requested not in _SELECTIONS:
            raise NativeProviderError(
                "INVALID_PROVIDER",
                f"cryptographic skin provider must be one of: {', '.join(sorted(_SELECTIONS))}",
            )
        self.requested = requested
        self._loaded = None
        self._provider_id = "python-cryptographic-skin-reference-v1"
        if requested != "python-reference":
            self._loaded = load_first_party_library(
                "jaya_trusted", specific_env="JAYA_TRUSTED_LIBRARY"
            )
        if self._loaded is not None:
            try:
                self._bind_native()
            except (AttributeError, NativeProviderError):
                self._loaded = None
                self._provider_id = "python-cryptographic-skin-reference-v1"
                if requested == "trusted-rust":
                    raise NativeProviderError(
                        "PROVIDER_UNAVAILABLE",
                        "the Rust provider does not expose cryptographic envelope evaluation",
                    ) from None
        elif requested == "trusted-rust":
            raise NativeProviderError(
                "PROVIDER_UNAVAILABLE",
                "the required Rust cryptographic skin provider could not be loaded",
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
            raise NativeProviderError("ABI_MISMATCH", "the cryptographic skin ABI is unsupported")
        library.jaya_trusted_capabilities.argtypes = []
        library.jaya_trusted_capabilities.restype = ctypes.c_uint64
        if int(library.jaya_trusted_capabilities()) & _CAPABILITY_CRYPTOGRAPHIC_SKIN == 0:
            raise NativeProviderError(
                "CAPABILITY_UNAVAILABLE",
                "the Rust cryptographic envelope capability is unavailable",
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
        library.jaya_trusted_evaluate_cryptographic_skin.argtypes = [
            pointer,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_uint8),
        ]
        library.jaya_trusted_evaluate_cryptographic_skin.restype = ctypes.c_int32

    def profile(self) -> dict[str, Any]:
        return {
            "contract_version": _ABI_VERSION,
            "requested_provider": self.requested,
            "selected_provider": self.provider_id,
            "native_available": self.native_available,
            "library_path": str(self._loaded.path) if self._loaded is not None else None,
            "receives_payload": False,
            "receives_secret_material": False,
            "receives_nonce": False,
            "receives_ciphertext": False,
            "receives_signature": False,
            "receives_verified_attestation_result": True,
        }

    def evaluate(self, contract: CryptographicEnvelopeContract) -> TrustedCryptographicSkinDecision:
        encoded = _encode_contract(contract)
        if self._loaded is None:
            return _evaluate_reference(contract)

        buffer = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
        output_effect = ctypes.c_uint8()
        output_reason = ctypes.c_uint8()
        status = self._loaded.library.jaya_trusted_evaluate_cryptographic_skin(
            buffer,
            len(encoded),
            ctypes.byref(output_effect),
            ctypes.byref(output_reason),
        )
        if int(status) != 0:
            code = _STATUS_CODES.get(int(status), "PROVIDER_FAILURE")
            raise NativeProviderError(
                code, f"trusted cryptographic envelope evaluation failed with status {status}"
            )
        reason = _REASONS.get(int(output_reason.value))
        if int(output_effect.value) not in {1, 2, 3} or reason is None:
            raise NativeProviderError(
                "ABI_INVALID", "cryptographic skin provider returned invalid output"
            )
        return TrustedCryptographicSkinDecision(int(output_effect.value), reason)


@lru_cache(maxsize=8)
def _cached_cryptographic_skin_gate(
    selection: str, library_dir: str, library_file: str
) -> TrustedCryptographicSkinGate:
    del library_dir, library_file
    return TrustedCryptographicSkinGate(selection)


def get_trusted_cryptographic_skin_gate(
    selection: str | None = None,
) -> TrustedCryptographicSkinGate:
    requested = (
        selection
        or os.getenv("JAYA_CRYPTOGRAPHIC_SKIN_PROVIDER")
        or os.getenv("JAYA_TRUSTED_PROVIDER", "auto")
    )
    return _cached_cryptographic_skin_gate(
        requested,
        os.getenv("JAYA_NATIVE_LIBRARY_DIR", ""),
        os.getenv("JAYA_TRUSTED_LIBRARY", ""),
    )


__all__ = [
    "CryptographicEnvelopeContract",
    "TrustedCryptographicSkinDecision",
    "TrustedCryptographicSkinGate",
    "get_trusted_cryptographic_skin_gate",
]
