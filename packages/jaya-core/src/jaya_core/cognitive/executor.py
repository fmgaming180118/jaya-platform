"""
executor.py — Executes cognitive and reasoning actions natively.
"""

import logging
from typing import Any, Dict, Optional
from jaya_core.cognitive.contracts import CognitiveStepResult
from jaya_core.ai_connectors.cognitive_model_adapter import CognitiveModelAdapter

logger = logging.getLogger(__name__)

class CognitiveActionExecutor:
    """
    Executes internal cognitive steps like planning, constraints calculation, 
    and architectural analysis using a real cognitive provider.
    """
    
    def __init__(self, model_adapter: Optional[CognitiveModelAdapter] = None):
        self.model_adapter = model_adapter
        
    def execute_reasoning(self, step: Any, context: Dict[str, Any]) -> CognitiveStepResult:
        """
        Execute a reasoning step using the connected cognitive model.
        """
        step_title = getattr(step, "title", "Unknown Reasoning Step")
        action_type = getattr(step, "action_type", "unknown")
        inputs = getattr(step, "inputs", {})
        
        logger.info("Executing cognitive step: %s (%s)", step_title, action_type)
        
        if not self.model_adapter:
            return CognitiveStepResult(
                ok=False,
                error="COGNITIVE_PROVIDER_UNAVAILABLE",
            )
            
        # Construct prompt based on action type and inputs
        prompt_lines = [
            f"Please perform cognitive reasoning for action: {action_type}",
            f"Step Title: {step_title}",
            "Inputs:",
        ]
        for k, v in inputs.items():
            prompt_lines.append(f" - {k}: {v}")
            
        if "previous_failure_reason" in context:
            prompt_lines.append(f"Note: Previous attempt failed because: {context['previous_failure_reason']}")
            
        prompt = "\n".join(prompt_lines)
        
        try:
            response = self.model_adapter.generate(prompt=prompt)
            
            artifacts = {"analysis_result": response.text}
            if action_type == "write_code_draft":
                from jaya_core.cognitive.contracts import CodeChangeArtifact
                artifacts["code_change"] = CodeChangeArtifact(
                    target_path=inputs.get("target_path", "unknown.py"),
                    original_digest="",
                    replacement_content=response.text,
                    explanation="Generated code draft",
                    expected_effect="Implement requested functionality",
                    generated_by=response.model_used,
                    confidence=response.confidence
                )
            
            # The response is a CognitiveResponse object
            return CognitiveStepResult(
                ok=True,
                output_text=response.text,
                artifacts=artifacts,
                derived_inputs={},
                confidence=response.confidence,
                provider=response.source,
                model=response.model_used,
            )
        except Exception as e:
            logger.error("Cognitive reasoning failed: %s", e)
            return CognitiveStepResult(
                ok=False,
                error=f"REASONING_ERROR: {str(e)}"
            )
