"""
Unit Test Suite for JAYA_AGENT Phase 1: Core Agent Loop & Steerability Engine
Verifies perception pipeline, intent classification, CoT reasoning loop, and latency.
"""

import os
import sys
import unittest

# Add JAYA_AGENT/src to path
agent_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if agent_src not in sys.path:
    sys.path.insert(0, agent_src)

from jaya_agent.runtime.agent_loop import AgentLoop
from jaya_agent.runtime.perception import PerceptionPipeline


class TestPhase1AgentLoop(unittest.TestCase):
    def setUp(self):
        self.perception = PerceptionPipeline()
        self.agent_loop = AgentLoop(enable_teacher_fallback=False)

    def test_perception_intent_classification(self):
        """Verify intent classification and confidence score > 90%."""
        event_coding = self.perception.process(
            "Write a Python script to optimize memory"
        )
        self.assertEqual(event_coding.intent, "coding_task")
        self.assertGreaterEqual(event_coding.confidence, 0.90)

        event_search = self.perception.process(
            "Search latest quantum computing research on duckduckgo"
        )
        self.assertEqual(event_search.intent, "web_search")
        self.assertGreaterEqual(event_search.confidence, 0.90)

    def test_agent_loop_cycle(self):
        """Verify full Perceive -> CoT Reason -> Act -> Reflect cycle."""
        res = self.agent_loop.process_step("Explain how GraphRAG temporal memory works")
        self.assertIn("response", res)
        self.assertIn("intent", res)
        self.assertIn("elapsed_ms", res)
        self.assertGreater(len(self.agent_loop.working_memory), 0)

    def test_latency_sub_100ms(self):
        """Verify local loop execution latency is sub-100ms."""
        res = self.agent_loop.process_step("Fast memory check")
        self.assertLess(res["elapsed_ms"], 100.0)

    def test_teacher_flag_cannot_trigger_implicit_network_provider(self):
        """Provider access must go through a capability-gated tool."""
        loop = AgentLoop(enable_teacher_fallback=True)
        result = loop.process_step("Search a private provider")
        self.assertIsNone(loop.teacher)
        self.assertFalse(loop.enable_teacher_fallback)
        self.assertEqual(result["mode"], "LOCAL_POLICY_ROUTER")


if __name__ == "__main__":
    unittest.main()
