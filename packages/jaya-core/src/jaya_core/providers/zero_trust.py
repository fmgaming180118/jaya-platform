"""Trusted P18 authorization-scope decisions with Rust or Python providers."""

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
_CAPABILITY_ZERO_TRUST_AUTHORIZATION = 1 << 2
_SELECTIONS = frozenset({"auto", "python-reference", "trusted-rust"})
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_CONTRACT_BYTES = 1024 * 1024
_REASONS = {
    1: "ZERO_TRUST_PRINCIPAL_UNKNOWN",
    2: "ZERO_TRUST_PRINCIPAL_REVOKED",
    3: "ZERO_TRUST_PRINCIPAL_STATE_UNAVAILABLE",
    4: "ZERO_TRUST_PRINCIPAL_KEY_STALE",
    5: "ZERO_TRUST_NODE_MISMATCH",
    6: "ZERO_TRUST_CAPABILITY_DENIED",
    7: "ZERO_TRUST_PAYLOAD_MISMATCH",
    8: "ATTESTATION_REQUIRED",
    9: "ZERO_TRUST_ATTESTATION_INVALID",
    10: "ZERO_TRUST_ATTESTATION_UNAVAILABLE",
    11: "VERIFIED_LEAST_PRIVILEGE",
}
_STATUS_CODES = {
    -1: "NULL_POINTER",
    -2: "INVALID_SIZE",
    -3: "INVALID_VALUE",
    -4: "RESOURCE_LIMIT_EXCEEDED",
}


@dataclass(frozen=True, slots=True)
class ZeroTrustAuthorizationContract:
    """Normalized authorization facts without payload, signature, or secret."""

    envelope_id: str
    principal_id: str
    envelope_node_id: str
    capability_id: str
    nonce: str
    principal_status: int
    principal_state: int
    attestation_state: int
    persisted_node_id: str | None
    capability_ids: tuple[str, ...]
    claimed_payload_sha256: str
    actual_payload_sha256: str


@dataclass(frozen=True, slots=True)
class TrustedZeroTrustDecision:
    """Stable P18 effect and reason returned by a trusted provider."""

    effect: int
    reason_code: str


def _identifier(value: str) -> bytes:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise NativeProviderError("INVALID_VALUE", "zero-trust identifier is invalid")
    return value.encode("ascii")


def _append_identifier(output: bytearray, value: str) -> None:
    encoded = _identifier(value)
    output.extend(struct.pack("<H", len(encoded)))
    output.extend(encoded)


def _digest(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise NativeProviderError("INVALID_VALUE", "zero-trust payload digest is invalid")
    return bytes.fromhex(value)


def _encode_contract(contract: ZeroTrustAuthorizationContract) -> bytes:
    if not isinstance(contract, ZeroTrustAuthorizationContract):
        raise NativeProviderError("INVALID_VALUE", "zero-trust contract is invalid")
    if (
        contract.principal_status not in {0, 1, 2}
        or contract.principal_state not in {0, 1, 2, 3, 4}
        or contract.attestation_state not in {0, 1, 2, 3}
    ):
        raise NativeProviderError("INVALID_VALUE", "zero-trust contract enum is invalid")
    has_principal = contract.principal_status != 0
    if has_principal != (contract.persisted_node_id is not None):
        raise NativeProviderError("INVALID_VALUE", "zero-trust principal scope is invalid")
    if has_principal and (
        not contract.capability_ids or len(contract.capability_ids) > (1 << 16) - 1
    ):
        raise NativeProviderError("INVALID_VALUE", "zero-trust capability scope is invalid")
    if not has_principal and (contract.capability_ids or contract.principal_state != 0):
        raise NativeProviderError("INVALID_VALUE", "unknown principal contains persisted state")

    output = bytearray(b"JZT1")
    for value in (
        contract.envelope_id,
        contract.principal_id,
        contract.envelope_node_id,
        contract.capability_id,
        contract.nonce,
    ):
        _append_identifier(output, value)
    output.extend(
        (
            contract.principal_status,
            contract.principal_state,
            contract.attestation_state,
        )
    )
    if has_principal:
        assert contract.persisted_node_id is not None
        _append_identifier(output, contract.persisted_node_id)
        output.extend(struct.pack("<H", len(contract.capability_ids)))
        for capability_id in contract.capability_ids:
            _append_identifier(output, capability_id)
    output.extend(_digest(contract.claimed_payload_sha256))
    output.extend(_digest(contract.actual_payload_sha256))
    if len(output) > _MAX_CONTRACT_BYTES:
        raise NativeProviderError("RESOURCE_LIMIT_EXCEEDED", "zero-trust contract is too large")
    return bytes(output)


class TrustedZeroTrustGate:
    """Evaluate P18 scope without receiving payloads, keys, or signatures."""

    def __init__(self, selection: str = "auto") -> None:
        requested = str(selection).strip().casefold()
        if requested not in _SELECTIONS:
            raise NativeProviderError(
                "INVALID_PROVIDER",
                f"zero-trust provider must be one of: {', '.join(sorted(_SELECTIONS))}",
            )
        self.requested = requested
        self._loaded = None
        self._provider_id = "python-zero-trust-reference-v1"
        if requested != "python-reference":
            self._loaded = load_first_party_library(
                "jaya_trusted", specific_env="JAYA_TRUSTED_LIBRARY"
            )
        if self._loaded is not None:
            try:
                self._bind_native()
            except (AttributeError, NativeProviderError):
                self._loaded = None
                self._provider_id = "python-zero-trust-reference-v1"
                if requested == "trusted-rust":
                    raise NativeProviderError(
                        "PROVIDER_UNAVAILABLE",
                        "the Rust provider does not expose zero-trust evaluation",
                    ) from None
        elif requested == "trusted-rust":
            raise NativeProviderError(
                "PROVIDER_UNAVAILABLE",
                "the required Rust zero-trust provider could not be loaded",
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
            raise NativeProviderError("ABI_MISMATCH", "the Rust zero-trust ABI is unsupported")
        library.jaya_trusted_capabilities.argtypes = []
        library.jaya_trusted_capabilities.restype = ctypes.c_uint64
        if int(library.jaya_trusted_capabilities()) & _CAPABILITY_ZERO_TRUST_AUTHORIZATION == 0:
            raise NativeProviderError(
                "CAPABILITY_UNAVAILABLE",
                "the Rust zero-trust capability is unavailable",
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
        library.jaya_trusted_evaluate_zero_trust.argtypes = [
            pointer,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_uint8),
        ]
        library.jaya_trusted_evaluate_zero_trust.restype = ctypes.c_int32

    def profile(self) -> dict[str, Any]:
        return {
            "contract_version": _ABI_VERSION,
            "requested_provider": self.requested,
            "selected_provider": self.provider_id,
            "native_available": self.native_available,
            "library_path": str(self._loaded.path) if self._loaded is not None else None,
            "receives_payload": False,
            "receives_secret_material": False,
            "receives_signature": False,
            "receives_verified_attestation_result": True,
        }

    def evaluate(self, contract: ZeroTrustAuthorizationContract) -> TrustedZeroTrustDecision:
        encoded = _encode_contract(contract)
        if self._loaded is None:
            if contract.principal_status == 0 or contract.principal_state == 1:
                return TrustedZeroTrustDecision(2, _REASONS[1])
            if contract.principal_status == 2 or contract.principal_state == 2:
                return TrustedZeroTrustDecision(2, _REASONS[2])
            if contract.principal_state == 3:
                return TrustedZeroTrustDecision(2, _REASONS[3])
            if contract.principal_state == 4:
                return TrustedZeroTrustDecision(2, _REASONS[4])
            if contract.persisted_node_id != contract.envelope_node_id:
                return TrustedZeroTrustDecision(2, _REASONS[5])
            if contract.capability_id not in contract.capability_ids:
                return TrustedZeroTrustDecision(2, _REASONS[6])
            if contract.claimed_payload_sha256 != contract.actual_payload_sha256:
                return TrustedZeroTrustDecision(2, _REASONS[7])
            if contract.attestation_state == 0:
                return TrustedZeroTrustDecision(3, _REASONS[8])
            if contract.attestation_state == 3:
                return TrustedZeroTrustDecision(2, _REASONS[10])
            if contract.attestation_state == 2:
                return TrustedZeroTrustDecision(2, _REASONS[9])
            return TrustedZeroTrustDecision(1, _REASONS[11])

        buffer = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
        output_effect = ctypes.c_uint8()
        output_reason = ctypes.c_uint8()
        status = self._loaded.library.jaya_trusted_evaluate_zero_trust(
            buffer,
            len(encoded),
            ctypes.byref(output_effect),
            ctypes.byref(output_reason),
        )
        if int(status) != 0:
            code = _STATUS_CODES.get(int(status), "PROVIDER_FAILURE")
            raise NativeProviderError(
                code, f"trusted zero-trust evaluation failed with status {status}"
            )
        reason = _REASONS.get(int(output_reason.value))
        if int(output_effect.value) not in {1, 2, 3} or reason is None:
            raise NativeProviderError("ABI_INVALID", "zero-trust provider returned invalid output")
        return TrustedZeroTrustDecision(int(output_effect.value), reason)


@lru_cache(maxsize=8)
def _cached_zero_trust_gate(
    selection: str, library_dir: str, library_file: str
) -> TrustedZeroTrustGate:
    del library_dir, library_file
    return TrustedZeroTrustGate(selection)


def get_trusted_zero_trust_gate(selection: str | None = None) -> TrustedZeroTrustGate:
    requested = (
        selection
        or os.getenv("JAYA_ZERO_TRUST_PROVIDER")
        or os.getenv("JAYA_TRUSTED_PROVIDER", "auto")
    )
    return _cached_zero_trust_gate(
        requested,
        os.getenv("JAYA_NATIVE_LIBRARY_DIR", ""),
        os.getenv("JAYA_TRUSTED_LIBRARY", ""),
    )


__all__ = [
    "TrustedZeroTrustDecision",
    "TrustedZeroTrustGate",
    "ZeroTrustAuthorizationContract",
    "get_trusted_zero_trust_gate",
]
