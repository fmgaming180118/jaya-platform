"""
contracts.py — Typed, versioned cognitive contracts for JAYA Core.

All cognitive structures passed through public boundaries MUST use these contracts.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class IntentType(str, Enum):
    ASK_INFORMATION = "ASK_INFORMATION"
    CREATE_PLAN = "CREATE_PLAN"
    EXECUTE_TASK = "EXECUTE_TASK"
    CREATE_3D_DESIGN = "CREATE_3D_DESIGN"
    WRITE_CODE = "WRITE_CODE"
    CONTROL_DEVICE = "CONTROL_DEVICE"
    MANAGE_MEMORY = "MANAGE_MEMORY"
    UNKNOWN = "UNKNOWN"


class RiskClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE = "REVERSIBLE"
    DESTRUCTIVE = "DESTRUCTIVE"
    PHYSICAL_ACTION = "PHYSICAL_ACTION"
    SECURITY_SENSITIVE = "SECURITY_SENSITIVE"
    COGNITIVE_UPDATE = "COGNITIVE_UPDATE"


class ActionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


@dataclass
class ConstraintViolation:
    """Represents a constraint violation."""
    constraint_name: str
    message: str
    severity: str = "error"  # "error" or "warning"
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserRequest:
    request_id: str
    raw_prompt: str
    user_id: str = "default_user"
    active_context: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UserRequest:
        return cls(
            request_id=str(data["request_id"]),
            raw_prompt=str(data["raw_prompt"]),
            user_id=str(data.get("user_id", "default_user")),
            active_context=dict(data.get("active_context") or {}),
            schema_version=str(data.get("schema_version", "1.0")),
        )


@dataclass
class Intent:
    intent_id: str
    intent_type: IntentType
    domain: str
    confidence: float
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    missing_context: List[str] = field(default_factory=list)
    clarification_required: bool = False
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["intent_type"] = self.intent_type.value
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Intent:
        return cls(
            intent_id=str(data["intent_id"]),
            intent_type=IntentType(data["intent_type"]),
            domain=str(data.get("domain", "general")),
            confidence=float(data.get("confidence", 1.0)),
            extracted_entities=dict(data.get("extracted_entities") or {}),
            missing_context=list(data.get("missing_context") or []),
            clarification_required=bool(data.get("clarification_required", False)),
            schema_version=str(data.get("schema_version", "1.0")),
        )


@dataclass
class Goal:
    goal_id: str
    title: str
    intent_type: IntentType
    domain: str = "general"
    constraints: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["intent_type"] = self.intent_type.value
        return res


@dataclass
class Constraint:
    name: str
    value: Any
    is_hard_constraint: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityRequirement:
    capability_id: str
    min_version: str = "1.0"
    is_optional: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActionStep:
    step_id: str
    title: str
    action_type: str
    required_capability: str
    risk_class: RiskClass = RiskClass.READ_ONLY
    execution_target: str = "local"  # "local" or "remote"
    approval_required: bool = False
    inputs: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    status: ActionStatus = ActionStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["risk_class"] = self.risk_class.value
        res["status"] = self.status.value
        return res


@dataclass
class ActionPlan:
    plan_id: str
    goal_id: str
    steps: List[ActionStep] = field(default_factory=list)
    domain: str = "general"
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "steps": [s.to_dict() for s in self.steps],
            "domain": self.domain,
            "schema_version": self.schema_version,
        }


@dataclass
class ResourceBudget:
    max_memory_mb: int = 512
    max_duration_seconds: int = 30
    allow_network: bool = True
    allow_remote_offload: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class JayaIRAction:
    step_id: str
    action: str
    capability: str
    execution_target: str
    approval_required: bool
    risk_class: str
    inputs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class JayaIRRequest:
    request_id: str
    schema_version: str
    goal: Dict[str, Any]
    constraints: Dict[str, Any]
    required_capabilities: List[str]
    steps: List[JayaIRAction] = field(default_factory=list)
    resource_budget: ResourceBudget = field(default_factory=ResourceBudget)
    approval_required_before: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "schema_version": self.schema_version,
            "goal": self.goal,
            "constraints": self.constraints,
            "required_capabilities": self.required_capabilities,
            "steps": [s.to_dict() for s in self.steps],
            "resource_budget": self.resource_budget.to_dict(),
            "approval_required_before": self.approval_required_before,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class ActionResult:
    request_id: str
    step_id: str
    status: ActionStatus
    output: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["status"] = self.status.value
        return res


@dataclass
class EvaluationResult:
    request_id: str
    is_goal_achieved: bool
    should_replan: bool
    summary: str
    next_step_id: Optional[str] = None
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
