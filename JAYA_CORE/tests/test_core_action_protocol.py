"""End-to-end security tests for CORE-015 action execution evidence."""

from __future__ import annotations

import inspect
from dataclasses import replace

import pytest
from src.brain_v2.engine.action_protocol import (
    ACTION_PLAN_SCHEMA_VERSION,
    ACTION_SIGNING_KEY_ENV,
    ActionPolicy,
    ActionProtocolConfigurationError,
    ActionProtocolError,
    AuthorizationCode,
    ExecutionReceipt,
    PolicyBoundExecutor,
    ProtocolFailureCode,
    ReceiptOutcome,
)
from src.brain_v2.engine.spec_generators import IntentMatch, SpecGeneratorRouter


class MutableClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock()


@pytest.fixture
def policy(clock: MutableClock) -> ActionPolicy:
    return ActionPolicy(
        signing_secret=b"core-015-test-signing-key-material",
        environment="test",
        test_mode=True,
        clock=clock,
    )


def _route(
    policy: ActionPolicy,
    intent_type: str,
    parameters: dict | None = None,
):
    router = SpecGeneratorRouter(action_policy=policy)
    return router.route(
        IntentMatch(
            intent_type=intent_type,
            confidence=1.0,
            parameters=parameters or {},
        )
    )


def test_plan_authorize_execute_receipt_e2e(policy: ActionPolicy) -> None:
    bundle = _route(policy, "shutdown", {"reason": "maintenance"})
    plan = bundle.action_plan

    assert plan is not None
    assert plan.schema_version == ACTION_PLAN_SCHEMA_VERSION
    assert plan.status == "PLAN_ONLY"
    assert plan.signature
    assert plan.risk.name == "CRITICAL"
    assert plan.required_capabilities == ("system.power",)
    assert plan.side_effect_class.name == "DESTRUCTIVE"
    assert bundle.action_spec is not None
    assert bundle.action_spec.status == "PLAN_ONLY"
    assert bundle.execution_status == "PLAN_ONLY"

    confirmation = policy.confirm_plan(
        plan,
        actor_id="user-owner",
        confirmed=True,
    )
    decision = policy.authorize(
        plan,
        available_capabilities={"system.power"},
        confirmation=confirmation,
    )
    assert decision.authorized is True
    assert decision.code is AuthorizationCode.AUTHORIZED

    observed_actions: list[str] = []
    executor = PolicyBoundExecutor(
        policy,
        executor_id="test-executor",
        capabilities={"system.power"},
    )
    result = executor.execute(
        plan,
        decision,
        lambda step: (
            observed_actions.append(step.action) or {"observed_action": step.action}
        ),
    )

    assert observed_actions == ["shutdown_system"]
    assert result.succeeded is True
    assert result.receipt.outcome is ReceiptOutcome.SUCCEEDED
    assert result.receipt.signature
    assert bundle.execution_status == "PLAN_ONLY"

    policy.verify_receipt(
        result.receipt,
        plan=plan,
        authorization=decision,
        consume=False,
    )
    assert (
        bundle.apply_execution_receipt(
            policy=policy,
            authorization=decision,
            receipt=result.receipt,
        )
        == "EXECUTED"
    )
    assert bundle.execution_status == "EXECUTED"


def test_missing_capability_and_destructive_without_confirmation_are_denied(
    policy: ActionPolicy,
) -> None:
    bundle = _route(policy, "shutdown")
    plan = bundle.action_plan
    assert plan is not None

    missing_capability = policy.authorize(
        plan,
        available_capabilities=set(),
    )
    assert missing_capability.authorized is False
    assert missing_capability.code is AuthorizationCode.MISSING_CAPABILITY

    no_confirmation = policy.authorize(
        plan,
        available_capabilities={"system.power"},
    )
    assert no_confirmation.authorized is False
    assert no_confirmation.code is AuthorizationCode.CONFIRMATION_REQUIRED

    executor = PolicyBoundExecutor(
        policy,
        executor_id="test-executor",
        capabilities={"system.power"},
    )
    with pytest.raises(ActionProtocolError) as exc_info:
        executor.execute(plan, no_confirmation, lambda step: step.action)
    assert exc_info.value.code is ProtocolFailureCode.INVALID_AUTHORIZATION


def test_tampered_and_expired_plan_are_denied(
    policy: ActionPolicy,
    clock: MutableClock,
) -> None:
    bundle = _route(policy, "shutdown")
    plan = bundle.action_plan
    assert plan is not None

    tampered = replace(plan, risk=plan.risk - 1)
    tampered_decision = policy.authorize(
        tampered,
        available_capabilities={"system.power"},
    )
    assert tampered_decision.authorized is False
    assert tampered_decision.code is AuthorizationCode.INVALID_PLAN

    clock.now = plan.expires_at + 0.001
    expired_decision = policy.authorize(
        plan,
        available_capabilities={"system.power"},
    )
    assert expired_decision.authorized is False
    assert expired_decision.code is AuthorizationCode.EXPIRED_PLAN


def test_plan_and_authorization_replay_are_rejected(policy: ActionPolicy) -> None:
    bundle = _route(policy, "status")
    plan = bundle.action_plan
    assert plan is not None

    decision = policy.authorize(
        plan,
        available_capabilities={"observability.status.read"},
    )
    replayed_plan = policy.authorize(
        plan,
        available_capabilities={"observability.status.read"},
    )
    assert decision.authorized is True
    assert replayed_plan.code is AuthorizationCode.REPLAYED_PLAN

    executor = PolicyBoundExecutor(
        policy,
        executor_id="status-executor",
        capabilities={"observability.status.read"},
    )
    executor.execute(plan, decision, lambda step: {"action": step.action})
    with pytest.raises(ActionProtocolError) as exc_info:
        executor.execute(plan, decision, lambda step: {"action": step.action})
    assert exc_info.value.code is ProtocolFailureCode.REPLAYED_AUTHORIZATION


def test_forged_tampered_expired_and_replayed_receipt_are_rejected(
    clock: MutableClock,
) -> None:
    policy = ActionPolicy(
        signing_secret=b"core-015-receipt-signing-key-material",
        environment="test",
        test_mode=True,
        clock=clock,
        receipt_ttl_s=5.0,
        authorization_ttl_s=60.0,
    )
    bundle = _route(policy, "status")
    plan = bundle.action_plan
    assert plan is not None
    decision = policy.authorize(
        plan,
        available_capabilities={"observability.status.read"},
    )

    forged = ExecutionReceipt(
        receipt_id="receipt-forged",
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        authorization_digest=decision.decision_digest,
        executor_id="caller",
        idempotency_key=plan.idempotency_key,
        outcome=ReceiptOutcome.SUCCEEDED,
        result_digest="sha256:" + ("0" * 64),
        executed_steps=tuple(step.step_id for step in plan.ordered_steps),
        failed_step_id="",
        started_at=clock.now,
        completed_at=clock.now,
        expires_at=clock.now + 5,
        receipt_digest="sha256:" + ("1" * 64),
        signature="2" * 64,
    )
    with pytest.raises(ActionProtocolError) as forged_error:
        bundle.apply_execution_receipt(
            policy=policy,
            authorization=decision,
            receipt=forged,
        )
    assert forged_error.value.code is ProtocolFailureCode.INVALID_RECEIPT
    assert bundle.execution_status == "PLAN_ONLY"

    executor = PolicyBoundExecutor(
        policy,
        executor_id="status-executor",
        capabilities={"observability.status.read"},
    )
    result = executor.execute(plan, decision, lambda step: {"value": step.action})
    tampered = replace(result.receipt, result_digest="sha256:" + ("f" * 64))
    with pytest.raises(ActionProtocolError) as tampered_error:
        policy.verify_receipt(
            tampered,
            plan=plan,
            authorization=decision,
        )
    assert tampered_error.value.code is ProtocolFailureCode.INVALID_RECEIPT

    policy.verify_receipt(
        result.receipt,
        plan=plan,
        authorization=decision,
    )
    with pytest.raises(ActionProtocolError) as replay_error:
        policy.verify_receipt(
            result.receipt,
            plan=plan,
            authorization=decision,
        )
    assert replay_error.value.code is ProtocolFailureCode.REPLAYED_RECEIPT

    second_policy = ActionPolicy(
        signing_secret=b"core-015-receipt-signing-key-material",
        environment="test",
        test_mode=True,
        clock=clock,
        receipt_ttl_s=5.0,
        authorization_ttl_s=60.0,
    )
    clock.now += 6.0
    with pytest.raises(ActionProtocolError) as expired_error:
        second_policy.verify_receipt(
            result.receipt,
            plan=plan,
            authorization=decision,
        )
    assert expired_error.value.code is ProtocolFailureCode.EXPIRED_RECEIPT


def test_failed_handler_produces_signed_failure_not_claimed_success(
    policy: ActionPolicy,
) -> None:
    bundle = _route(policy, "status")
    plan = bundle.action_plan
    assert plan is not None
    decision = policy.authorize(
        plan,
        available_capabilities={"observability.status.read"},
    )
    executor = PolicyBoundExecutor(
        policy,
        executor_id="status-executor",
        capabilities={"observability.status.read"},
    )

    def failing_handler(_step):
        raise OSError("observed failure")

    result = executor.execute(plan, decision, failing_handler)
    assert result.succeeded is False
    assert result.receipt.outcome is ReceiptOutcome.FAILED
    assert "OSError" in result.error
    assert "success" not in inspect.signature(executor.execute).parameters
    assert (
        bundle.apply_execution_receipt(
            policy=policy,
            authorization=decision,
            receipt=result.receipt,
        )
        == "EXECUTION_FAILED"
    )


def test_unsigned_compatibility_plan_remains_plan_only_and_cannot_authorize(
    policy: ActionPolicy,
) -> None:
    bundle = SpecGeneratorRouter().route(
        IntentMatch(intent_type="status", confidence=1.0)
    )
    plan = bundle.action_plan
    assert plan is not None
    assert plan.signature == ""
    assert bundle.execution_status == "PLAN_ONLY"

    decision = policy.authorize(
        plan,
        available_capabilities={"observability.status.read"},
    )
    assert decision.authorized is False
    assert decision.code is AuthorizationCode.INVALID_PLAN


def test_production_secret_and_explicit_ephemeral_test_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ACTION_SIGNING_KEY_ENV, raising=False)
    with pytest.raises(ActionProtocolConfigurationError):
        ActionPolicy(environment="production")
    with pytest.raises(ActionProtocolConfigurationError):
        ActionPolicy(environment="development")

    ephemeral = ActionPolicy(environment="test", test_mode=True)
    assert ephemeral.status()["key_source"] == "ephemeral-test"

    monkeypatch.setenv(
        ACTION_SIGNING_KEY_ENV,
        "production-action-signing-key-material",
    )
    production = ActionPolicy(environment="production")
    assert production.status()["key_source"] == ACTION_SIGNING_KEY_ENV
    with pytest.raises(ActionProtocolConfigurationError):
        ActionPolicy(
            signing_secret=b"constructor-secret-is-not-production",
            environment="production",
        )
