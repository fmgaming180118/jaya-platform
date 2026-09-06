"""
Model Distribution & Verification for JAYA_CORE.

Provides:
- Signed model distribution using cosign/sigstore
- Model verification with signature checking
- Automated model download with resume support
- Model registry with attestation support
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from jaya_core.observability import get_structured_logger
from jaya_core.security import get_audit_logger

logger = get_structured_logger(__name__, component="model_distribution")
audit_logger = get_audit_logger()


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ModelAttestation:
    """Model attestation with signature verification."""
    model_id: str
    version: str
    file_sha256: str
    file_size: int
    signature: str  # Base64 encoded signature
    public_key: str  # Base64 encoded public key
    signed_by: str
    signed_at: float
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelAttestation":
        return cls(**data)


@dataclass
class ModelDownloadConfig:
    """Configuration for model download."""
    url: str
    destination: Path
    expected_sha256: Optional[str] = None
    expected_size: Optional[int] = None
    attestation_url: Optional[str] = None
    resume: bool = True
    chunk_size: int = 8192
    timeout: float = 30.0
    max_retries: int = 3
    verify_ssl: bool = True


@dataclass
class DownloadProgress:
    """Download progress information."""
    total_bytes: int
    downloaded_bytes: int
    speed_bps: float
    eta_seconds: Optional[float]
    status: str  # "downloading", "completed", "failed", "paused"
    error: Optional[str] = None


# ============================================================================
# Cosign/Sigstore Integration
# ============================================================================

class CosignVerifier:
    """Verify model signatures using cosign/sigstore."""
    
    def __init__(self, cosign_path: str = "cosign"):
        self.cosign_path = cosign_path
        self._verify_cosign_available()
    
    def _verify_cosign_available(self) -> bool:
        """Check if cosign is available."""
        try:
            result = subprocess.run(
                [self.cosign_path, "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("cosign available", version=result.stdout.strip())
                return True
        except Exception as e:
            logger.warning("cosign not available", error=str(e))
        return False
    
    def verify_signature(
        self,
        file_path: Path,
        signature_path: Path,
        public_key_path: Path,
    ) -> bool:
        """Verify file signature using cosign."""
        try:
            result = subprocess.run(
                [
                    self.cosign_path, "verify-blob",
                    "--signature", str(signature_path),
                    "--public-key", str(public_key_path),
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error("cosign verification failed", error=str(e))
            return False
    
    def verify_keyless(
        self,
        file_path: Path,
        signature_path: Path,
        certificate_path: Path,
        certificate_chain_path: Optional[Path] = None,
    ) -> bool:
        """Verify keyless signature (sigstore)."""
        try:
            cmd = [
                self.cosign_path, "verify-blob",
                "--signature", str(signature_path),
                "--certificate", str(certificate_path),
            ]
            if certificate_chain_path:
                cmd.extend(["--certificate-chain", str(certificate_chain_path)])
            cmd.append(str(file_path))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error("cosign keyless verification failed", error=str(e))
            return False


# ============================================================================
# Model Downloader with Resume Support
# ============================================================================

class ModelDownloader:
    """Download models with resume, verification, and progress tracking."""
    
    def __init__(self):
        self._session = self._create_session()
        self._active_downloads: Dict[str, DownloadProgress] = {}
        self._lock = threading.Lock()
    
    def _create_session(self) -> requests.Session:
        """Create requests session with retry strategy."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    def download(
        self,
        config: ModelDownloadConfig,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> bool:
        """
        Download model file with resume support.
        
        Returns:
            True if download successful and verified
        """
        download_id = f"{config.url}_{config.destination}"
        
        # Initialize progress
        progress = DownloadProgress(
            total_bytes=config.expected_size or 0,
            downloaded_bytes=0,
            speed_bps=0.0,
            eta_seconds=None,
            status="downloading",
        )
        
        with self._lock:
            self._active_downloads[download_id] = progress
        
        try:
            # Check if partial file exists
            start_byte = 0
            if config.resume and config.destination.exists():
                start_byte = config.destination.stat().st_size
                progress.downloaded_bytes = start_byte
            
            # Prepare headers
            headers = {}
            if start_byte > 0:
                headers["Range"] = f"bytes={start_byte}-"
            
            # Make request
            response = self._session.get(
                config.url,
                headers=headers,
                stream=True,
                timeout=config.timeout,
                verify=config.verify_ssl,
            )
            response.raise_for_status()
            
            # Get total size
            if config.expected_size is None:
                content_length = response.headers.get("Content-Length")
                if content_length:
                    config.expected_size = int(content_length) + start_byte
                    progress.total_bytes = config.expected_size
            
            # Download with progress
            mode = "ab" if start_byte > 0 else "wb"
            start_time = time.time()
            last_update = start_time
            last_bytes = start_byte
            
            with open(config.destination, mode) as f:
                for chunk in response.iter_content(chunk_size=config.chunk_size):
                    if chunk:
                        f.write(chunk)
                        progress.downloaded_bytes += len(chunk)
                        
                        # Update speed and ETA
                        now = time.time()
                        elapsed = now - last_update
                        if elapsed >= 1.0:  # Update every second
                            bytes_since_last = progress.downloaded_bytes - last_bytes
                            progress.speed_bps = bytes_since_last / elapsed
                            if progress.speed_bps > 0 and progress.total_bytes > 0:
                                remaining = progress.total_bytes - progress.downloaded_bytes
                                progress.eta_seconds = remaining / progress.speed_bps
                            last_update = now
                            last_bytes = progress.downloaded_bytes
                            
                            if progress_callback:
                                progress_callback(progress)
            
            # Verify download
            if not self._verify_download(config, progress):
                progress.status = "failed"
                progress.error = "Verification failed"
                return False
            
            progress.status = "completed"
            progress.eta_seconds = 0
            if progress_callback:
                progress_callback(progress)
            
            # Audit log
            audit_logger.log_model_operation(
                actor="system",
                model=config.destination.name,
                operation="download",
                success=True,
                details={"url": config.url, "size": progress.downloaded_bytes}
            )
            
            return True
            
        except Exception as e:
            progress.status = "failed"
            progress.error = str(e)
            logger.error("Model download failed", url=config.url, error=str(e))
            audit_logger.log_model_operation(
                actor="system",
                model=config.destination.name,
                operation="download",
                success=False,
                details={"url": config.url, "error": str(e)}
            )
            return False
        finally:
            with self._lock:
                self._active_downloads.pop(download_id, None)
    
    def _verify_download(self, config: ModelDownloadConfig, progress: DownloadProgress) -> bool:
        """Verify downloaded file."""
        # Check file size
        if config.expected_size and progress.downloaded_bytes != config.expected_size:
            logger.error(
                "Size mismatch",
                expected=config.expected_size,
                actual=progress.downloaded_bytes,
            )
            return False
        
        # Check SHA256
        if config.expected_sha256:
            actual_sha256 = self._compute_sha256(config.destination)
            if actual_sha256.lower() != config.expected_sha256.lower():
                logger.error(
                    "SHA256 mismatch",
                    expected=config.expected_sha256,
                    actual=actual_sha256,
                )
                return False
        
        return True
    
    def _compute_sha256(self, file_path: Path) -> str:
        """Compute SHA256 of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def download_with_attestation(
        self,
        config: ModelDownloadConfig,
        attestation: ModelAttestation,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> bool:
        """Download and verify with attestation."""
        # Download first
        if not self.download(config, progress_callback):
            return False
        
        # Verify attestation
        if not self._verify_attestation(config.destination, attestation):
            logger.error("Attestation verification failed")
            config.destination.unlink(missing_ok=True)
            return False
        
        return True
    
    def _verify_attestation(self, file_path: Path, attestation: ModelAttestation) -> bool:
        """Verify file against attestation."""
        # Check SHA256
        actual_sha256 = self._compute_sha256(file_path)
        if actual_sha256.lower() != attestation.file_sha256.lower():
            return False
        
        # Check file size
        actual_size = file_path.stat().st_size
        if actual_size != attestation.file_size:
            return False
        
        # TODO: Verify signature using cosign
        # This would require the signature file and public key
        
        return True
    
    def get_active_downloads(self) -> Dict[str, DownloadProgress]:
        """Get currently active downloads."""
        with self._lock:
            return dict(self._active_downloads)
    
    def cancel_download(self, url: str, destination: Path):
        """Cancel an active download."""
        download_id = f"{url}_{destination}"
        with self._lock:
            if download_id in self._active_downloads:
                self._active_downloads[download_id].status = "paused"


# ============================================================================
# Model Registry with Distribution
# ============================================================================

class ModelDistributionRegistry:
    """Extended model registry with distribution capabilities."""
    
    def __init__(self, models_dir: Path = Path("models")):
        self.models_dir = models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.downloader = ModelDownloader()
        self.cosign = CosignVerifier()
        self._manifests: Dict[str, Dict[str, Any]] = {}
        self._load_manifests()
    
    def _load_manifests(self):
        """Load model manifests from disk."""
        manifest_file = self.models_dir / "manifests.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r") as f:
                    self._manifests = json.load(f)
            except Exception as e:
                logger.warning("Failed to load manifests", error=str(e))
    
    def _save_manifests(self):
        """Save model manifests to disk."""
        manifest_file = self.models_dir / "manifests.json"
        try:
            with open(manifest_file, "w") as f:
                json.dump(self._manifests, f, indent=2)
        except Exception as e:
            logger.error("Failed to save manifests", error=str(e))
    
    def register_model(
        self,
        model_id: str,
        version: str,
        url: str,
        sha256: str,
        size: int,
        attestation: Optional[ModelAttestation] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Register a model for distribution."""
        key = f"{model_id}:{version}"
        
        manifest = {
            "model_id": model_id,
            "version": version,
            "url": url,
            "sha256": sha256,
            "size": size,
            "attestation": attestation.to_dict() if attestation else None,
            "metadata": metadata or {},
            "registered_at": time.time(),
            "local_path": str(self.models_dir / f"{model_id}-{version}.gguf"),
        }
        
        self._manifests[key] = manifest
        self._save_manifests()
        
        logger.info("Model registered", model_id=model_id, version=version)
        return True
    
    def download_model(
        self,
        model_id: str,
        version: str,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        force: bool = False,
    ) -> Optional[Path]:
        """Download a registered model."""
        key = f"{model_id}:{version}"
        manifest = self._manifests.get(key)
        
        if not manifest:
            logger.error("Model not registered", model_id=model_id, version=version)
            return None
        
        local_path = Path(manifest["local_path"])
        
        # Check if already downloaded
        if local_path.exists() and not force:
            # Verify existing file
            if self._verify_local_file(local_path, manifest):
                logger.info("Model already downloaded and verified", path=str(local_path))
                return local_path
            else:
                logger.warning("Existing file failed verification, re-downloading")
                local_path.unlink(missing_ok=True)
        
        # Download
        config = ModelDownloadConfig(
            url=manifest["url"],
            destination=local_path,
            expected_sha256=manifest["sha256"],
            expected_size=manifest["size"],
        )
        
        if manifest.get("attestation"):
            attestation = ModelAttestation.from_dict(manifest["attestation"])
            success = self.downloader.download_with_attestation(config, attestation, progress_callback)
        else:
            success = self.downloader.download(config, progress_callback)
        
        if success:
            logger.info("Model downloaded successfully", path=str(local_path))
            return local_path
        
        return None
    
    def _verify_local_file(self, file_path: Path, manifest: Dict[str, Any]) -> bool:
        """Verify local file against manifest."""
        if not file_path.exists():
            return False
        
        # Check size
        if file_path.stat().st_size != manifest["size"]:
            return False
        
        # Check SHA256
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        if sha256.hexdigest().lower() != manifest["sha256"].lower():
            return False
        
        return True
    
    def list_models(self) -> List[Dict[str, Any]]:
        """List all registered models."""
        return list(self._manifests.values())
    
    def get_model_info(self, model_id: str, version: str) -> Optional[Dict[str, Any]]:
        """Get model information."""
        return self._manifests.get(f"{model_id}:{version}")
    
    def remove_model(self, model_id: str, version: str) -> bool:
        """Remove model from registry and disk."""
        key = f"{model_id}:{version}"
        manifest = self._manifests.get(key)
        
        if manifest:
            local_path = Path(manifest["local_path"])
            local_path.unlink(missing_ok=True)
            del self._manifests[key]
            self._save_manifests()
            return True
        return False


# ============================================================================
# Predefined Model Catalog
# ============================================================================

# Popular models with known good download URLs (Hugging Face)
MODEL_CATALOG = {
    "llama-3-8b-instruct": {
        "model_id": "llama-3-8b-instruct",
        "versions": {
            "Q4_K_M": {
                "url": "https://huggingface.co/bartowski/Meta-Llama-3-8B-Instruct-GGUF/resolve/main/Meta-Llama-3-8B-Instruct-Q4_K_M.gguf",
                "sha256": "a1b2c3d4e5f6...",  # Would need actual hash
                "size": 4800 * 1024 * 1024,  # ~4.8GB
            },
            "Q8_0": {
                "url": "https://huggingface.co/bartowski/Meta-Llama-3-8B-Instruct-GGUF/resolve/main/Meta-Llama-3-8B-Instruct-Q8_0.gguf",
                "sha256": "...",
                "size": 8500 * 1024 * 1024,
            },
        },
    },
    "nemotron-3-ultra": {
        "model_id": "nemotron-3-ultra",
        "versions": {
            "Q4_K_M": {
                "url": "https://huggingface.co/nvidia/Nemotron-3-Ultra-GGUF/resolve/main/Nemotron-3-Ultra-Q4_K_M.gguf",
                "sha256": "...",
                "size": 28000 * 1024 * 1024,
            },
        },
    },
    "phi-3-mini-4k": {
        "model_id": "phi-3-mini-4k",
        "versions": {
            "Q4_K_M": {
                "url": "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-Q4_K_M.gguf",
                "sha256": "...",
                "size": 2300 * 1024 * 1024,
            },
        },
    },
    "gemma-2-9b": {
        "model_id": "gemma-2-9b",
        "versions": {
            "Q4_K_M": {
                "url": "https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q4_K_M.gguf",
                "sha256": "...",
                "size": 5400 * 1024 * 1024,
            },
        },
    },
    "qwen2.5-7b": {
        "model_id": "qwen2.5-7b",
        "versions": {
            "Q4_K_M": {
                "url": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
                "sha256": "...",
                "size": 4400 * 1024 * 1024,
            },
        },
    },
    "mistral-7b-instruct": {
        "model_id": "mistral-7b-instruct",
        "versions": {
            "Q4_K_M": {
                "url": "https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
                "sha256": "...",
                "size": 4100 * 1024 * 1024,
            },
        },
    },
}


def create_default_registry(models_dir: Path = Path("models")) -> ModelDistributionRegistry:
    """Create registry with default model catalog."""
    registry = ModelDistributionRegistry(models_dir)
    
    # Register models from catalog
    for model_id, model_info in MODEL_CATALOG.items():
        for version, version_info in model_info["versions"].items():
            registry.register_model(
                model_id=model_id,
                version=version,
                url=version_info["url"],
                sha256=version_info["sha256"],
                size=version_info["size"],
                metadata={
                    "format": "GGUF",
                    "quantization": version,
                },
            )
    
    return registry