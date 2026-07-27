"""
Unit Test Suite for JAYA_AGENT Phase 4: Triple-Layer Memory & Self-Evolution Bridge
Verifies WorkingMemoryManager compression, RAGMemoryEngine patch retrieval, and EcosystemSyncBridge.
"""

import sys
import os
import unittest

# Add JAYA_AGENT/src to path
agent_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, agent_src)

from memory.working_memory import WorkingMemoryManager
from memory.rag_memory import RAGMemoryEngine
from memory.sync_bridge import EcosystemSyncBridge


class TestPhase4Memory(unittest.TestCase):

    def test_working_memory_compression(self):
        """Verify working memory turns sliding window compression."""
        wm = WorkingMemoryManager(max_turns=5)
        for i in range(12):
            wm.add_turn("user", f"Test message turn #{i}")
        
        self.assertLessEqual(len(wm.history), 10)
        self.assertTrue(len(wm.summary) > 0)
        formatted = wm.get_formatted_context()
        self.assertIn("SUMMARY OF PRIOR CONVERSATION", formatted)

    def test_rag_memory_retrieval(self):
        """Verify RAG memory querying synchronized SQLite patches."""
        rag = RAGMemoryEngine()
        patches = rag.query_relevant_patches("Memory", limit=3)
        self.assertIsInstance(patches, list)

    def test_ecosystem_sync_bridge(self):
        """Verify automatic EcosystemSyncBridge hot-reloading."""
        bridge = EcosystemSyncBridge()
        res = bridge.sync_latest_evolution()
        self.assertIn("synced_db", res)
        self.assertIn("synced_adapters", res)
        self.assertIn("total_patches", res)


if __name__ == "__main__":
    unittest.main()
