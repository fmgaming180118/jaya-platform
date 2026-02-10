
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
        
    def add_experience(self, code, result, score=None, error=None, metadata=None):
        """
        Log an experiment result.
        
        Args:
            code: Code content
            result: Result type (SUCCESS, FAIL_*, RESEARCH_REPORT, etc)
            score: Performance score (optional)
            error: Error message (optional)
            metadata: Additional metadata dict (optional)
        """
        entry = {
            "timestamp": time.time(),
            "hash": self._hash_code(code),
            "result": result, # "SUCCESS", "FAIL_INTEGRITY", "FAIL_BENCHMARK", "RESEARCH_REPORT"
            "score": score,
            "error": str(error) if error else None,
        }
        
        # Add metadata if provided
        if metadata:
            entry.update(metadata)
        
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

    def add_variant(self, syntax, compiler, generation, score):
        """
        Store a language evolution variant with full code + metadata.
        Auto-prunes to keep only top-10 best variants.
        """
        variant = {
            "type": "evolution_variant",
            "timestamp": time.time(),
            "generation": generation,
            "score": score,
            "syntax": syntax,
            "compiler": compiler,
            "hash": self._hash_code(syntax + compiler),
        }
        
        # Add to history
        self.history.append(variant)
        
        # Auto-cleanup: keep only top-10 variants by score (higher is better)
        variants = [e for e in self.history if e.get("type") == "evolution_variant"]
        if len(variants) > 10:
            # Sort by score descending
            variants.sort(key=lambda x: x.get("score", 0), reverse=True)
            # Keep top 10
            top_variants = variants[:10]
            # Remove low-scoring variants from history
            self.history = [e for e in self.history if e.get("type") != "evolution_variant"] + top_variants
        
        self._save_memory()
        print(f"[MEMORY] 💾 Variant Gen {generation} saved (Score: {score:.2f})")

    def get_best_variants(self, limit=10):
        """Retrieve top N evolution variants."""
        variants = [e for e in self.history if e.get("type") == "evolution_variant"]
        variants.sort(key=lambda x: x.get("score", 0), reverse=True)
        return variants[:limit]
