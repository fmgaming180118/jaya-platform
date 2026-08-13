"""
Multi-Modal Foundation Package for JAYA_CORE.

Provides vision processing, audio processing, multi-modal fusion,
and integration with cognitive model adapters.
"""

from __future__ import annotations

from .foundation import (
    ModalityType,
    MultiModalContent,
    VisionResult,
    AudioResult,
    VisionProcessor,
    LLaVAVisionProcessor,
    OpenAIVisionProcessor,
    AudioProcessor,
    WhisperAudioProcessor,
    OpenAIAudioProcessor,
    MultiModalFusion,
    MultiModalCognitiveAdapter,
    create_vision_processor,
    create_audio_processor,
    create_multimodal_adapter,
    get_vision_processor,
    get_audio_processor,
    get_multimodal_adapter,
)

__all__ = [
    "ModalityType",
    "MultiModalContent",
    "VisionResult",
    "AudioResult",
    "VisionProcessor",
    "LLaVAVisionProcessor",
    "OpenAIVisionProcessor",
    "AudioProcessor",
    "WhisperAudioProcessor",
    "OpenAIAudioProcessor",
    "MultiModalFusion",
    "MultiModalCognitiveAdapter",
    "create_vision_processor",
    "create_audio_processor",
    "create_multimodal_adapter",
    "get_vision_processor",
    "get_audio_processor",
    "get_multimodal_adapter",
]