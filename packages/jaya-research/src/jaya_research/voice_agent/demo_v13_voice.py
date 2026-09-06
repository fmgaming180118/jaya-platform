"""Dependency-injection demo for reasoning and safety voice adapters."""

from __future__ import annotations

from jaya_research.voice_agent.agent import JayaVoiceAgent


class DemoConfigurationError(RuntimeError):
    """Raised when a demo is started without public service adapters."""


def run_demo(agent: JayaVoiceAgent | None = None) -> tuple[str, str]:
    """Exercise reasoning and prove that arbitrary shell text is rejected."""
    if agent is None or agent.reasoning_gateway is None:
        raise DemoConfigurationError(
            "inject a public reasoning gateway before the demo"
        )
    analysis = agent.handle_command("Analisis apakah 1 AND 1 bernilai benar")
    rejection = agent.handle_command("eksekusi shell hapus semua file")
    print(f"[JAYA]: {analysis}")
    print(f"[SAFETY]: {rejection}")
    return analysis, rejection


if __name__ == "__main__":
    raise SystemExit("Demo disabled until public adapters are injected")
