"""Interactive text interface for JAYA Agent."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Protocol

from jaya_agent.runtime.agent_loop import AgentLoop
from jaya_agent.runtime.perception import EventType
from jaya_agent.skills.base_skill import SkillRegistry

logger = logging.getLogger(__name__)


class PatchStateProvider(Protocol):
    """Public provider for verified, Agent-owned patch state."""

    def get_patch_state(self) -> Mapping[str, Any]:
        """Return a state containing ``verified`` and ``verified_count``."""
        ...


class TextInterface:
    """Handle CLI slash commands and pass prompts to the Agent loop."""

    def __init__(
        self,
        agent_loop: AgentLoop | None = None,
        *,
        patch_state_provider: PatchStateProvider | None = None,
    ) -> None:
        self.agent_loop = agent_loop or AgentLoop()
        self.patch_state_provider = patch_state_provider

    def handle_command(self, user_input: str) -> str | None:
        """Handle a slash command, or return ``None`` for normal prompts."""
        command = user_input.strip().lower()

        if command == "/help":
            return (
                "=== JAYA_AGENT CLI SLASH COMMANDS ===\n"
                "/help    - Show this help menu\n"
                "/status  - Show system CPU/RAM metrics & active mode\n"
                "/patches - View verified Agent-owned patch state\n"
                "/tools   - List all available tool schemas\n"
                "/clear   - Clear working memory history\n"
                "/exit    - Exit CLI interactive session"
            )

        if command == "/status":
            result = self.agent_loop.process_step("Check system status")
            return (
                f"System Status: {result.get('response', '')} "
                f"(Mode: {result.get('mode')})"
            )

        if command == "/patches":
            return self._patch_state()

        if command == "/tools":
            schemas = SkillRegistry.get_all_tool_schemas()
            tool_names = [schema["function"]["name"] for schema in schemas]
            return f"Registered Tools ({len(schemas)}): {', '.join(tool_names)}"

        if command == "/clear":
            self.agent_loop.working_memory.clear()
            return "Working memory history cleared."

        return None

    def _patch_state(self) -> str:
        if self.patch_state_provider is None:
            return (
                "Memory DB Status: UNAVAILABLE (patch-state provider not configured)."
            )
        try:
            state = self.patch_state_provider.get_patch_state()
        except Exception as exc:
            logger.warning(
                "Patch-state provider failed (%s)",
                type(exc).__name__,
            )
            return "Memory DB Status: UNAVAILABLE (provider check failed)."
        if not isinstance(state, Mapping) or state.get("verified") is not True:
            return "Memory DB Status: UNAVAILABLE (state is not verified)."
        count = state.get("verified_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return "Memory DB Status: UNAVAILABLE (verified count is invalid)."
        return f"Memory DB Status: {count} verified patches."

    def process_prompt(self, user_input: str) -> str:
        """Process one prompt through a slash command or the Agent loop."""
        if not user_input or not user_input.strip():
            return ""
        command_result = self.handle_command(user_input)
        if command_result is not None:
            return command_result

        step_result = self.agent_loop.process_step(
            user_input,
            event_type=EventType.TEXT,
        )
        response = step_result.get("response", "")
        mode = step_result.get("mode", "local")
        elapsed = step_result.get("elapsed_ms", 0)
        return f"{response}\n\n[Latency: {elapsed}ms | Engine: {mode}]"
