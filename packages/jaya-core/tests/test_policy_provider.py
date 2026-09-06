"""Reference and failure contracts for the P15 trusted policy provider."""

from __future__ import annotations

import pytest

from jaya_core.providers import NativeProviderError, TrustedPolicyGate, TrustedPolicyRule
from jaya_core.providers import policy as policy_module


def test_reference_policy_provider_preserves_first_match_and_default() -> None:
    gate = TrustedPolicyGate("python-reference")
    rules = (
        TrustedPolicyRule(effect=2, risk_mask=1 << 2),
        TrustedPolicyRule(
            effect=1,
            risk_mask=1 << 0,
            capability_ids=("core.logic.evaluate",),
        ),
    )

    matched = gate.evaluate(
        capability_id="core.logic.evaluate",
        risk_code=0,
        rules=rules,
        default_effect=3,
    )
    defaulted = gate.evaluate(
        capability_id="device.switch",
        risk_code=1,
        rules=rules,
        default_effect=3,
    )

    assert (matched.effect, matched.rule_index) == (1, 1)
    assert (defaulted.effect, defaulted.rule_index) == (3, None)
    assert gate.profile()["selected_provider"] == "python-policy-reference-v1"


@pytest.mark.parametrize(
    ("capability_id", "risk_code", "rules", "expected_code"),
    [
        ("../escape", 0, (TrustedPolicyRule(1, 1),), "INVALID_VALUE"),
        ("core.logic.evaluate", 6, (TrustedPolicyRule(1, 1),), "INVALID_VALUE"),
        ("core.logic.evaluate", 0, (), "INVALID_SIZE"),
        (
            "core.logic.evaluate",
            0,
            (TrustedPolicyRule(9, 1),),
            "INVALID_VALUE",
        ),
    ],
)
def test_reference_policy_provider_rejects_invalid_contracts(
    capability_id: str,
    risk_code: int,
    rules: tuple[TrustedPolicyRule, ...],
    expected_code: str,
) -> None:
    gate = TrustedPolicyGate("python-reference")
    with pytest.raises(NativeProviderError) as failure:
        gate.evaluate(
            capability_id=capability_id,
            risk_code=risk_code,
            rules=rules,
            default_effect=2,
        )
    assert failure.value.code == expected_code


def test_strict_policy_provider_fails_closed_without_library(monkeypatch) -> None:
    monkeypatch.setattr(
        policy_module,
        "load_first_party_library",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(NativeProviderError) as failure:
        TrustedPolicyGate("trusted-rust")
    assert failure.value.code == "PROVIDER_UNAVAILABLE"
