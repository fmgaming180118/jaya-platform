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
        
        # Check resource limits from resource profile
        max_mem = self.resource_profile.max_memory_mb if self.resource_profile else 512
        max_dur = self.resource_profile.max_duration_seconds if self.resource_profile else 300
        if hasattr(ir, 'resource_budget') and ir.resource_budget:
            budget = ir.resource_budget
            if budget.max_memory_mb > max_mem:
                violations.append(ConstraintViolation(
                    constraint_name="max_memory_mb",
                    message=f"Memory budget exceeds limit: {budget.max_memory_mb}MB > {max_mem}MB",
                    severity="error",
                    details={"requested": budget.max_memory_mb, "limit": max_mem}
                ))
            
            if budget.max_duration_seconds > max_dur:
                violations.append(ConstraintViolation(
                    constraint_name="max_duration_seconds",
                    message=f"Duration budget exceeds limit: {budget.max_duration_seconds}s > {max_dur}s",
                    severity="error",
                    details={"requested": budget.max_duration_seconds, "limit": max_dur}
                ))
        
        # Check destructive actions require approval
        if hasattr(ir, 'steps'):
            for step in ir.steps:
                risk = step.risk_class.value if hasattr(step, 'risk_class') and hasattr(step.risk_class, 'value') else step.get('risk_class')
                app_req = step.approval_required if hasattr(step, 'approval_required') else step.get('approval_required')
                s_id = step.step_id if hasattr(step, 'step_id') else step.get('step_id')
                if risk == 'DESTRUCTIVE' and not app_req:
                    violations.append(ConstraintViolation(
                        constraint_name="no_destructive_without_approval",
                        message=f"Destructive step requires approval: {s_id}",
                        severity="error",
                        details={"step_id": s_id}
                    ))
        
        return violations
    
    def _is_capability_available(self, capability: str, context: Dict[str, Any]) -> bool:
        """Check if a capability is available via CapabilityRegistry."""
        if self.capability_registry is None:
            # Fallback for when no registry was passed
            known_capabilities = {
                "core.reason",
                "cad.parametric_modeling",
                "fs.read",
                "fs.write",
                "device.control",
                "memory.read",
                "memory.write",
                "process.execute",
                "web.search",
                "fs.list",
            }
            return capability in known_capabilities

        manifest = self.capability_registry.lookup(capability)
        if manifest is None:
            logger.warning("Capability not in registry: %s", capability)
            return False
        
        if manifest.health_status != "HEALTHY":
            logger.warning("Capability not HEALTHY: %s (status: %s)", capability, manifest.health_status)
            return False
        
        max_mem = self.resource_profile.max_memory_mb if self.resource_profile else 512
        memory_available = context.get("memory_available_mb", max_mem)
        if manifest.min_memory_mb > memory_available:
            logger.warning("Capability %s requires %dMB, only %dMB available", 
                          capability, manifest.min_memory_mb, memory_available)
            return False
        
        is_online = context.get("is_online", True)
        if not is_online and not manifest.offline_available:
            logger.warning("Capability %s not available offline", capability)
            return False
        
        return True