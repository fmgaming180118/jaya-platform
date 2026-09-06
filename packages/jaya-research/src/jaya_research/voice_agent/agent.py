"""Voice client for Research with explicit reasoning and capability adapters."""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from typing import Any, Protocol

from jaya_research.capability_boundary import (
    ArbitraryExecutionRejected,
    CapabilityBoundaryError,
    CapabilityGateway,
    request_capability,
)

logger = logging.getLogger("JayaVoice")


class ReasoningGateway(Protocol):
    """Public adapter for a separately running Core reasoning service."""

    def analyze(self, text: str) -> str:
        """Return an analysis without exposing Core implementation objects."""
        ...


class SearchGateway(Protocol):
    """Public adapter for grounded search and answer generation."""

    def answer(self, text: str) -> str:
        """Return a grounded answer for one user question."""
        ...


class SafetyReviewer(Protocol):
    """Public policy adapter used before structured effect requests."""

    def review(self, action: str, arguments: Mapping[str, Any]) -> str | None:
        """Return a rejection reason, or ``None`` when review passes."""
        ...


class VoiceDependencyUnavailable(RuntimeError):
    """Raised when an optional voice dependency was not explicitly provided."""


class JayaVoiceAgent(threading.Thread):
    """Voice front end that never imports Core internals or executes shell text."""

    def __init__(
        self,
        api_key: str | None = None,
        rag_client: Any | None = None,
        *,
        reasoning_gateway: ReasoningGateway | None = None,
        search_gateway: SearchGateway | None = None,
        capability_gateway: CapabilityGateway | None = None,
        safety_reviewer: SafetyReviewer | None = None,
        mouth: Any | None = None,
        enable_audio: bool = False,
    ) -> None:
        super().__init__()
        self.running = False
        self.api_key = api_key
        self.rag_client = rag_client
        self.reasoning_gateway = reasoning_gateway
        self.search_gateway = search_gateway
        self.capability_gateway = capability_gateway
        self.safety_reviewer = safety_reviewer
        self.mouth = mouth
        self._stop_event = threading.Event()
        self.wake_word: Any | None = None
        self.profile_manager: Any | None = None
        if enable_audio:
            self._initialize_audio_components()

    def _initialize_audio_components(self) -> None:
        """Load local audio components only after explicit activation."""
        try:
            from jaya_research.voice_agent.profile_manager import ProfileManager
            from jaya_research.voice_agent.wake_word import WakeWordDetector

            self.wake_word = WakeWordDetector()
            self.profile_manager = ProfileManager()
            if self.mouth is None:
                from jaya_research.voice_agent.tts import JayaMouth

                self.mouth = JayaMouth()
                self.mouth.start()
        except Exception as exc:
            self.wake_word = None
            self.profile_manager = None
            logger.error("Voice component initialization failed: %s", exc)

    def run(self) -> None:
        """Run the explicitly enabled microphone loop."""
        self.running = True
        try:
            self._run_voice_loop()
        except Exception as exc:
            logger.error("Voice loop stopped after an error: %s", exc)
        finally:
            self.running = False

    def stop(self) -> None:
        """Signal the voice loop to stop."""
        self._stop_event.set()
        self.running = False

    def _run_voice_loop(self) -> None:
        """Capture wake-word audio without embedding any action implementation."""
        if self.wake_word is None or self.profile_manager is None:
            raise VoiceDependencyUnavailable(
                "audio was not enabled or voice components are unavailable"
            )
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise VoiceDependencyUnavailable(
                "sounddevice and numpy are required for microphone input"
            ) from exc

        sample_rate = 16_000
        chunk_size = 1_280
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            blocksize=chunk_size,
            dtype="int16",
        ) as stream:
            while not self._stop_event.is_set() and stream.active:
                data, _ = stream.read(chunk_size)
                prediction = self.wake_word.detect(np.asarray(data).flatten())
                if not prediction:
                    continue
                verified, _ = self.profile_manager.verify_speaker(
                    np.asarray(data).flatten()
                )
                if verified:
                    self._speak("Siap, saya mendengarkan.")
                    command = self._capture_command(sample_rate)
                    if command:
                        response = self.handle_command(command)
                        self._speak(response)

    @staticmethod
    def _capture_command(sample_rate: int) -> str | None:
        """Capture one bounded utterance after explicit microphone activation."""
        try:
            import sounddevice as sd
            import speech_recognition as sr
        except ImportError as exc:
            raise VoiceDependencyUnavailable(
                "speech_recognition is required for command capture"
            ) from exc
        recognizer = sr.Recognizer()
        with sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=8_000,
            dtype="int16",
            channels=1,
        ) as stream:
            data, _ = stream.read(sample_rate * 5)
        audio = sr.AudioData(data.tobytes(), sample_rate, 2)
        try:
            return str(recognizer.recognize_google(audio, language="id-ID"))
        except sr.UnknownValueError:
            return None
        except sr.RequestError as exc:
            raise VoiceDependencyUnavailable(
                "speech recognition provider is unavailable"
            ) from exc

    def handle_command(self, text: str) -> str:
        """Route text to public adapters; raw execution is always rejected."""
        command = str(text or "").strip()
        if not command:
            return "Perintah kosong."
        lowered = command.casefold()
        try:
            if "jalankan perintah" in lowered or "eksekusi shell" in lowered:
                raise ArbitraryExecutionRejected(
                    "perintah shell bebas tidak didukung oleh JAYA Research"
                )
            if "lakukan training" in lowered or "pengenalan suara" in lowered:
                return self._request_effect("voice.enrollment", {"profile": "default"})
            if "status sistem" in lowered or "cek cpu" in lowered:
                return self._request_effect("system.status", {})
            if "aplikasi berjalan" in lowered:
                return self._request_effect("process.list", {"limit": 5})
            if "buka aplikasi" in lowered:
                application = lowered.replace("buka aplikasi", "", 1).strip()
                if not application:
                    return "Aplikasi apa yang ingin dibuka?"
                return self._request_effect(
                    "application.open", {"application": application}
                )
            if "logika" in lowered or "analisis" in lowered:
                query = (
                    lowered.replace("logika", "", 1).replace("analisis", "", 1).strip()
                )
                if not query:
                    return "Analisis apa yang Anda perlukan?"
                if self.reasoning_gateway is None:
                    raise VoiceDependencyUnavailable(
                        "reasoning gateway belum dikonfigurasi"
                    )
                return str(self.reasoning_gateway.analyze(query))
            if self.search_gateway is not None:
                return str(self.search_gateway.answer(command))
            if self.rag_client is not None:
                return self.process_query(command)
            raise VoiceDependencyUnavailable("search gateway belum dikonfigurasi")
        except CapabilityBoundaryError as exc:
            return f"Permintaan ditolak: {exc}"
        except VoiceDependencyUnavailable as exc:
            return f"Layanan tidak tersedia: {exc}"

    def _request_effect(
        self,
        action: str,
        arguments: Mapping[str, Any],
    ) -> str:
        if self.safety_reviewer is not None:
            rejection = self.safety_reviewer.review(action, arguments)
            if rejection:
                return f"Permintaan ditolak: {rejection}"
        receipt = request_capability(
            self.capability_gateway,
            action=action,
            arguments=arguments,
        )
        message = receipt.get("message") or receipt.get("status") or "accepted"
        return str(message)

    def _speak(self, text: str) -> None:
        if self.mouth is not None:
            self.mouth.speak(str(text))

    def process_query(self, text: str) -> str:
        """Query an injected Research RAG client without initializing providers."""
        if self.rag_client is None:
            raise VoiceDependencyUnavailable("RAG client belum dikonfigurasi")
        results = self.rag_client.query(text)
        context = ""
        if isinstance(results, Mapping) and "answer" in results:
            context = str(results["answer"])
        elif isinstance(results, list):
            context = "\n".join(
                str(document.get("content", ""))
                for document in results[:2]
                if isinstance(document, Mapping)
            )
        return f"Response based on context: {context[:500]}..."


if __name__ == "__main__":
    raise SystemExit(
        "Inject public reasoning/search/capability adapters before starting voice"
    )
