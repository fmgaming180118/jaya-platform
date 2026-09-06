"""
Working Memory Manager for JAYA_AGENT.
Implements sliding window context buffer and conversation context compression.
"""

import time
from typing import Dict, Any, List, Optional


class WorkingMemoryManager:
    """
    Manages short-term working memory and context compression.
    """

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self.history: List[Dict[str, Any]] = []
        self.summary: str = ""
        print(f"[WORKING MEMORY] Initialized (Window Size: {self.max_turns} turns).")

    def add_turn(self, role: str, content: str, intent: Optional[str] = None):
        """Adds a turn to working memory history."""
        turn = {
            "role": role,
            "content": content,
            "intent": intent or "general",
            "timestamp": time.time()
        }
        self.history.append(turn)
        if len(self.history) > self.max_turns:
            self._compress_context()

    def _compress_context(self):
        """Compresses older history turns into a compact memory summary."""
        turns_to_compress = self.history[:-10]
        self.history = self.history[-10:]

        summary_snippets = [f"{t['role']}: {t['content'][:40]}..." for t in turns_to_compress]
        new_summary = " | ".join(summary_snippets)
        if self.summary:
            self.summary = f"{self.summary} || {new_summary}"
        else:
            self.summary = new_summary
        print(f"[WORKING MEMORY] Compressed {len(turns_to_compress)} turns into summary.")

    def get_context_prompt(self) -> str:
        """Returns compressed context prompt for reasoning."""
        pass

    def get_formatted_context(self) -> str:
        """Formats summary and active turns into a prompt context string."""
        context_lines = []
        if self.summary:
            context_lines.append(f"[SUMMARY OF PRIOR CONVERSATION]: {self.summary}")
        for t in self.history:
            context_lines.append(f"{t['role'].upper()}: {t['content']}")
        return "\n".join(context_lines)
