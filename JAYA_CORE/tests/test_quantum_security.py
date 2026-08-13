"""Executable honesty and agility gates for P16 Quantum Resistant."""

from __future__ import annotations

import os

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from scripts.run_jaya_core_server import _build_runtime
from src.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from src.brain_v2.protection.pqc import (
    OQSMLDSA65Provider,
    PQCWrapper,
    QuantumFailureCode,
    QuantumPolicy,
    QuantumSecurityError,
    QuantumSignatureAuthority,
    QuantumSuite,
)
from src.core_config import CoreConfig
from src.security.capsule import CapsuleKind
from src.security.cryptographic_skin import CryptographicSkin
from src.security.quantum_lifecycle import PersistentQuantumAuthority


class _TestMLDSAProvider:
    provider_id = "test-only-ml-dsa-contract"
    algorithm = "ML-DSA-65"

    def __init__(self) -> None:
        self._private = Ed25519PrivateKey.generate()

    def available(self) -> bool:
        return True

    def public_key(self) -> bytes:
        return self._private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

    def sign(self, payload: bytes) -> bytes:
        return self._private.sign(b"TEST-CONTRACT-NOT-PQ:" + payload)

    def verify(self, payload: bytes, signature: bytes, public_key: bytes) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature, b"TEST-CONTRACT-NOT-PQ:" + payload
            )
            return True
        except (InvalidSignature, ValueError):
            return False


class _UnavailableMLDSAProvider(_TestMLDSAProvider):
    provider_id = "unavailable-production-provider"

    def available(self) -> bool:
        return False


def _policy(minimum: QuantumSuite) -> QuantumPolicy:
    return QuantumPolicy(
        policy_version=1,
        minimum_suite=minimum,
        asset_lifetime_days=3_650,
        threat_horizon_year=2035,
        allow_classical_until_year=2028,
    )


def test_p16_classical_compatibility_is_never_labeled_quantum_resistant() -> None:
    wrapper = PQCWrapper()
    payload = os.urandom(64)
    signature = wrapper.sign(payload)

    assert wrapper.verify(payload, signature) is True
    assert wrapper.verify(payload + b"tamper", signature) is False
    assert wrapper.algorithm == "ED25519_CLASSICAL_NOT_PQ"
    assert wrapper.quantum_resistant is False
    assert wrapper.status()["status"] == "CLASSICAL_ONLY"


def test_p16_policy_rejects_downgrade_and_expired_classical_horizon() -> None:
    authority = QuantumSignatureAuthority(
        _policy(QuantumSuite.HYBRID_ED25519_ML_DSA_65),
        pq_provider=_TestMLDSAProvider(),
        current_year=2026,
    )
    with pytest.raises(QuantumSecurityError) as downgrade:
        authority.sign(b"artifact", QuantumSuite.CLASSICAL_ED25519)
    assert downgrade.value.code is QuantumFailureCode.DOWNGRADE_REJECTED

    with pytest.raises(QuantumSecurityError) as expired:
        QuantumSignatureAuthority(
            _policy(QuantumSuite.CLASSICAL_ED25519),
            current_year=2029,
        )
    assert expired.value.code is QuantumFailureCode.POLICY_EXPIRED


def test_p16_missing_production_provider_is_blocked_external_not_fallback() -> None:
    provider = _UnavailableMLDSAProvider()
    authority = QuantumSignatureAuthority(
        _policy(QuantumSuite.HYBRID_ED25519_ML_DSA_65),
        pq_provider=provider,
        current_year=2026,
    )
    with pytest.raises(QuantumSecurityError) as unavailable:
        authority.sign(b"artifact", QuantumSuite.HYBRID_ED25519_ML_DSA_65)

    assert unavailable.value.code is QuantumFailureCode.PROVIDER_UNAVAILABLE
    assert authority.status()["pq_provider_available"] is False
    assert authority.status()["quantum_resistant"] is False


def test_p16_hybrid_contract_requires_both_signatures_and_payload_binding() -> None:
    authority = QuantumSignatureAuthority(
        _policy(QuantumSuite.HYBRID_ED25519_ML_DSA_65),
        pq_provider=_TestMLDSAProvider(),
        current_year=2026,
    )
    payload = b"hybrid-contract-artifact"
    envelope = authority.sign(payload, QuantumSuite.HYBRID_ED25519_ML_DSA_65)

    assert authority.verify(payload, envelope) is True
    with pytest.raises(QuantumSecurityError) as tampered:
        authority.verify(payload + b"tamper", envelope)
    missing_pq = {**envelope.to_dict(), "pq_signature": None}
    assert authority.verify(payload, missing_pq) is False
    assert envelope.suite is QuantumSuite.HYBRID_ED25519_ML_DSA_65
    assert tampered.value.code is QuantumFailureCode.INVALID_ENVELOPE


def test_p16_unknown_fields_policy_version_and_suite_are_rejected() -> None:
    authority = QuantumSignatureAuthority(
        _policy(QuantumSuite.CLASSICAL_ED25519),
        current_year=2026,
    )
    envelope = authority.sign(b"artifact", QuantumSuite.CLASSICAL_ED25519)
    with pytest.raises(QuantumSecurityError) as unknown:
        authority.verify(b"artifact", {**envelope.to_dict(), "unknown": True})
    with pytest.raises(QuantumSecurityError) as version:
        authority.verify(b"artifact", {**envelope.to_dict(), "policy_version": 999})
    with pytest.raises(QuantumSecurityError) as suite:
        authority.verify(b"artifact", {**envelope.to_dict(), "suite": "FAKE_PQ"})

    assert unknown.value.code is QuantumFailureCode.INVALID_ENVELOPE
    assert version.value.code is QuantumFailureCode.INVALID_ENVELOPE
    assert suite.value.code is QuantumFailureCode.INVALID_ENVELOPE


@pytest.mark.skipif(
    not OQSMLDSA65Provider().available(),
    reason="BLOCKED_EXTERNAL: maintained liboqs ML-DSA-65 provider unavailable",
)
def test_p16_real_ml_dsa_provider_sign_verify_and_measurement() -> None:
    provider = OQSMLDSA65Provider()
    authority = QuantumSignatureAuthority(
        _policy(QuantumSuite.ML_DSA_65),
        pq_provider=provider,
        current_year=2026,
    )
    payload = os.urandom(4_096)
    envelope = authority.sign(payload, QuantumSuite.ML_DSA_65)

    assert authority.verify(payload, envelope) is True
    assert authority.status()["quantum_resistant"] is True
    assert len(envelope.pq_signature or "") > 0
    assert provider.versions() == {
        "liboqs_python": "0.16.0",
        "liboqs": "0.16.0",
    }
    provider.close()


@pytest.mark.skipif(
    not OQSMLDSA65Provider().available(),
    reason="BLOCKED_EXTERNAL: maintained liboqs ML-DSA-65 provider unavailable",
)
def test_p16_persistent_rotation_restart_and_revocation(tmp_path) -> None:
    identity_root = tmp_path / "identity"
    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(
            identity_root / "keystore", "p16-identity-" + ("i" * 40)
        ),
    )
    anchor.enroll()
    database = tmp_path / "core.db"
    skin = CryptographicSkin(
        database,
        "p16-skin-" + ("s" * 40),
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    lifecycle = PersistentQuantumAuthority(
        database,
        skin,
        _policy(QuantumSuite.HYBRID_ED25519_ML_DSA_65),
        current_year=2026,
    )
    payload = b"persistent-p16-artifact"
    first_key = lifecycle.active_key_id
    old_envelope = lifecycle.sign(payload)
    second_key = lifecycle.rotate()
    assert second_key != first_key
    assert lifecycle.verify(payload, old_envelope) is True
    lifecycle.close()
    skin.close()
    anchor.close()

    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(
            identity_root / "keystore", "p16-identity-" + ("i" * 40)
        ),
    )
    skin = CryptographicSkin(
        database,
        "p16-skin-" + ("s" * 40),
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    lifecycle = PersistentQuantumAuthority(
        database,
        skin,
        _policy(QuantumSuite.HYBRID_ED25519_ML_DSA_65),
        current_year=2026,
    )
    assert lifecycle.active_key_id == second_key
    assert lifecycle.verify(payload, old_envelope) is True
    lifecycle.revoke(first_key)
    with pytest.raises(QuantumSecurityError) as revoked:
        lifecycle.verify(payload, old_envelope)
    assert revoked.value.code is QuantumFailureCode.KEY_REVOKED
    lifecycle.close()
    skin.close()
    anchor.close()


@pytest.mark.skipif(
    not OQSMLDSA65Provider().available(),
    reason="BLOCKED_EXTERNAL: maintained liboqs ML-DSA-65 provider unavailable",
)
def test_p16_canonical_launcher_and_runtime_capsule_wiring(tmp_path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    identity_root = data_root / "identity"
    identity_secret = "p16-launcher-identity-" + ("i" * 40)
    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", identity_secret),
    )
    anchor.enroll()
    anchor.close()
    config = CoreConfig.from_env(
        {
            "JAYA_CORE_DATA_DIR": str(data_root),
            "JAYA_IDENTITY_DIR": str(identity_root),
            "JAYA_NODE_ID": "p16-node",
            "JAYA_REQUIRE_IDENTITY": "true",
            "JAYA_IDENTITY_KEY_SECRET": identity_secret,
            "JAYA_REQUIRE_PRIVACY": "true",
            "JAYA_PRIVACY_KEY_SECRET": "p16-privacy-" + ("p" * 40),
            "JAYA_REQUIRE_ZERO_TRUST": "true",
            "JAYA_REQUIRE_CRYPTOGRAPHIC_SKIN": "true",
            "JAYA_CRYPTOGRAPHIC_SKIN_SECRET": "p16-skin-" + ("s" * 40),
            "JAYA_REQUIRE_QUANTUM_SECURITY": "true",
            "JAYA_QUANTUM_POLICY_VERSION": "7",
            "JAYA_QUANTUM_ASSET_LIFETIME_DAYS": "3650",
            "JAYA_QUANTUM_THREAT_HORIZON_YEAR": "2035",
            "JAYA_QUANTUM_CLASSICAL_CUTOFF_YEAR": "2028",
        },
        core_dir=tmp_path,
    )
    runtime = _build_runtime(config)
    try:
        payload = b"portable-quantum-brain"
        capsule = runtime.seal_capsule(
            payload, kind=CapsuleKind.BRAIN, subject="brain:primary"
        )
        assert runtime.open_capsule(
            capsule,
            expected_kind=CapsuleKind.BRAIN,
            expected_subject="brain:primary",
        ) == payload
        assert runtime.operational_snapshot()["quantum_security"]["ready"] is True
        assert runtime.is_ready() is True
    finally:
        runtime.close()
