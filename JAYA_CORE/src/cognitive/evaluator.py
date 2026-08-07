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

from JAYA_CORE.src.cognitive.contracts import GoalEvaluationResult, Goal

class EvaluationStatus(Enum):
    ACHIEVED = "ACHIEVED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    UNVERIFIED = "UNVERIFIED"

class GoalEvaluator:
    """Evaluates whether a goal has been achieved based on observations and postconditions."""
    
    def __init__(self, model_adapter: Optional[CognitiveModelAdapter] = None):
        self.model_adapter = model_adapter
        
    def evaluate_goal_progress(
        self, 
        goal: Goal, 
        observations: List[Dict[str, Any]], 
        plan: Any
    ) -> GoalEvaluationResult:
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
            return GoalEvaluationResult(
                status=EvaluationStatus.FAILED.value,
                confidence=0.9,
                evidence=f"Failed steps detected: {', '.join([s.get('action_type', s.get('tool_executed', 'unknown')) for s in failed_steps])}",
                remaining_work=[]
            )
            
        if not self.model_adapter or not self.model_adapter.has_reasoning_provider():
            # Fallback if no model adapter
            successful_steps = [obs for obs in observations if obs.get("ok", False) or obs.get("status") == "SUCCESS"]
            if successful_steps and len(successful_steps) >= len(getattr(plan, "steps", [])):
                return GoalEvaluationResult(
                    status=EvaluationStatus.UNVERIFIED.value,
                    confidence=0.0,
                    evidence="Fallback: All planned steps reported SUCCESS, but model unavailable to verify postconditions. Cannot confirm ACHIEVED.",
                    remaining_work=[]
                )
            return GoalEvaluationResult(
                status=EvaluationStatus.PARTIAL.value,
                confidence=0.5,
                evidence="Fallback: Plan partially executed.",
                remaining_work=[]
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
            response = self.model_adapter.generate(prompt=prompt)
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
                
                return GoalEvaluationResult(
                    status=status.value,
                    confidence=response.confidence,
                    evidence=data.get("reasoning", "No reasoning provided"),
                    remaining_work=[]
                )
            else:
                return GoalEvaluationResult(
                    status=EvaluationStatus.UNKNOWN.value,
                    confidence=0.0,
                    evidence="Failed to parse LLM evaluation response.",
                    remaining_work=[]
                )
        except Exception as e:
            logger.error("Error evaluating goal progress: %s", e)
            return GoalEvaluationResult(
                status=EvaluationStatus.UNKNOWN.value,
                confidence=0.0,
                evidence=f"Error evaluating goal progress: {str(e)}",
                remaining_work=[]
            )
