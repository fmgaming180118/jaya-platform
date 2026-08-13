"""
spontaneity.py — Pillar 3 (Active Dreaming) & Pillar 6 (Spontaneity Engine) for JAYA_CORE

Implements proactive spontaneity and idle-time hypothesis generation:
- SpontaneousHypothesis: Representation of an autonomously generated hypothesis during idle time.
- SpontaneityEngine: Generates background curiosity prompts, hypothesis simulations, and spontaneous actions.
"""

import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SpontaneousHypothesis:
    """A hypothesis or curiosity prompt generated during idle/dreaming mode."""
    hypothesis_id: str
    topic: str
    hypothesis_text: str
    confidence: float
    suggested_action: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class SpontaneityEngine:
    """
    Pillar 3 & 6 Engine: Proactive Spontaneity & Active Dreaming.
    Generates autonomous curiosity prompts, idle-time research hypotheses,
    and proactive recommendations.
    """

    CURIOSITY_TOPICS = [
        "quantum_compiler_optimization",
        "agentic_rag_recall_enhancement",
        "zero_trust_sandbox_hardening",
        "qlora_student_distillation",
        "autonomous_curriculum_evolution",
        "sovereign_memory_compression",
    ]

    def __init__(self, spontaneity_level: float = 0.5):
        self.spontaneity_level = spontaneity_level
        self._history: List[SpontaneousHypothesis] = []

    def is_idle_trigger(self, cpu_load: float, is_silence_mode: bool) -> bool:
        """Determines if the system is in idle state suitable for active dreaming."""
        return is_silence_mode or cpu_load < 0.30

    def generate_hypothesis(self, topic: Optional[str] = None) -> SpontaneousHypothesis:
        """Generates a spontaneous research or optimization hypothesis."""
        target_topic = topic or random.choice(self.CURIOSITY_TOPICS)
        hypo_id = f"hypo-{target_topic}-{int(time.time())}"

        hypo_text = f"Hypothesis on {target_topic}: Idle-time optimization may increase throughput by {random.randint(5, 15)}%."
        confidence = round(random.uniform(0.75, 0.98), 3)
        suggested_action = f"run_simulation({target_topic})"

        hypothesis = SpontaneousHypothesis(
            hypothesis_id=hypo_id,
            topic=target_topic,
            hypothesis_text=hypo_text,
            confidence=confidence,
            suggested_action=suggested_action,
            metadata={"dream_mode": True, "spontaneity_level": self.spontaneity_level}
        )
        self._history.append(hypothesis)
        return hypothesis

    def get_dream_history(self) -> List[SpontaneousHypothesis]:
        """Returns all hypotheses generated during active dreaming."""
        return list(self._history)
