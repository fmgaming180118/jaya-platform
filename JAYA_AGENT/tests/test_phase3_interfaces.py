"""
Unit Test Suite for JAYA_AGENT Phase 3: Real-Time Multimodal Voice & Text Interfaces
Verifies TextInterface CLI commands, VoiceInterface transcript processing,
and FastAPI endpoint routes.
"""

# Local src bootstrap must precede project imports.
# ruff: noqa: E402

import os
import sys
import unittest

from fastapi.testclient import TestClient

# Add JAYA_AGENT/src to path
agent_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if agent_src not in sys.path:
    sys.path.insert(0, agent_src)

from interfaces.api_server import create_api_app
from interfaces.text_interface import TextInterface
from interfaces.voice_interface import VoiceInterface
from runtime.agent_loop import AgentLoop


class TestPhase3Interfaces(unittest.TestCase):
    def setUp(self):
        self.text_if = TextInterface(
            agent_loop=AgentLoop(enable_teacher_fallback=False)
        )
        self.voice_if = VoiceInterface(
            agent_loop=AgentLoop(enable_teacher_fallback=False)
        )
        self.app = create_api_app(agent_loop=self.text_if.agent_loop)
        self.client = TestClient(self.app)

    def test_cli_slash_commands(self):
        """Verify slash commands handling (/help, /status, /tools, /patches)."""
        help_resp = self.text_if.process_prompt("/help")
        self.assertIn("SLASH COMMANDS", help_resp)

        tools_resp = self.text_if.process_prompt("/tools")
        self.assertIn("Registered Tools", tools_resp)

        patches_resp = self.text_if.process_prompt("/patches")
        self.assertIn("UNAVAILABLE", patches_resp)
        self.assertNotIn("207 verified patches", patches_resp)

    def test_voice_transcript_processing(self):
        """Verify voice transcript processing in VoiceInterface."""
        res = self.voice_if.process_voice_transcript("JAYA optimize system RAM")
        self.assertIn("response", res)
        self.assertEqual(res["transcript"], "JAYA optimize system RAM")

    def test_api_server_endpoints(self):
        """Verify FastAPI REST endpoints (/agent/status, /agent/tools, /agent/chat)."""
        status_res = self.client.get("/agent/status")
        self.assertEqual(status_res.status_code, 200)
        self.assertTrue(status_res.json()["ok"])

        tools_res = self.client.get("/agent/tools")
        self.assertEqual(tools_res.status_code, 200)
        self.assertTrue(tools_res.json()["ok"])

        chat_res = self.client.post(
            "/agent/chat", json={"prompt": "Explain Phase 3 Interface"}
        )
        self.assertEqual(chat_res.status_code, 200)
        self.assertTrue(chat_res.json()["ok"])


if __name__ == "__main__":
    unittest.main()
