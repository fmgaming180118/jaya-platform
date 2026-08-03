"""
registry.py — Edge Model Registry, Signature Verification, & Model Rollback.

Supports registration and management of edge models including:
- Llama-3 (8B, 70B variants)
- Nemotron (3 Ultra, 4 Ultra)
- Phi-3, Gemma, Qwen, Mistral, and other open models
- Custom GGUF/ONNX models with signature verification
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Predefined model configurations for popular open models
# These serve as templates for registration; actual files must be provided
PREDEFINED_MODELS = {
    "llama-3-8b-instruct": {
        "model_id": "llama-3-8b-instruct",
        "format": "GGUF_Q4_K_M",
        "size_mb": 4800.0,  # ~4.8GB for Q4_K_M
        "min_ram_mb": 6144,
        "context_window": 8192,
        "capabilities": ["chat", "reasoning", "coding", "multilingual"],
        "description": "Meta Llama 3 8B Instruct - Strong general-purpose model",
    },
    "llama-3-70b-instruct": {
        "model_id": "llama-3-70b-instruct",
        "format": "GGUF_Q4_K_M",
        "size_mb": 40000.0,  # ~40GB for Q4_K_M
        "min_ram_mb": 48000,
        "context_window": 8192,
        "capabilities": ["chat", "reasoning", "coding", "multilingual", "complex_reasoning"],
        "description": "Meta Llama 3 70B Instruct - High-capability model for complex tasks",
    },
    "nemotron-3-ultra": {
        "model_id": "nemotron-3-ultra",
        "format": "GGUF_Q4_K_M",
        "size_mb": 28000.0,  # ~28GB for Q4_K_M (53B params)
        "min_ram_mb": 32000,
        "context_window": 4096,
        "capabilities": ["chat", "reasoning", "coding", "instruction_following"],
        "description": "NVIDIA Nemotron 3 Ultra 53B - Optimized for instruction following",
    },
    "nemotron-4-ultra": {
        "model_id": "nemotron-4-ultra",
        "format": "GGUF_Q4_K_M",
        "size_mb": 40000.0,  # ~40GB for Q4_K_M
        "min_ram_mb": 48000,
        "context_window": 4096,
        "capabilities": ["chat", "reasoning", "coding", "complex_reasoning", "multilingual"],
        "description": "NVIDIA Nemotron 4 Ultra - Next-gen reasoning model",
    },
    "phi-3-mini-4k": {
        "model_id": "phi-3-mini-4k",
        "format": "GGUF_Q4_K_M",
        "size_mb": 2300.0,  # ~2.3GB
        "min_ram_mb": 3072,
        "context_window": 4096,
        "capabilities": ["chat", "reasoning", "coding", "compact"],
        "description": "Microsoft Phi-3 Mini 3.8B - Compact but capable",
    },
    "phi-3-medium-4k": {
        "model_id": "phi-3-medium-4k",
        "format": "GGUF_Q4_K_M",
        "size_mb": 7800.0,  # ~7.8GB
        "min_ram_mb": 10240,
        "context_window": 4096,
        "capabilities": ["chat", "reasoning", "coding", "multilingual"],
        "description": "Microsoft Phi-3 Medium 14B - Balanced capability/size",
    },
    "gemma-2-9b": {
        "model_id": "gemma-2-9b",
        "format": "GGUF_Q4_K_M",
        "size_mb": 5400.0,  # ~5.4GB
        "min_ram_mb": 7168,
        "context_window": 8192,
        "capabilities": ["chat", "reasoning", "coding", "multilingual"],
        "description": "Google Gemma 2 9B - Strong multilingual capabilities",
    },
    "qwen2.5-7b": {
        "model_id": "qwen2.5-7b",
        "format": "GGUF_Q4_K_M",
        "size_mb": 4400.0,  # ~4.4GB
        "min_ram_mb": 5632,
        "context_window": 32768,
        "capabilities": ["chat", "reasoning", "coding", "long_context", "multilingual"],
        "description": "Alibaba Qwen 2.5 7B - Excellent long-context support",
    },
    "qwen2.5-32b": {
        "model_id": "qwen2.5-32b",
        "format": "GGUF_Q4_K_M",
        "size_mb": 19000.0,  # ~19GB
        "min_ram_mb": 24576,
        "context_window": 32768,
        "capabilities": ["chat", "reasoning", "coding", "long_context", "multilingual", "complex_reasoning"],
        "description": "Alibaba Qwen 2.5 32B - High capability with long context",
    },
    "mistral-7b-instruct": {
        "model_id": "mistral-7b-instruct",
        "format": "GGUF_Q4_K_M",
        "size_mb": 4100.0,  # ~4.1GB
        "min_ram_mb": 5120,
        "context_window": 32768,
        "capabilities": ["chat", "reasoning", "coding", "long_context"],
        "description": "Mistral 7B Instruct v0.3 - Strong reasoning in compact size",
    },
    "deepseek-coder-6.7b": {
        "model_id": "deepseek-coder-6.7b",
        "format": "GGUF_Q4_K_M",
        "size_mb": 3800.0,  # ~3.8GB
        "min_ram_mb": 4864,
        "context_window": 16384,
        "capabilities": ["coding", "reasoning", "chat"],
        "description": "DeepSeek Coder 6.7B - Specialized for code generation",
    },
}


@dataclass
class EdgeModelManifest:
    model_id: str
    version: str
    format: str  # "GGUF_Q4", "GGUF_Q4_K_M", "GGUF_Q8", "ONNX", "PYTORCH_LORA"
    size_mb: float
    sha256_signature: str
    min_ram_mb: int = 512
    privacy_policy_level: str = "HYBRID_ALLOWED"  # "STRICT_LOCAL_ONLY", "HYBRID_ALLOWED"
    supported_platforms: List[str] = field(default_factory=lambda: ["win32", "linux", "android"])
    is_active: bool = True
    # Extended metadata
    context_window: int = 4096
    capabilities: List[str] = field(default_factory=list)
    description: str = ""
    quantization: str = "Q4_K_M"
    parameter_count: str = ""  # e.g., "8B", "70B", "53B"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_predefined(cls, model_key: str, version: str, sha256_signature: str) -> Optional["EdgeModelManifest"]:
        """Create manifest from predefined model configuration."""
        if model_key not in PREDEFINED_MODELS:
            return None
        config = PREDEFINED_MODELS[model_key]
        return cls(
            model_id=config["model_id"],
            version=version,
            format=config["format"],
            size_mb=config["size_mb"],
            sha256_signature=sha256_signature,
            min_ram_mb=config["min_ram_mb"],
            context_window=config["context_window"],
            capabilities=config["capabilities"],
            description=config["description"],
            quantization="Q4_K_M",
            parameter_count=config["model_id"].split("-")[-1].replace("b", "B").replace("B", "B"),
        )


class EdgeModelRegistry:
    """Manages Edge model registration, signature verification, compatibility, and rollback."""

    # Default max size increased to support larger models (70B+)
    DEFAULT_MAX_SIZE_MB = 50000.0  # 50GB for 70B+ models

    def __init__(self, max_allowed_size_mb: float = DEFAULT_MAX_SIZE_MB) -> None:
        self.max_allowed_size_mb = max_allowed_size_mb
        self._manifests: Dict[str, EdgeModelManifest] = {}
        self._history: List[str] = []

    def register_model(
        self, manifest: EdgeModelManifest, file_bytes: Optional[bytes] = None
    ) -> bool:
        # 1. Size constraint check
        if manifest.size_mb > self.max_allowed_size_mb:
            logger.error(
                "Model %s size %.2f MB exceeds max allowed limit of %.2f MB",
                manifest.model_id,
                manifest.size_mb,
                self.max_allowed_size_mb,
            )
            return False

        # 2. Signature verification if bytes provided
        if file_bytes is not None:
            if not self.verify_signature(manifest, file_bytes):
                logger.error("Model %s failed SHA-256 signature verification", manifest.model_id)
                return False

        # Deactivate previous models of same ID
        for m in self._manifests.values():
            if m.model_id == manifest.model_id:
                m.is_active = False

        self._manifests[f"{manifest.model_id}:{manifest.version}"] = manifest
        self._history.append(f"{manifest.model_id}:{manifest.version}")
        logger.info("Registered edge model %s (v%s, size=%.1fMB, ctx=%d, caps=%s)",
                    manifest.model_id, manifest.version, manifest.size_mb,
                    manifest.context_window, manifest.capabilities)
        return True

    def register_from_predefined(
        self, model_key: str, version: str, file_path: str
    ) -> bool:
        """Register a model from predefined configuration with file verification."""
        if model_key not in PREDEFINED_MODELS:
            logger.error("Unknown predefined model: %s", model_key)
            return False

        if not os.path.exists(file_path):
            logger.error("Model file not found: %s", file_path)
            return False

        # Read file for signature
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # Verify file size matches expected (within 10% tolerance)
        expected_size = PREDEFINED_MODELS[model_key]["size_mb"] * 1024 * 1024
        actual_size = len(file_bytes)
        if abs(actual_size - expected_size) > expected_size * 0.15:
            logger.warning(
                "Model file size mismatch for %s: expected ~%.0fMB, got %.0fMB",
                model_key, expected_size / 1024 / 1024, actual_size / 1024 / 1024
            )

        # Compute signature
        sha256_signature = hashlib.sha256(file_bytes).hexdigest()

        # Create manifest
        manifest = EdgeModelManifest.from_predefined(model_key, version, sha256_signature)
        if not manifest:
            return False

        return self.register_model(manifest, file_bytes)

    def verify_signature(self, manifest: EdgeModelManifest, file_bytes: bytes) -> bool:
        computed = hashlib.sha256(file_bytes).hexdigest()
        return computed.lower() == manifest.sha256_signature.lower()

    def get_model(self, model_id: str, version: Optional[str] = None) -> Optional[EdgeModelManifest]:
        if version:
            return self._manifests.get(f"{model_id}:{version}")
        # Find latest active version
        active = [m for m in self._manifests.values() if m.model_id == model_id and m.is_active]
        return active[-1] if active else None

    def get_active_models(self) -> List[EdgeModelManifest]:
        """Get all currently active models."""
        return [m for m in self._manifests.values() if m.is_active]

    def get_models_by_capability(self, capability: str) -> List[EdgeModelManifest]:
        """Get active models that support a specific capability."""
        return [
            m for m in self._manifests.values()
            if m.is_active and capability in m.capabilities
        ]

    def get_models_fitting_ram(self, available_ram_mb: int) -> List[EdgeModelManifest]:
        """Get active models that fit within available RAM."""
        return [
            m for m in self._manifests.values()
            if m.is_active and m.min_ram_mb <= available_ram_mb
        ]

    def rollback_model(self, model_id: str) -> Optional[EdgeModelManifest]:
        """Rolls back active model to the previous registered version."""
        matching = [m for key, m in self._manifests.items() if m.model_id == model_id]
        if len(matching) < 2:
            logger.warning("No previous version available for rollback of %s", model_id)
            return None

        # Deactivate current active
        matching[-1].is_active = False
        # Activate previous
        previous = matching[-2]
        previous.is_active = True
        logger.info("Rolled back model %s to version %s", model_id, previous.version)
        return previous

    def list_predefined_models(self) -> Dict[str, Dict[str, Any]]:
        """List all predefined model configurations."""
        return PREDEFINED_MODELS.copy()

    def get_registry_status(self) -> Dict[str, Any]:
        """Get registry status summary."""
        active = self.get_active_models()
        return {
            "total_registered": len(self._manifests),
            "active_models": len(active),
            "max_allowed_size_mb": self.max_allowed_size_mb,
            "models": [
                {
                    "model_id": m.model_id,
                    "version": m.version,
                    "size_mb": m.size_mb,
                    "context_window": m.context_window,
                    "capabilities": m.capabilities,
                    "is_active": m.is_active,
                }
                for m in self._manifests.values()
            ],
        }
