"""
Perception Pipeline & Event Normalizer for JAYA_AGENT.
Normalizes text, voice, and system events into unified AgentEvent objects
with intent classification and confidence scoring.
"""

import time
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


class EventType(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    SYSTEM_EVENT = "system_event"
    TOOL_RESULT = "tool_result"


@dataclass
class AgentEvent:
    """Unified Event Data Structure across all interfaces."""
    event_id: str
    event_type: EventType
    raw_content: str
    normalized_text: str = ""
    intent: str = "general_query"
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class PerceptionPipeline:
    """
    Perception Engine that processes raw interface inputs, cleans tokens,
    classifies intent with confidence scoring, and prepares context for AgentLoop.
    """

    INTENT_PATTERNS = [
        (r"\b(code|coding|function|script|python|fix|bug|debug|api)\b", "coding_task", 0.95),
        (r"\b(search|find|google|duckduckgo|web|lookup|latest)\b", "web_search", 0.92),
        (r"\b(memory|ram|cache|sqlite|database|clean|optimize)\b", "system_optimization", 0.94),
        (r"\b(who|what|why|how|explain|describe|tell)\b", "knowledge_query", 0.90),
        (r"\b(run|execute|start|stop|toggle|launch)\b", "command_execution", 0.93),
    ]

    def __init__(self):
        print("[PERCEPTION] Perception Pipeline initialized.")

    def process(self, raw_input: str, event_type: EventType = EventType.TEXT, metadata: Optional[Dict[str, Any]] = None) -> AgentEvent:
        """
        Processes raw input string or audio token stream into a normalized AgentEvent.
        """
        if not raw_input:
            raw_input = ""

        # 1. Normalize text (lowercase, strip whitespace)
        normalized = raw_input.strip()

        # 2. Intent Classification via pattern matching & confidence calculation
        intent, confidence = self._classify_intent(normalized)

        event_id = f"EVT-{int(time.time() * 1000)}"
        return AgentEvent(
            event_id=event_id,
            event_type=event_type,
            raw_content=raw_input,
            normalized_text=normalized,
            intent=intent,
            confidence=confidence,
            metadata=metadata or {},
            timestamp=time.time()
        )

    def _classify_intent(self, text: str) -> tuple[str, float]:
        """Classifies intent and calculates confidence score (> 90%)."""
        text_lower = text.lower()
        for pattern, intent, conf in self.INTENT_PATTERNS:
            if re.search(pattern, text_lower):
                return intent, conf
        return "general_conversation", 0.88
