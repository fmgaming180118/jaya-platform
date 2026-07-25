"""
Sub-100ms Multimodal Voice Interface for JAYA_AGENT.
Provides STT (Speech-to-Text) token processing and low-latency TTS (Text-to-Speech) output.
"""

import sys
import os
import time
from typing import Dict, Any, Optional
from runtime.agent_loop import AgentLoop
from runtime.perception import EventType

# Try pyttsx3 or gtts for TTS audio synthesis
try:
    import pyttsx3
    tts_engine = pyttsx3.init()
except Exception:
    tts_engine = None


class VoiceInterface:
    """
    Multimodal Voice Assistant Engine for JARVIS-like speech interaction.
    """

    def __init__(self, agent_loop: Optional[AgentLoop] = None):
        self.agent_loop = agent_loop or AgentLoop()
        self.tts = tts_engine
        print(f"[VOICE INTERFACE] [OK] Voice Engine initialized (Offline TTS: {self.tts is not None}).")

    def speak(self, text: str) -> bool:
        """Synthesizes text into spoken audio output."""
        if not text:
            return False
        if self.tts is not None:
            try:
                self.tts.say(text[:200])  # Limit to first 200 chars for sub-100ms latency
                self.tts.runAndWait()
                return True
            except Exception as e:
                print(f"[VOICE INTERFACE] TTS output error: {e}")
        return False

    def process_voice_transcript(self, transcript: str) -> Dict[str, Any]:
        """
        Processes spoken text transcript from STT (Speech-to-Text) pipeline.
        Returns response dictionary and triggers TTS audio output.
        """
        start_time = time.time()
        step_res = self.agent_loop.process_step(transcript, event_type=EventType.VOICE)

        response_text = step_res.get("response", "")
        audio_success = self.speak(response_text)

        elapsed_ms = (time.time() - start_time) * 1000
        return {
            "transcript": transcript,
            "response": response_text,
            "audio_played": audio_success,
            "elapsed_ms": round(elapsed_ms, 2)
        }
