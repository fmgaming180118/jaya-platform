"""
Unit Test Suite for JAYA_AGENT Phase 2: Hermes-Style Function Calling & Skill Registry
Verifies skill registration, Hermes-compatible JSON schema generation, tool execution, and sandbox interlock.
"""

import sys
import os
import asyncio
import unittest

# Add JAYA_AGENT/src to path
agent_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if agent_src not in sys.path:
    sys.path.insert(0, agent_src)

from skills.base_skill import SkillRegistry
from skills.builtin.file_skill import FileOperationsSkill
from skills.builtin.system_skill import SystemControlSkill
from skills.builtin.web_skill import WebResearchSkill
from skills.builtin.memory_skill import MemoryManagerSkill
from security.sandbox_interlock import SandboxInterlock


class TestPhase2Skills(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        SkillRegistry.register(FileOperationsSkill())
        SkillRegistry.register(SystemControlSkill())
        SkillRegistry.register(WebResearchSkill())
        SkillRegistry.register(MemoryManagerSkill())

    def test_json_schema_generation(self):
        """Verify Hermes 3 compatible JSON schema auto-generation."""
        schemas = SkillRegistry.get_all_tool_schemas()
        self.assertGreater(len(schemas), 0)
        tool_names = [s["function"]["name"] for s in schemas]
        self.assertIn("file_skill_read_file", tool_names)
        self.assertIn("file_skill_write_file", tool_names)

    def test_file_skill_execution(self):
        """Verify file_skill tool action execution via SkillRegistry."""
        test_file = "test_phase2_file.txt"
        
        # Write
        res_write = asyncio.run(SkillRegistry.execute_action(
            "file_skill_write_file",
            {"filepath": test_file, "content": "JAYA AGENT PHASE 2 TEST"}
        ))
        self.assertTrue(res_write["success"])

        # Read
        res_read = asyncio.run(SkillRegistry.execute_action(
            "file_skill_read_file",
            {"filepath": test_file}
        ))
        self.assertTrue(res_read["success"])
        self.assertEqual(res_read["result"], "JAYA AGENT PHASE 2 TEST")

        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)

    def test_system_status_execution(self):
        """Verify system control status tool execution."""
        res = asyncio.run(SkillRegistry.execute_action("system_skill_get_system_status", {}))
        self.assertTrue(res["success"])
        self.assertIn("RAM", res["result"])

    def test_sandbox_interlock_execution(self):
        """Verify safe code execution inside SandboxInterlock."""
        interlock = SandboxInterlock(max_ram_mb=256, timeout_sec=10)
        res = interlock.execute_safe_code("print('Hello from JAYA Sandbox Interlock')")
        self.assertTrue(res["success"])
        self.assertIn("Hello from JAYA Sandbox Interlock", res["output"])


if __name__ == "__main__":
    unittest.main()
