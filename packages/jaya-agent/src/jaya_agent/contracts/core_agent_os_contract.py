"""
core_agent_os_contract.py — Typed, versioned contracts for the Core → Agent → OS boundary.

All cross-layer dispatches MUST use these typed contracts.
No direct JAYA_OS import is allowed here; the OS boundary is crossed only via
the JAYA_AGENT security adapter (capability_sandbox.py).

Ownership:
    JAYA_CORE   produces  →  CoreToAgentDispatch
    JAYA_AGENT  produces  →  AgentToolRequest
    JAYA_OS     produces  →  OsExecutionReceipt

Rules enforced by ContractValidator:
    - request_id must be non-empty string ≤ 128 chars
    - schema_version must be "1.0"
    - resource_budget must be present and within bounds
    - action must be in the OS allowlist
    - ACTIVE_CAPABILITY must not be bypassed (tool request must carry a grant_token)
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Allowed OS actions (mirrors DEFAULT_ACTION_POLICIES in capability_sandbox.py)
# ---------------------------------------------------------------------------
ALLOWED_OS_ACTIONS: frozenset[str] = frozenset(
    {
        "fs.read",
        "fs.list",
        "fs.write",
        "web.search",
        "process.execute",
        "system.status",
        "device.audio.output",
        "system.memory.optimize",
    }
)

_SCHEMA_VERSION = "1.0"
_MAX_DISPATCH_BUDGET_SECONDS = 300
_MIN_DISPATCH_BUDGET_SECONDS = 1
_MAX_REQUEST_ID_LENGTH = 128


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass
class ResourceBudgetEnvelope:
    """Lightweight resource budget for cross-layer dispatch."""

    max_duration_seconds: int = 30
    max_memory_mb: int = 512
    allow_network: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CoreToAgentDispatch:
    """
    Message emitted by JAYA Core to JAYA Agent to initiate a planned task.

    Core MUST NOT include raw credentials, OS paths, or direct capability
    grant tokens inside this contract.  The Agent is responsible for acquiring
    a capability grant from JAYA OS before executing any tool action.
    """

    request_id: str
    plan_id: str
    schema_version: str = _SCHEMA_VERSION
    goal_title: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    resource_budget: ResourceBudgetEnvelope = field(default_factory=ResourceBudgetEnvelope)
    issued_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["resource_budget"] = self.resource_budget.to_dict()
        return d


@dataclass
class AgentToolRequest:
    """
    Request from JAYA Agent to JAYA OS to execute one sandboxed tool action.

    The Agent MUST supply a valid `grant_token` obtained from
    CapabilitySandbox.issue_grant() before submitting this request.
    The Agent MUST NOT forge or modify `grant_token`.
    """

    dispatch_id: str
    step_id: str
    action: str
    resources: List[str]
    grant_token: str
    idempotency_key: str
    schema_version: str = _SCHEMA_VERSION
    inputs: Dict[str, Any] = field(default_factory=dict)
    issued_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OsExecutionReceipt:
    """
    Execution result returned by JAYA OS to JAYA Agent after a sandboxed action.

    Contains redacted evidence only — no raw secrets, paths, or user data.
    The embedded `audit_receipt` is the authoritative record of what happened.
    """

    dispatch_id: str
    step_id: str
    success: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    audit_receipt: Optional[Dict[str, Any]] = None
    replayed: bool = False
    schema_version: str = _SCHEMA_VERSION
    completed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


@dataclass
class ContractValidationResult:
    is_valid: bool
    violations: List[str] = field(default_factory=list)


class ContractValidator:
    """
    Validates typed contracts at each layer boundary.

    Designed to be called by the Agent before forwarding a dispatch to OS and
    before returning a receipt to Core.
    """

    def validate_core_to_agent(self, dispatch: CoreToAgentDispatch) -> ContractValidationResult:
        """Validate that a CoreToAgentDispatch is well-formed and within budget."""
        violations: List[str] = []

        if not dispatch.request_id or len(dispatch.request_id) > _MAX_REQUEST_ID_LENGTH:
            violations.append(
                f"request_id must be 1–{_MAX_REQUEST_ID_LENGTH} characters; "
                f"got {len(dispatch.request_id or '')!r}"
            )

        if dispatch.schema_version != _SCHEMA_VERSION:
            violations.append(
                f"schema_version must be '{_SCHEMA_VERSION}'; "
                f"got '{dispatch.schema_version}'"
            )

        budget = dispatch.resource_budget
        if not (
            _MIN_DISPATCH_BUDGET_SECONDS
            <= budget.max_duration_seconds
            <= _MAX_DISPATCH_BUDGET_SECONDS
        ):
            violations.append(
                f"resource_budget.max_duration_seconds must be "
                f"{_MIN_DISPATCH_BUDGET_SECONDS}–{_MAX_DISPATCH_BUDGET_SECONDS}; "
                f"got {budget.max_duration_seconds}"
            )
        if not (64 <= budget.max_memory_mb <= 4096):
            violations.append(
                f"resource_budget.max_memory_mb must be 64–4096; "
                f"got {budget.max_memory_mb}"
            )

        return ContractValidationResult(is_valid=len(violations) == 0, violations=violations)

    def validate_agent_tool_request(self, request: AgentToolRequest) -> ContractValidationResult:
        """Validate that an AgentToolRequest carries a valid grant_token and allowed action."""
        violations: List[str] = []

        if not request.grant_token or len(request.grant_token) < 16:
            violations.append(
                "grant_token is missing or too short; Agent MUST obtain a grant "
                "from CapabilitySandbox before issuing a tool request"
            )

        if request.action not in ALLOWED_OS_ACTIONS:
            violations.append(
                f"action '{request.action}' is not in the OS allowlist; "
                f"allowed: {sorted(ALLOWED_OS_ACTIONS)}"
            )

        if not request.idempotency_key or len(request.idempotency_key) < 12:
            violations.append(
                "idempotency_key must be at least 12 characters"
            )

        if not request.resources:
            violations.append("resources list must not be empty")

        if request.schema_version != _SCHEMA_VERSION:
            violations.append(
                f"schema_version must be '{_SCHEMA_VERSION}'; "
                f"got '{request.schema_version}'"
            )

        return ContractValidationResult(is_valid=len(violations) == 0, violations=violations)

    def validate_os_receipt(self, receipt: OsExecutionReceipt) -> ContractValidationResult:
        """Validate that an OsExecutionReceipt is structurally complete."""
        violations: List[str] = []

        if not receipt.dispatch_id:
            violations.append("dispatch_id must not be empty")

        if receipt.success and receipt.audit_receipt is None:
            violations.append(
                "audit_receipt must be present on successful executions"
            )

        if not receipt.success and not receipt.error_code:
            violations.append(
                "error_code must be present on failed executions"
            )

        if receipt.schema_version != _SCHEMA_VERSION:
            violations.append(
                f"schema_version must be '{_SCHEMA_VERSION}'; "
                f"got '{receipt.schema_version}'"
            )

        return ContractValidationResult(is_valid=len(violations) == 0, violations=violations)
