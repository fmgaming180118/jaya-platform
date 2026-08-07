"""
evaluator.py — Evaluates goal progress and triggers replanning if necessary.
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from JAYA_CORE.src.ai_connectors.cognitive_model_adapter import CognitiveModelAdapter

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
    """Evaluates whether a goal has been achieved based on observations and postconditions."""
    
    def __init__(self, model_adapter: Optional[CognitiveModelAdapter] = None):
        self.model_adapter = model_adapter
        
    def evaluate_goal_progress(
        self, 
        goal: Any, 
        observations: List[Dict[str, Any]], 
        plan: Any
    ) -> EvaluationResult:
        """
        Evaluate goal progress based on the execution history.
        Verifies explicit postconditions rather than just assuming success if steps passed.
        """
        goal_title = getattr(goal, "title", "Unknown")
        logger.info("Evaluating progress for goal: %s", goal_title)
        
        # Fast fail if explicit failure occurred
        failed_steps = [obs for obs in observations if not obs.get("ok", False) and obs.get("status") == "FAILED"]
        
        if failed_steps:
            logger.info("Evaluation: FAILED (%d failed steps)", len(failed_steps))
            return EvaluationResult(
                status=EvaluationStatus.FAILED,
                confidence=0.9,
                reasoning=f"Failed steps detected: {', '.join([s.get('action_type', s.get('tool_executed', 'unknown')) for s in failed_steps])}",
                remaining_tasks=[]
            )
            
        if not self.model_adapter:
            # Fallback if no model adapter
            successful_steps = [obs for obs in observations if obs.get("ok", False) or obs.get("status") == "SUCCESS"]
            if successful_steps and len(successful_steps) >= len(getattr(plan, "steps", [])):
                return EvaluationResult(
                    status=EvaluationStatus.ACHIEVED,
                    confidence=0.5,
                    reasoning="Fallback: All planned steps reported SUCCESS, but model unavailable to verify postconditions.",
                    remaining_tasks=[]
                )
            return EvaluationResult(
                status=EvaluationStatus.PARTIAL,
                confidence=0.5,
                reasoning="Fallback: Plan partially executed.",
                remaining_tasks=[]
            )

        # Call cognitive model to evaluate real postconditions
        prompt = (
            f"Please evaluate if the following goal was achieved:\n"
            f"Goal: {goal_title}\n"
            f"Observations:\n"
        )
        for idx, obs in enumerate(observations):
            prompt += f" {idx+1}. Step ID: {obs.get('step_id')}, Status: {obs.get('status')}, Result: {obs.get('result')}\n"
            
        prompt += "\nRespond ONLY with a JSON object containing keys: 'status' (ACHIEVED, PARTIAL, or FAILED) and 'reasoning' (brief text)."
        
        try:
            response = self.model_adapter.generate(prompt=prompt, privacy_level="INTERNAL")
            text = response.text.strip()
            
            # Simple parse
            import json
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                status_str = data.get("status", "UNKNOWN")
                try:
                    status = EvaluationStatus(status_str)
                except ValueError:
                    status = EvaluationStatus.UNKNOWN
                
                return EvaluationResult(
                    status=status,
                    confidence=response.confidence,
                    reasoning=data.get("reasoning", "No reasoning provided"),
                    remaining_tasks=[]
                )
            else:
                return EvaluationResult(
                    status=EvaluationStatus.UNKNOWN,
                    confidence=0.0,
                    reasoning="Failed to parse LLM evaluation response.",
                    remaining_tasks=[]
                )
        except Exception as e:
            logger.error("Error evaluating goal progress: %s", e)
            return EvaluationResult(
                status=EvaluationStatus.UNKNOWN,
                confidence=0.0,
                reasoning=f"Error evaluating goal progress: {str(e)}",
                remaining_tasks=[]
            )
