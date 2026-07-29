"""Capability integration tests for JAYA_AGENT skills."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

agent_source = Path(__file__).resolve().parents[1] / "src"
if str(agent_source) not in sys.path:
    sys.path.insert(0, str(agent_source))

from security.capability_sandbox import CapabilityDenied, CapabilitySandbox
from security.sandbox_interlock import SandboxInterlock
from skills.base_skill import SkillRegistry
from skills.builtin.file_skill import FileOperationsSkill
from skills.builtin.memory_skill import MemoryManagerSkill
from skills.builtin.system_skill import (
    SYSTEM_METRICS_RESOURCE,
    SystemControlSkill,
)
from skills.builtin.web_skill import WebResearchSkill


class TestPhase2Skills(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = CapabilitySandbox(signing_key=b"s" * 32)
        SkillRegistry.clear()
        SkillRegistry.configure_sandbox(self.sandbox)
        SkillRegistry.register(FileOperationsSkill())
        SkillRegistry.register(SystemControlSkill())
        SkillRegistry.register(WebResearchSkill(client=_FakeSearchClient()))
        SkillRegistry.register(MemoryManagerSkill(manager=_FakeMemoryManager()))

    def test_json_schema_exposes_capability_requirement(self) -> None:
        schemas = SkillRegistry.get_all_tool_schemas()
        tools = {schema["function"]["name"]: schema["function"] for schema in schemas}
        write_schema = tools["file_skill_write_file"]
        self.assertEqual(write_schema["x-jaya-capability"], "file.write")
        self.assertTrue(write_schema["x-jaya-explicit-grant-required"])
        self.assertFalse(
            write_schema["parameters"]["additionalProperties"],
        )

    def test_file_write_and_read_need_scoped_grants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = (Path(temporary_directory) / "result.txt").resolve()
            write_grant = self.sandbox.issue_grant(
                subject="phase2-test",
                actions=("file.write",),
                resources={"file.write": (str(path),)},
                ttl_seconds=30,
                consented_actions=("file.write",),
                consent_reference="test-consent-write-001",
            )
            written = asyncio.run(
                SkillRegistry.execute_action(
                    "file_skill_write_file",
                    {"filepath": str(path), "content": "JAYA AGENT"},
                    grant_token=write_grant,
                    idempotency_key="phase2-write-0001",
                )
            )
            self.assertTrue(written["success"])
            self.assertEqual(path.read_text(encoding="utf-8"), "JAYA AGENT")
            self.assertEqual(written["receipt"]["status"], "SUCCEEDED")

            read_grant = self.sandbox.issue_grant(
                subject="phase2-test",
                actions=("file.read",),
                resources={"file.read": (str(path),)},
                ttl_seconds=30,
            )
            read = asyncio.run(
                SkillRegistry.execute_action(
                    "file_skill_read_file",
                    {"filepath": str(path)},
                    grant_token=read_grant,
                    idempotency_key="phase2-read-00001",
                )
            )
            self.assertTrue(read["success"])
            self.assertEqual(read["result"], "JAYA AGENT")

    def test_missing_grant_and_direct_call_are_denied(self) -> None:
        denied = asyncio.run(
            SkillRegistry.execute_action(
                "system_skill_get_system_status",
                {},
                idempotency_key="phase2-status-001",
            )
        )
        self.assertFalse(denied["success"])
        self.assertEqual(denied["error_code"], "CAPABILITY_GRANT_REQUIRED")
        with self.assertRaises(CapabilityDenied):
            FileOperationsSkill().read_file(str(Path(__file__).resolve()))

    def test_system_status_happy_path(self) -> None:
        grant = self.sandbox.issue_grant(
            subject="phase2-test",
            actions=("system.status",),
            resources={"system.status": (SYSTEM_METRICS_RESOURCE,)},
            ttl_seconds=30,
        )
        result = asyncio.run(
            SkillRegistry.execute_action(
                "system_skill_get_system_status",
                {},
                grant_token=grant,
                idempotency_key="phase2-status-002",
            )
        )
        self.assertTrue(result["success"])
        self.assertIn("RAM", result["result"])

    def test_legacy_arbitrary_code_execution_is_denied(self) -> None:
        interlock = SandboxInterlock(max_ram_mb=256, timeout_sec=10)
        result = interlock.execute_safe_code(
            "import os; os.system('arbitrary command')"
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "ARBITRARY_CODE_DENIED")


class _FakeSearchClient:
    def search(self, query: str, max_results: int) -> list[dict[str, object]]:
        return [{"title": query, "max_results": max_results}]


class _FakeMemoryManager:
    def optimize_sqlite_database(self) -> None:
        return None

    def enforce_memory_cap(self, max_ram_mb: int) -> dict[str, float]:
        return {"current_rss_mb": float(max_ram_mb) / 2}


if __name__ == "__main__":
    unittest.main()
