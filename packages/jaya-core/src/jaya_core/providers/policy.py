"""Trusted P15 policy-rule evaluation with a Rust or Python provider."""

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
_CAPABILITY_POLICY_EVALUATION = 1 << 0
_SELECTIONS = frozenset({"auto", "python-reference", "trusted-rust"})
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,191}")
_VALID_EFFECTS = frozenset({1, 2, 3})
_MAX_POLICY_BYTES = 1024 * 1024
_MAX_RULES = 4096
_NO_RULE = (1 << 32) - 1
_STATUS_CODES = {
    -1: "NULL_POINTER",
    -2: "INVALID_SIZE",
    -3: "INVALID_VALUE",
    -4: "RESOURCE_LIMIT_EXCEEDED",
}


@dataclass(frozen=True, slots=True)
class TrustedPolicyRule:
    """Normalized rule contract consumed by both policy providers."""

    effect: int
    risk_mask: int
    capability_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TrustedPolicyDecision:
    """Provider result; ``rule_index=None`` means the default effect matched."""

    effect: int
    rule_index: int | None


def _validate_identifier(value: str) -> bytes:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise NativeProviderError("INVALID_VALUE", "policy capability identifier is invalid")
    return value.encode("ascii")


def _validate_rule(rule: TrustedPolicyRule) -> tuple[bytes, ...]:
    if not isinstance(rule, TrustedPolicyRule):
        raise NativeProviderError("INVALID_VALUE", "policy rule contract is invalid")
    if rule.effect not in _VALID_EFFECTS or not 0 <= rule.risk_mask <= 0b0011_1111:
        raise NativeProviderError("INVALID_VALUE", "policy rule enum is invalid")
    if len(rule.capability_ids) > (1 << 16) - 1:
        raise NativeProviderError("RESOURCE_LIMIT_EXCEEDED", "policy rule is too large")
    if len(set(rule.capability_ids)) != len(rule.capability_ids):
        raise NativeProviderError("INVALID_VALUE", "policy capability ids must be unique")
    return tuple(_validate_identifier(value) for value in rule.capability_ids)


@lru_cache(maxsize=32)
def _encode_rules(rules: tuple[TrustedPolicyRule, ...]) -> bytes:
    if not 0 < len(rules) <= _MAX_RULES:
        code = "INVALID_SIZE" if not rules else "RESOURCE_LIMIT_EXCEEDED"
        raise NativeProviderError(code, "policy rule count is invalid")
    output = bytearray(b"JPR1")
    output.extend(struct.pack("<I", len(rules)))
    for rule in rules:
        capabilities = _validate_rule(rule)
        output.extend(struct.pack("<BBH", rule.effect, rule.risk_mask, len(capabilities)))
        for capability in capabilities:
            output.extend(struct.pack("<H", len(capability)))
            output.extend(capability)
        if len(output) > _MAX_POLICY_BYTES:
            raise NativeProviderError("RESOURCE_LIMIT_EXCEEDED", "policy table is too large")
    return bytes(output)


class TrustedPolicyGate:
    """Select one immutable P15 rule through a bounded provider contract."""

    def __init__(self, selection: str = "auto") -> None:
        requested = str(selection).strip().casefold()
        if requested not in _SELECTIONS:
            raise NativeProviderError(
                "INVALID_PROVIDER",
                f"policy provider must be one of: {', '.join(sorted(_SELECTIONS))}",
            )
        self.requested = requested
        self._loaded = None
        self._provider_id = "python-policy-reference-v1"
        if requested != "python-reference":
            self._loaded = load_first_party_library(
                "jaya_trusted", specific_env="JAYA_TRUSTED_LIBRARY"
            )
        if self._loaded is not None:
            try:
                self._bind_native()
            except (AttributeError, NativeProviderError):
                self._loaded = None
                self._provider_id = "python-policy-reference-v1"
                if requested == "trusted-rust":
                    raise NativeProviderError(
                        "PROVIDER_UNAVAILABLE",
                        "the Rust provider does not expose policy evaluation",
                    ) from None
        elif requested == "trusted-rust":
            raise NativeProviderError(
                "PROVIDER_UNAVAILABLE", "the required Rust policy provider could not be loaded"
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
            raise NativeProviderError("ABI_MISMATCH", "the Rust policy ABI is unsupported")
        library.jaya_trusted_capabilities.argtypes = []
        library.jaya_trusted_capabilities.restype = ctypes.c_uint64
        if int(library.jaya_trusted_capabilities()) & _CAPABILITY_POLICY_EVALUATION == 0:
            raise NativeProviderError(
                "CAPABILITY_UNAVAILABLE", "the Rust policy capability is unavailable"
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
        library.jaya_trusted_evaluate_policy.argtypes = [
            pointer,
            ctypes.c_size_t,
            pointer,
            ctypes.c_size_t,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        library.jaya_trusted_evaluate_policy.restype = ctypes.c_int32

    def profile(self) -> dict[str, Any]:
        return {
            "contract_version": _ABI_VERSION,
            "requested_provider": self.requested,
            "selected_provider": self.provider_id,
            "native_available": self.native_available,
            "library_path": str(self._loaded.path) if self._loaded is not None else None,
        }

    def evaluate(
        self,
        *,
        capability_id: str,
        risk_code: int,
        rules: tuple[TrustedPolicyRule, ...],
        default_effect: int,
    ) -> TrustedPolicyDecision:
        capability = _validate_identifier(capability_id)
        if not 0 <= risk_code < 6 or default_effect not in _VALID_EFFECTS:
            raise NativeProviderError("INVALID_VALUE", "policy request enum is invalid")
        encoded = _encode_rules(rules)
        if self._loaded is None:
            requested_risk = 1 << risk_code
            for index, rule in enumerate(rules):
                capability_matches = not rule.capability_ids or capability_id in rule.capability_ids
                risk_matches = rule.risk_mask == 0 or rule.risk_mask & requested_risk != 0
                if capability_matches and risk_matches:
                    return TrustedPolicyDecision(rule.effect, index)
            return TrustedPolicyDecision(default_effect, None)

        policy_buffer = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
        capability_buffer = (ctypes.c_uint8 * len(capability)).from_buffer_copy(capability)
        output_effect = ctypes.c_uint8()
        output_rule_index = ctypes.c_uint32()
        status = self._loaded.library.jaya_trusted_evaluate_policy(
            policy_buffer,
            len(encoded),
            capability_buffer,
            len(capability),
            risk_code,
            default_effect,
            ctypes.byref(output_effect),
            ctypes.byref(output_rule_index),
        )
        if int(status) != 0:
            code = _STATUS_CODES.get(int(status), "PROVIDER_FAILURE")
            raise NativeProviderError(
                code, f"trusted policy evaluation failed with status {status}"
            )
        rule_index = int(output_rule_index.value)
        if rule_index == _NO_RULE:
            return TrustedPolicyDecision(int(output_effect.value), None)
        if rule_index >= len(rules):
            raise NativeProviderError("ABI_INVALID", "policy provider returned an invalid rule")
        return TrustedPolicyDecision(int(output_effect.value), rule_index)


@lru_cache(maxsize=8)
def _cached_policy_gate(selection: str, library_dir: str, library_file: str) -> TrustedPolicyGate:
    del library_dir, library_file
    return TrustedPolicyGate(selection)


def get_trusted_policy_gate(selection: str | None = None) -> TrustedPolicyGate:
    requested = (
        selection or os.getenv("JAYA_POLICY_PROVIDER") or os.getenv("JAYA_TRUSTED_PROVIDER", "auto")
    )
    return _cached_policy_gate(
        requested,
        os.getenv("JAYA_NATIVE_LIBRARY_DIR", ""),
        os.getenv("JAYA_TRUSTED_LIBRARY", ""),
    )


__all__ = [
    "TrustedPolicyDecision",
    "TrustedPolicyGate",
    "TrustedPolicyRule",
    "get_trusted_policy_gate",
]
