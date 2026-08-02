"""
registry.py — Edge Model Registry, Signature Verification, & Model Rollback.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EdgeModelManifest:
    model_id: str
    version: str
    format: str  # "GGUF_Q4", "ONNX", "PYTORCH_LORA"
    size_mb: float
    sha256_signature: str
    min_ram_mb: int = 512
    privacy_policy_level: str = "HYBRID_ALLOWED"  # "STRICT_LOCAL_ONLY", "HYBRID_ALLOWED"
    supported_platforms: List[str] = field(default_factory=lambda: ["win32", "linux", "android"])
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EdgeModelRegistry:
    """Manages Edge model registration, signature verification, compatibility, and rollback."""

    def __init__(self, max_allowed_size_mb: float = 300.0) -> None:
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
        logger.info("Registered edge model %s (v%s, size=%.1fMB)", manifest.model_id, manifest.version, manifest.size_mb)
        return True

    def verify_signature(self, manifest: EdgeModelManifest, file_bytes: bytes) -> bool:
        computed = hashlib.sha256(file_bytes).hexdigest()
        return computed.lower() == manifest.sha256_signature.lower()

    def get_model(self, model_id: str, version: Optional[str] = None) -> Optional[EdgeModelManifest]:
        if version:
            return self._manifests.get(f"{model_id}:{version}")
        # Find latest active version
        active = [m for m in self._manifests.values() if m.model_id == model_id and m.is_active]
        return active[-1] if active else None

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
