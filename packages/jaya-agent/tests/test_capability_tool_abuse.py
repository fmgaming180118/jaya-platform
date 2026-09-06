"""End-to-end abuse tests for capability-gated Agent tools."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

agent_source = Path(__file__).resolve().parents[1] / "src"
if str(agent_source) not in sys.path:
    sys.path.insert(0, str(agent_source))

from jaya_agent.security.capability_sandbox import CapabilityDenied, CapabilitySandbox
from jaya_agent.skills.base_skill import SkillRegistry
from jaya_agent.skills.builtin.file_skill import FileOperationsSkill
from jaya_agent.skills.builtin.memory_skill import MEMORY_RESOURCE, MemoryManagerSkill
from jaya_agent.skills.builtin.voice_skill import (
    AUDIO_OUTPUT_RESOURCE,
    VoiceOutputSkill,
)
from jaya_agent.skills.builtin.web_skill import WebResearchSkill


class _FakeSearchClient:
    def search(self, query: str, max_results: int) -> list[dict[str, object]]:
        return [{"title": query, "count": max_results}]


class _FakeMemoryManager:
    calls = 0

    def optimize_sqlite_database(self) -> None:
        self.calls += 1

    def enforce_memory_cap(self, max_ram_mb: int) -> dict[str, float]:
        return {"current_rss_mb": max_ram_mb / 4}


class _FakeSpeechEngine:
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.wait_calls = 0

    def say(self, text: str) -> None:
        self.spoken.append(text)

    def runAndWait(self) -> None:
        self.wait_calls += 1


def _configure(*skills) -> CapabilitySandbox:
    sandbox = CapabilitySandbox(signing_key=b"agent-abuse-test-key-00000000001")
    SkillRegistry.clear()
    SkillRegistry.configure_sandbox(sandbox)
    for skill in skills:
        SkillRegistry.register(skill)
    return sandbox


def test_web_tool_requires_exact_provider_scope_and_blocks_direct_call() -> None:
    skill = WebResearchSkill(client=_FakeSearchClient())
    sandbox = _configure(skill)
    resources = skill.NETWORK_RESOURCES
    grant = sandbox.issue_grant(
        subject="agent-test",
        actions=("web.search",),
        resources={"web.search": resources},
        ttl_seconds=30,
        max_uses=2,
    )
    result = asyncio.run(
        SkillRegistry.execute_action(
            "web_skill_web_search",
            {"query": "grounded research"},
            grant_token=grant,
            idempotency_key="agent-web-search-001",
        )
    )
    assert result["success"]
    assert json.loads(result["result"])[0]["title"] == "grounded research"

    evil_grant = sandbox.issue_grant(
        subject="agent-test",
        actions=("web.search",),
        resources={"web.search": ("https://evil.example",)},
        ttl_seconds=30,
    )
    denied = asyncio.run(
        SkillRegistry.execute_action(
            "web_skill_web_search",
            {"query": "exfiltrate"},
            grant_token=evil_grant,
            idempotency_key="agent-web-search-002",
        )
    )
    assert not denied["success"]
    assert denied["error_code"] == "RESOURCE_NOT_GRANTED"
    with pytest.raises(CapabilityDenied):
        skill.web_search("bypass registry")


def test_file_scope_and_idempotency_block_repeat_side_effect(
    tmp_path: Path,
) -> None:
    sandbox = _configure(FileOperationsSkill())
    target = (tmp_path / "allowed.txt").resolve()
    outside = (tmp_path.parent / "outside.txt").resolve()
    grant = sandbox.issue_grant(
        subject="agent-test",
        actions=("fs.write",),
        resources={"fs.write": (str(target),)},
        ttl_seconds=30,
        max_uses=2,
        consented_actions=("fs.write",),
        consent_reference="user-approved-target",
    )

    async def write(path: Path, content: str, key: str):
        return await SkillRegistry.execute_action(
            "file_skill_write_file",
            {"filepath": str(path), "content": content},
            grant_token=grant,
            idempotency_key=key,
        )

    first = asyncio.run(write(target, "approved", "agent-file-write-001"))
    replay = asyncio.run(write(target, "approved", "agent-file-write-001"))
    assert first["success"] and replay["success"]
    assert replay["replayed"] is True
    assert target.read_text(encoding="utf-8") == "approved"

    invalid_type = asyncio.run(
        SkillRegistry.execute_action(
            "file_skill_write_file",
            {"filepath": 123, "content": "must not be coerced"},
            grant_token=grant,
            idempotency_key="agent-file-write-bad-type",
        )
    )
    assert not invalid_type["success"]
    assert invalid_type["error_code"] == "INVALID_TOOL_ARGUMENT_TYPES"

    escaped = asyncio.run(write(outside, "denied", "agent-file-write-002"))
    assert not escaped["success"]
    assert escaped["error_code"] == "RESOURCE_NOT_GRANTED"
    assert not outside.exists()
    assert str(target) not in json.dumps(first["receipt"])


def test_memory_write_requires_consent_and_unknown_arguments_are_rejected() -> None:
    manager = _FakeMemoryManager()
    sandbox = _configure(MemoryManagerSkill(manager=manager))
    with pytest.raises(ValueError, match="Explicit consent"):
        sandbox.issue_grant(
            subject="agent-test",
            actions=("system.memory.optimize",),
            resources={"system.memory.optimize": (MEMORY_RESOURCE,)},
            ttl_seconds=30,
        )

    grant = sandbox.issue_grant(
        subject="agent-test",
        actions=("system.memory.optimize",),
        resources={"system.memory.optimize": (MEMORY_RESOURCE,)},
        ttl_seconds=30,
        consented_actions=("system.memory.optimize",),
        consent_reference="user-approved-memory-maintenance",
    )
    invalid = asyncio.run(
        SkillRegistry.execute_action(
            "memory_skill_optimize_memory",
            {"arbitrary_command": "format disk"},
            grant_token=grant,
            idempotency_key="agent-memory-0001",
        )
    )
    assert not invalid["success"]
    assert invalid["error_code"] == "INVALID_TOOL_ARGUMENTS"
    assert manager.calls == 0

    valid = asyncio.run(
        SkillRegistry.execute_action(
            "memory_skill_optimize_memory",
            {},
            grant_token=grant,
            idempotency_key="agent-memory-0002",
        )
    )
    assert valid["success"]
    assert manager.calls == 1


def test_audio_output_requires_explicit_consent_and_dispatch() -> None:
    engine = _FakeSpeechEngine()
    skill = VoiceOutputSkill(engine)
    sandbox = _configure(skill)
    with pytest.raises(CapabilityDenied):
        skill.speak("bypass")
    with pytest.raises(ValueError, match="Explicit consent"):
        sandbox.issue_grant(
            subject="agent-test",
            actions=("device.audio.output",),
            resources={"device.audio.output": (AUDIO_OUTPUT_RESOURCE,)},
            ttl_seconds=30,
        )

    grant = sandbox.issue_grant(
        subject="agent-test",
        actions=("device.audio.output",),
        resources={"device.audio.output": (AUDIO_OUTPUT_RESOURCE,)},
        ttl_seconds=30,
        consented_actions=("device.audio.output",),
        consent_reference="user-approved-audio-output",
    )
    result = asyncio.run(
        SkillRegistry.execute_action(
            "voice_skill_speak",
            {"text": "JAYA ready"},
            grant_token=grant,
            idempotency_key="agent-audio-output-01",
        )
    )
    assert result["success"]
    assert engine.spoken == ["JAYA ready"]
    assert engine.wait_calls == 1
    assert result["receipt"]["consent_digest"]
