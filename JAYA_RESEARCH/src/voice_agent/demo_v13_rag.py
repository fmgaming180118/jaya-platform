"""Dependency-injection demo for the Research voice search client."""

from __future__ import annotations

from src.voice_agent.agent import JayaVoiceAgent


class DemoConfigurationError(RuntimeError):
    """Raised when a demo is started without public service adapters."""


def run_demo(agent: JayaVoiceAgent | None = None) -> str:
    """Run one harmless query through a caller-configured voice agent."""
    if agent is None or agent.search_gateway is None:
        raise DemoConfigurationError("inject a public search gateway before the demo")
    response = agent.handle_command("Jelaskan machine learning secara ringkas")
    print(f"[JAYA]: {response}")
    return response


if __name__ == "__main__":
    raise SystemExit("Demo disabled until a public search gateway is injected")
