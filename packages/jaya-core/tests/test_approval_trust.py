from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jaya_core.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyBundle,
    PolicyEffect,
    PolicyError,
    PolicyFailureCode,
    PolicyRequest,
    PolicyRisk,
    PolicyRule,
    create_owner_approval,
)
from jaya_core.security.approval_trust import (
    ApprovalTrustAction,
    ApprovalTrustError,
    ApprovalTrustFailureCode,
    ApprovalTrustRegistry,
)


def _public(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _payload_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _event(
    registry: ApprovalTrustRegistry,
    root: Ed25519PrivateKey,
    action: ApprovalTrustAction,
    *,
    public_key: bytes | None = None,
    reason: str,
):
    return registry.prepare_event(
        approver_id="human-owner",
        action=action,
        public_key=public_key,
        reason=reason,
        occurred_at=datetime.now(UTC).isoformat(),
        signer=root.sign,
    )


def _approval(
    signer: Ed25519PrivateKey,
    policy: PolicyBundle,
    request: PolicyRequest,
):
    now = datetime.now(UTC)
    return create_owner_approval(
        approver_id="human-owner",
        actor_brain_id=request.actor_brain_id,
        capability_id=request.capability_id,
        payload_sha256=request.payload_sha256,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=2)).isoformat(),
        signer=signer.sign,
    )


def test_p15_dynamic_trust_rotation_revocation_recovery_and_restart(
    tmp_path: Path,
) -> None:
    root = Ed25519PrivateKey.generate()
    owner_v1 = Ed25519PrivateKey.generate()
    owner_v2 = Ed25519PrivateKey.generate()
    owner_v3 = Ed25519PrivateKey.generate()
    trust_db = tmp_path / "approval-trust.db"
    policy_db = tmp_path / "ethical-heart.db"
    registry = ApprovalTrustRegistry(trust_db, _public(root))
    registry.apply(
        _event(
            registry,
            root,
            ApprovalTrustAction.INSTALL,
            public_key=_public(owner_v1),
            reason="initial owner enrollment",
        )
    )
    policy = PolicyBundle(
        policy_id="test.dynamic-approval",
        version=1,
        brain_id="brain-dynamic-approval",
        rules=(
            PolicyRule(
                rule_id="deny.destructive",
                effect=PolicyEffect.DENY,
                risk_classes=(PolicyRisk.DESTRUCTIVE,),
                reason_code="DESTRUCTIVE_DENIED",
            ),
        ),
        default_effect=PolicyEffect.REQUIRE_APPROVAL,
        default_reason_code="OWNER_APPROVAL_REQUIRED",
    )
    payload = {"device": "lamp", "state": "on"}
    request = PolicyRequest(
        request_id="dynamic-owner-request",
        actor_brain_id=policy.brain_id,
        node_id="node-dynamic-approval",
        capability_id="device.switch",
        risk_class=PolicyRisk.PHYSICAL_ACTION,
        permissions=("device.write",),
        payload_sha256=_payload_digest(payload),
    )
    heart = EthicalHeart(
        policy_db,
        policy,
        approval_key_resolver=registry.resolve_public_key,
    )
    try:
        assert heart.evaluate(request, _approval(owner_v1, policy, request)).effect is (
            PolicyEffect.ALLOW
        )
        stale_rotation = _event(
            registry,
            root,
            ApprovalTrustAction.ROTATE,
            public_key=_public(owner_v3),
            reason="stale concurrent rotation",
        )
        registry.apply(
            _event(
                registry,
                root,
                ApprovalTrustAction.ROTATE,
                public_key=_public(owner_v2),
                reason="scheduled owner rotation",
            )
        )
        with pytest.raises(ApprovalTrustError) as conflict:
            registry.apply(stale_rotation)
        assert conflict.value.code is ApprovalTrustFailureCode.CONFLICT

        with pytest.raises(PolicyError) as retired:
            heart.evaluate(request, _approval(owner_v1, policy, request))
        assert retired.value.code is PolicyFailureCode.APPROVAL_INVALID
        assert heart.evaluate(request, _approval(owner_v2, policy, request)).effect is (
            PolicyEffect.ALLOW
        )

        registry.apply(
            _event(
                registry,
                root,
                ApprovalTrustAction.REVOKE,
                reason="owner access appeal under review",
            )
        )
        with pytest.raises(PolicyError) as revoked:
            heart.evaluate(request, _approval(owner_v2, policy, request))
        assert revoked.value.code is PolicyFailureCode.APPROVAL_INVALID

        registry.apply(
            _event(
                registry,
                root,
                ApprovalTrustAction.RECOVER,
                public_key=_public(owner_v3),
                reason="approved owner recovery",
            )
        )
        assert heart.evaluate(request, _approval(owner_v3, policy, request)).effect is (
            PolicyEffect.ALLOW
        )
        assert registry.status()["active_approvers"] == 1
        assert registry.audit_chain_valid() is True
        assert heart.status()["approval_trust_source"] == "dynamic_resolver"
    finally:
        heart.close()
        registry.close()

    restarted_registry = ApprovalTrustRegistry(trust_db, _public(root))
    restarted_heart = EthicalHeart(
        policy_db,
        policy,
        approval_key_resolver=restarted_registry.resolve_public_key,
    )
    try:
        assert restarted_heart.evaluate(
            request,
            _approval(owner_v3, policy, request),
        ).effect is PolicyEffect.ALLOW
        assert restarted_registry.status()["events"] == 4
        assert restarted_heart.audit_chain_valid() is True
    finally:
        restarted_heart.close()
        restarted_registry.close()


def test_p15_dynamic_trust_tamper_and_wrong_root_fail_closed(
    tmp_path: Path,
) -> None:
    root = Ed25519PrivateKey.generate()
    owner = Ed25519PrivateKey.generate()
    trust_db = tmp_path / "approval-trust.db"
    registry = ApprovalTrustRegistry(trust_db, _public(root))
    registry.apply(
        _event(
            registry,
            root,
            ApprovalTrustAction.INSTALL,
            public_key=_public(owner),
            reason="initial owner enrollment",
        )
    )
    registry.close()

    with pytest.raises(ApprovalTrustError) as wrong_root:
        ApprovalTrustRegistry(trust_db, _public(Ed25519PrivateKey.generate()))
    assert wrong_root.value.code is ApprovalTrustFailureCode.CONFLICT

    with sqlite3.connect(trust_db) as connection:
        row = connection.execute(
            "SELECT event_json FROM approval_trust_events WHERE sequence = 1"
        ).fetchone()
        value = json.loads(row[0])
        value["reason"] = "tampered enrollment"
        connection.execute(
            "UPDATE approval_trust_events SET event_json = ? WHERE sequence = 1",
            (json.dumps(value, sort_keys=True),),
        )
    with pytest.raises(ApprovalTrustError) as corrupted:
        ApprovalTrustRegistry(trust_db, _public(root))
    assert corrupted.value.code in {
        ApprovalTrustFailureCode.CORRUPT,
        ApprovalTrustFailureCode.INVALID_SIGNATURE,
    }


def test_p15_dynamic_trust_failure_is_a_stable_policy_error(tmp_path: Path) -> None:
    policy = PolicyBundle(
        policy_id="test.unavailable-approval-trust",
        version=1,
        brain_id="brain-unavailable-trust",
        rules=(
            PolicyRule(
                rule_id="approval.required",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                risk_classes=(PolicyRisk.PHYSICAL_ACTION,),
            ),
        ),
    )
    request = PolicyRequest(
        request_id="unavailable-trust-request",
        actor_brain_id=policy.brain_id,
        node_id="node-unavailable-trust",
        capability_id="device.switch",
        risk_class=PolicyRisk.PHYSICAL_ACTION,
        permissions=(),
        payload_sha256=_payload_digest({"state": "on"}),
    )
    signer = Ed25519PrivateKey.generate()

    def unavailable(_: str) -> bytes | None:
        raise RuntimeError("registry offline")

    heart = EthicalHeart(
        tmp_path / "policy.db",
        policy,
        approval_key_resolver=unavailable,
    )
    try:
        with pytest.raises(PolicyError) as failure:
            heart.evaluate(request, _approval(signer, policy, request))
        assert failure.value.code is PolicyFailureCode.APPROVAL_TRUST_UNAVAILABLE
    finally:
        heart.close()
