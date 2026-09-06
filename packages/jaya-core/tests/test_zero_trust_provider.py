"""Reference, two-stage, and failure contracts for the P18 trusted provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from jaya_core.brain_v2.protection.zero_trust import (
    TrustEffect,
    ZeroTrustAuthority,
    create_trust_envelope,
)
from jaya_core.providers import (
    NativeProviderError,
    TrustedZeroTrustGate,
    ZeroTrustAuthorizationContract,
)
from jaya_core.providers import zero_trust as zero_trust_module


def _contract(**changes: object) -> ZeroTrustAuthorizationContract:
    values = {
        "envelope_id": "trust-envelope-1",
        "principal_id": "principal-1",
        "envelope_node_id": "node-1",
        "capability_id": "core.logic.evaluate",
        "nonce": "nonce-1",
        "principal_status": 1,
        "principal_state": 0,
        "attestation_state": 0,
        "persisted_node_id": "node-1",
        "capability_ids": ("core.logic.evaluate",),
        "claimed_payload_sha256": "a" * 64,
        "actual_payload_sha256": "a" * 64,
    }
    values.update(changes)
    return ZeroTrustAuthorizationContract(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        (
            {"principal_status": 0, "persisted_node_id": None, "capability_ids": ()},
            (2, "ZERO_TRUST_PRINCIPAL_UNKNOWN"),
        ),
        ({"principal_status": 2}, (2, "ZERO_TRUST_PRINCIPAL_REVOKED")),
        ({"principal_state": 4}, (2, "ZERO_TRUST_PRINCIPAL_KEY_STALE")),
        ({"persisted_node_id": "node-other"}, (2, "ZERO_TRUST_NODE_MISMATCH")),
        ({"capability_id": "filesystem.erase"}, (2, "ZERO_TRUST_CAPABILITY_DENIED")),
        ({"actual_payload_sha256": "b" * 64}, (2, "ZERO_TRUST_PAYLOAD_MISMATCH")),
        ({}, (3, "ATTESTATION_REQUIRED")),
        ({"attestation_state": 1}, (1, "VERIFIED_LEAST_PRIVILEGE")),
        ({"attestation_state": 2}, (2, "ZERO_TRUST_ATTESTATION_INVALID")),
        ({"attestation_state": 3}, (2, "ZERO_TRUST_ATTESTATION_UNAVAILABLE")),
    ],
)
def test_reference_gate_covers_least_privilege_paths(
    changes: dict[str, object], expected: tuple[int, str]
) -> None:
    decision = TrustedZeroTrustGate("python-reference").evaluate(_contract(**changes))
    assert (decision.effect, decision.reason_code) == expected


@pytest.mark.parametrize(
    "contract",
    [
        _contract(envelope_id="../escape"),
        _contract(principal_status=3),
        _contract(claimed_payload_sha256="not-a-digest"),
        _contract(principal_status=0, persisted_node_id=None, capability_ids=("invalid",)),
    ],
)
def test_reference_gate_rejects_malformed_contract(
    contract: ZeroTrustAuthorizationContract,
) -> None:
    with pytest.raises(NativeProviderError) as failure:
        TrustedZeroTrustGate("python-reference").evaluate(contract)
    assert failure.value.code == "INVALID_VALUE"


def test_authority_only_invokes_attestation_after_scope_passes(tmp_path: Path) -> None:
    verifier_calls: list[dict[str, object]] = []

    def verifier(value: object) -> bool:
        assert isinstance(value, dict)
        verifier_calls.append(value)
        return True

    authority = ZeroTrustAuthority(
        tmp_path / "two-stage.db",
        attestation_verifier=verifier,  # type: ignore[arg-type]
        authorization_gate=TrustedZeroTrustGate("python-reference"),
    )
    payload = {"query": "trust.required"}
    envelope = create_trust_envelope(
        principal_id="principal-1",
        node_id="node-1",
        capability_id="core.logic.evaluate",
        payload=payload,
        policy_receipt_sha256="a" * 64,
        privacy_receipt_sha256="b" * 64,
        signer=lambda purpose, digest: {"purpose": purpose, "payload_sha256": digest},
    )
    try:
        unknown = authority.authorize(envelope, payload)
        assert unknown.reason_code == "ZERO_TRUST_PRINCIPAL_UNKNOWN"
        assert verifier_calls == []

        authority.ensure_principal("principal-1", "node-1", ("core.logic.evaluate",))
        allowed = authority.authorize(envelope, payload)
        assert allowed.effect is TrustEffect.ALLOW
        assert allowed.reason_code == "VERIFIED_LEAST_PRIVILEGE"
        assert len(verifier_calls) == 1
    finally:
        authority.close()


def test_strict_zero_trust_provider_fails_closed_without_library(monkeypatch) -> None:
    monkeypatch.setattr(
        zero_trust_module,
        "load_first_party_library",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(NativeProviderError) as failure:
        TrustedZeroTrustGate("trusted-rust")
    assert failure.value.code == "PROVIDER_UNAVAILABLE"
