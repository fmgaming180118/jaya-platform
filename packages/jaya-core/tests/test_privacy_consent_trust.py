from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jaya_core.security.approval_trust import (
    ApprovalTrustAction,
    ApprovalTrustRegistry,
)
from jaya_core.security.sovereign_privacy import (
    DataClassification,
    DataDestination,
    DataPurpose,
    PrivacyEffect,
    PrivacyError,
    PrivacyFailureCode,
    PrivacyUseRequest,
    SovereignPrivacy,
    create_consent_grant,
)

_OWNER = "privacy-trust-owner"
_APPROVER = "privacy-consent-owner"
_SECRET = "privacy-consent-trust-secret-" + ("x" * 40)


def _public(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _trust_event(
    registry: ApprovalTrustRegistry,
    root: Ed25519PrivateKey,
    action: ApprovalTrustAction,
    *,
    public_key: bytes | None = None,
    reason: str,
):
    return registry.prepare_event(
        approver_id=_APPROVER,
        action=action,
        public_key=public_key,
        reason=reason,
        occurred_at=datetime.now(UTC).isoformat(),
        signer=root.sign,
    )


def _grant(signer: Ed25519PrivateKey, consent_id: str):
    now = datetime.now(UTC)
    return create_consent_grant(
        approver_id=_APPROVER,
        owner_id=_OWNER,
        subject_id=_OWNER,
        classifications=(DataClassification.CONFIDENTIAL,),
        purposes=(DataPurpose.MODEL_INFERENCE,),
        providers=("privacy-provider",),
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
        signer=signer.sign,
        consent_id=consent_id,
    )


def _request(consent_id: str) -> PrivacyUseRequest:
    return PrivacyUseRequest(
        request_id=f"request-{consent_id}",
        actor_id=_OWNER,
        owner_id=_OWNER,
        subject_id=_OWNER,
        data_id="privacy-trust-data",
        classification=DataClassification.CONFIDENTIAL,
        purpose=DataPurpose.MODEL_INFERENCE,
        destination=DataDestination.EXTERNAL_PROVIDER,
        provider_id="privacy-provider",
        payload_sha256="a" * 64,
        consent_id=consent_id,
    )


def test_p20_dynamic_consent_trust_rotation_revocation_recovery_and_restart(
    tmp_path: Path,
) -> None:
    root = Ed25519PrivateKey.generate()
    owner_v1 = Ed25519PrivateKey.generate()
    owner_v2 = Ed25519PrivateKey.generate()
    owner_v3 = Ed25519PrivateKey.generate()
    trust_db = tmp_path / "privacy-trust.db"
    privacy_db = tmp_path / "privacy.db"
    registry = ApprovalTrustRegistry(trust_db, _public(root))
    registry.apply(
        _trust_event(
            registry,
            root,
            ApprovalTrustAction.INSTALL,
            public_key=_public(owner_v1),
            reason="initial privacy consent enrollment",
        )
    )
    privacy = SovereignPrivacy(
        privacy_db,
        _SECRET,
        consent_key_resolver=registry.resolve_public_key,
    )
    grant_v1 = _grant(owner_v1, "consent-v1")
    try:
        privacy.install_consent(grant_v1)
        assert privacy.evaluate(_request(grant_v1.consent_id)).effect is (PrivacyEffect.ALLOW)

        registry.apply(
            _trust_event(
                registry,
                root,
                ApprovalTrustAction.ROTATE,
                public_key=_public(owner_v2),
                reason="scheduled privacy consent rotation",
            )
        )
        with pytest.raises(PrivacyError) as retired:
            privacy.evaluate(_request(grant_v1.consent_id))
        assert retired.value.code is PrivacyFailureCode.CONSENT_INVALID

        grant_v2 = _grant(owner_v2, "consent-v2")
        privacy.install_consent(grant_v2)
        assert privacy.evaluate(_request(grant_v2.consent_id)).effect is (PrivacyEffect.ALLOW)

        registry.apply(
            _trust_event(
                registry,
                root,
                ApprovalTrustAction.REVOKE,
                reason="privacy consent signer suspended",
            )
        )
        with pytest.raises(PrivacyError) as revoked:
            privacy.evaluate(_request(grant_v2.consent_id))
        assert revoked.value.code is PrivacyFailureCode.CONSENT_INVALID

        registry.apply(
            _trust_event(
                registry,
                root,
                ApprovalTrustAction.RECOVER,
                public_key=_public(owner_v3),
                reason="approved privacy consent recovery",
            )
        )
        grant_v3 = _grant(owner_v3, "consent-v3")
        privacy.install_consent(grant_v3)
        assert privacy.evaluate(_request(grant_v3.consent_id)).effect is (PrivacyEffect.ALLOW)
        assert privacy.status()["consent_trust_source"] == "dynamic_resolver"
        assert privacy.audit_chain_valid() is True
        assert registry.audit_chain_valid() is True
    finally:
        privacy.close()
        registry.close()

    restarted_registry = ApprovalTrustRegistry(trust_db, _public(root))
    restarted_privacy = SovereignPrivacy(
        privacy_db,
        _SECRET,
        consent_key_resolver=restarted_registry.resolve_public_key,
    )
    try:
        assert restarted_privacy.evaluate(_request(grant_v3.consent_id)).effect is (
            PrivacyEffect.ALLOW
        )
        assert restarted_registry.status()["events"] == 4
        assert restarted_privacy.audit_chain_valid() is True
    finally:
        restarted_privacy.close()
        restarted_registry.close()


def test_p20_dynamic_consent_trust_failure_is_stable_and_fail_closed(
    tmp_path: Path,
) -> None:
    signer = Ed25519PrivateKey.generate()

    def unavailable(_: str) -> bytes | None:
        raise RuntimeError("privacy trust registry offline")

    privacy = SovereignPrivacy(
        tmp_path / "privacy.db",
        _SECRET,
        consent_key_resolver=unavailable,
    )
    try:
        with pytest.raises(PrivacyError) as failure:
            privacy.install_consent(_grant(signer, "consent-unavailable"))
        assert failure.value.code is PrivacyFailureCode.CONSENT_TRUST_UNAVAILABLE
    finally:
        privacy.close()


def test_p20_static_and_dynamic_consent_trust_are_mutually_exclusive(
    tmp_path: Path,
) -> None:
    signer = Ed25519PrivateKey.generate()
    with pytest.raises(PrivacyError) as failure:
        SovereignPrivacy(
            tmp_path / "privacy.db",
            _SECRET,
            consent_public_keys={_APPROVER: _public(signer)},
            consent_key_resolver=lambda _: _public(signer),
        )
    assert failure.value.code is PrivacyFailureCode.INVALID_INPUT
