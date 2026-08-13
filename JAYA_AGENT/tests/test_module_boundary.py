# Local src bootstrap must precede project imports.
# ruff: noqa: E402

from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path
from typing import Any

_AGENT_ROOT = Path(__file__).resolve().parents[1]
_AGENT_SOURCE = _AGENT_ROOT / "src"
if str(_AGENT_SOURCE) not in sys.path:
    sys.path.insert(0, str(_AGENT_SOURCE))

from interfaces.text_interface import TextInterface
from runtime.agent_loop import AgentLoop
from security.capability_sandbox import CapabilitySandbox
from skills.base_skill import SkillRegistry
from skills.builtin.memory_skill import MEMORY_RESOURCE, MemoryManagerSkill
from skills.builtin.web_skill import WebResearchSkill


class _PatchState:
    def __init__(self, count: int, verified: bool = True) -> None:
        self.count = count
        self.verified = verified

    def get_patch_state(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "verified_count": self.count,
        }


def _configure(skill: Any) -> CapabilitySandbox:
    sandbox = CapabilitySandbox(signing_key=b"boundary-test-signing-key-000001")
    SkillRegistry.clear()
    SkillRegistry.configure_sandbox(sandbox)
    SkillRegistry.register(skill)
    return sandbox


def test_web_skill_without_adapter_fails_closed() -> None:
    skill = WebResearchSkill()
    sandbox = _configure(skill)
    grant = sandbox.issue_grant(
        subject="boundary-test",
        actions=("web.search",),
        resources={"web.search": skill.NETWORK_RESOURCES},
        ttl_seconds=30,
    )
    result = asyncio.run(
        SkillRegistry.execute_action(
            "web_skill_web_search",
            {"query": "public adapter required"},
            grant_token=grant,
            idempotency_key="boundary-web-0001",
        )
    )
    assert result["success"] is False
    assert result["error_code"] == "ADAPTER_UNAVAILABLE"


def test_memory_skill_without_adapter_fails_closed() -> None:
    sandbox = _configure(MemoryManagerSkill())
    grant = sandbox.issue_grant(
        subject="boundary-test",
        actions=("system.memory.optimize",),
        resources={"system.memory.optimize": (MEMORY_RESOURCE,)},
        ttl_seconds=30,
        consented_actions=("system.memory.optimize",),
        consent_reference="boundary-memory-consent",
    )
    result = asyncio.run(
        SkillRegistry.execute_action(
            "memory_skill_optimize_memory",
            {},
            grant_token=grant,
            idempotency_key="boundary-memory-0001",
        )
    )
    assert result["success"] is False
    assert result["error_code"] == "ADAPTER_UNAVAILABLE"


def test_patch_command_uses_provider_state_or_unavailable() -> None:
    default_interface = TextInterface(
        agent_loop=AgentLoop(enable_teacher_fallback=False)
    )
    assert "UNAVAILABLE" in default_interface.process_prompt("/patches")
    assert "207" not in default_interface.process_prompt("/patches")

    verified_interface = TextInterface(
        agent_loop=AgentLoop(enable_teacher_fallback=False),
        patch_state_provider=_PatchState(13),
    )
    assert (
        verified_interface.process_prompt("/patches")
        == "Memory DB Status: 13 verified patches."
    )

    unverified_interface = TextInterface(
        agent_loop=AgentLoop(enable_teacher_fallback=False),
        patch_state_provider=_PatchState(999, verified=False),
    )
    assert "UNAVAILABLE" in unverified_interface.process_prompt("/patches")
    assert "999" not in unverified_interface.process_prompt("/patches")


def test_agent_skills_do_not_import_research_or_mutate_sys_path() -> None:
    for relative in (
        "skills/builtin/web_skill.py",
        "skills/builtin/memory_skill.py",
    ):
        path = _AGENT_SOURCE / relative
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert all("research" not in name.casefold() for name in imported)
        assert "sys.path" not in source
        assert "JAYA_RESEARCH" not in source

    interface_source = (_AGENT_SOURCE / "interfaces/text_interface.py").read_text(
        encoding="utf-8"
    )
    assert "207 verified patches" not in interface_source
