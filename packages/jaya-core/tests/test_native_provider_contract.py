"""Integration contract for the optional first-party C++ and Rust providers."""

from __future__ import annotations

import os
from dataclasses import replace

import numpy as np
import pytest

from jaya_core.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from jaya_core.brain_v2.protection.zero_trust import (
    TrustEffect,
    ZeroTrustAuthority,
    create_trust_envelope,
)
from jaya_core.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyBundle,
    PolicyEffect,
    PolicyRequest,
    PolicyRisk,
    PolicyRule,
)
from jaya_core.pillars.binary_cortex import BinaryCortexService
from jaya_core.providers import (
    ComputeProvider,
    CryptographicEnvelopeContract,
    NativeProviderError,
    PrivacyUseContract,
    TrustedArtifactGate,
    TrustedCryptographicSkinGate,
    TrustedPolicyGate,
    TrustedPolicyRule,
    TrustedPrivacyGate,
    TrustedZeroTrustGate,
    VerifiedConsentScope,
    ZeroTrustAuthorizationContract,
)
from jaya_core.providers import compute as compute_module
from jaya_core.providers import cryptographic_skin as cryptographic_skin_module
from jaya_core.providers import policy as policy_module
from jaya_core.providers import privacy as privacy_module
from jaya_core.providers import trusted as trusted_module
from jaya_core.providers import zero_trust as zero_trust_module
from jaya_core.security.cryptographic_skin import CryptographicSkin
from jaya_core.security.sovereign_privacy import (
    DataClassification,
    DataDestination,
    DataPurpose,
    PrivacyEffect,
    PrivacyUseRequest,
    SovereignPrivacy,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("JAYA_NATIVE_TEST_REQUIRED") != "1",
        reason="native provider build is exercised in the native-cpu CI lane",
    ),
]


def test_cpp_binary_contract_matches_scalar_reference_with_tail_bits() -> None:
    provider = ComputeProvider("native-cpu")
    left = np.where(np.arange(1_031) % 3, 1, -1).astype(np.int8)
    right = np.where(np.arange(1_031) % 7, 1, -1).astype(np.int8)

    matches, result = provider.binary_dot(left, right)
    left_packed = provider.binary_pack(left)
    right_packed = provider.binary_pack(right)
    packed_matches, packed_result = provider.binary_dot_packed(left_packed, right_packed, left.size)

    expected = int(np.dot(left.astype(np.int64), right.astype(np.int64)))
    assert provider.provider_id == "jaya-cpp20-cpu-v1"
    assert matches == packed_matches
    assert result == packed_result == expected
    assert matches == int(np.count_nonzero(left == right))
    assert len(left_packed) == 129


def test_cpp_ternary_contract_matches_numpy_reference() -> None:
    provider = ComputeProvider("native-cpu")
    rng = np.random.default_rng(20260831)
    inputs = rng.normal(size=(7, 31)).astype(np.float32)
    weights = rng.integers(-1, 2, size=(31, 19), dtype=np.int8)

    actual = provider.ternary_linear(inputs, weights)
    expected = inputs @ weights.astype(np.float32)

    np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-5)


def test_cpp_provider_rejects_invalid_binary_and_ternary_values() -> None:
    provider = ComputeProvider("native-cpu")
    with pytest.raises(NativeProviderError) as binary_error:
        provider.binary_dot(np.array([1, 0], dtype=np.int8), np.array([1, 1], dtype=np.int8))
    assert binary_error.value.code == "INVALID_VALUE"

    with pytest.raises(NativeProviderError) as ternary_error:
        provider.ternary_linear(
            np.ones((1, 2), dtype=np.float32), np.array([[1], [2]], dtype=np.int8)
        )
    assert ternary_error.value.code == "INVALID_VALUE"


def test_rust_gate_enforces_identifier_layout_and_ternary_contracts() -> None:
    gate = TrustedArtifactGate("trusted-rust")
    gate.validate_identifier("artifact-01.alpha")
    gate.validate_binary_layout(
        (b"\x03",),
        input_features=2,
        max_features=64,
        max_outputs=8,
        max_total_bits=512,
    )
    gate.validate_ternary_values(np.array([-1, 0, 1], dtype=np.int8), max_length=8)

    with pytest.raises(NativeProviderError) as identifier_error:
        gate.validate_identifier("../artifact")
    assert identifier_error.value.code == "INVALID_VALUE"
    with pytest.raises(NativeProviderError) as padding_error:
        gate.validate_binary_layout(
            (b"\x83",),
            input_features=2,
            max_features=64,
            max_outputs=8,
            max_total_bits=512,
        )
    assert padding_error.value.code == "INVALID_VALUE"
    with pytest.raises(NativeProviderError) as ternary_error:
        gate.validate_ternary_values(np.array([-1, 2, 1], dtype=np.int8), max_length=8)
    assert ternary_error.value.code == "INVALID_VALUE"


def test_rust_policy_gate_drives_p15_end_to_end(tmp_path) -> None:
    gate = TrustedPolicyGate("trusted-rust")
    rules = (
        TrustedPolicyRule(effect=2, risk_mask=1 << 2),
        TrustedPolicyRule(
            effect=1,
            risk_mask=1 << 0,
            capability_ids=("core.logic.evaluate",),
        ),
    )
    assert (
        gate.evaluate(
            capability_id="core.logic.evaluate",
            risk_code=0,
            rules=rules,
            default_effect=3,
        ).rule_index
        == 1
    )
    assert (
        gate.evaluate(
            capability_id="device.switch",
            risk_code=1,
            rules=rules,
            default_effect=3,
        ).effect
        == 3
    )

    policy = PolicyBundle(
        policy_id="test.native-policy",
        version=1,
        brain_id="brain-native",
        rules=(
            PolicyRule(
                rule_id="allow.logic",
                effect=PolicyEffect.ALLOW,
                capability_ids=("core.logic.evaluate",),
                risk_classes=(PolicyRisk.READ_ONLY,),
                reason_code="NATIVE_RULE_MATCH",
            ),
        ),
        default_effect=PolicyEffect.DENY,
    )
    heart = EthicalHeart(tmp_path / "native-policy.db", policy, policy_gate=gate)
    try:
        decision = heart.evaluate(
            PolicyRequest(
                request_id="native-policy-request",
                actor_brain_id="brain-native",
                node_id="node-native",
                capability_id="core.logic.evaluate",
                risk_class=PolicyRisk.READ_ONLY,
                permissions=(),
                payload_sha256="0" * 64,
            )
        )
        assert decision.effect is PolicyEffect.ALLOW
        assert decision.reason_code == "NATIVE_RULE_MATCH"
        assert heart.status()["policy_evaluator"]["selected_provider"] == ("jaya-rust-trusted-v1")
    finally:
        heart.close()


def test_rust_privacy_gate_drives_p20_end_to_end(tmp_path) -> None:
    gate = TrustedPrivacyGate("trusted-rust")
    contract = PrivacyUseContract(
        actor_id="owner-native",
        owner_id="owner-native",
        subject_id="subject-native",
        provider_id="provider-native",
        classification_code=2,
        purpose_code=2,
        destination_code=1,
    )
    scope = VerifiedConsentScope(
        owner_id="owner-native",
        subject_id="subject-native",
        classification_mask=1 << 2,
        purpose_mask=1 << 2,
        provider_ids=("provider-native",),
    )
    assert gate.evaluate(contract).reason_code == "SIGNED_CONSENT_REQUIRED"
    assert gate.evaluate(contract, scope).reason_code == "SIGNED_CONSENT_ALLOWED"

    privacy = SovereignPrivacy(
        tmp_path / "native-privacy.db",
        "native-privacy-secret-" + ("x" * 32),
        privacy_gate=gate,
    )
    try:
        decision = privacy.evaluate(
            PrivacyUseRequest(
                request_id="native-privacy-request",
                actor_id="owner-native",
                owner_id="owner-native",
                subject_id="subject-native",
                data_id="native-data",
                classification=DataClassification.CONFIDENTIAL,
                purpose=DataPurpose.CORE_REASONING,
                destination=DataDestination.LOCAL,
                provider_id="local-provider",
                payload_sha256="0" * 64,
            )
        )
        assert decision.effect is PrivacyEffect.ALLOW
        assert decision.reason_code == "OWNER_LOCAL_PURPOSE_ALLOWED"
        assert privacy.status()["privacy_scope_provider"]["selected_provider"] == (
            "jaya-rust-trusted-v1"
        )
    finally:
        privacy.close()


def test_rust_zero_trust_gate_drives_p18_end_to_end(tmp_path) -> None:
    gate = TrustedZeroTrustGate("trusted-rust")
    contract = ZeroTrustAuthorizationContract(
        envelope_id="trust-native-envelope",
        principal_id="principal-native",
        envelope_node_id="node-native",
        capability_id="core.logic.evaluate",
        nonce="nonce-native",
        principal_status=1,
        principal_state=0,
        attestation_state=0,
        persisted_node_id="node-native",
        capability_ids=("core.logic.evaluate",),
        claimed_payload_sha256="a" * 64,
        actual_payload_sha256="a" * 64,
    )
    assert gate.evaluate(contract).reason_code == "ATTESTATION_REQUIRED"
    assert (
        gate.evaluate(replace(contract, attestation_state=1)).reason_code
        == "VERIFIED_LEAST_PRIVILEGE"
    )

    authority = ZeroTrustAuthority(
        tmp_path / "native-zero-trust.db",
        attestation_verifier=lambda _: True,
        authorization_gate=gate,
    )
    authority.ensure_principal("principal-native", "node-native", ("core.logic.evaluate",))
    payload = {"query": "native-trust"}
    envelope = create_trust_envelope(
        principal_id="principal-native",
        node_id="node-native",
        capability_id="core.logic.evaluate",
        payload=payload,
        policy_receipt_sha256="a" * 64,
        privacy_receipt_sha256="b" * 64,
        signer=lambda purpose, digest: {"purpose": purpose, "payload_sha256": digest},
    )
    try:
        decision = authority.authorize(envelope, payload)
        assert decision.effect is TrustEffect.ALLOW
        assert authority.status()["authorization_provider"]["selected_provider"] == (
            "jaya-rust-trusted-v1"
        )
    finally:
        authority.close()


def test_rust_cryptographic_skin_gate_drives_p13_end_to_end(tmp_path) -> None:
    gate = TrustedCryptographicSkinGate("trusted-rust")
    pending = CryptographicEnvelopeContract(
        envelope_id="env-native-envelope",
        key_id="key-native-envelope",
        purpose="core.artifact",
        subject="artifact:native-envelope",
        content_type="application/jaya-artifact",
        schema_version=1,
        algorithm_suite_code=1,
        operation_code=2,
        key_state=0,
        attestation_state=0,
        temporal_state=0,
        nonce_size_bytes=0,
        ciphertext_size_bytes=0,
        max_payload_bytes=4096,
    )
    assert gate.evaluate(pending).reason_code == "ATTESTATION_REQUIRED"
    complete = replace(
        pending,
        key_state=1,
        attestation_state=1,
        temporal_state=1,
        nonce_size_bytes=12,
        ciphertext_size_bytes=128,
    )
    assert gate.evaluate(complete).reason_code == "VERIFIED_CRYPTOGRAPHIC_ENVELOPE"

    identity = DNAAnchor(
        tmp_path / "identity",
        EncryptedFileKeyStore(
            tmp_path / "identity" / "keystore",
            "native-p13-identity-secret-" + ("i" * 40),
        ),
    )
    identity.enroll()
    skin = CryptographicSkin(
        tmp_path / "native-p13.db",
        "native-p13-skin-secret-" + ("s" * 40),
        attestation_signer=lambda purpose, digest: identity.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=identity.verify_attestation,
        envelope_gate=gate,
    )
    try:
        envelope = skin.seal(
            b"native-cryptographic-envelope",
            purpose="core.artifact",
            subject="artifact:native-p13",
        )
        assert skin.open(envelope) == b"native-cryptographic-envelope"
        assert skin.status()["envelope_gate"]["selected_provider"] == ("jaya-rust-trusted-v1")
    finally:
        skin.close()
        identity.close()


def test_p29_service_reports_and_executes_both_native_boundaries() -> None:
    service = BinaryCortexService(
        compute_provider=ComputeProvider("native-cpu"),
        trusted_gate=TrustedArtifactGate("trusted-rust"),
    )
    result = service.dot([1, -1, 1, 1, -1], [1, 1, 1, -1, -1])
    profile = service.kernel_profile()

    assert result.data["dot_product"] == 1
    assert result.data["kernel"] == "CPP20_XNOR_POPCOUNT"
    assert result.data["compute_provider"] == "jaya-cpp20-cpu-v1"
    assert profile["trusted_artifact_gate"]["selected_provider"] == "jaya-rust-trusted-v1"


def test_strict_profiles_fail_closed_when_libraries_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(compute_module, "load_first_party_library", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cryptographic_skin_module, "load_first_party_library", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(policy_module, "load_first_party_library", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(privacy_module, "load_first_party_library", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trusted_module, "load_first_party_library", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        zero_trust_module, "load_first_party_library", lambda *_args, **_kwargs: None
    )

    with pytest.raises(NativeProviderError) as compute_error:
        ComputeProvider("native-cpu")
    with pytest.raises(NativeProviderError) as trusted_error:
        TrustedArtifactGate("trusted-rust")
    with pytest.raises(NativeProviderError) as policy_error:
        TrustedPolicyGate("trusted-rust")
    with pytest.raises(NativeProviderError) as privacy_error:
        TrustedPrivacyGate("trusted-rust")
    with pytest.raises(NativeProviderError) as zero_trust_error:
        TrustedZeroTrustGate("trusted-rust")
    with pytest.raises(NativeProviderError) as cryptographic_skin_error:
        TrustedCryptographicSkinGate("trusted-rust")

    assert compute_error.value.code == "PROVIDER_UNAVAILABLE"
    assert trusted_error.value.code == "PROVIDER_UNAVAILABLE"
    assert policy_error.value.code == "PROVIDER_UNAVAILABLE"
    assert privacy_error.value.code == "PROVIDER_UNAVAILABLE"
    assert zero_trust_error.value.code == "PROVIDER_UNAVAILABLE"
    assert cryptographic_skin_error.value.code == "PROVIDER_UNAVAILABLE"


def test_auto_profile_uses_labeled_reference_when_native_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(compute_module, "load_first_party_library", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cryptographic_skin_module, "load_first_party_library", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(policy_module, "load_first_party_library", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(privacy_module, "load_first_party_library", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trusted_module, "load_first_party_library", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        zero_trust_module, "load_first_party_library", lambda *_args, **_kwargs: None
    )
    compute = ComputeProvider("auto")
    policy = TrustedPolicyGate("auto")
    privacy = TrustedPrivacyGate("auto")
    trusted = TrustedArtifactGate("auto")
    zero_trust = TrustedZeroTrustGate("auto")
    cryptographic_skin = TrustedCryptographicSkinGate("auto")

    assert compute.profile()["selected_provider"] == "numpy-reference-v1"
    assert trusted.profile()["selected_provider"] == "python-artifact-validation-v1"
    assert policy.profile()["selected_provider"] == "python-policy-reference-v1"
    assert privacy.profile()["selected_provider"] == "python-privacy-reference-v1"
    assert zero_trust.profile()["selected_provider"] == "python-zero-trust-reference-v1"
    assert cryptographic_skin.profile()["selected_provider"] == (
        "python-cryptographic-skin-reference-v1"
    )
    assert compute.binary_dot([1, -1], [1, 1]) == (1, 0)
    trusted.validate_identifier("fallback-artifact")
