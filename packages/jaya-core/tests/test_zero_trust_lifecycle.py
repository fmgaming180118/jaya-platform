from __future__ import annotations

import json
import shutil
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jaya_core.brain_v2.protection.dna_anchor import (
    DNAAnchor,
    DNAAnchorError,
    DNAFailureCode,
    EncryptedFileKeyStore,
)
from jaya_core.brain_v2.protection.zero_trust import (
    TrustEffect,
    TrustError,
    TrustFailureCode,
    ZeroTrustAuthority,
    create_trust_envelope,
)

_SECRET = "zero-trust-lifecycle-secret-" + ("z" * 40)
_NODE = "zero-trust-lifecycle-node"
_CAPABILITY = "core.logic.evaluate"


def _anchor(root: Path) -> DNAAnchor:
    return DNAAnchor(root, EncryptedFileKeyStore(root / "keystore", _SECRET))


def _signer(anchor: DNAAnchor):
    return lambda purpose, digest: anchor.sign_attestation(purpose, digest).to_dict()


def _state_resolver(anchor: DNAAnchor):
    def resolve(principal_id: str) -> dict[str, object] | None:
        try:
            record = anchor.load_identity()
        except DNAAnchorError as exc:
            if exc.code is DNAFailureCode.IDENTITY_REVOKED:
                return {"active": False, "key_version": 0}
            raise
        if record.brain_id != principal_id:
            return None
        return {"active": True, "key_version": record.key_version}

    return resolve


def _envelope(anchor: DNAAnchor, principal_id: str, payload: dict[str, object]):
    return create_trust_envelope(
        principal_id=principal_id,
        node_id=_NODE,
        capability_id=_CAPABILITY,
        payload=payload,
        policy_receipt_sha256="a" * 64,
        privacy_receipt_sha256="b" * 64,
        signer=_signer(anchor),
    )


def test_p18_dynamic_dna_rotation_revocation_and_restart_fail_closed(
    tmp_path: Path,
) -> None:
    identity_root = tmp_path / "identity"
    database = tmp_path / "zero-trust.db"
    anchor = _anchor(identity_root)
    record, _ = anchor.enroll()
    authority = ZeroTrustAuthority(
        database,
        attestation_verifier=anchor.verify_attestation,
        principal_state_resolver=_state_resolver(anchor),
    )
    authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    payload = {"query": "rotation-proof"}
    stale_envelope = _envelope(anchor, record.brain_id, payload)
    try:
        rotated, _ = anchor.rotate_key()
        stale = authority.authorize(stale_envelope, payload)
        assert stale.effect is TrustEffect.DENY
        assert stale.reason_code == TrustFailureCode.PRINCIPAL_KEY_STALE.value

        current_envelope = _envelope(anchor, record.brain_id, payload)
        current = authority.authorize(current_envelope, payload)
        assert current.effect is TrustEffect.ALLOW
        assert authority.validates(_CAPABILITY, payload, current) is True
        assert rotated.key_version == 2
        assert authority.status()["principal_state_source"] == "dynamic_resolver"
    finally:
        authority.close()
        anchor.close()

    restarted_anchor = _anchor(identity_root)
    restarted = ZeroTrustAuthority(
        database,
        attestation_verifier=restarted_anchor.verify_attestation,
        principal_state_resolver=_state_resolver(restarted_anchor),
    )
    try:
        replay = restarted.authorize(current_envelope, payload)
        assert replay.reason_code == TrustFailureCode.REPLAY_DETECTED.value
        revocation_candidate = _envelope(restarted_anchor, record.brain_id, payload)
        restarted_anchor.revoke("representative zero trust identity revocation")
        revoked = restarted.authorize(revocation_candidate, payload)
        assert revoked.effect is TrustEffect.DENY
        assert revoked.reason_code == TrustFailureCode.PRINCIPAL_REVOKED.value
        assert restarted.audit_chain_valid() is True
    finally:
        restarted.close()
        restarted_anchor.close()


def test_p18_envelope_acl_and_nonce_storage_tamper_fail_closed(
    tmp_path: Path,
) -> None:
    identity_root = tmp_path / "identity"
    anchor = _anchor(identity_root)
    record, _ = anchor.enroll()
    database = tmp_path / "seed.db"
    authority = ZeroTrustAuthority(
        database,
        attestation_verifier=anchor.verify_attestation,
    )
    authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    payload = {"query": "integrity-proof"}
    decision = authority.authorize(_envelope(anchor, record.brain_id, payload), payload)
    assert decision.effect is TrustEffect.ALLOW
    authority.close()

    envelope_tamper = tmp_path / "envelope-tamper.db"
    shutil.copy2(database, envelope_tamper)
    with sqlite3.connect(envelope_tamper) as connection:
        row = connection.execute(
            "SELECT envelope_json FROM trust_decisions WHERE decision_id = 1"
        ).fetchone()
        value = json.loads(row[0])
        value["capability_id"] = "filesystem.erase"
        connection.execute(
            "UPDATE trust_decisions SET envelope_json = ? WHERE decision_id = 1",
            (json.dumps(value, sort_keys=True),),
        )

    acl_tamper = tmp_path / "acl-tamper.db"
    shutil.copy2(database, acl_tamper)
    with sqlite3.connect(acl_tamper) as connection:
        connection.execute(
            "UPDATE trust_principals SET capabilities_json = ?",
            ('["core.logic.evaluate","filesystem.erase"]',),
        )

    nonce_tamper = tmp_path / "nonce-tamper.db"
    shutil.copy2(database, nonce_tamper)
    with sqlite3.connect(nonce_tamper) as connection:
        connection.execute("DELETE FROM trust_nonces")

    for tampered in (envelope_tamper, acl_tamper, nonce_tamper):
        with pytest.raises(TrustError) as failure:
            ZeroTrustAuthority(
                tampered,
                attestation_verifier=anchor.verify_attestation,
            )
        assert failure.value.code is TrustFailureCode.CORRUPT_AUDIT
    anchor.close()


def test_p18_clock_resolver_verifier_payload_and_storage_fail_stably(
    tmp_path: Path,
) -> None:
    anchor = _anchor(tmp_path / "identity")
    record, _ = anchor.enroll()
    payload = {"query": "failure-boundary"}

    current: list[object] = [datetime.now(UTC)]
    clock_authority = ZeroTrustAuthority(
        tmp_path / "clock.db",
        attestation_verifier=anchor.verify_attestation,
        clock=lambda: current[0],  # type: ignore[return-value]
    )
    clock_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    current[0] = None
    with pytest.raises(TrustError) as clock_failure:
        clock_authority.authorize(_envelope(anchor, record.brain_id, payload), payload)
    assert clock_failure.value.code is TrustFailureCode.CLOCK_UNAVAILABLE
    clock_authority.close()

    def unavailable_state(_: str) -> dict[str, object] | None:
        raise RuntimeError("principal registry unavailable")

    state_authority = ZeroTrustAuthority(
        tmp_path / "state.db",
        attestation_verifier=anchor.verify_attestation,
        principal_state_resolver=unavailable_state,
    )
    state_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    state_denied = state_authority.authorize(_envelope(anchor, record.brain_id, payload), payload)
    assert state_denied.reason_code == (TrustFailureCode.PRINCIPAL_STATE_UNAVAILABLE.value)
    state_authority.close()

    def unavailable_verifier(_: object) -> bool:
        raise RuntimeError("attestation registry unavailable")

    verifier_authority = ZeroTrustAuthority(
        tmp_path / "verifier.db",
        attestation_verifier=unavailable_verifier,  # type: ignore[arg-type]
    )
    verifier_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    verifier_denied = verifier_authority.authorize(
        _envelope(anchor, record.brain_id, payload), payload
    )
    assert verifier_denied.reason_code == TrustFailureCode.ATTESTATION_UNAVAILABLE.value
    assert verifier_authority.audit_chain_valid() is True
    verifier_authority.close()

    payload_authority = ZeroTrustAuthority(
        tmp_path / "payload.db",
        attestation_verifier=anchor.verify_attestation,
        max_payload_bytes=1_024,
    )
    payload_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    large_payload = {"value": "x" * 2_048}
    oversized = payload_authority.authorize(
        _envelope(anchor, record.brain_id, large_payload), large_payload
    )
    assert oversized.reason_code == TrustFailureCode.PAYLOAD_TOO_LARGE.value
    payload_authority.close()

    lock_database = tmp_path / "lock.db"
    lock_authority = ZeroTrustAuthority(
        lock_database,
        attestation_verifier=anchor.verify_attestation,
        storage_timeout_seconds=0.05,
    )
    lock_authority.ensure_principal(record.brain_id, _NODE, (_CAPABILITY,))
    blocker = sqlite3.connect(lock_database, timeout=1.0)
    blocker.execute("BEGIN IMMEDIATE")
    started = time.perf_counter()
    try:
        with pytest.raises(TrustError) as storage_failure:
            lock_authority.authorize(_envelope(anchor, record.brain_id, payload), payload)
        assert storage_failure.value.code is TrustFailureCode.STORAGE_ERROR
        assert time.perf_counter() - started < 1.0
    finally:
        blocker.rollback()
        blocker.close()
        lock_authority.close()
        anchor.close()


def test_p18_rejects_unsupported_storage_schema(tmp_path: Path) -> None:
    database = tmp_path / "schema.db"
    authority = ZeroTrustAuthority(
        database,
        attestation_verifier=lambda _: True,
    )
    authority.close()
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE trust_metadata SET value = '999' WHERE key = 'schema_version'")
    with pytest.raises(TrustError) as failure:
        ZeroTrustAuthority(database, attestation_verifier=lambda _: True)
    assert failure.value.code is TrustFailureCode.STORAGE_SCHEMA_UNSUPPORTED
