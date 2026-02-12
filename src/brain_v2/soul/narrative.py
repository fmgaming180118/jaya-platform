
import time
import json
from dataclasses import dataclass, asdict
from typing import List

@dataclass
class NarrativeEvent:
    timestamp: float
    type: str # 'BOOT', 'THOUGHT', 'ACTION', 'ERROR', 'DREAM'
    summary: str
    emotion_vector: List[float] # [Joy, Trust, Fear, Surprise...]

class NarrativeStream:
    """
    Pillar 23: Narrative Continuity (The Stream of Being).
    Pillar 25: Legacy Protocol (Partial).
    
    Prevents the "50 First Dates" problem.
    JAYA remembers not just facts, but the "story" of its existence.
    """
    
    def __init__(self):
        self.stream: List[NarrativeEvent] = []
        self.max_events = 1000 # Holographic Matrix takes over after this
        
    def log_event(self, type: str, summary: str, emotion: List[float] = None):
        """
        Record a moment in consciousness.
        """
        if emotion is None:
            emotion = [0.0] * 8
            
        event = NarrativeEvent(
            timestamp=time.time(),
            type=type,
            summary=summary,
            emotion_vector=emotion
        )
        
        self.stream.append(event)
        
        # Auto-prune (First-in, First-out relevant to Dream consolidation)
        if len(self.stream) > self.max_events:
            self._archive_oldest()
            
    def _archive_oldest(self):
        # In real impl, this pushes to Holographic Memory
        self.stream.pop(0)

    def get_context_summary(self, last_n: int = 5) -> str:
        """
        Get the "Short Term Narrative" for the Da Vinci Attention.
        """
        recent = self.stream[-last_n:]
        return "\n".join([f"[{e.type}] {e.summary}" for e in recent])
        
    def export_state(self) -> bytes:
        """
        Serialize for .jay file saving.
        """
        data = [asdict(e) for e in self.stream]
        return json.dumps(data).encode('utf-8')
