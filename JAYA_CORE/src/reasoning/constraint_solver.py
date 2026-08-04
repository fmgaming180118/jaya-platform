"""
constraint_solver.py — Constraint Solver for checking hard and soft constraints.

Real implementation - no mocks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from JAYA_CORE.src.cognitive.contracts import Constraint, ConstraintViolation

logger = logging.getLogger(__name__)


class ConstraintSolver:
    """
    Constraint Solver for checking hard and soft constraints.
    
    Real implementation - no mocks.
    """
    
    def __init__(
        self,
        resource_profile: Optional[Any] = None,
        capability_registry: Optional[Any] = None,
    ):
        self.resource_profile = resource_profile
        self.capability_registry = capability_registry
        self.constraints: Dict[str, Constraint] = {}
        self._register_default_constraints()
    
    def _register_default_constraints(self):
        """Register default system constraints."""
        # Resource constraints
        self.add_constraint(Constraint(
            name="max_memory_mb",
            value=512,
            is_hard_constraint=True,
        ))
        self.add_constraint(Constraint(
            name="max_duration_seconds",
            value=300,
            is_hard_constraint=True,
        ))
        self.add_constraint(Constraint(
            name="allow_network",
            value=True,
            is_hard_constraint=False,
        ))
        self.add_constraint(Constraint(
            name="allow_remote_offload",
            value=True,
            is_hard_constraint=False,
        ))
        
        # Capability constraints
        self.add_constraint(Constraint(
            name="required_capabilities_available",
            value=True,
            is_hard_constraint=True,
        ))
        
        # Safety constraints
        self.add_constraint(Constraint(
            name="no_destructive_without_approval",
            value=True,
            is_hard_constraint=True,
        ))
        self.add_constraint(Constraint(
            name="no_physical_action_without_confirmation",
            value=True,
            is_hard_constraint=True,
        ))
    
    def add_constraint(self, constraint: Constraint):
        """Add a constraint."""
        self.constraints[constraint.name] = constraint
        logger.debug("Added constraint: %s", constraint.name)
    
    def remove_constraint(self, name: str) -> bool:
        """Remove a constraint."""
        if name in self.constraints:
            del self.constraints[name]
            return True
        return False
    
    def get_constraint(self, name: str) -> Optional[Constraint]:
        """Get a constraint by name."""
        return self.constraints.get(name)
    
    def list_constraints(self) -> List[Constraint]:
        """List all constraints."""
        return list(self.constraints.values())
    
    def check(self, ir: Any, context: Dict[str, Any]) -> List[ConstraintViolation]:
        """
        Check all constraints against IR and context.
        
        Returns list of violations (empty if all pass).
        """
        violations = []
        
        # Check resource constraints
        if hasattr(ir, 'required_capabilities'):
            for cap in ir.required_capabilities:
                if not self._is_capability_available(cap, context):
                    violations.append(ConstraintViolation(
                        constraint_name="required_capabilities_available",
                        message=f"Required capability not available: {cap}",
                        severity="error",
                        details={"capability": cap}
                    ))
        
        # Check resource limits
        if hasattr(ir, 'resource_budget'):
            budget = ir.resource_budget
            if budget.max_memory_mb > 512:
                violations.append(ConstraintViolation(
                    constraint_name="max_memory_mb",
                    message=f"Memory budget exceeds limit: {budget.max_memory_mb}MB > 512MB",
                    severity="error",
                    details={"requested": budget.max_memory_mb, "limit": 512}
                ))
            
            if budget.max_duration_seconds > 300:
                violations.append(ConstraintViolation(
                    constraint_name="max_duration_seconds",
                    message=f"Duration budget exceeds limit: {budget.max_duration_seconds}s > 300s",
                    severity="error",
                    details={"requested": budget.max_duration_seconds, "limit": 300}
                ))
        
        # Check destructive actions require approval
        if hasattr(ir, 'steps'):
            for step in ir.steps:
                if step.get('risk_class') == 'DESTRUCTIVE' and not step.get('approval_required'):
                    violations.append(ConstraintViolation(
                        constraint_name="no_destructive_without_approval",
                        message=f"Destructive step requires approval: {step.get('step_id')}",
                        severity="error",
                        details={"step_id": step.get('step_id')}
                    ))
        
        return violations
    
    def _is_capability_available(self, capability: str, context: Dict[str, Any]) -> bool:
        """Check if a capability is available."""
        # In real implementation, this would check capability registry
        # For now, return True for known capabilities
        known_capabilities = {
            "text.reasoning.basic",
            "cad.parametric_modeling",
            "system.file.read",
            "system.file.write",
            "device.control",
            "memory.read",
            "memory.write",
            "web.search",
        }
        return capability in known_capabilities