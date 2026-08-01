"""
decision.py — Decision and Permission Gate for JAYA Core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .contracts import ActionStep, RiskClass


@dataclass
class DecisionPolicyResult:
    allowed: bool
    requires_user_approval: bool
    requires_checkpoint: bool
    reason: str = ""


class DecisionGate:
    """Evaluates action steps against risk policies before execution."""

    def evaluate_step(self, step: ActionStep, is_online: bool = True) -> DecisionPolicyResult:
        if step.risk_class == RiskClass.READ_ONLY:
            return DecisionPolicyResult(
                allowed=True,
                requires_user_approval=False,
                requires_checkpoint=False,
                reason="READ_ONLY action is inherently safe",
            )

        if step.risk_class == RiskClass.REVERSIBLE:
            return DecisionPolicyResult(
                allowed=True,
                requires_user_approval=step.approval_required,
                requires_checkpoint=True,
                reason="REVERSIBLE action requires a local checkpoint",
            )

        if step.risk_class in (RiskClass.DESTRUCTIVE, RiskClass.PHYSICAL_ACTION):
            return DecisionPolicyResult(
                allowed=True,
                requires_user_approval=True,
                requires_checkpoint=True,
                reason=f"{step.risk_class.value} action requires explicit user approval",
            )

        if step.risk_class == RiskClass.SECURITY_SENSITIVE:
            return DecisionPolicyResult(
                allowed=True,
                requires_user_approval=True,
                requires_checkpoint=True,
                reason="SECURITY_SENSITIVE action requires strict approval and audit log",
            )

        if step.risk_class == RiskClass.COGNITIVE_UPDATE:
            return DecisionPolicyResult(
                allowed=False,
                requires_user_approval=True,
                requires_checkpoint=True,
                reason="COGNITIVE_UPDATE must pass through promotion gate, not direct execution",
            )

        return DecisionPolicyResult(
            allowed=False,
            requires_user_approval=True,
            requires_checkpoint=True,
            reason=f"Unknown risk class '{step.risk_class}'",
        )
