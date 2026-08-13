"""P16 Quantum Resistant: honest crypto agility with no fake PQ fallback."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

_SAFE_PROVIDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (TypeError, ValueError) as exc:
        raise QuantumSecurityError(
            QuantumFailureCode.INVALID_ENVELOPE,
            "quantum signature envelope contains invalid encoded data",
        ) from exc


class QuantumSuite(str, Enum):
    CLASSICAL_ED25519 = "CLASSICAL_ED25519"
    HYBRID_ED25519_ML_DSA_65 = "HYBRID_ED25519_ML_DSA_65"
    ML_DSA_65 = "ML_DSA_65"


_SUITE_RANK = {
    QuantumSuite.CLASSICAL_ED25519: 0,
    QuantumSuite.HYBRID_ED25519_ML_DSA_65: 1,
    QuantumSuite.ML_DSA_65: 2,
}


class QuantumFailureCode(str, Enum):
    INVALID_INPUT = "QUANTUM_INVALID_INPUT"
    INVALID_ENVELOPE = "QUANTUM_INVALID_ENVELOPE"
    PROVIDER_UNAVAILABLE = "QUANTUM_PROVIDER_UNAVAILABLE"
    ALGORITHM_UNSUPPORTED = "QUANTUM_ALGORITHM_UNSUPPORTED"
    DOWNGRADE_REJECTED = "QUANTUM_DOWNGRADE_REJECTED"
    SIGNATURE_INVALID = "QUANTUM_SIGNATURE_INVALID"
    POLICY_EXPIRED = "QUANTUM_POLICY_EXPIRED"
    KEY_REVOKED = "QUANTUM_KEY_REVOKED"


class QuantumSecurityError(RuntimeError):
    def __init__(self, code: QuantumFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class QuantumPolicy:
    policy_version: int
    minimum_suite: QuantumSuite
    asset_lifetime_days: int
    threat_horizon_year: int
    allow_classical_until_year: int

    def validate(self, current_year: int) -> None:
        if (
            self.policy_version <= 0
            or not 1 <= self.asset_lifetime_days <= 36_500
            or not 2025 <= self.threat_horizon_year <= 2200
            or not 2025 <= self.allow_classical_until_year <= 2200
        ):
            raise QuantumSecurityError(
                QuantumFailureCode.INVALID_INPUT,
                "quantum algorithm policy is invalid",
            )
        if (
            self.minimum_suite is QuantumSuite.CLASSICAL_ED25519
            and current_year > self.allow_classical_until_year
        ):
            raise QuantumSecurityError(
                QuantumFailureCode.POLICY_EXPIRED,
                "classical-only policy has passed its declared horizon",
            )


class PostQuantumSignatureProvider(Protocol):
    provider_id: str
    algorithm: str

    def available(self) -> bool:
        ...

    def public_key(self) -> bytes:
        ...

    def sign(self, payload: bytes) -> bytes:
        ...

    def verify(self, payload: bytes, signature: bytes, public_key: bytes) -> bool:
        ...


class OQSMLDSA65Provider:
    """Optional liboqs-backed ML-DSA-65 production adapter."""

    provider_id = "liboqs-ml-dsa-65"
    algorithm = "ML-DSA-65"

    def __init__(
        self,
        *,
        secret_key: bytes | None = None,
        public_key: bytes | None = None,
    ) -> None:
        try:
            self._oqs = importlib.import_module("oqs")
            mechanisms = set(self._oqs.get_enabled_sig_mechanisms())
            self._mechanism = next(
                (name for name in ("ML-DSA-65", "Dilithium3") if name in mechanisms),
                None,
            )
        except (ImportError, AttributeError, RuntimeError):
            self._oqs = None
            self._mechanism = None
        self._signer = None
        self._public_key = bytes(public_key) if public_key is not None else None
        if self.available():
            self._signer = self._oqs.Signature(self._mechanism, secret_key)
            if secret_key is None:
                self._public_key = bytes(self._signer.generate_keypair())
            elif self._public_key is None:
                raise QuantumSecurityError(
                    QuantumFailureCode.INVALID_INPUT,
                    "restored ML-DSA key requires its public key",
                )

    def available(self) -> bool:
        return self._oqs is not None and self._mechanism is not None

    def public_key(self) -> bytes:
        self._require_available()
        return bytes(self._public_key or b"")

    def sign(self, payload: bytes) -> bytes:
        self._require_available()
        return bytes(self._signer.sign(payload))

    def export_secret_key(self) -> bytes:
        self._require_available()
        return bytes(self._signer.export_secret_key())

    def versions(self) -> dict[str, str]:
        self._require_available()
        return {
            "liboqs_python": str(self._oqs.oqs_python_version()),
            "liboqs": str(self._oqs.oqs_version()),
        }

    def close(self) -> None:
        signer = self._signer
        if signer is not None:
            signer.free()
            self._signer = None

    def verify(self, payload: bytes, signature: bytes, public_key: bytes) -> bool:
        self._require_available()
        try:
            with self._oqs.Signature(self._mechanism) as verifier:
                return bool(verifier.verify(payload, signature, public_key))
        except Exception:
            return False

    def _require_available(self) -> None:
        if not self.available():
            raise QuantumSecurityError(
                QuantumFailureCode.PROVIDER_UNAVAILABLE,
                "liboqs ML-DSA-65 provider is unavailable",
            )


@dataclass(frozen=True, slots=True)
class AgileSignatureEnvelope:
    payload_sha256: str
    suite: QuantumSuite
    policy_version: int
    provider_id: str
    classical_public_key: str | None
    classical_signature: str | None
    pq_public_key: str | None
    pq_signature: str | None
    schema_version: int = 1

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["suite"] = self.suite.value
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> AgileSignatureEnvelope:
        expected = {
            "classical_public_key",
            "classical_signature",
            "payload_sha256",
            "policy_version",
            "pq_public_key",
            "pq_signature",
            "provider_id",
            "schema_version",
            "suite",
        }
        if set(value) != expected:
            raise QuantumSecurityError(
                QuantumFailureCode.INVALID_ENVELOPE,
                "quantum signature envelope schema is invalid",
            )
        try:
            return cls(
                payload_sha256=str(value["payload_sha256"]),
                suite=QuantumSuite(str(value["suite"])),
                policy_version=int(value["policy_version"]),
                provider_id=str(value["provider_id"]),
                classical_public_key=(
                    None
                    if value["classical_public_key"] is None
                    else str(value["classical_public_key"])
                ),
                classical_signature=(
                    None
                    if value["classical_signature"] is None
                    else str(value["classical_signature"])
                ),
                pq_public_key=(
                    None
                    if value["pq_public_key"] is None
                    else str(value["pq_public_key"])
                ),
                pq_signature=(
                    None
                    if value["pq_signature"] is None
                    else str(value["pq_signature"])
                ),
                schema_version=int(value["schema_version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise QuantumSecurityError(
                QuantumFailureCode.INVALID_ENVELOPE,
                "quantum signature envelope schema is invalid",
            ) from exc


class QuantumSignatureAuthority:
    """Apply a versioned suite policy and reject cryptographic downgrade."""

    def __init__(
        self,
        policy: QuantumPolicy,
        *,
        pq_provider: PostQuantumSignatureProvider | None = None,
        classical_private_key: Ed25519PrivateKey | None = None,
        current_year: int,
    ) -> None:
        policy.validate(current_year)
        self.policy = policy
        self.pq_provider = pq_provider
        self._classical = classical_private_key or Ed25519PrivateKey.generate()

    def sign(
        self,
        payload: bytes,
        suite: QuantumSuite,
    ) -> AgileSignatureEnvelope:
        self._enforce_suite(suite)
        digest = hashlib.sha256(payload).hexdigest()
        classical_public: str | None = None
        classical_signature: str | None = None
        pq_public: str | None = None
        pq_signature: str | None = None
        if suite in {
            QuantumSuite.CLASSICAL_ED25519,
            QuantumSuite.HYBRID_ED25519_ML_DSA_65,
        }:
            classical_public = _encode(
                self._classical.public_key().public_bytes(
                    serialization.Encoding.Raw,
                    serialization.PublicFormat.Raw,
                )
            )
            classical_signature = _encode(self._classical.sign(payload))
        provider_id = "cryptography-ed25519-classical"
        if suite in {
            QuantumSuite.HYBRID_ED25519_ML_DSA_65,
            QuantumSuite.ML_DSA_65,
        }:
            provider = self._require_pq_provider()
            provider_id = provider.provider_id
            pq_public = _encode(provider.public_key())
            pq_signature = _encode(provider.sign(payload))
        return AgileSignatureEnvelope(
            payload_sha256=digest,
            suite=suite,
            policy_version=self.policy.policy_version,
            provider_id=provider_id,
            classical_public_key=classical_public,
            classical_signature=classical_signature,
            pq_public_key=pq_public,
            pq_signature=pq_signature,
        )

    def verify(
        self,
        payload: bytes,
        value: AgileSignatureEnvelope | Mapping[str, object],
    ) -> bool:
        envelope = (
            value
            if isinstance(value, AgileSignatureEnvelope)
            else AgileSignatureEnvelope.from_dict(value)
        )
        self._enforce_suite(envelope.suite)
        if (
            envelope.schema_version != 1
            or envelope.policy_version != self.policy.policy_version
            or not _SAFE_PROVIDER.fullmatch(envelope.provider_id)
            or envelope.payload_sha256 != hashlib.sha256(payload).hexdigest()
        ):
            raise QuantumSecurityError(
                QuantumFailureCode.INVALID_ENVELOPE,
                "quantum signature envelope metadata is invalid",
            )
        classical_valid = envelope.suite is QuantumSuite.ML_DSA_65
        if envelope.suite in {
            QuantumSuite.CLASSICAL_ED25519,
            QuantumSuite.HYBRID_ED25519_ML_DSA_65,
        }:
            try:
                if (
                    not envelope.classical_public_key
                    or not envelope.classical_signature
                ):
                    raise ValueError
                Ed25519PublicKey.from_public_bytes(
                    _decode(envelope.classical_public_key)
                ).verify(_decode(envelope.classical_signature), payload)
                classical_valid = True
            except (InvalidSignature, ValueError):
                classical_valid = False
        pq_valid = envelope.suite is QuantumSuite.CLASSICAL_ED25519
        if envelope.suite in {
            QuantumSuite.HYBRID_ED25519_ML_DSA_65,
            QuantumSuite.ML_DSA_65,
        }:
            provider = self._require_pq_provider()
            if envelope.provider_id != provider.provider_id:
                raise QuantumSecurityError(
                    QuantumFailureCode.INVALID_ENVELOPE,
                    "quantum signature provider does not match the active provider",
                )
            pq_valid = bool(
                envelope.pq_public_key
                and envelope.pq_signature
                and provider.verify(
                    payload,
                    _decode(envelope.pq_signature),
                    _decode(envelope.pq_public_key),
                )
            )
        return classical_valid and pq_valid

    def status(self) -> dict[str, object]:
        provider = self.pq_provider
        return {
            "ready": (
                self.policy.minimum_suite is QuantumSuite.CLASSICAL_ED25519
                or bool(provider and provider.available())
            ),
            "policy_version": self.policy.policy_version,
            "minimum_suite": self.policy.minimum_suite.value,
            "asset_lifetime_days": self.policy.asset_lifetime_days,
            "threat_horizon_year": self.policy.threat_horizon_year,
            "pq_provider_available": bool(provider and provider.available()),
            "pq_provider_id": provider.provider_id if provider else None,
            "quantum_resistant": bool(provider and provider.available()),
        }

    def _enforce_suite(self, suite: QuantumSuite) -> None:
        if _SUITE_RANK[suite] < _SUITE_RANK[self.policy.minimum_suite]:
            raise QuantumSecurityError(
                QuantumFailureCode.DOWNGRADE_REJECTED,
                "signature suite is below the configured quantum policy",
            )

    def _require_pq_provider(self) -> PostQuantumSignatureProvider:
        if self.pq_provider is None or not self.pq_provider.available():
            raise QuantumSecurityError(
                QuantumFailureCode.PROVIDER_UNAVAILABLE,
                "a maintained ML-DSA-65 provider is unavailable",
            )
        if self.pq_provider.algorithm not in {"ML-DSA-65", "Dilithium3"}:
            raise QuantumSecurityError(
                QuantumFailureCode.ALGORITHM_UNSUPPORTED,
                "post-quantum provider algorithm is unsupported",
            )
        return self.pq_provider


class PQCWrapper:
    """Legacy compatibility wrapper, explicitly classical and not PQ secure."""

    algorithm = "ED25519_CLASSICAL_NOT_PQ"
    quantum_resistant = False

    def __init__(self, secret_key: bytes = b"") -> None:
        del secret_key
        self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._sign_count = 0
        self._verify_count = 0

    def sign(self, data: bytes) -> bytes:
        self._sign_count += 1
        return self._private_key.sign(data)

    def verify(self, data: bytes, signature: bytes) -> bool:
        self._verify_count += 1
        try:
            self._public_key.verify(signature, data)
            return True
        except InvalidSignature:
            return False

    def status(self) -> dict[str, object]:
        return {
            "algorithm": self.algorithm,
            "quantum_resistant": False,
            "status": "CLASSICAL_ONLY",
            "signs": self._sign_count,
            "verifies": self._verify_count,
        }


__all__ = [
    "AgileSignatureEnvelope",
    "OQSMLDSA65Provider",
    "PQCWrapper",
    "PostQuantumSignatureProvider",
    "QuantumFailureCode",
    "QuantumPolicy",
    "QuantumSecurityError",
    "QuantumSignatureAuthority",
    "QuantumSuite",
]
