"""Reference and failure contracts for the P20 privacy scope provider."""

from __future__ import annotations

import pytest

from jaya_core.providers import (
    NativeProviderError,
    PrivacyUseContract,
    TrustedPrivacyGate,
    VerifiedConsentScope,
)
from jaya_core.providers import privacy as privacy_module


def _external_request(**changes: object) -> PrivacyUseContract:
    values = {
        "actor_id": "owner-1",
        "owner_id": "owner-1",
        "subject_id": "subject-1",
        "provider_id": "provider-real",
        "classification_code": 2,
        "purpose_code": 2,
        "destination_code": 1,
    }
    values.update(changes)
    return PrivacyUseContract(**values)  # type: ignore[arg-type]


def test_reference_privacy_gate_covers_owner_public_and_consent_paths() -> None:
    gate = TrustedPrivacyGate("python-reference")
    local = gate.evaluate(_external_request(destination_code=0))
    public = gate.evaluate(_external_request(classification_code=0))
    missing = gate.evaluate(_external_request())
    scope = VerifiedConsentScope(
        owner_id="owner-1",
        subject_id="subject-1",
        classification_mask=1 << 2,
        purpose_mask=1 << 2,
        provider_ids=("provider-real",),
    )
    allowed = gate.evaluate(_external_request(), scope)
    mismatched = gate.evaluate(
        _external_request(provider_id="provider-other"),
        scope,
    )

    assert (local.effect, local.reason_code) == (1, "OWNER_LOCAL_PURPOSE_ALLOWED")
    assert (public.effect, public.reason_code) == (1, "PUBLIC_EXTERNAL_USE_ALLOWED")
    assert (missing.effect, missing.reason_code) == (2, "SIGNED_CONSENT_REQUIRED")
    assert (allowed.effect, allowed.reason_code) == (1, "SIGNED_CONSENT_ALLOWED")
    assert (mismatched.effect, mismatched.reason_code) == (2, "CONSENT_SCOPE_INVALID")


@pytest.mark.parametrize(
    "privacy_contract",
    [
        _external_request(actor_id="../escape"),
        _external_request(classification_code=4),
        _external_request(purpose_code=6),
        _external_request(destination_code=3),
    ],
)
def test_reference_privacy_gate_rejects_invalid_contract(
    privacy_contract: PrivacyUseContract,
) -> None:
    with pytest.raises(NativeProviderError) as failure:
        TrustedPrivacyGate("python-reference").evaluate(privacy_contract)
    assert failure.value.code == "INVALID_VALUE"


def test_strict_privacy_provider_fails_closed_without_library(monkeypatch) -> None:
    monkeypatch.setattr(
        privacy_module,
        "load_first_party_library",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(NativeProviderError) as failure:
        TrustedPrivacyGate("trusted-rust")
    assert failure.value.code == "PROVIDER_UNAVAILABLE"
