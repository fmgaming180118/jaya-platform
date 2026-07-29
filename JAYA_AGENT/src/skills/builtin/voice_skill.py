"""Explicitly consented audio-output skill for JAYA_AGENT."""

from __future__ import annotations

from typing import Any

from security.capability_sandbox import require_active_capability
from skills.base_skill import Skill, skill_action

AUDIO_OUTPUT_RESOURCE = "system://audio/output"
_MAX_SPEECH_CHARACTERS = 500


class VoiceOutputSkill(Skill):
    """Speak bounded text only through an injected offline engine."""

    name = "voice_skill"
    description = "Consent-gated audio output"

    def __init__(self, engine: Any) -> None:
        if engine is None or not callable(getattr(engine, "say", None)):
            raise TypeError("Voice output requires an injected speech engine")
        if not callable(getattr(engine, "runAndWait", None)):
            raise TypeError("Speech engine must expose runAndWait")
        self._engine = engine

    @skill_action(
        "speak",
        "Speaks bounded text through the local audio output device",
        params={"text": "str"},
        capability="device.audio.output",
        fixed_resources=(AUDIO_OUTPUT_RESOURCE,),
        timeout_seconds=10.0,
    )
    def speak(self, text: str) -> str:
        require_active_capability(
            "device.audio.output",
            (AUDIO_OUTPUT_RESOURCE,),
        )
        clean_text = text.strip()
        if not clean_text or len(clean_text) > _MAX_SPEECH_CHARACTERS:
            raise ValueError("Speech text is empty or exceeds policy")
        self._engine.say(clean_text)
        self._engine.runAndWait()
        return f"Spoke {len(clean_text)} characters"
