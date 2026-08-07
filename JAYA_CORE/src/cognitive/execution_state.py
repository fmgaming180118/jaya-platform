"""
execution_state.py — Manages the state and dataflow of an ActionPlan execution.
"""

from typing import Any, Dict, List, Set, Optional
from dataclasses import dataclass, field

@dataclass
class PlanExecutionState:
    """Tracks the state of a plan execution and manages dataflow between steps."""
    plan_id: str
    goal_id: str
    current_step: Optional[str] = None
    completed_steps: Set[str] = field(default_factory=set)
    failed_steps: Set[str] = field(default_factory=set)
    step_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    attempt: int = 1
    status: str = "PENDING"
    
    def record_step_success(self, step_id: str, result: Dict[str, Any]) -> None:
        """Record a successful step execution and store its outputs."""
        self.completed_steps.add(step_id)
        self.step_results[step_id] = result
        self.current_step = None
        
        # Extract and store artifacts/outputs
        if "artifacts" in result:
            for k, v in result["artifacts"].items():
                self.artifacts[f"{step_id}.{k}"] = v
                
        if "output" in result:
             self.artifacts[f"{step_id}.output"] = result["output"]
             
        self.observations.append({
            "step_id": step_id,
            "status": "SUCCESS",
            "result": result
        })

    def record_step_failure(self, step_id: str, error: str, result: Dict[str, Any]) -> None:
        """Record a failed step execution."""
        self.failed_steps.add(step_id)
        self.step_results[step_id] = result
        self.status = "FAILED"
        self.observations.append({
            "step_id": step_id,
            "status": "FAILED",
            "error": error,
            "result": result
        })

    def resolve_references(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve input references like `step-1.code_change.replacement_content` from stored artifacts.
        If a reference cannot be resolved, raises ValueError.
        """
        resolved = {}
        for key, value in inputs.items():
            if isinstance(value, str) and value.startswith("ref:"):
                ref_path = value[4:] # strip 'ref:'
                if ref_path in self.artifacts:
                    resolved[key] = self.artifacts[ref_path]
                else:
                    parts = ref_path.split('.')
                    if len(parts) >= 2:
                        base_ref = f"{parts[0]}.{parts[1]}"
                        if base_ref in self.artifacts:
                            nested_val = self.artifacts[base_ref]
                            try:
                                for p in parts[2:]:
                                    if isinstance(nested_val, dict):
                                        nested_val = nested_val[p]
                                    else:
                                        nested_val = getattr(nested_val, p)
                                resolved[key] = nested_val
                                continue
                            except (KeyError, AttributeError, TypeError):
                                pass
                    
                    raise ValueError(f"UNRESOLVED_ACTION_INPUT: Reference {ref_path} not found in artifacts.")
            else:
                resolved[key] = value
        return resolved
