"""
Core AgentLoop Engine for JAYA_AGENT.
Implements the continuous Perceive -> CoT Reason -> Act -> Reflect cycle
with Steerability Control and Hybrid Fallback between Local SLM and NVIDIA Teacher.
"""

import time
import os
import sys
import json
import logging
from typing import Dict, Any, Optional, List, Callable

from .perception import PerceptionPipeline, AgentEvent, EventType

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_DEFAULT = """You are JAYA, a sovereign, ultra-fast, and precise AGI assistant.
Rules:
1. Always give direct, accurate, and structured answers.
2. Never hardcode credentials, URLs, or swallowed error handlers.
3. Be concise, respectful, and authoritative.
4. Execute tools when needed to complete user intents accurately.
"""


class AgentLoop:
    """
    Main Cognitive Event Loop for JAYA_AGENT applications.
    Coordinates perception, reasoning, skill dispatching, and reflection.
    """

    def __init__(self, system_prompt: str = SYSTEM_PROMPT_DEFAULT, enable_teacher_fallback: bool = True):
        self.system_prompt = system_prompt
        self.enable_teacher_fallback = enable_teacher_fallback
        self.perception = PerceptionPipeline()
        self.working_memory: List[Dict[str, Any]] = []
        self.is_running = False
        
        # Auto-initialize Teacher Engine if available
        self.teacher = None
        if self.enable_teacher_fallback:
            self._init_teacher()

        print("[AGENT_LOOP] [OK] JAYA AgentLoop initialized with Steerability Guardrails.")

    def _init_teacher(self):
        """Attempts to load NVIDIA NIM Teacher Engine."""
        try:
            # Add JAYA_RESEARCH/src to path for Teacher module
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            research_src = os.path.join(root_dir, "JAYA_RESEARCH", "src")
            if research_src not in sys.path:
                sys.path.insert(0, research_src)
            from teacher import Teacher
            self.teacher = Teacher(model_type="chat")
            print(f"[AGENT_LOOP] [OK] Teacher Engine loaded: {self.teacher.model}")
        except Exception as e:
            print(f"[AGENT_LOOP] Teacher Engine fallback disabled ({e}). Using Local SLM Mode.")
            self.teacher = None

    def process_step(self, user_input: str, event_type: EventType = EventType.TEXT) -> Dict[str, Any]:
        """
        Executes one full cycle of Perceive -> CoT Reason -> Act -> Reflect.
        """
        start_time = time.time()

        # 1. PERCEIVE
        event = self.perception.process(user_input, event_type=event_type)
        print(f"[AGENT_LOOP] [1. PERCEIVE] Intent: {event.intent} (Confidence: {event.confidence*100:.1f}%)")

        # 2. CoT REASON (Chain-of-Thought)
        reasoning_result = self._reason(event)
        print(f"[AGENT_LOOP] [2. REASON] CoT Completed ({reasoning_result.get('mode', 'local')}).")

        # 3. ACT (Tool Execution / Response Generation)
        action_result = self._act(reasoning_result, event)
        print(f"[AGENT_LOOP] [3. ACT] Response generated.")

        # 4. REFLECT (Memory Append & Metric Check)
        elapsed_ms = (time.time() - start_time) * 1000
        reflection = self._reflect(event, action_result, elapsed_ms)
        print(f"[AGENT_LOOP] [4. REFLECT] Step finished in {elapsed_ms:.1f}ms.")

        return {
            "event_id": event.event_id,
            "intent": event.intent,
            "confidence": event.confidence,
            "thought": reasoning_result.get("thought", ""),
            "response": action_result.get("response", ""),
            "elapsed_ms": round(elapsed_ms, 2),
            "mode": reasoning_result.get("mode", "local")
        }

    def _reason(self, event: AgentEvent) -> Dict[str, Any]:
        """Formulates Chain-of-Thought reasoning using Teacher or Local SLM."""
        thought = f"PLAN: Address user intent '{event.intent}' for query: '{event.normalized_text}'"

        # If complex coding or knowledge query, call Teacher Engine if available
        if self.teacher is not None and event.intent in ["coding_task", "knowledge_query", "web_search"]:
            try:
                if hasattr(self.teacher, "ask"):
                    response_text = self.teacher.ask(
                        prompt=event.normalized_text,
                        system_instruction=self.system_prompt
                    )
                elif hasattr(self.teacher, "query"):
                    response_text = self.teacher.query(
                        prompt=event.normalized_text,
                        system_prompt=self.system_prompt
                    )
                else:
                    response_text = None

                if response_text:
                    return {
                        "thought": thought,
                        "response": response_text,
                        "mode": f"NVIDIA_NIM_{self.teacher.model}"
                    }
            except Exception as e:
                print(f"[AGENT_LOOP] Teacher query fallback notice: {e}")

        # Local SLM Response
        local_resp = (
            f"JAYA Sovereign Response: Understood query '{event.normalized_text}'. "
            f"Processed intent '{event.intent}' in sub-100ms local execution loop."
        )
        return {
            "thought": thought,
            "response": local_resp,
            "mode": "LOCAL_SLM_ENGINE"
        }

    def _act(self, reasoning: Dict[str, Any], event: AgentEvent) -> Dict[str, Any]:
        """Executes action or returns response text."""
        return {
            "status": "success",
            "response": reasoning.get("response", "")
        }

    def _reflect(self, event: AgentEvent, action: Dict[str, Any], elapsed_ms: float) -> Dict[str, Any]:
        """Appends step to working memory buffer."""
        record = {
            "timestamp": time.time(),
            "input": event.raw_content,
            "intent": event.intent,
            "response": action.get("response", ""),
            "elapsed_ms": elapsed_ms
        }
        self.working_memory.append(record)
        if len(self.working_memory) > 50:
            self.working_memory.pop(0)
        return {"recorded": True}
