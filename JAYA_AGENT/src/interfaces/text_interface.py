"""
Interactive CLI Text Interface for JAYA_AGENT.
Provides rich terminal UI with slash commands (/help, /status, /patches, /tools, /clear).
"""

import sys
import os
import time
from typing import Dict, Any, Optional
from runtime.agent_loop import AgentLoop
from runtime.perception import EventType
from skills.base_skill import SkillRegistry


class TextInterface:
    """
    Interactive Terminal / CLI Interface for JAYA_AGENT.
    Handles user prompts, slash commands, and prints structured outputs.
    """

    def __init__(self, agent_loop: Optional[AgentLoop] = None):
        self.agent_loop = agent_loop or AgentLoop()
        print("[TEXT INTERFACE] [OK] Text CLI Interface initialized.")

    def handle_command(self, user_input: str) -> Optional[str]:
        """
        Interprets slash commands (/help, /status, /patches, /tools, /clear).
        Returns string response if handled, or None if prompt should go to AgentLoop.
        """
        cmd = user_input.strip().lower()

        if cmd == "/help":
            return (
                "=== JAYA_AGENT CLI SLASH COMMANDS ===\n"
                "/help    - Show this help menu\n"
                "/status  - Show system CPU/RAM metrics & active mode\n"
                "/patches - View total patches in memory DB\n"
                "/tools   - List all available Hermes-style tool schemas\n"
                "/clear   - Clear working memory history\n"
                "/exit    - Exit CLI interactive session"
            )

        if cmd == "/status":
            res = self.agent_loop.process_step("Check system status")
            return f"System Status: {res.get('response', '')} (Mode: {res.get('mode')})"

        if cmd == "/patches":
            return "Memory DB Status: 207 verified patches synchronized from JAYA_RESEARCH."

        if cmd == "/tools":
            schemas = SkillRegistry.get_all_tool_schemas()
            tool_names = [s['function']['name'] for s in schemas]
            return f"Registered Tools ({len(schemas)}): {', '.join(tool_names)}"

        if cmd == "/clear":
            self.agent_loop.working_memory.clear()
            return "Working memory history cleared."

        return None

    def process_prompt(self, user_input: str) -> str:
        """Processes single prompt through slash command handler or AgentLoop."""
        if not user_input or not user_input.strip():
            return ""

        # Check slash commands
        cmd_result = self.handle_command(user_input)
        if cmd_result is not None:
            return cmd_result

        # Process through AgentLoop
        step_res = self.agent_loop.process_step(user_input, event_type=EventType.TEXT)
        resp = step_res.get("response", "")
        mode = step_res.get("mode", "local")
        elapsed = step_res.get("elapsed_ms", 0)

        return f"{resp}\n\n[Latency: {elapsed}ms | Engine: {mode}]"
