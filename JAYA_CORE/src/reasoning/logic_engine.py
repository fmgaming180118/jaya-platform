"""
logic_engine.py — Logic Engine for verifying logical consistency of plans.

Real implementation - no mocks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from JAYA_CORE.src.cognitive.contracts import (
    ActionPlan,
    ActionStep,
    ActionStatus,
    RiskClass,
    ConstraintViolation,
)

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of verification."""
    passed: bool
    violations: List[ConstraintViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class LogicEngine:
    """
    Logic Engine for verifying logical consistency of plans.
    
    Real implementation - no mocks.
    """
    
    def __init__(self):
        self.rules: List[Callable[[Any], List[ConstraintViolation]]] = []
        self._register_default_rules()
    
    def _register_default_rules(self):
        """Register default logic rules."""
        # Rule: No circular dependencies
        self.rules.append(self._check_circular_dependencies)
        
        # Rule: All dependencies must exist
        self.rules.append(self._check_dependencies_exist)
        
        # Rule: Approval required steps must have approval
        self.rules.append(self._check_approval_requirements)
        
        # Rule: Risk class consistency
        self.rules.append(self._check_risk_class_consistency)
    
    def add_rule(self, rule: Callable[[Any], List[ConstraintViolation]]):
        """Add a custom logic rule."""
        self.rules.append(rule)
    
    def verify_plan(self, plan: Any) -> VerificationResult:
        """
        Verify a plan against all logic rules.
        
        Returns VerificationResult with any violations.
        """
        violations = []
        warnings = []
        
        for rule in self.rules:
            try:
                result = rule(plan)
                if isinstance(result, list):
                    violations.extend(result)
                elif result is not None:
                    violations.append(result)
            except Exception as e:
                logger.error("Logic rule failed: %s", e)
                violations.append(ConstraintViolation(
                    constraint_name="logic_rule_error",
                    message=f"Logic rule failed: {str(e)}",
                    severity="error"
                ))
        
        return VerificationResult(
            passed=len(violations) == 0,
            violations=violations,
            warnings=warnings,
        )
    
    def _check_circular_dependencies(self, plan: Any) -> List[ConstraintViolation]:
        """Check for circular dependencies in plan steps."""
        violations = []
        
        if not hasattr(plan, 'steps'):
            return violations
        
        # Build dependency graph
        graph = {}
        step_ids = set()
        
        for step in plan.steps:
            step_id = step.step_id if hasattr(step, 'step_id') else step.get('step_id')
            deps = step.dependencies if hasattr(step, 'dependencies') else step.get('dependencies', [])
            graph[step_id] = deps
            step_ids.add(step_id)
        
        # Check for cycles using DFS
        visited = set()
        rec_stack = set()
        
        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in step_ids:
                    continue
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node in step_ids:
            if node not in visited:
                if dfs(node):
                    violations.append(ConstraintViolation(
                        constraint_name="circular_dependency",
                        message="Circular dependency detected in plan steps",
                        severity="error"
                    ))
                    break
        
        return violations
    
    def _check_dependencies_exist(self, plan: Any) -> List[ConstraintViolation]:
        """Check that all dependencies reference existing steps."""
        violations = []
        
        if not hasattr(plan, 'steps'):
            return violations
        
        step_ids = {step.step_id if hasattr(step, 'step_id') else step.get('step_id') 
                   for step in plan.steps}
        
        for step in plan.steps:
            deps = step.dependencies if hasattr(step, 'dependencies') else step.get('dependencies', [])
            for dep in deps:
                if dep not in step_ids:
                    violations.append(ConstraintViolation(
                        constraint_name="missing_dependency",
                        message=f"Step {step.step_id} depends on non-existent step: {dep}",
                        severity="error",
                        details={"step": step.step_id, "missing_dep": dep}
                    ))
        
        return violations
    
    def _check_approval_requirements(self, plan: Any) -> List[ConstraintViolation]:
        """Check that destructive steps have approval_required=True."""
        violations = []
        
        if not hasattr(plan, 'steps'):
            return violations
        
        for step in plan.steps:
            risk_class = step.risk_class if hasattr(step, 'risk_class') else step.get('risk_class')
            approval = step.approval_required if hasattr(step, 'approval_required') else step.get('approval_required', False)
            
            if risk_class == 'DESTRUCTIVE' and not approval:
                violations.append(ConstraintViolation(
                    constraint_name="approval_required",
                    message=f"Destructive step requires approval: {step.step_id}",
                    severity="error",
                    details={"step_id": step.step_id}
                ))
        
        return violations
    
    def _check_risk_class_consistency(self, plan: Any) -> List[ConstraintViolation]:
        """Check risk class consistency with action types."""
        violations = []
        
        if not hasattr(plan, 'steps'):
            return violations
        
        for step in plan.steps:
            action_type = step.action_type if hasattr(step, 'action_type') else step.get('action_type')
            risk_class = step.risk_class if hasattr(step, 'risk_class') else step.get('risk_class')
            
            # Check consistency
            if action_type in ['export_model', 'delete_file', 'execute_command'] and risk_class != 'DESTRUCTIVE':
                violations.append(ConstraintViolation(
                    constraint_name="risk_class_mismatch",
                    message=f"Action {action_type} should be DESTRUCTIVE risk class",
                    severity="warning",
                    details={"step_id": step.step_id, "action_type": action_type}
                ))
        
        return violations