"""
Unit Test Suite for JAYA_AGENT Phase 5: Multi-Agent Collaboration & Sovereign Desktop Shell
Verifies specialized agent delegation, consensus verification, and desktop widget spec generation.
"""

import sys
import os
import unittest

# Add JAYA_AGENT/src to path
agent_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if agent_src not in sys.path:
    sys.path.insert(0, agent_src)

from jaya_agent.multiagent.router import MultiAgentRouter, SpecializedAgent
from jaya_agent.interfaces.desktop_shell import DesktopShell


class TestPhase5MultiagentDesktop(unittest.TestCase):

    def setUp(self):
        self.router = MultiAgentRouter()
        self.desktop_shell = DesktopShell()

    def test_multiagent_routing_delegation(self):
        """Verify routing user tasks to specialized agents (CodingAgent, ResearchAgent, SystemAgent)."""
        res_code = self.router.delegate_and_execute("Fix memory leak in Python script", intent="coding_task")
        self.assertEqual(res_code["delegated_to"], "CodingAgent")

        res_search = self.router.delegate_and_execute("Search quantum computing papers", intent="web_search")
        self.assertEqual(res_search["delegated_to"], "ResearchAgent")

        res_sys = self.router.delegate_and_execute("Optimize RAM usage", intent="system_optimization")
        self.assertEqual(res_sys["delegated_to"], "SystemAgent")
        self.assertTrue(res_sys["consensus_approved"])

    def test_desktop_shell_widget_spec_generation(self):
        """Verify dynamic desktop widget spec generation from user prompt."""
        res = self.desktop_shell.render_desktop_intent("Optimize system memory")
        self.assertIn("widget_spec", res)
        self.assertEqual(res["widget_spec"]["type"], "SystemMonitorWidget")
        self.assertEqual(res["total_mounted_widgets"], 1)


if __name__ == "__main__":
    unittest.main()
