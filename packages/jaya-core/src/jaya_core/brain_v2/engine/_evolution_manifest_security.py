"""Canonicalization, trust, and signing primitives for evolution manifest v1."""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import math
import os
import re
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

SCHEMA_VERSION = "jaya-evolution-manifest-v1"
SIGNATURE_ALGORITHM = "HMAC-SHA256"
ABSENT_RESTORE_DIGEST = "absent"

DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SPDX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]{0,63}$")
_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class EvolutionContractError(ValueError):
    """Typed, secret-free manifest or trust-contract rejection."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_json(value: Any) -> bytes:
    """Encode JSON deterministically and reject non-finite values."""
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise EvolutionContractError(
            "NON_CANONICAL_JSON",
            "Manifest values must be finite JSON values",
        ) from exc
    return encoded.encode("utf-8")


def digest_bytes(value: bytes) -> str:
    """Return a tagged SHA-256 digest."""
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def digest_file(path: str | Path, *, chunk_bytes: int = 1024 * 1024) -> str:
    """Hash a regular file without mutating it."""
    candidate = Path(path)
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def validate_relative_install_path(value: str) -> str:
    """Validate one canonical POSIX-style path below an injected root."""
    if not isinstance(value, str):
        raise EvolutionContractError(
            "UNSAFE_INSTALL_PATH",
            "Install paths must be canonical relative paths",
        )
    raw = value
    if (
        not raw
        or raw != raw.strip()
        or len(raw) > 512
        or raw.startswith(("/", "\\"))
        or "\\" in raw
        or "%" in raw
        or _WINDOWS_DRIVE_PATTERN.match(raw)
        or any(ord(character) < 32 for character in raw)
    ):
        raise EvolutionContractError(
            "UNSAFE_INSTALL_PATH",
            "Install paths must be canonical relative paths",
        )
    decoded = raw
    for _ in range(4):
        next_value = urllib.parse.unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    if decoded != raw:
        raise EvolutionContractError(
            "UNSAFE_INSTALL_PATH",
            "Encoded install paths are not accepted",
        )

    path = PurePosixPath(raw)
    raw_parts = raw.split("/")
    if (
        path.is_absolute()
        or not raw_parts
        or any(part in {"", ".", ".."} for part in raw_parts)
    ):
        raise EvolutionContractError(
            "UNSAFE_INSTALL_PATH",
            "Install paths must remain below the injected data root",
        )
    for part in raw_parts:
        reserved_stem = part.split(".", maxsplit=1)[0].upper()
        if (
            part.endswith((" ", "."))
            or ":" in part
            or reserved_stem in _WINDOWS_RESERVED
        ):
            raise EvolutionContractError(
                "UNSAFE_INSTALL_PATH",
                "Install path contains an unsafe platform component",
            )
    return path.as_posix()


def identifier(value: Any, *, field: str) -> str:
    """Validate one manifest identifier."""
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        raise EvolutionContractError(
            "SCHEMA_INVALID",
            f"{field} must be a safe identifier",
        )
    return value


def bounded_string(value: Any, *, field: str, maximum: int = 2048) -> str:
    """Validate a bounded, printable, non-empty string."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise EvolutionContractError(
            "SCHEMA_INVALID",
            f"{field} must be a non-empty bounded string",
        )
    return value


def timestamp(value: Any, *, field: str) -> float:
    """Validate a positive finite timestamp."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise EvolutionContractError(
            "SCHEMA_INVALID",
            f"{field} must be a positive timestamp",
        )
    return float(value)


def tagged_digest(value: Any, *, field: str) -> str:
    """Validate a tagged SHA-256 digest."""
    if not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value):
        raise EvolutionContractError(
            "SCHEMA_INVALID",
            f"{field} must be a tagged SHA-256 digest",
        )
    return value


def require_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    """Require one JSON object."""
    if not isinstance(value, Mapping):
        raise EvolutionContractError(
            "SCHEMA_INVALID",
            f"{field} must be an object",
        )
    return value


def require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    field: str,
) -> None:
    """Reject missing and unknown schema fields."""
    if set(value) != expected:
        raise EvolutionContractError(
            "SCHEMA_INVALID",
            f"{field} contains missing or unsupported fields",
        )


def signature_payload(document: Mapping[str, Any]) -> bytes:
    """Canonicalize a document while excluding only its signature value."""
    unsigned = copy.deepcopy(dict(document))
    signature = require_mapping(unsigned.get("signature"), field="signature")
    signature_without_value = dict(signature)
    signature_without_value.pop("value", None)
    unsigned["signature"] = signature_without_value
    return canonical_json(unsigned)


def _normalize_key_map(
    keys: Mapping[str, bytes],
    *,
    field: str,
) -> MappingProxyType:
    normalized: dict[str, bytes] = {}
    for raw_key_id, raw_secret in keys.items():
        key_id = identifier(raw_key_id, field=f"{field}.key_id")
        if not isinstance(raw_secret, bytes) or len(raw_secret) < 32:
            raise EvolutionContractError(
                "TRUST_CONFIGURATION_INVALID",
                f"{field} secrets must contain at least 32 bytes",
            )
        normalized[key_id] = bytes(raw_secret)
    return MappingProxyType(normalized)


@dataclass(frozen=True, repr=False)
class EvolutionTrustStore:
    """Distinct trusted keys for package signatures and human approvals."""

    manifest_keys: Mapping[str, bytes]
    approval_keys: Mapping[str, bytes]
    environment: str = "production"
    test_mode: bool = False

    def __post_init__(self) -> None:
        environment = str(self.environment or "production").strip().casefold()
        manifest_keys = _normalize_key_map(
            self.manifest_keys,
            field="manifest_keys",
        )
        approval_keys = _normalize_key_map(
            self.approval_keys,
            field="approval_keys",
        )
        if environment in {"prod", "production"}:
            if self.test_mode:
                raise EvolutionContractError(
                    "TRUST_CONFIGURATION_INVALID",
                    "Test trust cannot be enabled in production",
                )
            if not manifest_keys or not approval_keys:
                raise EvolutionContractError(
                    "TRUST_KEYS_REQUIRED",
                    "Production requires manifest and approval trust keys",
                )
        if set(manifest_keys.values()) & set(approval_keys.values()):
            raise EvolutionContractError(
                "TRUST_CONFIGURATION_INVALID",
                "Manifest and approval trust keys must be distinct",
            )
        object.__setattr__(self, "manifest_keys", manifest_keys)
        object.__setattr__(self, "approval_keys", approval_keys)
        object.__setattr__(self, "environment", environment)

    @classmethod
    def for_test(
        cls,
        *,
        manifest_key_id: str,
        manifest_key: bytes,
        approval_key_id: str,
        approval_key: bytes,
    ) -> EvolutionTrustStore:
        """Create explicit test trust; there are no built-in or generated keys."""
        return cls(
            manifest_keys={manifest_key_id: manifest_key},
            approval_keys={approval_key_id: approval_key},
            environment="test",
            test_mode=True,
        )

    @classmethod
    def from_environment(
        cls,
        *,
        environment: str | None = None,
    ) -> EvolutionTrustStore:
        """Load base64-encoded key maps from explicit production variables."""

        def load_map(variable: str) -> dict[str, bytes]:
            raw = os.getenv(variable, "")
            if not raw:
                return {}
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict) or any(
                    not isinstance(value, str) for value in payload.values()
                ):
                    raise TypeError
                return {
                    str(key_id): base64.b64decode(value, validate=True)
                    for key_id, value in payload.items()
                }
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise EvolutionContractError(
                    "TRUST_CONFIGURATION_INVALID",
                    f"{variable} must be a JSON map of base64 keys",
                ) from exc

        return cls(
            manifest_keys=load_map("JAYA_EVOLUTION_MANIFEST_TRUST_KEYS_JSON"),
            approval_keys=load_map("JAYA_EVOLUTION_APPROVAL_TRUST_KEYS_JSON"),
            environment=environment
            or os.getenv("JAYA_ENVIRONMENT")
            or os.getenv("JAYA_ENV")
            or "production",
        )


class EvolutionManifestSigner:
    """Explicit signer used by trusted build and human-approval workflows."""

    def __init__(
        self,
        *,
        manifest_key_id: str,
        manifest_key: bytes,
        approval_key_id: str,
        approval_key: bytes,
    ) -> None:
        trust = EvolutionTrustStore.for_test(
            manifest_key_id=manifest_key_id,
            manifest_key=manifest_key,
            approval_key_id=approval_key_id,
            approval_key=approval_key,
        )
        self._manifest_key_id = manifest_key_id
        self._manifest_key = trust.manifest_keys[manifest_key_id]
        self._approval_key_id = approval_key_id
        self._approval_key = trust.approval_keys[approval_key_id]

    @staticmethod
    def _signed(
        document: Mapping[str, Any],
        *,
        key_id: str,
        key: bytes,
    ) -> dict[str, Any]:
        signed = copy.deepcopy(dict(document))
        signed["signature"] = {
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": key_id,
        }
        signature = hmac.new(
            key,
            signature_payload(signed),
            hashlib.sha256,
        ).hexdigest()
        signed["signature"]["value"] = signature
        return signed

    def sign_approval(self, approval: Mapping[str, Any]) -> dict[str, Any]:
        """Sign a human approval with the dedicated approval key."""
        return self._signed(
            approval,
            key_id=self._approval_key_id,
            key=self._approval_key,
        )

    def sign_manifest(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        """Sign the complete manifest, including its signed approval."""
        return self._signed(
            manifest,
            key_id=self._manifest_key_id,
            key=self._manifest_key,
        )
