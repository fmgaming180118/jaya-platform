
import json
import os
import hashlib
import time

class DiscoveryMemory:
    def __init__(self, memory_file="discovery_memory.json"):
        self.memory_file = memory_file
        self.history = self._load_memory()
        
    def _load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_memory(self):
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2)
            
    def _hash_code(self, code):
        """Generate a consistent hash for code content."""
        return hashlib.sha256(code.strip().encode()).hexdigest()
    
    def seen_before(self, code):
        """Check if this exact code mutation has been tried."""
        code_hash = self._hash_code(code)
        for entry in self.history:
            if entry.get("hash") == code_hash:
                return True
        return False
        
    def add_experience(self, code, result, score=None, error=None):
        """Log an experiment result."""
        entry = {
            "timestamp": time.time(),
            "hash": self._hash_code(code),
            "result": result, # "SUCCESS", "FAIL_INTEGRITY", "FAIL_BENCHMARK"
            "score": score,
            "error": str(error) if error else None,
            # We could ideally add "Teacher Description" here if we asked for it
        }
        self.history.append(entry)
        self._save_memory()
        print(f"[MEMORY] 🧠 Experiment logged: {result}")

    def get_best_discoveries(self, limit=3):
        """Retrieve top successful mutations to use as context (RAG)."""
        successes = [e for e in self.history if e["result"] == "SUCCESS"]
        # Sort by score (lower is better for time)
        successes.sort(key=lambda x: x["score"] if x["score"] else 999)
        return successes[:limit]

    def get_recent_failures(self, limit=3):
        """Retrieve recent failures to warn the Teacher."""
        failures = [e for e in self.history if "FAIL" in e["result"]]
        return failures[-limit:]
