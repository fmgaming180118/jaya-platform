"""
Core AgentLoop Engine for JAYA_AGENT.
Implements the continuous Perceive -> CoT Reason -> Act -> Reflect cycle
without implicit provider or tool side effects.
"""

import logging
import time
from typing import Any, Dict, List

from .perception import AgentEvent, EventType, PerceptionPipeline

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_DEFAULT = """You are JAYA, a precise assistant.
Rules:
1. Always give direct, accurate, and structured answers.
2. Never hardcode credentials, URLs, or swallowed error handlers.
3. Be concise, respectful, and authoritative.
4. Never claim a tool ran without a verified execution receipt.
"""


class AgentLoop:
    """
    Main Cognitive Event Loop for JAYA_AGENT applications.
    Coordinates perception, reasoning, skill dispatching, and reflection.
    """

    def __init__(
        self,
        system_prompt: str = SYSTEM_PROMPT_DEFAULT,
        enable_teacher_fallback: bool = False,
    ):
        self.system_prompt = system_prompt
        self.enable_teacher_fallback = False
        self.perception = PerceptionPipeline()
        self.working_memory: List[Dict[str, Any]] = []
        self.is_running = False
        self.teacher = None
        if enable_teacher_fallback:
            logger.warning(
                "Direct Teacher provider fallback is disabled; provider calls "
                "must use a capability-gated tool"
            )

        print(
            "[AGENT_LOOP] [OK] JAYA AgentLoop initialized with Steerability Guardrails."
        )

    def process_step(
        self, user_input: str, event_type: EventType = EventType.TEXT
    ) -> Dict[str, Any]:
        """
        Executes one full cycle of Perceive -> CoT Reason -> Act -> Reflect.
        """
        start_time = time.time()

        # 1. PERCEIVE
        event = self.perception.process(user_input, event_type=event_type)
        print(
            "[AGENT_LOOP] [1. PERCEIVE] "
            f"Intent: {event.intent} "
            f"(Confidence: {event.confidence * 100:.1f}%)"
        )

        # 2. CoT REASON (Chain-of-Thought)
        reasoning_result = self._reason(event)
        print(
            "[AGENT_LOOP] [2. REASON] Route selected "
            f"({reasoning_result.get('mode', 'local')})."
        )

        # 3. ACT (Tool Execution / Response Generation)
        action_result = self._act(reasoning_result, event)
        print("[AGENT_LOOP] [3. ACT] Response generated.")

        # 4. REFLECT (Memory Append & Metric Check)
        elapsed_ms = (time.time() - start_time) * 1000
        self._reflect(event, action_result, elapsed_ms)
        print(f"[AGENT_LOOP] [4. REFLECT] Step finished in {elapsed_ms:.1f}ms.")

        return {
            "event_id": event.event_id,
            "intent": event.intent,
            "confidence": event.confidence,
            "thought": reasoning_result.get("thought", ""),
            "response": action_result.get("response", ""),
            "elapsed_ms": round(elapsed_ms, 2),
            "mode": reasoning_result.get("mode", "local"),
        }

    def _reason(self, event: AgentEvent) -> Dict[str, Any]:
        """Formulates a local response without implicit network effects."""
        thought = "Local policy route selected; no hidden action executed"

        local_resp = (
            f"Understood query '{event.normalized_text}' with intent "
            f"'{event.intent}'. No external provider or tool was invoked."
        )
        return {
            "thought": thought,
            "response": local_resp,
            "mode": "LOCAL_POLICY_ROUTER",
        }

    def _act(self, reasoning: Dict[str, Any], event: AgentEvent) -> Dict[str, Any]:
        """Executes action or returns response text."""
        return {"status": "success", "response": reasoning.get("response", "")}

    def _reflect(
        self, event: AgentEvent, action: Dict[str, Any], elapsed_ms: float
    ) -> Dict[str, Any]:
        """Appends step to working memory buffer."""
        record = {
            "timestamp": time.time(),
            "input": event.raw_content,
            "intent": event.intent,
            "response": action.get("response", ""),
            "elapsed_ms": elapsed_ms,
        }
        self.working_memory.append(record)
        if len(self.working_memory) > 50:
            self.working_memory.pop(0)
        return {"recorded": True}
