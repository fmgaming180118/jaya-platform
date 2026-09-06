"""Contract and failure tests for the P13 cryptographic-envelope gate."""

from __future__ import annotations

from dataclasses import replace

import pytest

from jaya_core.providers import (
    CryptographicEnvelopeContract,
    NativeProviderError,
    TrustedCryptographicSkinGate,
)
from jaya_core.providers import cryptographic_skin as provider_module


def _contract(**changes: int | str) -> CryptographicEnvelopeContract:
    contract = CryptographicEnvelopeContract(
        envelope_id="env-provider-1",
        key_id="key-provider-1",
        purpose="core.artifact",
        subject="artifact:provider-1",
        content_type="application/jaya-artifact",
        schema_version=1,
        algorithm_suite_code=1,
        operation_code=2,
        key_state=1,
        attestation_state=1,
        temporal_state=1,
        nonce_size_bytes=12,
        ciphertext_size_bytes=128,
        max_payload_bytes=4096,
    )
    return replace(contract, **changes)


def test_reference_gate_requires_attestation_then_bytes_before_allowing() -> None:
    gate = TrustedCryptographicSkinGate("python-reference")
    pending = _contract(
        key_state=0,
        attestation_state=0,
        temporal_state=0,
        nonce_size_bytes=0,
        ciphertext_size_bytes=0,
    )
    metadata = _contract(nonce_size_bytes=0, ciphertext_size_bytes=0)

    assert gate.evaluate(pending).reason_code == "ATTESTATION_REQUIRED"
    assert gate.evaluate(metadata).reason_code == "ENVELOPE_BYTES_REQUIRED"
    assert gate.evaluate(_contract()).reason_code == "VERIFIED_CRYPTOGRAPHIC_ENVELOPE"
    assert gate.profile()["receives_secret_material"] is False
    assert gate.profile()["receives_ciphertext"] is False


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"attestation_state": 2}, "CRYPTO_SKIN_SIGNATURE_INVALID"),
        ({"key_state": 3}, "CRYPTO_SKIN_KEY_REVOKED"),
        ({"temporal_state": 2}, "CRYPTO_SKIN_CLOCK_SKEW"),
        ({"temporal_state": 3}, "CRYPTO_SKIN_ENVELOPE_EXPIRED"),
        ({"nonce_size_bytes": 8}, "CRYPTO_SKIN_NONCE_INVALID"),
        ({"ciphertext_size_bytes": 8}, "CRYPTO_SKIN_CIPHERTEXT_INVALID"),
        (
            {"ciphertext_size_bytes": 4097 + 16},
            "CRYPTO_SKIN_PAYLOAD_TOO_LARGE",
        ),
        ({"schema_version": 2}, "CRYPTO_SKIN_CONTRACT_INVALID"),
    ),
)
def test_reference_gate_denies_normalized_failure_paths(
    changes: dict[str, int], reason: str
) -> None:
    decision = TrustedCryptographicSkinGate("python-reference").evaluate(_contract(**changes))
    assert decision.effect == 2
    assert decision.reason_code == reason


def test_contract_encoder_rejects_untrusted_shapes() -> None:
    gate = TrustedCryptographicSkinGate("python-reference")
    with pytest.raises(NativeProviderError) as identifier:
        gate.evaluate(_contract(envelope_id="../escape"))
    with pytest.raises(NativeProviderError) as pending:
        gate.evaluate(_contract(attestation_state=0))

    assert identifier.value.code == "INVALID_VALUE"
    assert pending.value.code == "INVALID_VALUE"


def test_strict_and_auto_provider_selection_fail_or_fallback_honestly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_module, "load_first_party_library", lambda *_a, **_k: None)
    with pytest.raises(NativeProviderError) as strict:
        TrustedCryptographicSkinGate("trusted-rust")
    fallback = TrustedCryptographicSkinGate("auto")

    assert strict.value.code == "PROVIDER_UNAVAILABLE"
    assert fallback.provider_id == "python-cryptographic-skin-reference-v1"
    assert fallback.native_available is False
