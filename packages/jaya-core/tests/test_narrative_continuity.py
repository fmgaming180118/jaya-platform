from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jaya_core.brain_v2.engine.narrative_continuity import (
    DNAAnchorNarrativeSigner,
    NarrativeContinuity,
    NarrativeContinuityError,
    NarrativeFailureCode,
    NarrativeTruthClass,
)
from jaya_core.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from jaya_core.cognitive.runtime import JayaCoreRuntime

_TEST_SECRET = "narrative-test-secret-material-32-bytes-minimum"


class TestNarrativeSigner:
    """Test-only implementation of the signer contract."""

    __test__ = False

    def __init__(self) -> None:
        self._private = Ed25519PrivateKey.generate()

    @property
    def actor_id(self) -> str:
        return "test-brain"

    @property
    def key_id(self) -> str:
        return "test-brain:1"

    def sign(self, purpose: str, payload_sha256: str) -> dict[str, object]:
        message = f"{purpose}:{payload_sha256}".encode()
        return {
            "purpose": purpose,
            "payload_sha256": payload_sha256,
            "signature": base64.b64encode(self._private.sign(message)).decode(),
        }

    def verify(self, attestation: dict[str, object]) -> bool:
        try:
            purpose = str(attestation["purpose"])
            digest = str(attestation["payload_sha256"])
            signature = base64.b64decode(str(attestation["signature"]), validate=True)
            self._private.public_key().verify(
                signature, f"{purpose}:{digest}".encode()
            )
            return True
        except (KeyError, ValueError, InvalidSignature):
            return False

    def health_check(self) -> bool:
        return True


def _anchor(root: Path) -> DNAAnchor:
    anchor = DNAAnchor(
        root / "identity",
        EncryptedFileKeyStore(root / "keystore", _TEST_SECRET),
    )
    anchor.enroll()
    return anchor


def test_missing_identity_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(NarrativeContinuityError) as raised:
        NarrativeContinuity(tmp_path / "narrative.sqlite3")
    assert raised.value.code is NarrativeFailureCode.IDENTITY_NOT_CONFIGURED


def test_test_signer_contract_and_duplicate_request(tmp_path: Path) -> None:
    ledger = NarrativeContinuity(tmp_path / "unit.sqlite3", TestNarrativeSigner())
    ledger.remember_turn("analisis data", request_id="turn-1")
    with pytest.raises(NarrativeContinuityError) as duplicate:
        ledger.remember_turn("analisis lain", request_id="turn-1")
    assert duplicate.value.code is NarrativeFailureCode.DUPLICATE_REQUEST
    ledger.close()


def test_verified_fact_rejects_unregistered_evidence(tmp_path: Path) -> None:
    ledger = NarrativeContinuity(tmp_path / "evidence.sqlite3", TestNarrativeSigner())
    with pytest.raises(NarrativeContinuityError) as rejected:
        ledger.record_verified_fact(
            request_id="fact-unregistered",
            subject="unverified.subject",
            value="claim",
            evidence_refs=("evidence:" + "0" * 64,),
        )
    assert rejected.value.code is NarrativeFailureCode.INVALID_INPUT
    ledger.close()


def test_dna_signed_restart_fact_commitment_and_correction(tmp_path: Path) -> None:
    anchor = _anchor(tmp_path)
    signer = DNAAnchorNarrativeSigner(anchor)
    database = tmp_path / "narrative.sqlite3"
    ledger = NarrativeContinuity(database, signer)
    evidence_a = ledger.register_evidence(
        content=b"release=alpha",
        source_uri="memory://release-manifest-a",
        media_type="text/plain",
    )
    evidence_b = ledger.register_evidence(
        content=b"release=beta",
        source_uri="memory://release-manifest-b",
        media_type="text/plain",
    )
    commitment_evidence = ledger.register_evidence(
        content=b"review requested by operator",
        source_uri="memory://commitment-request",
        media_type="text/plain",
    )
    first = ledger.record_verified_fact(
        request_id="fact-1",
        subject="project.release",
        value="alpha",
        evidence_refs=(evidence_a,),
    )
    ledger.record_verified_fact(
        request_id="fact-2",
        subject="project.release",
        value="beta",
        evidence_refs=(evidence_b,),
    )
    ledger.record_commitment(
        request_id="commitment-1",
        commitment_id="commitment:review",
        subject="project.review",
        details={"owner": "operator", "state": "requested"},
        evidence_refs=(commitment_evidence,),
    )
    conflicted = ledger.snapshot(limit=20, max_chars=20_000)
    assert conflicted["summary"]["conflicts"][0]["subject"] == "project.release"
    ledger.record_correction(
        request_id="correction-1",
        correction_of=first.event_id,
        subject="project.release",
        corrected_value="beta",
        evidence_refs=(evidence_b,),
        truth_class=NarrativeTruthClass.VERIFIED_FACT,
    )
    before_restart = ledger.snapshot(limit=20, max_chars=20_000)
    ledger.close()

    reopened = NarrativeContinuity(database, signer)
    after_restart = reopened.boot_context()
    assert after_restart["snapshot_sha256"] == before_restart["snapshot_sha256"]
    assert after_restart["conflicts"] == []
    assert after_restart["verified_facts"][0]["value"] == "beta"
    assert after_restart["active_commitments"][0]["commitment_id"] == "commitment:review"
    assert reopened.verify_integrity()
    reopened.close()
    anchor.close()


def test_append_only_triggers_reject_update_and_delete(tmp_path: Path) -> None:
    ledger = NarrativeContinuity(tmp_path / "append-only.sqlite3", TestNarrativeSigner())
    ledger.remember_turn("event permanen", request_id="turn-permanent")
    connection = sqlite3.connect(tmp_path / "append-only.sqlite3")
    with pytest.raises(sqlite3.DatabaseError):
        connection.execute(
            "UPDATE narrative_events SET subject = ? WHERE request_id = ?",
            ("changed", "turn-permanent"),
        )
    with pytest.raises(sqlite3.DatabaseError):
        connection.execute(
            "DELETE FROM narrative_events WHERE request_id = ?",
            ("turn-permanent",),
        )
    connection.close()
    ledger.close()


def test_partial_corruption_is_reported_not_swallowed(tmp_path: Path) -> None:
    database = tmp_path / "corrupt.sqlite3"
    signer = TestNarrativeSigner()
    ledger = NarrativeContinuity(database, signer)
    ledger.remember_turn("event untuk verifikasi", request_id="turn-corrupt")
    ledger.close()
    connection = sqlite3.connect(database)
    connection.execute("DROP TRIGGER narrative_events_no_update")
    connection.execute(
        "UPDATE narrative_events SET payload_json = ? WHERE request_id = ?",
        (json.dumps({"tampered": True}), "turn-corrupt"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(NarrativeContinuityError) as corrupt:
        NarrativeContinuity(database, signer)
    assert corrupt.value.code is NarrativeFailureCode.LEDGER_CORRUPT


def test_external_commit_invalidates_cached_integrity_before_next_append(
    tmp_path: Path,
) -> None:
    database = tmp_path / "live-corrupt.sqlite3"
    signer = TestNarrativeSigner()
    ledger = NarrativeContinuity(database, signer)
    ledger.remember_turn("event asli", request_id="turn-original")

    connection = sqlite3.connect(database)
    connection.execute("DROP TRIGGER narrative_events_no_update")
    connection.execute(
        "UPDATE narrative_events SET payload_json = ? WHERE request_id = ?",
        (json.dumps({"tampered": True}), "turn-original"),
    )
    connection.commit()
    connection.close()

    with pytest.raises(NarrativeContinuityError) as corrupt:
        ledger.remember_turn("event berikutnya", request_id="turn-after-tamper")
    assert corrupt.value.code is NarrativeFailureCode.LEDGER_CORRUPT
    ledger.close()


def test_legacy_json_is_imported_as_raw_events_only(tmp_path: Path) -> None:
    legacy = tmp_path / "narrative.json"
    legacy.write_text(
        json.dumps(
            {
                "events": [{"kind": "turn", "user": "legacy input"}],
                "summary": "This text must not become a verified fact",
            }
        ),
        encoding="utf-8",
    )
    ledger = NarrativeContinuity(persist_path=legacy, signer=TestNarrativeSigner())
    snapshot = ledger.snapshot(limit=10, max_chars=10_000)
    assert snapshot["total_events"] == 1
    assert snapshot["summary"]["verified_facts"] == []
    assert snapshot["recent"][0]["truth_class"] == "RAW_EVENT"
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() in json.dumps(
        snapshot["recent"][0]
    )
    ledger.close()


def test_canonical_runtime_wires_signed_boot_context(tmp_path: Path) -> None:
    anchor = _anchor(tmp_path)
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "runtime.sqlite3",
        identity_anchor=anchor,
        identity_required=True,
        narrative_db_path=tmp_path / "runtime-narrative.sqlite3",
        narrative_required=True,
    )
    assert runtime.narrative_continuity is not None
    evidence_ref = runtime.narrative_continuity.register_evidence(
        content=b"runtime.mode=local",
        source_uri="memory://runtime-configuration-receipt",
        media_type="text/plain",
    )
    runtime.narrative_continuity.record_verified_fact(
        request_id="runtime-fact-1",
        subject="runtime.mode",
        value="local",
        evidence_refs=(evidence_ref,),
    )
    boot = runtime.narrative_boot_context()
    assert boot["available"] is True
    assert boot["verified_facts"][0]["subject"] == "runtime.mode"
    capability = runtime.capability_registry.lookup("core.narrative.context")
    assert capability is not None
    assert capability.health_status == "HEALTHY"
    assert runtime.operational_snapshot()["narrative_continuity"]["signed"] is True
    runtime.close()
