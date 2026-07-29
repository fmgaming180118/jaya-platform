"""Voice transcript input without implicit audio-device side effects."""

from __future__ import annotations

import time
from typing import Any

from runtime.agent_loop import AgentLoop
from runtime.perception import EventType


class VoiceInterface:
    """Process transcripts; audio output requires a separate capability tool."""

    def __init__(self, agent_loop: AgentLoop | None = None) -> None:
        self.agent_loop = agent_loop or AgentLoop()

    def speak(self, text: str) -> bool:
        """Compatibility method that cannot bypass the audio capability tool."""

        del text
        return False

    def process_voice_transcript(self, transcript: str) -> dict[str, Any]:
        """Process STT text without automatically touching an audio device."""

        start_time = time.time()
        result = self.agent_loop.process_step(
            transcript,
            event_type=EventType.VOICE,
        )
        return {
            "transcript": transcript,
            "response": result.get("response", ""),
            "audio_played": False,
            "audio_status": "CAPABILITY_GRANT_REQUIRED",
            "elapsed_ms": round((time.time() - start_time) * 1000, 2),
        }
