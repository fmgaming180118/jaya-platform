"""Real evidence gates for P20 Sovereign Privacy."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jaya_core.cognitive.contracts import (
    ActionPlan,
    ActionStep,
    RiskClass,
    UserRequest,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.identity.models import NodeClass
from jaya_core.memory.episodic import EpisodicMemoryStore
from jaya_core.memory.events import MemoryEvent
from jaya_core.models.protocol import ModelCost, ModelRequest, ModelResponse
from jaya_core.observability.structured_logging import StructuredFormatter
from jaya_core.resources.profiler import ResourceProfile
from jaya_core.security.sovereign_privacy import (
    DataClassification,
    DataDestination,
    DataPurpose,
    PrivacyEffect,
    PrivacyError,
    PrivacyFailureCode,
    PrivacyMemoryCodec,
    PrivacyUseRequest,
    SovereignPrivacy,
    create_consent_grant,
)

_SECRET = "privacy-test-secret-" + ("s" * 40)
_OWNER = "owner-privacy-test"


def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _request(
    *,
    destination: DataDestination,
    consent_id: str | None = None,
    provider_id: str = "provider-real",
) -> PrivacyUseRequest:
    return PrivacyUseRequest(
        request_id="privacy-request-1",
        actor_id=_OWNER,
        owner_id=_OWNER,
        subject_id=_OWNER,
        data_id="prompt-request-1",
        classification=DataClassification.CONFIDENTIAL,
        purpose=DataPurpose.MODEL_INFERENCE,
        destination=destination,
        provider_id=provider_id,
        payload_sha256="a" * 64,
        consent_id=consent_id,
    )


def test_p20_external_use_requires_signed_scoped_consent_and_revocation(
    tmp_path: Path,
) -> None:
    signer = Ed25519PrivateKey.generate()
    privacy = SovereignPrivacy(
        tmp_path / "privacy.db",
        _SECRET,
        consent_public_keys={"owner-key": _public_bytes(signer)},
    )
    now = datetime.now(timezone.utc)
    grant = create_consent_grant(
        approver_id="owner-key",
        owner_id=_OWNER,
        subject_id=_OWNER,
        classifications=(DataClassification.CONFIDENTIAL,),
        purposes=(DataPurpose.MODEL_INFERENCE,),
        providers=("provider-real",),
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
        signer=signer.sign,
    )
    try:
        denied = privacy.evaluate(
            _request(destination=DataDestination.EXTERNAL_PROVIDER)
        )
        assert denied.effect is PrivacyEffect.DENY
        assert denied.reason_code == "SIGNED_CONSENT_REQUIRED"

        privacy.install_consent(grant)
        allowed = privacy.evaluate(
            _request(
                destination=DataDestination.EXTERNAL_PROVIDER,
                consent_id=grant.consent_id,
            )
        )
        assert allowed.effect is PrivacyEffect.ALLOW
        assert allowed.consent_id == grant.consent_id

        with pytest.raises(PrivacyError) as wrong_provider:
            privacy.evaluate(
                _request(
                    destination=DataDestination.EXTERNAL_PROVIDER,
                    consent_id=grant.consent_id,
                    provider_id="provider-other",
                )
            )
        assert wrong_provider.value.code is PrivacyFailureCode.CONSENT_INVALID

        privacy.revoke_consent(_OWNER, grant.consent_id)
        with pytest.raises(PrivacyError) as revoked:
            privacy.evaluate(
                _request(
                    destination=DataDestination.EXTERNAL_PROVIDER,
                    consent_id=grant.consent_id,
                )
            )
        assert revoked.value.code is PrivacyFailureCode.CONSENT_REVOKED
        assert privacy.audit_chain_valid() is True
    finally:
        privacy.close()


def test_p20_encrypted_vault_restart_export_and_owner_deletion(
    tmp_path: Path,
) -> None:
    database = tmp_path / "privacy.db"
    needle = "SYNTHETIC-PRIVATE-CONTENT"
    privacy = SovereignPrivacy(database, _SECRET)
    privacy.store(
        actor_id=_OWNER,
        owner_id=_OWNER,
        subject_id=_OWNER,
        data_id="private-record-1",
        classification=DataClassification.RESTRICTED,
        allowed_purposes=(DataPurpose.MEMORY, DataPurpose.EXPORT),
        payload={"medical_note": needle, "score": 7},
        retention_seconds=600,
    )
    assert privacy.plaintext_absent(needle) is True
    assert needle.encode() not in database.read_bytes()
    privacy.close()

    restarted = SovereignPrivacy(database, _SECRET)
    try:
        payload = restarted.retrieve(
            actor_id=_OWNER,
            data_id="private-record-1",
            purpose=DataPurpose.MEMORY,
        )
        assert payload["medical_note"] == needle
        exported = restarted.export_owner(_OWNER)
        assert exported["records"][0]["payload"]["medical_note"] == needle

        receipt = restarted.delete_owner(_OWNER)
        assert receipt["event"] == "OWNER_DATA_DELETED"
        with pytest.raises(PrivacyError) as deleted:
            restarted.retrieve(
                actor_id=_OWNER,
                data_id="private-record-1",
                purpose=DataPurpose.MEMORY,
            )
        assert deleted.value.code is PrivacyFailureCode.DATA_DELETED
        assert restarted.audit_chain_valid() is True
    finally:
        restarted.close()


def test_p20_wrong_key_and_ciphertext_tamper_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "privacy.db"
    privacy = SovereignPrivacy(database, _SECRET)
    privacy.store(
        actor_id=_OWNER,
        owner_id=_OWNER,
        subject_id=_OWNER,
        data_id="private-record-tamper",
        classification=DataClassification.CONFIDENTIAL,
        allowed_purposes=(DataPurpose.MEMORY,),
        payload={"value": "real"},
        retention_seconds=600,
    )
    privacy.close()

    wrong_key = SovereignPrivacy(database, "different-secret-" + ("x" * 40))
    try:
        with pytest.raises(PrivacyError) as failed:
            wrong_key.retrieve(
                actor_id=_OWNER,
                data_id="private-record-tamper",
                purpose=DataPurpose.MEMORY,
            )
        assert failed.value.code is PrivacyFailureCode.DECRYPTION_FAILED
    finally:
        wrong_key.close()

    connection = sqlite3.connect(database)
    with connection:
        connection.execute(
            "UPDATE privacy_vault SET ciphertext = ciphertext || 'A' "
            "WHERE data_id = 'private-record-tamper'"
        )
    connection.close()
    tampered = SovereignPrivacy(database, _SECRET)
    try:
        with pytest.raises(PrivacyError) as failed:
            tampered.retrieve(
                actor_id=_OWNER,
                data_id="private-record-tamper",
                purpose=DataPurpose.MEMORY,
            )
        assert failed.value.code is PrivacyFailureCode.CORRUPT_DATA
    finally:
        tampered.close()


def test_p20_retention_purge_and_cross_owner_fail_closed(tmp_path: Path) -> None:
    current = [datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)]
    privacy = SovereignPrivacy(
        tmp_path / "privacy.db",
        _SECRET,
        clock=lambda: current[0],
    )
    try:
        privacy.store(
            actor_id=_OWNER,
            owner_id=_OWNER,
            subject_id=_OWNER,
            data_id="retained-record",
            classification=DataClassification.CONFIDENTIAL,
            allowed_purposes=(DataPurpose.MEMORY,),
            payload={"value": "retained"},
            retention_seconds=10,
        )
        with pytest.raises(PrivacyError) as cross_owner:
            privacy.retrieve(
                actor_id="owner-attacker",
                data_id="retained-record",
                purpose=DataPurpose.MEMORY,
            )
        assert cross_owner.value.code is PrivacyFailureCode.OWNER_MISMATCH

        current[0] += timedelta(seconds=11)
        with pytest.raises(PrivacyError) as expired:
            privacy.retrieve(
                actor_id=_OWNER,
                data_id="retained-record",
                purpose=DataPurpose.MEMORY,
            )
        assert expired.value.code is PrivacyFailureCode.DATA_EXPIRED
        assert privacy.purge_expired() == 1
        with pytest.raises(PrivacyError) as purged:
            privacy.retrieve(
                actor_id=_OWNER,
                data_id="retained-record",
                purpose=DataPurpose.MEMORY,
            )
        assert purged.value.code is PrivacyFailureCode.DATA_DELETED
    finally:
        privacy.close()


def test_p20_episodic_payload_is_encrypted_and_survives_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.db"
    needle = "SYNTHETIC-MEMORY-SECRET"
    privacy = SovereignPrivacy(database, _SECRET)
    memory = EpisodicMemoryStore(database, PrivacyMemoryCodec(privacy))
    event = MemoryEvent(
        event_id="event-privacy-1",
        event_type="PRIVATE_EVENT",
        session_id=_OWNER,
        goal_id="goal-privacy-1",
        payload={"secret_note": needle},
        node_id="node-privacy-1",
        timestamp="2026-08-13T00:00:00+00:00",
        sequence_number=1,
    )
    assert memory.append_event(event) is True
    memory.close()
    privacy.close()
    assert needle.encode() not in database.read_bytes()

    restarted_privacy = SovereignPrivacy(database, _SECRET)
    restarted_memory = EpisodicMemoryStore(
        database, PrivacyMemoryCodec(restarted_privacy)
    )
    try:
        restored = restarted_memory.query_by_session(_OWNER)
        assert restored[0].payload == {"secret_note": needle}
    finally:
        restarted_memory.close()
        restarted_privacy.close()


def test_p20_structured_logs_redact_messages_nested_fields_and_exceptions() -> None:
    formatter = StructuredFormatter()
    try:
        raise RuntimeError("token=SYNTHETIC-EXCEPTION-SECRET")
    except RuntimeError:
        record = logging.LogRecord(
            name="privacy-test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="password=SYNTHETIC-MESSAGE-SECRET",
            args=(),
            exc_info=__import__("sys").exc_info(),
        )
    record.extra_fields = {
        "nested": {"api_key": "SYNTHETIC-FIELD-SECRET"},
        "items": ["token=SYNTHETIC-LIST-SECRET"],
    }
    rendered = formatter.format(record)
    parsed = json.loads(rendered)

    assert "SYNTHETIC" not in rendered
    assert parsed["message"] == "password=***REDACTED***"
    assert parsed["nested"]["api_key"] == "***REDACTED***"
    assert parsed["items"][0] == "token=***REDACTED***"
    assert parsed["exception"]["message"] == "token=***REDACTED***"


def test_p20_runtime_blocks_external_model_and_encrypts_prompt_memory(
    tmp_path: Path,
) -> None:
    class StableProfiler:
        def profile(self) -> ResourceProfile:
            return ResourceProfile(
                node_class=NodeClass.STANDARD,
                total_memory_mb=8_192,
                available_memory_mb=4_096,
                process_memory_mb=128,
                cpu_count=4,
                storage_free_mb=10_000,
                network_available=True,
                power_mode="NORMAL",
            )

    class SafePlanner:
        def create_plan(self, goal: object) -> ActionPlan:
            return ActionPlan(
                plan_id="plan-private-runtime",
                goal_id="goal-private-runtime",
                steps=[
                    ActionStep(
                        step_id="step-private-runtime",
                        title="Private reasoning",
                        action_type="reason",
                        required_capability="core.reason",
                        risk_class=RiskClass.READ_ONLY,
                    )
                ],
            )

    class NetworkModel:
        model_id = "external-model-real"

        def __init__(self) -> None:
            self.calls = 0

        def is_ready(self) -> bool:
            return True

        def estimate_cost(self, request: ModelRequest) -> ModelCost:
            return ModelCost(
                estimated_memory_mb=64,
                estimated_latency_ms=10,
                requires_network=True,
            )

        def generate(self, request: ModelRequest) -> ModelResponse:
            self.calls += 1
            return ModelResponse(text="external", model_id=self.model_id)

    database = tmp_path / "runtime.db"
    prompt = "SYNTHETIC-RUNTIME-PRIVATE-PROMPT"
    privacy = SovereignPrivacy(database, _SECRET)
    runtime = JayaCoreRuntime(
        db_path=database,
        resource_profiler=StableProfiler(),  # type: ignore[arg-type]
        privacy_guard=privacy,
        privacy_required=True,
    )
    network_model = NetworkModel()
    try:
        core_reason = runtime.capability_registry.lookup("core.reason")
        assert core_reason is not None
        core_reason.health_status = "HEALTHY"
        runtime.planner = SafePlanner()  # type: ignore[assignment]
        runtime.model_router.register_model(network_model)

        response = runtime.process(
            UserRequest(
                request_id="private-runtime-request",
                raw_prompt=prompt,
                user_id=_OWNER,
            )
        )
        assert response.status == "SUCCESS"
        assert network_model.calls == 0
        assert response.metadata.get("privacy_receipt") is None
        assert privacy.status()["encrypted_records"] >= 1
        assert privacy.plaintext_absent(prompt) is True
    finally:
        runtime.close()

    assert prompt.encode() not in database.read_bytes()
