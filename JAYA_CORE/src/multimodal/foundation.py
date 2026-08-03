"""
Multi-Modal Foundation for JAYA_CORE.

Provides:
- Vision processing (image understanding, OCR, visual QA)
- Audio processing (speech-to-text, text-to-speech)
- Multi-modal fusion (combining text, image, audio)
- Model adapters for multi-modal LLMs (LLaVA, GPT-4V, etc.)
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from JAYA_CORE.src.observability import get_structured_logger, record_error
from JAYA_CORE.src.security import get_audit_logger, InputValidator

logger = get_structured_logger(__name__, component="multimodal")
audit_logger = get_audit_logger()


# ============================================================================
# Data Classes
# ============================================================================

class ModalityType(Enum):
    """Supported modalities."""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


@dataclass
class MultiModalContent:
    """Multi-modal content container."""
    modality: ModalityType
    data: Union[str, bytes, np.ndarray]  # Base64 string, bytes, or array
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # For images
    width: Optional[int] = None
    height: Optional[int] = None
    format: Optional[str] = None
    
    # For audio
    sample_rate: Optional[int] = None
    duration: Optional[float] = None
    channels: Optional[int] = None
    
    def to_base64(self) -> str:
        """Convert to base64 string."""
        if isinstance(self.data, str):
            return self.data
        elif isinstance(self.data, bytes):
            return base64.b64encode(self.data).decode('utf-8')
        elif isinstance(self.data, np.ndarray):
            # For images, encode as PNG
            import cv2
            _, buffer = cv2.imencode('.png', self.data)
            return base64.b64encode(buffer).decode('utf-8')
        return ""
    
    @classmethod
    def from_file(cls, file_path: str) -> "MultiModalContent":
        """Load from file."""
        path = Path(file_path)
        suffix = path.suffix.lower()
        
        if suffix in ['.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff']:
            modality = ModalityType.IMAGE
            with open(file_path, 'rb') as f:
                data = f.read()
            # Get image info
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    width, height = img.size
                    format = img.format
            except Exception:
                width = height = None
                format = suffix[1:]
            
            return cls(
                modality=modality,
                data=data,
                width=width,
                height=height,
                format=format,
            )
        
        elif suffix in ['.wav', '.mp3', '.flac', '.ogg', '.m4a']:
            modality = ModalityType.AUDIO
            with open(file_path, 'rb') as f:
                data = f.read()
            return cls(
                modality=modality,
                data=data,
            )
        
        elif suffix in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
            modality = ModalityType.VIDEO
            with open(file_path, 'rb') as f:
                data = f.read()
            return cls(
                modality=modality,
                data=data,
            )
        
        else:
            # Default to text
            modality = ModalityType.TEXT
            with open(file_path, 'r', encoding='utf-8') as f:
                data = f.read()
            return cls(
                modality=modality,
                data=data,
            )


@dataclass
class VisionResult:
    """Result from vision processing."""
    description: str
    objects: List[Dict[str, Any]] = field(default_factory=list)
    text: str = ""  # OCR text
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AudioResult:
    """Result from audio processing."""
    transcript: str = ""
    language: str = ""
    duration: float = 0.0
    segments: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Vision Processing
# ============================================================================

class VisionProcessor(ABC):
    """Abstract vision processor."""
    
    @abstractmethod
    def describe_image(self, image: MultiModalContent, prompt: str = None) -> VisionResult:
        """Describe image content."""
        pass
    
    @abstractmethod
    def extract_text(self, image: MultiModalContent) -> str:
        """Extract text from image (OCR)."""
        pass
    
    @abstractmethod
    def detect_objects(self, image: MultiModalContent) -> List[Dict[str, Any]]:
        """Detect objects in image."""
        pass
    
    @abstractmethod
    def answer_visual_question(self, image: MultiModalContent, question: str) -> str:
        """Answer question about image."""
        pass


class LLaVAVisionProcessor(VisionProcessor):
    """LLaVA-based vision processor."""
    
    def __init__(self, model_path: str = None, use_ollama: bool = False, ollama_model: str = "llava:7b"):
        self.model_path = model_path
        self.use_ollama = use_ollama
        self.ollama_model = ollama_model
        self._model = None
        self._processor = None
    
    def _load_model(self):
        """Load LLaVA model."""
        if self.use_ollama:
            # Use Ollama API
            logger.info("Using Ollama for LLaVA", model=self.ollama_model)
            return
        
        try:
            # Try to load local LLaVA model
            from transformers import LlavaNextProcessor, LlavaNextForConditionalGeneration
            import torch
            
            model_id = self.model_path or "llava-hf/llava-v1.6-mistral-7b-hf"
            self._processor = LlavaNextProcessor.from_pretrained(model_id)
            self._model = LlavaNextForConditionalGeneration.from_pretrained(
                model_id,
                torch_dtype=torch.float16,
                device_map="auto",
            )
            logger.info("Loaded LLaVA model", model=model_id)
        except ImportError:
            logger.warning("transformers not available for LLaVA")
        except Exception as e:
            logger.error("Failed to load LLaVA model", error=str(e))
    
    def describe_image(self, image: MultiModalContent, prompt: str = None) -> VisionResult:
        """Describe image using LLaVA."""
        prompt = prompt or "Describe this image in detail."
        
        if self.use_ollama:
            return self._ollama_vision(image, prompt)
        
        if not self._model:
            self._load_model()
        
        if not self._model:
            return VisionResult(description="Vision model not available", confidence=0.0)
        
        try:
            import torch
            from PIL import Image
            import io
            
            # Load image
            if isinstance(image.data, str):
                img_data = base64.b64decode(image.data)
            else:
                img_data = image.data
            
            pil_image = Image.open(io.BytesIO(img_data)).convert("RGB")
            
            # Process
            conversation = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image"},
                    ],
                },
            ]
            
            prompt_text = self._processor.apply_chat_template(conversation, add_generation_prompt=True)
            inputs = self._processor(pil_image, prompt_text, return_tensors="pt").to(self._model.device)
            
            with torch.no_grad():
                output = self._model.generate(**inputs, max_new_tokens=512)
            
            response = self._processor.decode(output[0], skip_special_tokens=True)
            # Extract assistant response
            if "ASSISTANT:" in response:
                description = response.split("ASSISTANT:")[-1].strip()
            else:
                description = response
            
            return VisionResult(description=description, confidence=0.9)
            
        except Exception as e:
            logger.error("LLaVA description failed", error=str(e))
            return VisionResult(description=f"Error: {str(e)}", confidence=0.0)
    
    def _ollama_vision(self, image: MultiModalContent, prompt: str) -> VisionResult:
        """Use Ollama for vision."""
        import requests
        
        try:
            b64_image = image.to_base64()
            
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "images": [b64_image],
                    "stream": False,
                },
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()
            
            return VisionResult(
                description=result.get("response", ""),
                confidence=0.85,
            )
        except Exception as e:
            logger.error("Ollama vision failed", error=str(e))
            return VisionResult(description=f"Error: {str(e)}", confidence=0.0)
    
    def extract_text(self, image: MultiModalContent) -> str:
        """Extract text using LLaVA."""
        result = self.describe_image(image, "Extract all text from this image. Return only the text content.")
        return result.description
    
    def detect_objects(self, image: MultiModalContent) -> List[Dict[str, Any]]:
        """Detect objects using LLaVA."""
        result = self.describe_image(image, "List all objects in this image with their locations. Return as JSON array.")
        try:
            import json
            return json.loads(result.description)
        except Exception:
            return [{"description": result.description}]
    
    def answer_visual_question(self, image: MultiModalContent, question: str) -> str:
        """Answer visual question."""
        result = self.describe_image(image, question)
        return result.description


class OpenAIVisionProcessor(VisionProcessor):
    """OpenAI GPT-4V vision processor."""
    
    def __init__(self, api_key: str = None, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client
    
    def _encode_image(self, image: MultiModalContent) -> str:
        """Encode image for OpenAI API."""
        return image.to_base64()
    
    def describe_image(self, image: MultiModalContent, prompt: str = None) -> VisionResult:
        prompt = prompt or "Describe this image in detail."
        
        try:
            client = self._get_client()
            b64_image = self._encode_image(image)
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                            },
                        ],
                    },
                ],
                max_tokens=512,
            )
            
            return VisionResult(
                description=response.choices[0].message.content,
                confidence=0.95,
            )
        except Exception as e:
            logger.error("OpenAI vision failed", error=str(e))
            return VisionResult(description=f"Error: {str(e)}", confidence=0.0)
    
    def extract_text(self, image: MultiModalContent) -> str:
        result = self.describe_image(image, "Extract all text from this image. Return only the text content.")
        return result.description
    
    def detect_objects(self, image: MultiModalContent) -> List[Dict[str, Any]]:
        result = self.describe_image(image, "List all objects in this image with bounding boxes if possible. Return as JSON.")
        try:
            import json
            return json.loads(result.description)
        except Exception:
            return [{"description": result.description}]
    
    def answer_visual_question(self, image: MultiModalContent, question: str) -> str:
        result = self.describe_image(image, question)
        return result.description


# ============================================================================
# Audio Processing
# ============================================================================

class AudioProcessor(ABC):
    """Abstract audio processor."""
    
    @abstractmethod
    def transcribe(self, audio: MultiModalContent, language: str = None) -> AudioResult:
        """Transcribe audio to text."""
        pass
    
    @abstractmethod
    def synthesize(self, text: str, voice: str = None) -> MultiModalContent:
        """Synthesize text to speech."""
        pass


class WhisperAudioProcessor(AudioProcessor):
    """Whisper-based audio processor."""
    
    def __init__(self, model_size: str = "base", use_ollama: bool = False):
        self.model_size = model_size
        self.use_ollama = use_ollama
        self._model = None
    
    def _load_model(self):
        """Load Whisper model."""
        if self.use_ollama:
            return
        
        try:
            import whisper
            self._model = whisper.load_model(self.model_size)
            logger.info("Loaded Whisper model", size=self.model_size)
        except ImportError:
            logger.warning("whisper not available")
        except Exception as e:
            logger.error("Failed to load Whisper", error=str(e))
    
    def transcribe(self, audio: MultiModalContent, language: str = None) -> AudioResult:
        """Transcribe audio using Whisper."""
        if self.use_ollama:
            return self._ollama_transcribe(audio, language)
        
        if not self._model:
            self._load_model()
        
        if not self._model:
            return AudioResult(transcript="Model not available", confidence=0.0)
        
        try:
            # Save audio to temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                if isinstance(audio.data, str):
                    tmp.write(base64.b64decode(audio.data))
                else:
                    tmp.write(audio.data)
                tmp_path = tmp.name
            
            # Transcribe
            result = self._model.transcribe(tmp_path, language=language)
            
            # Cleanup
            os.unlink(tmp_path)
            
            return AudioResult(
                transcript=result["text"],
                language=result.get("language", ""),
                duration=result.get("duration", 0),
                segments=result.get("segments", []),
                confidence=0.9,
            )
        except Exception as e:
            logger.error("Whisper transcription failed", error=str(e))
            return AudioResult(transcript=f"Error: {str(e)}", confidence=0.0)
    
    def _ollama_transcribe(self, audio: MultiModalContent, language: str = None) -> AudioResult:
        """Use Ollama for transcription (if supported)."""
        # Ollama doesn't directly support audio transcription yet
        # This would need a separate service
        return AudioResult(transcript="Ollama transcription not implemented", confidence=0.0)
    
    def synthesize(self, text: str, voice: str = None) -> MultiModalContent:
        """Synthesize speech (placeholder - would use TTS)."""
        # Would integrate with TTS like Coqui, Edge TTS, etc.
        return MultiModalContent(
            modality=ModalityType.AUDIO,
            data=b"",
            metadata={"text": text, "voice": voice, "note": "TTS not implemented"},
        )


class OpenAIAudioProcessor(AudioProcessor):
    """OpenAI Whisper/TTS audio processor."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client
    
    def transcribe(self, audio: MultiModalContent, language: str = None) -> AudioResult:
        try:
            client = self._get_client()
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                if isinstance(audio.data, str):
                    tmp.write(base64.b64decode(audio.data))
                else:
                    tmp.write(audio.data)
                tmp_path = tmp.name
            
            with open(tmp_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=language,
                )
            
            os.unlink(tmp_path)
            
            return AudioResult(
                transcript=transcript.text,
                language=language or "",
                confidence=0.95,
            )
        except Exception as e:
            logger.error("OpenAI transcription failed", error=str(e))
            return AudioResult(transcript=f"Error: {str(e)}", confidence=0.0)
    
    def synthesize(self, text: str, voice: str = "alloy") -> MultiModalContent:
        try:
            client = self._get_client()
            
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
            )
            
            audio_data = response.content
            
            return MultiModalContent(
                modality=ModalityType.AUDIO,
                data=audio_data,
                metadata={"text": text, "voice": voice},
            )
        except Exception as e:
            logger.error("OpenAI TTS failed", error=str(e))
            return MultiModalContent(
                modality=ModalityType.AUDIO,
                data=b"",
                metadata={"error": str(e)},
            )


# ============================================================================
# Multi-Modal Fusion
# ============================================================================

class MultiModalFusion:
    """Fuse multiple modalities for unified understanding."""
    
    def __init__(
        self,
        vision_processor: VisionProcessor = None,
        audio_processor: AudioProcessor = None,
    ):
        self.vision_processor = vision_processor or LLaVAVisionProcessor(use_ollama=True)
        self.audio_processor = audio_processor or WhisperAudioProcessor(use_ollama=True)
    
    def process_multimodal(
        self,
        contents: List[MultiModalContent],
        text_prompt: str = "",
    ) -> Dict[str, Any]:
        """Process multiple modalities together."""
        results = {
            "text": text_prompt,
            "vision": [],
            "audio": [],
            "fused_description": "",
        }
        
        # Process each modality
        for content in contents:
            if content.modality == ModalityType.IMAGE:
                vision_result = self.vision_processor.describe_image(content, text_prompt)
                results["vision"].append({
                    "description": vision_result.description,
                    "objects": vision_result.objects,
                    "text": vision_result.text,
                })
            
            elif content.modality == ModalityType.AUDIO:
                audio_result = self.audio_processor.transcribe(content)
                results["audio"].append({
                    "transcript": audio_result.transcript,
                    "language": audio_result.language,
                })
        
        # Fuse descriptions
        fused_parts = []
        if text_prompt:
            fused_parts.append(f"User query: {text_prompt}")
        
        for v in results["vision"]:
            fused_parts.append(f"Image: {v['description']}")
        
        for a in results["audio"]:
            fused_parts.append(f"Audio: {a['transcript']}")
        
        results["fused_description"] = "\n\n".join(fused_parts)
        
        return results
    
    def answer_multimodal_question(
        self,
        contents: List[MultiModalContent],
        question: str,
    ) -> str:
        """Answer question using all modalities."""
        # Process each modality with the question
        context_parts = [f"Question: {question}"]
        
        for content in contents:
            if content.modality == ModalityType.IMAGE:
                answer = self.vision_processor.answer_visual_question(content, question)
                context_parts.append(f"Visual answer: {answer}")
            
            elif content.modality == ModalityType.AUDIO:
                transcript = self.audio_processor.transcribe(content).transcript
                context_parts.append(f"Audio transcript: {transcript}")
        
        # In a real implementation, this would feed to an LLM
        return "\n\n".join(context_parts)


# ============================================================================
# Multi-Modal Adapter for Cognitive Model
# ============================================================================

class MultiModalCognitiveAdapter:
    """Adapter to integrate multi-modal processing with cognitive model."""
    
    def __init__(self, base_adapter=None):
        self.base_adapter = base_adapter
        self.fusion = MultiModalFusion()
    
    def generate_with_vision(
        self,
        prompt: str,
        images: List[MultiModalContent],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Generate response with image understanding."""
        # Process images
        vision_results = []
        for img in images:
            result = self.fusion.vision_processor.describe_image(img, prompt)
            vision_results.append(result.description)
        
        # Combine with prompt
        enhanced_prompt = prompt
        if vision_results:
            enhanced_prompt = f"{prompt}\n\nImage context:\n" + "\n".join(vision_results)
        
        # Generate using base adapter
        if self.base_adapter:
            response = self.base_adapter.generate(enhanced_prompt, context)
            return {
                "text": response.text if hasattr(response, 'text') else str(response),
                "vision_context": vision_results,
            }
        
        return {
            "text": enhanced_prompt,
            "vision_context": vision_results,
        }
    
    def generate_with_audio(
        self,
        prompt: str,
        audio: MultiModalContent,
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Generate response with audio understanding."""
        # Transcribe audio
        transcript = self.fusion.audio_processor.transcribe(audio).transcript
        
        enhanced_prompt = f"{prompt}\n\nAudio transcript: {transcript}"
        
        if self.base_adapter:
            response = self.base_adapter.generate(enhanced_prompt, context)
            return {
                "text": response.text if hasattr(response, 'text') else str(response),
                "audio_transcript": transcript,
            }
        
        return {
            "text": enhanced_prompt,
            "audio_transcript": transcript,
        }
    
    def generate_multimodal(
        self,
        prompt: str,
        images: List[MultiModalContent] = None,
        audio: List[MultiModalContent] = None,
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Generate response with multiple modalities."""
        contents = []
        if images:
            contents.extend(images)
        if audio:
            contents.extend(audio)
        
        fused = self.fusion.process_multimodal(contents, prompt)
        
        if self.base_adapter:
            response = self.base_adapter.generate(fused["fused_description"], context)
            return {
                "text": response.text if hasattr(response, 'text') else str(response),
                "fused_context": fused,
            }
        
        return {
            "text": fused["fused_description"],
            "fused_context": fused,
        }


# ============================================================================
# Factory Functions
# ============================================================================

def create_vision_processor(
    provider: str = "llava",
    **kwargs
) -> VisionProcessor:
    """Create vision processor."""
    if provider.lower() == "llava":
        return LLaVAVisionProcessor(**kwargs)
    elif provider.lower() == "openai":
        return OpenAIVisionProcessor(**kwargs)
    else:
        raise ValueError(f"Unknown vision provider: {provider}")


def create_audio_processor(
    provider: str = "whisper",
    **kwargs
) -> AudioProcessor:
    """Create audio processor."""
    if provider.lower() == "whisper":
        return WhisperAudioProcessor(**kwargs)
    elif provider.lower() == "openai":
        return OpenAIAudioProcessor(**kwargs)
    else:
        raise ValueError(f"Unknown audio provider: {provider}")


def create_multimodal_adapter(
    base_adapter=None,
    vision_provider: str = "llava",
    audio_provider: str = "whisper",
    **kwargs
) -> MultiModalCognitiveAdapter:
    """Create multi-modal cognitive adapter."""
    vision = create_vision_processor(vision_provider, **kwargs)
    audio = create_audio_processor(audio_provider, **kwargs)
    fusion = MultiModalFusion(vision, audio)
    return MultiModalCognitiveAdapter(base_adapter)


# ============================================================================
# Default Instances
# ============================================================================

_vision_processor: Optional[VisionProcessor] = None
_audio_processor: Optional[AudioProcessor] = None
_multimodal_adapter: Optional[MultiModalCognitiveAdapter] = None


def get_vision_processor() -> VisionProcessor:
    """Get default vision processor."""
    global _vision_processor
    if _vision_processor is None:
        _vision_processor = create_vision_processor("llava", use_ollama=True)
    return _vision_processor


def get_audio_processor() -> AudioProcessor:
    """Get default audio processor."""
    global _audio_processor
    if _audio_processor is None:
        _audio_processor = create_audio_processor("whisper", use_ollama=True)
    return _audio_processor


def get_multimodal_adapter(base_adapter=None) -> MultiModalCognitiveAdapter:
    """Get default multi-modal adapter."""
    global _multimodal_adapter
    if _multimodal_adapter is None:
        _multimodal_adapter = create_multimodal_adapter(base_adapter)
    return _multimodal_adapter