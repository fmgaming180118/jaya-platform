"""
symbolic_reasoner.py — Symbolic Reasoning Engine for JAYA Core.

This module implements the symbolic reasoning engine that performs
constraint checking, HTN planning, and logic verification.
All implementations are REAL - no mocks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from jaya_core.cognitive.contracts import (
    ActionPlan,
    ActionStep,
    ActionStatus,
    Goal,
    IntentType,
    RiskClass,
    Constraint,
    CapabilityRequirement,
    ResourceBudget,
)
from jaya_core.capabilities.registry import CapabilityRegistry

logger = logging.getLogger(__name__)


@dataclass
class ConstraintViolation(Exception):
    """Represents a constraint violation."""
    constraint_name: str
    message: str
    severity: str = "error"  # "error" or "warning"
    details: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self):
        return f"ConstraintViolation({self.constraint_name}): {self.message}"


@dataclass
class VerificationResult:
    """Result of verification."""
    passed: bool
    violations: List[ConstraintViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ResourceProfile:
    """Resource profile for constraint checking."""
    def __init__(
        self,
        max_memory_mb: int = 512,
        max_duration_seconds: int = 300,
        allow_network: bool = True,
        allow_remote_offload: bool = True,
    ):
        self.max_memory_mb = max_memory_mb
        self.max_duration_seconds = max_duration_seconds
        self.allow_network = allow_network
        self.allow_remote_offload = allow_remote_offload


from jaya_core.reasoning.constraint_solver import ConstraintSolver


class LogicEngine:
    """
    Logic Engine for verifying logical consistency of plans.
    
    Real implementation - no mocks.
    """
    
    def __init__(self):
        self.rules: List[callable] = []
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
            
            if risk_class == RiskClass.DESTRUCTIVE and not approval:
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
            if action_type in ['export_model', 'delete_file', 'execute_command'] and risk_class != RiskClass.DESTRUCTIVE:
                violations.append(ConstraintViolation(
                    constraint_name="risk_class_mismatch",
                    message=f"Action {action_type} should be DESTRUCTIVE risk class",
                    severity="warning",
                    details={"step_id": step.step_id, "action_type": action_type}
                ))
        
        return violations


class SymbolicReasoner:
    """
    Symbolic Reasoning Engine for JAYA Core.
    
    Performs:
    1. Constraint checking (via ConstraintSolver)
    2. HTN Planning (via HTNPlanner)
    3. Logic verification (via LogicEngine)
    
    Real implementation - no mocks.
    """
    
    def __init__(
        self,
        htn_planner: Any = None,
        logic_engine: LogicEngine = None,
        constraint_solver: ConstraintSolver = None,
    ):
        self.htn_planner = htn_planner
        self.logic_engine = logic_engine or LogicEngine()
        self.constraint_solver = constraint_solver or ConstraintSolver()
        
        logger.info("SymbolicReasoner initialized")
    
    def verify_ir(self, ir: Any) -> bool:
        """
        Verify Intermediate Representation (IR) against constraints.
        
        Returns True if all constraints pass, False otherwise.
        """
        violations = self.constraint_solver.check(ir, {})
        
        if violations:
            logger.warning("IR verification failed with %d violations", len(violations))
            for v in violations:
                logger.warning("  - %s: %s", v.constraint_name, v.message)
            return False
        
        logger.debug("IR verification passed")
        return True
    
    def verify_plan(self, plan: Any) -> bool:
        """
        Verify ActionPlan against logic rules.
        
        Returns True if all logic rules pass, False otherwise.
        """
        result = self.logic_engine.verify_plan(plan)
        
        if not result.passed:
            logger.warning("Plan verification failed with %d violations", len(result.violations))
            for v in result.violations:
                logger.warning("  - %s: %s", v.constraint_name, v.message)
            return False
        
        logger.debug("Plan verification passed")
        return True
    
    def reason(self, ir: Any, context: Dict[str, Any]) -> Any:
        """
        Perform full symbolic reasoning: constraint check + planning + logic verification.
        
        Returns ExecutionPlan if successful, raises exception otherwise.
        """
        # 1. Check constraints
        violations = self.constraint_solver.check(ir, context)
        if violations:
            raise ConstraintViolation(
                constraint_name="constraint_check_failed",
                message=f"Constraint check failed with {len(violations)} violations",
                details={"violations": [v.message for v in violations]}
            )
        
        # 2. Create plan using HTN planner
        if self.htn_planner and hasattr(ir, 'goal'):
            plan = self.htn_planner.create_plan(ir.goal)
        else:
            # Fallback: create basic plan from IR
            plan = self._create_basic_plan(ir)
        
        # 3. Verify plan logic
        if not self.verify_plan(plan):
            raise ConstraintViolation(
                constraint_name="logic_verification_failed",
                message="Plan logic verification failed"
            )
        
        return plan
    
    def _create_basic_plan(self, ir: Any) -> Any:
        """Create basic plan from IR when HTN planner not available."""
        from jaya_core.cognitive.contracts import ActionPlan, ActionStep, ActionStatus, RiskClass
        
        steps = []
        if hasattr(ir, 'steps'):
            for i, step_data in enumerate(ir.steps):
                steps.append(ActionStep(
                    step_id=step_data.get('step_id', f'step-{i}'),
                    title=step_data.get('title', f'Step {i+1}'),
                    action_type=step_data.get('action_type', 'process_general_request'),
                    required_capability=step_data.get('required_capability', 'core.reason'),
                    risk_class=RiskClass(step_data.get('risk_class', 'READ_ONLY')),
                    execution_target=step_data.get('execution_target', 'local'),
                    approval_required=step_data.get('approval_required', False),
                    inputs=step_data.get('inputs', {}),
                    dependencies=step_data.get('dependencies', []),
                ))
        
        from jaya_core.cognitive.contracts import ActionPlan
        return ActionPlan(
            plan_id=f"plan-{hash(str(ir)) % 10000:04d}",
            goal_id=getattr(ir, 'goal_id', 'unknown'),
            steps=steps,
            domain=getattr(ir, 'domain', 'general'),
        )
    
    def get_verification_details(self, ir: Any, plan: Any = None) -> Dict[str, Any]:
        """Get detailed verification results."""
        constraint_violations = self.constraint_solver.check(ir, {})
        logic_result = self.logic_engine.verify_plan(plan) if plan else VerificationResult(passed=True)
        
        return {
            "constraints_passed": len(constraint_violations) == 0,
            "constraint_violations": [
                {"name": v.constraint_name, "message": v.message, "severity": v.severity}
                for v in constraint_violations
            ],
            "logic_passed": logic_result.passed,
            "logic_violations": [
                {"name": v.constraint_name, "message": v.message, "severity": v.severity}
                for v in logic_result.violations
            ],
            "warnings": logic_result.warnings,
        }


def create_symbolic_reasoner(
    resource_profile: ResourceProfile = None,
    capability_registry: CapabilityRegistry = None,
) -> SymbolicReasoner:
    """Factory function to create SymbolicReasoner with default components."""
    from jaya_core.cognitive.planner import GenericHierarchicalPlanner
    
    constraint_solver = ConstraintSolver(
        resource_profile=resource_profile,
        capability_registry=capability_registry,
    )
    
    return SymbolicReasoner(
        htn_planner=GenericHierarchicalPlanner(),
        logic_engine=LogicEngine(),
        constraint_solver=constraint_solver,
    )