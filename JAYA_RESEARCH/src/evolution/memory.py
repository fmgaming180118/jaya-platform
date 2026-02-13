import json
import time
from pathlib import Path
from typing import List, Dict, Optional

class EvolutionMemory:
    """
    The 'Hippocampus' of the Digital Twin.
    Stores stream of consciousness (thoughts), plans, and experiment results.
    """
    def __init__(self, storage_path="data/evolution/memory.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.thoughts: List[Dict] = []
        self._load()

    def _load(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    self.thoughts = data.get("thoughts", [])
            except Exception as e:
                print(f"[Memory] Load failed: {e}")

    def _save(self):
        try:
            with open(self.storage_path, 'w') as f:
                json.dump({"thoughts": self.thoughts[-1000:]}, f, indent=2) # Keep last 1000
        except Exception as e:
            print(f"[Memory] Save failed: {e}")

    def log_thought(self, content: str, mood: str = "neutral", context: Optional[Dict] = None):
        """Records a new thought."""
        thought = {
            "timestamp": time.time(),
            "content": content,
            "mood": mood,
            "context": context or {}
        }
        self.thoughts.append(thought)
        self._save()
        return thought

    def get_recent_thoughts(self, limit=10) -> List[Dict]:
        return self.thoughts[-limit:]

    def clear(self):
        self.thoughts = []
        self._save()
