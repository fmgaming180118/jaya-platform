"""Fail-closed action planning, authorization, and execution receipts.

The brain may create an :class:`ActionPlan`, but a plan is never evidence that
an action ran.  A policy authority must authenticate and authorize the plan,
and a policy-bound executor must observe the real handler result before a
signed :class:`ExecutionReceipt` can exist.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from enum import Enum, IntEnum
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

ACTION_PLAN_SCHEMA_VERSION = "jaya-action-plan-v1"
AUTHORIZATION_SCHEMA_VERSION = "jaya-action-authorization-v1"
CONFIRMATION_SCHEMA_VERSION = "jaya-action-confirmation-v1"
EXECUTION_RECEIPT_SCHEMA_VERSION = "jaya-execution-receipt-v1"
SIGNATURE_ALGORITHM = "HMAC-SHA256"
ACTION_SIGNING_KEY_ENV = "JAYA_ACTION_SIGNING_KEY"

_PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_CAPABILITY_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_MAX_JSON_DEPTH = 16
_MAX_JSON_ITEMS = 4096


class RiskLevel(IntEnum):
    """Minimum review level associated with an action plan."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class SideEffectClass(IntEnum):
    """Externally observable effect produced by an action."""

    NONE = 0
    READ = 1
    WRITE = 2
    DESTRUCTIVE = 3


class AuthorizationCode(str, Enum):
    """Typed result of the authorization boundary."""

    AUTHORIZED = "authorized"
    INVALID_PLAN = "invalid_plan"
    EXPIRED_PLAN = "expired_plan"
    REPLAYED_PLAN = "replayed_plan"
    UNSUPPORTED_ACTION = "unsupported_action"
    MISSING_CAPABILITY = "missing_capability"
    CONFIRMATION_REQUIRED = "confirmation_required"
    INVALID_CONFIRMATION = "invalid_confirmation"
    REPLAYED_CONFIRMATION = "replayed_confirmation"


class ProtocolFailureCode(str, Enum):
    """Typed failures raised outside the authorization-decision API."""

    CONFIGURATION = "configuration"
    INVALID_PLAN = "invalid_plan"
    EXPIRED_PLAN = "expired_plan"
    REPLAYED_PLAN = "replayed_plan"
    UNSUPPORTED_ACTION = "unsupported_action"
    MISSING_CAPABILITY = "missing_capability"
    CONFIRMATION_REQUIRED = "confirmation_required"
    INVALID_CONFIRMATION = "invalid_confirmation"
    REPLAYED_CONFIRMATION = "replayed_confirmation"
    INVALID_AUTHORIZATION = "invalid_authorization"
    EXPIRED_AUTHORIZATION = "expired_authorization"
    REPLAYED_AUTHORIZATION = "replayed_authorization"
    EXECUTION_REPLAY = "execution_replay"
    INVALID_EXECUTOR_RESULT = "invalid_executor_result"
    INVALID_RECEIPT = "invalid_receipt"
    EXPIRED_RECEIPT = "expired_receipt"
    REPLAYED_RECEIPT = "replayed_receipt"


class ReceiptOutcome(str, Enum):
    """Observed result of invoking the executor handler."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ActionProtocolError(RuntimeError):
    """Fail-closed protocol error with a stable machine-readable code."""

    def __init__(self, code: ProtocolFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class ActionProtocolConfigurationError(ActionProtocolError):
    """Raised when the action trust domain is configured unsafely."""

    def __init__(self, message: str) -> None:
        super().__init__(ProtocolFailureCode.CONFIGURATION, message)


def _require_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a valid identifier")
    return value


def _require_digest(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex>")
    return value


def _normalize_capabilities(values: Iterable[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError("capabilities must contain strings")
        capability = value.strip().lower()
        if not _CAPABILITY_RE.fullmatch(capability):
            raise ValueError(f"invalid capability: {value!r}")
        normalized.add(capability)
    return tuple(sorted(normalized))


def _freeze_json(value: Any, *, depth: int = 0, budget: list[int]) -> Any:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("JSON value exceeds maximum depth")
    budget[0] += 1
    if budget[0] > _MAX_JSON_ITEMS:
        raise ValueError("JSON value exceeds maximum item count")
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            frozen[key] = _freeze_json(item, depth=depth + 1, budget=budget)
        return MappingProxyType(dict(sorted(frozen.items())))
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, depth=depth + 1, budget=budget) for item in value
        )
    raise ValueError(f"value is not JSON-safe: {type(value).__name__}")


def _immutable_json(value: Any) -> Any:
    return _freeze_json(value, budget=[0])


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        serialized = json.dumps(
            _thaw_json(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"value is not canonical JSON: {exc}") from exc
    return serialized.encode("utf-8")


def _payload_digest(value: Mapping[str, Any]) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(value)).hexdigest()}"


def intent_digest(intent: Any) -> str:
    """Return a canonical digest without retaining raw user intent."""

    frozen = _immutable_json(intent)
    return _payload_digest({"intent": frozen})


@dataclass(frozen=True)
class ActionRequirement:
    """Trusted policy contract for one executable action."""

    required_capabilities: tuple[str, ...] = ()
    side_effect_class: SideEffectClass = SideEffectClass.NONE
    minimum_risk: RiskLevel = RiskLevel.LOW

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "required_capabilities",
            _normalize_capabilities(self.required_capabilities),
        )
        object.__setattr__(
            self,
            "side_effect_class",
            SideEffectClass(self.side_effect_class),
        )
        object.__setattr__(self, "minimum_risk", RiskLevel(self.minimum_risk))


DEFAULT_ACTION_CATALOG: Mapping[str, ActionRequirement] = MappingProxyType(
    {
        "format_result": ActionRequirement(),
        "get_config": ActionRequirement(
            ("config.read",),
            SideEffectClass.READ,
            RiskLevel.LOW,
        ),
        "get_status": ActionRequirement(
            ("observability.status.read",),
            SideEffectClass.READ,
            RiskLevel.LOW,
        ),
        "init_context": ActionRequirement(),
        "restart_system": ActionRequirement(
            ("system.power",),
            SideEffectClass.DESTRUCTIVE,
            RiskLevel.CRITICAL,
        ),
        "run_computation": ActionRequirement(
            ("compute.execute",),
            SideEffectClass.NONE,
            RiskLevel.LOW,
        ),
        "set_config": ActionRequirement(
            ("config.write",),
            SideEffectClass.WRITE,
            RiskLevel.HIGH,
        ),
        "shutdown_system": ActionRequirement(
            ("system.power",),
            SideEffectClass.DESTRUCTIVE,
            RiskLevel.CRITICAL,
        ),
    }
)


@dataclass(frozen=True)
class ActionStep:
    """One ordered, declarative action. It carries no execution claim."""

    step_id: str
    action: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    required_capabilities: tuple[str, ...] = ()
    side_effect_class: SideEffectClass = SideEffectClass.NONE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "step_id",
            _require_identifier(self.step_id, "step_id"),
        )
        object.__setattr__(self, "action", _require_identifier(self.action, "action"))
        object.__setattr__(
            self,
            "parameters",
            _immutable_json(dict(self.parameters)),
        )
        object.__setattr__(
            self,
            "required_capabilities",
            _normalize_capabilities(self.required_capabilities),
        )
        object.__setattr__(
            self,
            "side_effect_class",
            SideEffectClass(self.side_effect_class),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "parameters": _thaw_json(self.parameters),
            "required_capabilities": list(self.required_capabilities),
            "side_effect_class": self.side_effect_class.name.lower(),
        }


@dataclass(frozen=True)
class ActionPlan:
    """Versioned plan emitted by reasoning and authenticated by policy."""

    plan_id: str
    intent_digest: str
    ordered_steps: tuple[ActionStep, ...]
    risk: RiskLevel
    required_capabilities: tuple[str, ...]
    side_effect_class: SideEffectClass
    idempotency_key: str
    issued_at: float
    expires_at: float
    schema_version: str = ACTION_PLAN_SCHEMA_VERSION
    signature_algorithm: str = SIGNATURE_ALGORITHM
    plan_digest: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != ACTION_PLAN_SCHEMA_VERSION:
            raise ValueError("unsupported action plan schema")
        if self.signature_algorithm != SIGNATURE_ALGORITHM:
            raise ValueError("unsupported action plan signature algorithm")
        object.__setattr__(
            self, "plan_id", _require_identifier(self.plan_id, "plan_id")
        )
        object.__setattr__(
            self,
            "intent_digest",
            _require_digest(self.intent_digest, "intent_digest"),
        )
        steps = tuple(self.ordered_steps)
        if not steps or not all(isinstance(step, ActionStep) for step in steps):
            raise ValueError("ordered_steps must contain ActionStep values")
        step_ids = [step.step_id for step in steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("ordered_steps must use unique step_id values")
        object.__setattr__(self, "ordered_steps", steps)
        object.__setattr__(self, "risk", RiskLevel(self.risk))
        object.__setattr__(
            self,
            "required_capabilities",
            _normalize_capabilities(self.required_capabilities),
        )
        object.__setattr__(
            self,
            "side_effect_class",
            SideEffectClass(self.side_effect_class),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _require_identifier(self.idempotency_key, "idempotency_key"),
        )
        issued_at = float(self.issued_at)
        expires_at = float(self.expires_at)
        if not math.isfinite(issued_at) or not math.isfinite(expires_at):
            raise ValueError("plan timestamps must be finite")
        if expires_at <= issued_at:
            raise ValueError("plan expiry must be after issued_at")
        object.__setattr__(self, "issued_at", issued_at)
        object.__setattr__(self, "expires_at", expires_at)
        if self.plan_digest:
            _require_digest(self.plan_digest, "plan_digest")
        if self.signature and not re.fullmatch(r"[0-9a-f]{64}", self.signature):
            raise ValueError("plan signature must be 64 lowercase hex characters")

    @property
    def status(self) -> str:
        """A plan alone can only truthfully report PLAN_ONLY."""

        return "PLAN_ONLY"

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "signature_algorithm": self.signature_algorithm,
            "plan_id": self.plan_id,
            "intent_digest": self.intent_digest,
            "ordered_steps": [step.to_dict() for step in self.ordered_steps],
            "risk": self.risk.name.lower(),
            "required_capabilities": list(self.required_capabilities),
            "side_effect_class": self.side_effect_class.name.lower(),
            "idempotency_key": self.idempotency_key,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.unsigned_payload(),
            "plan_digest": self.plan_digest,
            "signature": self.signature,
            "status": self.status,
        }


@dataclass(frozen=True)
class ConfirmationGrant:
    """Signed proof that a specific destructive plan was confirmed."""

    plan_id: str
    plan_digest: str
    actor_id: str
    issued_at: float
    expires_at: float
    schema_version: str = CONFIRMATION_SCHEMA_VERSION
    signature_algorithm: str = SIGNATURE_ALGORITHM
    confirmation_digest: str = ""
    signature: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "signature_algorithm": self.signature_algorithm,
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "actor_id": self.actor_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.payload(),
            "confirmation_digest": self.confirmation_digest,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class AuthorizationDecision:
    """Authenticated policy decision bound to exactly one ActionPlan."""

    decision_id: str
    plan_id: str
    plan_digest: str
    authorized: bool
    code: AuthorizationCode
    reason: str
    granted_capabilities: tuple[str, ...]
    confirmation_digest: str
    issued_at: float
    expires_at: float
    schema_version: str = AUTHORIZATION_SCHEMA_VERSION
    signature_algorithm: str = SIGNATURE_ALGORITHM
    decision_digest: str = ""
    signature: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "signature_algorithm": self.signature_algorithm,
            "decision_id": self.decision_id,
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "authorized": self.authorized,
            "code": self.code.value,
            "reason": self.reason,
            "granted_capabilities": list(self.granted_capabilities),
            "confirmation_digest": self.confirmation_digest,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.payload(),
            "decision_digest": self.decision_digest,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class ExecutionReceipt:
    """Signed evidence created only after the executor invokes real work."""

    receipt_id: str
    plan_id: str
    plan_digest: str
    authorization_digest: str
    executor_id: str
    idempotency_key: str
    outcome: ReceiptOutcome
    result_digest: str
    executed_steps: tuple[str, ...]
    failed_step_id: str
    started_at: float
    completed_at: float
    expires_at: float
    schema_version: str = EXECUTION_RECEIPT_SCHEMA_VERSION
    signature_algorithm: str = SIGNATURE_ALGORITHM
    receipt_digest: str = ""
    signature: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "signature_algorithm": self.signature_algorithm,
            "receipt_id": self.receipt_id,
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "authorization_digest": self.authorization_digest,
            "executor_id": self.executor_id,
            "idempotency_key": self.idempotency_key,
            "outcome": self.outcome.value,
            "result_digest": self.result_digest,
            "executed_steps": list(self.executed_steps),
            "failed_step_id": self.failed_step_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "expires_at": self.expires_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.payload(),
            "receipt_digest": self.receipt_digest,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class ExecutionResult:
    """Executor return value; only its receipt is durable execution evidence."""

    receipt: ExecutionReceipt
    step_results: tuple[Any, ...]
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return self.receipt.outcome is ReceiptOutcome.SUCCEEDED


def build_action_plan(
    *,
    intent: Any,
    ordered_steps: Sequence[ActionStep],
    risk: RiskLevel,
    required_capabilities: Iterable[str],
    side_effect_class: SideEffectClass,
    ttl_s: float = 300.0,
    clock: Callable[[], float] = time.time,
    plan_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> ActionPlan:
    """Build an immutable draft. It remains unauthorized until policy seals it."""

    ttl = float(ttl_s)
    if not math.isfinite(ttl) or ttl <= 0:
        raise ValueError("ttl_s must be a positive finite number")
    issued_at = float(clock())
    draft = ActionPlan(
        plan_id=plan_id or f"plan-{uuid.uuid4().hex}",
        intent_digest=intent_digest(intent),
        ordered_steps=tuple(ordered_steps),
        risk=RiskLevel(risk),
        required_capabilities=tuple(required_capabilities),
        side_effect_class=SideEffectClass(side_effect_class),
        idempotency_key=idempotency_key or f"idem-{uuid.uuid4().hex}",
        issued_at=issued_at,
        expires_at=issued_at + ttl,
    )
    return replace(draft, plan_digest=_payload_digest(draft.unsigned_payload()))


class ActionPolicy:
    """Policy trust boundary for plan, confirmation, and receipt signatures."""

    def __init__(
        self,
        signing_secret: Optional[str | bytes] = None,
        *,
        environment: Optional[str] = None,
        test_mode: bool = False,
        clock: Callable[[], float] = time.time,
        authorization_ttl_s: float = 120.0,
        confirmation_ttl_s: float = 120.0,
        receipt_ttl_s: float = 300.0,
        action_catalog: Optional[Mapping[str, ActionRequirement]] = None,
    ) -> None:
        self._environment = (
            (
                environment
                or os.getenv("JAYA_ENVIRONMENT")
                or os.getenv("JAYA_ENV")
                or "development"
            )
            .strip()
            .lower()
        )
        self._production = self._environment in _PRODUCTION_ENVIRONMENTS
        self._test_mode = bool(test_mode)
        if self._production and self._test_mode:
            raise ActionProtocolConfigurationError(
                "test_mode cannot be enabled in production"
            )

        env_secret = os.getenv(ACTION_SIGNING_KEY_ENV)
        if self._production:
            if signing_secret not in (None, "", b""):
                raise ActionProtocolConfigurationError(
                    f"production signing secret must come from {ACTION_SIGNING_KEY_ENV}"
                )
            configured: Optional[str | bytes] = env_secret
            self._key_source = ACTION_SIGNING_KEY_ENV
        elif signing_secret not in (None, "", b""):
            configured = signing_secret
            self._key_source = "constructor"
        elif env_secret:
            configured = env_secret
            self._key_source = ACTION_SIGNING_KEY_ENV
        elif self._test_mode:
            configured = secrets.token_bytes(32)
            self._key_source = "ephemeral-test"
        else:
            raise ActionProtocolConfigurationError(
                f"{ACTION_SIGNING_KEY_ENV} or an explicit signing secret is required; "
                "ephemeral keys require test_mode=True"
            )

        secret = (
            configured
            if isinstance(configured, bytes)
            else str(configured).encode("utf-8")
        )
        if len(secret) < 32:
            raise ActionProtocolConfigurationError(
                f"{ACTION_SIGNING_KEY_ENV} must contain at least 32 bytes"
            )
        self._signing_secret = secret
        self._clock = clock
        self._authorization_ttl_s = self._positive_ttl(
            authorization_ttl_s,
            "authorization_ttl_s",
        )
        self._confirmation_ttl_s = self._positive_ttl(
            confirmation_ttl_s,
            "confirmation_ttl_s",
        )
        self._receipt_ttl_s = self._positive_ttl(receipt_ttl_s, "receipt_ttl_s")
        raw_catalog = action_catalog or DEFAULT_ACTION_CATALOG
        self._action_catalog = {
            _require_identifier(action, "catalog action"): requirement
            if isinstance(requirement, ActionRequirement)
            else ActionRequirement(**dict(requirement))
            for action, requirement in raw_catalog.items()
        }
        self._lock = threading.RLock()
        self._authorized_plans: set[str] = set()
        self._consumed_confirmations: set[str] = set()
        self._consumed_authorizations: set[str] = set()
        self._executed_idempotency_keys: set[str] = set()
        self._consumed_receipts: set[str] = set()

    @staticmethod
    def _positive_ttl(value: float, field_name: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed) or parsed <= 0:
            raise ActionProtocolConfigurationError(
                f"{field_name} must be a positive finite number"
            )
        return parsed

    def status(self) -> dict[str, Any]:
        return {
            "schema_version": ACTION_PLAN_SCHEMA_VERSION,
            "environment": self._environment,
            "key_source": self._key_source,
            "production": self._production,
            "test_mode": self._test_mode,
            "catalog_actions": tuple(sorted(self._action_catalog)),
        }

    def _sign(self, domain: str, payload: Mapping[str, Any]) -> str:
        message = domain.encode("ascii") + b"\0" + _canonical_json(payload)
        return hmac.new(self._signing_secret, message, hashlib.sha256).hexdigest()

    def _verify_signed(
        self,
        *,
        domain: str,
        payload: Mapping[str, Any],
        digest: str,
        signature: str,
    ) -> bool:
        try:
            expected_digest = _payload_digest(payload)
        except ValueError:
            return False
        return hmac.compare_digest(expected_digest, digest) and hmac.compare_digest(
            self._sign(domain, {**dict(payload), "digest": digest}),
            signature,
        )

    def seal_plan(self, plan: ActionPlan) -> ActionPlan:
        """Authenticate a planner draft after validating trusted action contracts."""

        if not isinstance(plan, ActionPlan):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_PLAN,
                "plan must be an ActionPlan",
            )
        expected_digest = _payload_digest(plan.unsigned_payload())
        if plan.plan_digest and not hmac.compare_digest(
            expected_digest,
            plan.plan_digest,
        ):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_PLAN,
                "plan digest mismatch before sealing",
            )
        if plan.signature:
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_PLAN,
                "an already signed plan cannot be resealed",
            )
        self._validate_plan_semantics(plan)
        signature = self._sign(
            "action-plan",
            {**plan.unsigned_payload(), "digest": expected_digest},
        )
        return replace(plan, plan_digest=expected_digest, signature=signature)

    def create_plan(self, **kwargs: Any) -> ActionPlan:
        """Build and seal a plan inside this policy trust domain."""

        kwargs.setdefault("clock", self._clock)
        return self.seal_plan(build_action_plan(**kwargs))

    def _validate_plan_semantics(self, plan: ActionPlan) -> None:
        capabilities: set[str] = set()
        effective_side_effect = SideEffectClass.NONE
        minimum_risk = RiskLevel.LOW
        for step in plan.ordered_steps:
            requirement = self._action_catalog.get(step.action)
            if requirement is None:
                raise ActionProtocolError(
                    ProtocolFailureCode.UNSUPPORTED_ACTION,
                    f"action is not registered by policy: {step.action}",
                )
            if step.required_capabilities != requirement.required_capabilities:
                raise ActionProtocolError(
                    ProtocolFailureCode.INVALID_PLAN,
                    f"step capability contract mismatch: {step.step_id}",
                )
            if step.side_effect_class is not requirement.side_effect_class:
                raise ActionProtocolError(
                    ProtocolFailureCode.INVALID_PLAN,
                    f"step side-effect contract mismatch: {step.step_id}",
                )
            capabilities.update(requirement.required_capabilities)
            effective_side_effect = max(
                effective_side_effect,
                requirement.side_effect_class,
            )
            minimum_risk = max(minimum_risk, requirement.minimum_risk)
        if plan.required_capabilities != tuple(sorted(capabilities)):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_PLAN,
                "plan capability set does not match its ordered steps",
            )
        if plan.side_effect_class is not effective_side_effect:
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_PLAN,
                "plan side-effect class does not match its ordered steps",
            )
        if plan.risk < minimum_risk:
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_PLAN,
                "plan risk is below the policy minimum",
            )

    def verify_plan(
        self,
        plan: ActionPlan,
        *,
        check_expiry: bool = True,
    ) -> None:
        """Verify structure, policy semantics, signature, and expiry."""

        if not isinstance(plan, ActionPlan):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_PLAN,
                "plan must be an ActionPlan",
            )
        try:
            valid_signature = self._verify_signed(
                domain="action-plan",
                payload=plan.unsigned_payload(),
                digest=plan.plan_digest,
                signature=plan.signature,
            )
        except (TypeError, ValueError):
            valid_signature = False
        if not valid_signature:
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_PLAN,
                "plan digest or signature mismatch",
            )
        self._validate_plan_semantics(plan)
        now = float(self._clock())
        if plan.issued_at > now + 5.0:
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_PLAN,
                "action plan issued_at is in the future",
            )
        if check_expiry and now >= plan.expires_at:
            raise ActionProtocolError(
                ProtocolFailureCode.EXPIRED_PLAN,
                "action plan expired",
            )

    def confirm_plan(
        self,
        plan: ActionPlan,
        *,
        actor_id: str,
        confirmed: bool,
    ) -> ConfirmationGrant:
        """Create proof of an explicit confirmation-boundary decision."""

        self.verify_plan(plan)
        if confirmed is not True:
            raise ActionProtocolError(
                ProtocolFailureCode.CONFIRMATION_REQUIRED,
                "explicit confirmation was not granted",
            )
        actor = _require_identifier(actor_id, "actor_id")
        now = float(self._clock())
        grant = ConfirmationGrant(
            plan_id=plan.plan_id,
            plan_digest=plan.plan_digest,
            actor_id=actor,
            issued_at=now,
            expires_at=min(plan.expires_at, now + self._confirmation_ttl_s),
        )
        digest = _payload_digest(grant.payload())
        return replace(
            grant,
            confirmation_digest=digest,
            signature=self._sign(
                "action-confirmation",
                {**grant.payload(), "digest": digest},
            ),
        )

    def _verify_confirmation(
        self,
        confirmation: ConfirmationGrant,
        plan: ActionPlan,
    ) -> None:
        if not isinstance(confirmation, ConfirmationGrant):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_CONFIRMATION,
                "destructive action requires a signed confirmation grant",
            )
        try:
            valid = self._verify_signed(
                domain="action-confirmation",
                payload=confirmation.payload(),
                digest=confirmation.confirmation_digest,
                signature=confirmation.signature,
            )
        except (AttributeError, TypeError, ValueError):
            valid = False
        if (
            not valid
            or confirmation.plan_id != plan.plan_id
            or confirmation.plan_digest != plan.plan_digest
        ):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_CONFIRMATION,
                "confirmation is invalid or bound to another plan",
            )
        if float(self._clock()) >= confirmation.expires_at:
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_CONFIRMATION,
                "confirmation expired",
            )
        if confirmation.confirmation_digest in self._consumed_confirmations:
            raise ActionProtocolError(
                ProtocolFailureCode.REPLAYED_CONFIRMATION,
                "confirmation was already consumed",
            )

    @staticmethod
    def _authorization_code(error: ActionProtocolError) -> AuthorizationCode:
        mapping = {
            ProtocolFailureCode.INVALID_PLAN: AuthorizationCode.INVALID_PLAN,
            ProtocolFailureCode.EXPIRED_PLAN: AuthorizationCode.EXPIRED_PLAN,
            ProtocolFailureCode.REPLAYED_PLAN: AuthorizationCode.REPLAYED_PLAN,
            ProtocolFailureCode.UNSUPPORTED_ACTION: (
                AuthorizationCode.UNSUPPORTED_ACTION
            ),
            ProtocolFailureCode.MISSING_CAPABILITY: (
                AuthorizationCode.MISSING_CAPABILITY
            ),
            ProtocolFailureCode.CONFIRMATION_REQUIRED: (
                AuthorizationCode.CONFIRMATION_REQUIRED
            ),
            ProtocolFailureCode.INVALID_CONFIRMATION: (
                AuthorizationCode.INVALID_CONFIRMATION
            ),
            ProtocolFailureCode.REPLAYED_CONFIRMATION: (
                AuthorizationCode.REPLAYED_CONFIRMATION
            ),
        }
        return mapping.get(error.code, AuthorizationCode.INVALID_PLAN)

    def _decision(
        self,
        *,
        plan: ActionPlan,
        authorized: bool,
        code: AuthorizationCode,
        reason: str,
        capabilities: tuple[str, ...],
        confirmation_digest: str = "",
    ) -> AuthorizationDecision:
        now = float(self._clock())
        decision = AuthorizationDecision(
            decision_id=f"auth-{uuid.uuid4().hex}",
            plan_id=plan.plan_id,
            plan_digest=plan.plan_digest,
            authorized=authorized,
            code=code,
            reason=reason,
            granted_capabilities=capabilities,
            confirmation_digest=confirmation_digest,
            issued_at=now,
            expires_at=min(plan.expires_at, now + self._authorization_ttl_s),
        )
        digest = _payload_digest(decision.payload())
        return replace(
            decision,
            decision_digest=digest,
            signature=self._sign(
                "action-authorization",
                {**decision.payload(), "digest": digest},
            ),
        )

    def authorize(
        self,
        plan: ActionPlan,
        *,
        available_capabilities: Iterable[str],
        confirmation: Optional[ConfirmationGrant] = None,
    ) -> AuthorizationDecision:
        """Evaluate capabilities and confirmation, consuming only approvals."""

        try:
            capabilities = _normalize_capabilities(available_capabilities)
        except ValueError as exc:
            capabilities = ()
            error = ActionProtocolError(
                ProtocolFailureCode.MISSING_CAPABILITY,
                str(exc),
            )
            return self._decision(
                plan=plan,
                authorized=False,
                code=self._authorization_code(error),
                reason=str(error),
                capabilities=capabilities,
            )

        try:
            self.verify_plan(plan)
            with self._lock:
                if plan.plan_digest in self._authorized_plans:
                    raise ActionProtocolError(
                        ProtocolFailureCode.REPLAYED_PLAN,
                        "action plan was already authorized",
                    )
                missing = sorted(
                    set(plan.required_capabilities).difference(capabilities)
                )
                if missing:
                    raise ActionProtocolError(
                        ProtocolFailureCode.MISSING_CAPABILITY,
                        f"missing capabilities: {', '.join(missing)}",
                    )
                confirmation_digest = ""
                if plan.side_effect_class is SideEffectClass.DESTRUCTIVE:
                    if confirmation is None:
                        raise ActionProtocolError(
                            ProtocolFailureCode.CONFIRMATION_REQUIRED,
                            "destructive action requires explicit confirmation",
                        )
                    self._verify_confirmation(confirmation, plan)
                    confirmation_digest = confirmation.confirmation_digest

                decision = self._decision(
                    plan=plan,
                    authorized=True,
                    code=AuthorizationCode.AUTHORIZED,
                    reason="authorized by policy",
                    capabilities=capabilities,
                    confirmation_digest=confirmation_digest,
                )
                self._authorized_plans.add(plan.plan_digest)
                if confirmation_digest:
                    self._consumed_confirmations.add(confirmation_digest)
                return decision
        except ActionProtocolError as exc:
            return self._decision(
                plan=plan,
                authorized=False,
                code=self._authorization_code(exc),
                reason=str(exc),
                capabilities=capabilities,
            )

    def verify_authorization(
        self,
        decision: AuthorizationDecision,
        plan: ActionPlan,
        *,
        check_expiry: bool = True,
    ) -> None:
        """Validate a signed authorization without consuming it."""

        self.verify_plan(plan, check_expiry=check_expiry)
        if not isinstance(decision, AuthorizationDecision):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_AUTHORIZATION,
                "authorization must be an AuthorizationDecision",
            )
        try:
            valid = self._verify_signed(
                domain="action-authorization",
                payload=decision.payload(),
                digest=decision.decision_digest,
                signature=decision.signature,
            )
        except (AttributeError, TypeError, ValueError):
            valid = False
        if (
            not valid
            or decision.plan_id != plan.plan_id
            or decision.plan_digest != plan.plan_digest
            or not decision.authorized
            or decision.code is not AuthorizationCode.AUTHORIZED
        ):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_AUTHORIZATION,
                "authorization is invalid, denied, tampered, or plan-mismatched",
            )
        now = float(self._clock())
        if decision.issued_at > now + 5.0:
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_AUTHORIZATION,
                "authorization issued_at is in the future",
            )
        if check_expiry and now >= decision.expires_at:
            raise ActionProtocolError(
                ProtocolFailureCode.EXPIRED_AUTHORIZATION,
                "authorization expired",
            )
        missing = set(plan.required_capabilities).difference(
            decision.granted_capabilities
        )
        if missing:
            raise ActionProtocolError(
                ProtocolFailureCode.MISSING_CAPABILITY,
                f"authorization is missing capabilities: {', '.join(sorted(missing))}",
            )
        if (
            plan.side_effect_class is SideEffectClass.DESTRUCTIVE
            and not decision.confirmation_digest
        ):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_AUTHORIZATION,
                "destructive authorization lacks confirmation evidence",
            )

    def reserve_execution(
        self,
        decision: AuthorizationDecision,
        plan: ActionPlan,
    ) -> None:
        """Atomically consume an authorization and idempotency key."""

        self.verify_authorization(decision, plan)
        with self._lock:
            if decision.decision_digest in self._consumed_authorizations:
                raise ActionProtocolError(
                    ProtocolFailureCode.REPLAYED_AUTHORIZATION,
                    "authorization was already consumed",
                )
            if plan.idempotency_key in self._executed_idempotency_keys:
                raise ActionProtocolError(
                    ProtocolFailureCode.EXECUTION_REPLAY,
                    "idempotency key was already executed",
                )
            self._consumed_authorizations.add(decision.decision_digest)
            self._executed_idempotency_keys.add(plan.idempotency_key)

    def _create_execution_receipt(
        self,
        *,
        plan: ActionPlan,
        decision: AuthorizationDecision,
        executor_id: str,
        outcome: ReceiptOutcome,
        result_payload: Mapping[str, Any],
        executed_steps: tuple[str, ...],
        failed_step_id: str,
        started_at: float,
        completed_at: float,
    ) -> ExecutionReceipt:
        """Internal factory used only by PolicyBoundExecutor after invocation."""

        result_hash = _payload_digest(result_payload)
        receipt = ExecutionReceipt(
            receipt_id=f"receipt-{uuid.uuid4().hex}",
            plan_id=plan.plan_id,
            plan_digest=plan.plan_digest,
            authorization_digest=decision.decision_digest,
            executor_id=_require_identifier(executor_id, "executor_id"),
            idempotency_key=plan.idempotency_key,
            outcome=outcome,
            result_digest=result_hash,
            executed_steps=executed_steps,
            failed_step_id=failed_step_id,
            started_at=started_at,
            completed_at=completed_at,
            expires_at=completed_at + self._receipt_ttl_s,
        )
        digest = _payload_digest(receipt.payload())
        return replace(
            receipt,
            receipt_digest=digest,
            signature=self._sign(
                "execution-receipt",
                {**receipt.payload(), "digest": digest},
            ),
        )

    def verify_receipt(
        self,
        receipt: ExecutionReceipt,
        *,
        plan: ActionPlan,
        authorization: AuthorizationDecision,
        consume: bool = True,
    ) -> None:
        """Verify execution evidence and reject replay by default."""

        if not isinstance(receipt, ExecutionReceipt):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_RECEIPT,
                "receipt must be an ExecutionReceipt",
            )
        self.verify_authorization(
            authorization,
            plan,
            check_expiry=False,
        )
        try:
            valid = self._verify_signed(
                domain="execution-receipt",
                payload=receipt.payload(),
                digest=receipt.receipt_digest,
                signature=receipt.signature,
            )
        except (AttributeError, TypeError, ValueError):
            valid = False
        expected_steps = tuple(step.step_id for step in plan.ordered_steps)
        completed_prefix = expected_steps[: len(receipt.executed_steps)]
        failed_is_valid = (
            receipt.outcome is ReceiptOutcome.SUCCEEDED
            and not receipt.failed_step_id
            and receipt.executed_steps == expected_steps
        ) or (
            receipt.outcome is ReceiptOutcome.FAILED
            and bool(receipt.failed_step_id)
            and receipt.executed_steps == completed_prefix
            and receipt.failed_step_id in expected_steps
            and expected_steps.index(receipt.failed_step_id)
            == len(receipt.executed_steps)
        )
        if (
            not valid
            or receipt.plan_id != plan.plan_id
            or receipt.plan_digest != plan.plan_digest
            or receipt.authorization_digest != authorization.decision_digest
            or receipt.idempotency_key != plan.idempotency_key
            or not failed_is_valid
        ):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_RECEIPT,
                "receipt is invalid, tampered, or not bound to this execution",
            )
        now = float(self._clock())
        if now >= receipt.expires_at:
            raise ActionProtocolError(
                ProtocolFailureCode.EXPIRED_RECEIPT,
                "execution receipt expired",
            )
        if (
            receipt.started_at > min(plan.expires_at, authorization.expires_at)
            or receipt.completed_at < receipt.started_at
            or receipt.started_at > now + 5.0
        ):
            raise ActionProtocolError(
                ProtocolFailureCode.INVALID_RECEIPT,
                "receipt timestamps are invalid",
            )
        if consume:
            with self._lock:
                if receipt.receipt_digest in self._consumed_receipts:
                    raise ActionProtocolError(
                        ProtocolFailureCode.REPLAYED_RECEIPT,
                        "execution receipt was already consumed",
                    )
                self._consumed_receipts.add(receipt.receipt_digest)


class PolicyBoundExecutor:
    """Executor that obtains receipts from policy only after invoking handlers."""

    def __init__(
        self,
        policy: ActionPolicy,
        *,
        executor_id: str,
        capabilities: Iterable[str],
    ) -> None:
        if not isinstance(policy, ActionPolicy):
            raise TypeError("policy must be an ActionPolicy")
        self._policy = policy
        self.executor_id = _require_identifier(executor_id, "executor_id")
        self.capabilities = _normalize_capabilities(capabilities)

    def execute(
        self,
        plan: ActionPlan,
        authorization: AuthorizationDecision,
        handler: Callable[[ActionStep], Any],
    ) -> ExecutionResult:
        """Invoke every ordered step and sign the observed result.

        No ``success`` argument exists: caller assertions cannot mint evidence.
        A normal handler return is observed success; an exception is observed
        failure.  In either case the authorization is consumed exactly once.
        """

        if not callable(handler):
            raise TypeError("handler must be callable")
        missing = set(plan.required_capabilities).difference(self.capabilities)
        if missing:
            raise ActionProtocolError(
                ProtocolFailureCode.MISSING_CAPABILITY,
                f"executor is missing capabilities: {', '.join(sorted(missing))}",
            )
        self._policy.reserve_execution(authorization, plan)

        started_at = float(self._policy._clock())
        executed_steps: list[str] = []
        step_results: list[Any] = []
        result_payload: dict[str, Any]
        outcome = ReceiptOutcome.SUCCEEDED
        failed_step_id = ""
        error = ""
        for step in plan.ordered_steps:
            try:
                result = handler(step)
                frozen_result = _immutable_json(result)
            except Exception as exc:
                outcome = ReceiptOutcome.FAILED
                failed_step_id = step.step_id
                error = f"{type(exc).__name__}: {exc}"
                result_payload = {
                    "outcome": outcome.value,
                    "executed_steps": list(executed_steps),
                    "failed_step_id": failed_step_id,
                    "error_type": type(exc).__name__,
                    "error_digest": _payload_digest({"message": str(exc)}),
                }
                break
            executed_steps.append(step.step_id)
            step_results.append(frozen_result)
        else:
            result_payload = {
                "outcome": outcome.value,
                "steps": [
                    {
                        "step_id": step_id,
                        "result": result,
                    }
                    for step_id, result in zip(
                        executed_steps,
                        step_results,
                        strict=True,
                    )
                ],
            }

        completed_at = float(self._policy._clock())
        receipt = self._policy._create_execution_receipt(
            plan=plan,
            decision=authorization,
            executor_id=self.executor_id,
            outcome=outcome,
            result_payload=result_payload,
            executed_steps=tuple(executed_steps),
            failed_step_id=failed_step_id,
            started_at=started_at,
            completed_at=completed_at,
        )
        return ExecutionResult(
            receipt=receipt,
            step_results=tuple(step_results),
            error=error,
        )
