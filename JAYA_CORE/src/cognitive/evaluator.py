"""
evaluator.py — Evaluates goal progress and triggers replanning if necessary.
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class EvaluationStatus(Enum):
    ACHIEVED = "ACHIEVED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"

class EvaluationResult:
    def __init__(
        self,
        status: EvaluationStatus,
        confidence: float,
        reasoning: str,
        remaining_tasks: Optional[List[str]] = None
    ):
        self.status = status
        self.confidence = confidence
        self.reasoning = reasoning
        self.remaining_tasks = remaining_tasks or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "remaining_tasks": self.remaining_tasks
        }

class GoalEvaluator:
    """Evaluates whether a goal has been achieved based on observations."""
    
    def __init__(self):
        # In a real implementation, this would connect to an LLM
        pass
        
    def evaluate_goal_progress(
        self, 
        goal: Any, 
        observations: List[Dict[str, Any]], 
        plan: Any
    ) -> EvaluationResult:
        """
        Evaluate goal progress based on the execution history.
        """
        logger.info("Evaluating progress for goal: %s", getattr(goal, "title", "Unknown"))
        
        # Simple heuristic evaluation (to be replaced by LLM)
        failed_steps = [obs for obs in observations if not obs.get("ok", False)]
        successful_steps = [obs for obs in observations if obs.get("ok", False)]
        
        if failed_steps:
            logger.info("Evaluation: FAILED (%d failed steps)", len(failed_steps))
            return EvaluationResult(
                status=EvaluationStatus.FAILED,
                confidence=0.9,
                reasoning=f"Failed steps detected: {', '.join([s.get('action_type', 'unknown') for s in failed_steps])}",
                remaining_tasks=[] # The planner will need to figure out how to recover
            )
            
        if successful_steps and len(successful_steps) >= len(getattr(plan, "steps", [])):
            logger.info("Evaluation: ACHIEVED")
            return EvaluationResult(
                status=EvaluationStatus.ACHIEVED,
                confidence=0.9,
                reasoning="All planned steps completed successfully.",
                remaining_tasks=[]
            )
            
        logger.info("Evaluation: PARTIAL")
        return EvaluationResult(
            status=EvaluationStatus.PARTIAL,
            confidence=0.8,
            reasoning="Plan partially executed, no failures so far.",
            remaining_tasks=[]
        )
