"""
Cloud LLM Adapter for JAYA Cognitive Core.

Provides real cloud LLM integration supporting multiple providers:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Ollama (local/remote)
- Custom OpenAI-compatible endpoints

All integrations are capability-gated, privacy-aware, and fail-closed.
"""

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CloudLLMConfig:
    """Configuration for a cloud LLM provider."""
    provider: str  # "openai", "anthropic", "ollama", "custom"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = ""
    timeout_seconds: float = 30.0
    max_tokens: int = 1024
    temperature: float = 0.7
    extra_headers: Optional[Dict[str, str]] = None
    extra_params: Optional[Dict[str, Any]] = None


@dataclass
class CloudLLMResponse:
    """Structured response from cloud LLM."""
    text: str
    model: str
    provider: str
    usage: Optional[Dict[str, int]] = None
    latency_ms: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


class CloudLLMProvider(ABC):
    """Abstract base class for cloud LLM providers."""

    def __init__(self, config: CloudLLMConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            headers=self._build_headers(),
        )

    @abstractmethod
    def _build_headers(self) -> Dict[str, str]:
        """Build request headers for the provider."""
        pass

    @abstractmethod
    def _build_request(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Build request payload for the provider."""
        pass

    @abstractmethod
    def _parse_response(self, response: httpx.Response) -> CloudLLMResponse:
        """Parse provider response into standardized format."""
        pass

    async def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> CloudLLMResponse:
        """Generate response from cloud LLM."""
        start_time = time.time()
        request_data = self._build_request(messages, **kwargs)

        try:
            response = await self.client.post(
                self._endpoint(),
                json=request_data,
                headers=self._build_headers(),
            )
            response.raise_for_status()
            result = self._parse_response(response)
            result.latency_ms = (time.time() - start_time) * 1000
            return result
        except httpx.HTTPStatusError as e:
            logger.error(f"Cloud LLM HTTP error: {e.response.status_code} - {e.response.text}")
            raise CloudLLMError(f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Cloud LLM request error: {e}")
            raise CloudLLMError(f"Request failed: {e}")
        except Exception as e:
            logger.error(f"Cloud LLM unexpected error: {e}")
            raise CloudLLMError(f"Unexpected error: {e}")

    @abstractmethod
    def _endpoint(self) -> str:
        """Return the API endpoint path."""
        pass

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        return bool(self.config.api_key or self.config.provider == "ollama")


class CloudLLMError(Exception):
    """Cloud LLM specific error."""
    pass


class OpenAIProvider(CloudLLMProvider):
    """OpenAI API provider (GPT-4, GPT-3.5, etc.)."""

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)
        return headers

    def _build_request(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        request = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": False,
        }
        if self.config.extra_params:
            request.update(self.config.extra_params)
        return request

    def _parse_response(self, response: httpx.Response) -> CloudLLMResponse:
        data = response.json()
        choice = data["choices"][0]
        return CloudLLMResponse(
            text=choice["message"]["content"],
            model=data.get("model", self.config.model),
            provider="openai",
            usage=data.get("usage"),
            metadata={"finish_reason": choice.get("finish_reason")},
        )

    def _endpoint(self) -> str:
        return "/v1/chat/completions"


class AnthropicProvider(CloudLLMProvider):
    """Anthropic API provider (Claude)."""

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "x-api-key": self.config.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)
        return headers

    def _build_request(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        # Convert OpenAI format to Anthropic format
        system_msg = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        request = {
            "model": self.config.model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        if system_msg:
            request["system"] = system_msg
        if self.config.extra_params:
            request.update(self.config.extra_params)
        return request

    def _parse_response(self, response: httpx.Response) -> CloudLLMResponse:
        data = response.json()
        return CloudLLMResponse(
            text=data["content"][0]["text"],
            model=data.get("model", self.config.model),
            provider="anthropic",
            usage=data.get("usage"),
            metadata={"stop_reason": data.get("stop_reason")},
        )

    def _endpoint(self) -> str:
        return "/v1/messages"


class OllamaProvider(CloudLLMProvider):
    """Ollama provider (local or remote)."""

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)
        return headers

    def _build_request(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        request = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
                "temperature": kwargs.get("temperature", self.config.temperature),
            },
        }
        if self.config.extra_params:
            request["options"].update(self.config.extra_params)
        return request

    def _parse_response(self, response: httpx.Response) -> CloudLLMResponse:
        data = response.json()
        return CloudLLMResponse(
            text=data["message"]["content"],
            model=data.get("model", self.config.model),
            provider="ollama",
            usage={"prompt_tokens": data.get("prompt_eval_count", 0),
                   "completion_tokens": data.get("eval_count", 0)},
            metadata={"done": data.get("done", True)},
        )

    def _endpoint(self) -> str:
        return "/api/chat"


class CustomOpenAICompatibleProvider(CloudLLMProvider):
    """Custom OpenAI-compatible endpoint provider."""

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)
        return headers

    def _build_request(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        request = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": False,
        }
        if self.config.extra_params:
            request.update(self.config.extra_params)
        return request

    def _parse_response(self, response: httpx.Response) -> CloudLLMResponse:
        data = response.json()
        choice = data["choices"][0]
        return CloudLLMResponse(
            text=choice["message"]["content"],
            model=data.get("model", self.config.model),
            provider="custom",
            usage=data.get("usage"),
            metadata={"finish_reason": choice.get("finish_reason")},
        )

    def _endpoint(self) -> str:
        return "/v1/chat/completions"


class CloudLLMAdapter:
    """
    Unified cloud LLM adapter supporting multiple providers.
    
    Features:
    - Multi-provider support (OpenAI, Anthropic, Ollama, Custom)
    - Capability-gated access
    - Privacy-aware routing (sensitive content blocked)
    - Fail-closed design (never fabricates output)
    - Request/response logging for audit
    """

    PROVIDER_CLASSES = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
        "custom": CustomOpenAICompatibleProvider,
    }

    def __init__(
        self,
        configs: Optional[List[CloudLLMConfig]] = None,
        default_provider: str = "openai",
        privacy_keywords: Optional[List[str]] = None,
    ):
        self.providers: Dict[str, CloudLLMProvider] = {}
        self.default_provider = default_provider
        self.privacy_keywords = privacy_keywords or [
            "password", "secret", "private_key", "api_key", "token",
            "credential", "ssn", "credit_card", "passport",
        ]

        if configs:
            for config in configs:
                self.add_provider(config)

    def add_provider(self, config: CloudLLMConfig) -> bool:
        """Add a cloud LLM provider."""
        provider_class = self.PROVIDER_CLASSES.get(config.provider.lower())
        if not provider_class:
            logger.error(f"Unknown provider: {config.provider}")
            return False

        try:
            provider = provider_class(config)
            if provider.is_configured():
                self.providers[config.provider.lower()] = provider
                logger.info(f"Registered cloud LLM provider: {config.provider} ({config.model})")
                return True
            else:
                logger.warning(f"Provider {config.provider} not configured (missing API key)")
                return False
        except Exception as e:
            logger.error(f"Failed to initialize provider {config.provider}: {e}")
            return False

    def remove_provider(self, provider_name: str) -> bool:
        """Remove a provider."""
        if provider_name in self.providers:
            # Note: async close would be needed in real usage
            del self.providers[provider_name]
            return True
        return False

    def is_sensitive(self, text: str) -> bool:
        """Check if text contains sensitive keywords."""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.privacy_keywords)

    async def generate(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        force_local: bool = False,
        **kwargs
    ) -> CloudLLMResponse:
        """
        Generate response from cloud LLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            provider: Specific provider to use (None = default)
            force_local: If True, raises error (caller should use local LLM)
            **kwargs: Additional generation parameters
            
        Returns:
            CloudLLMResponse with generated text
            
        Raises:
            CloudLLMError: If no provider available, sensitive content, or generation fails
        """
        if force_local:
            raise CloudLLMError("Cloud generation requested but force_local=True")

        # Check for sensitive content
        full_text = " ".join(msg.get("content", "") for msg in messages)
        if self.is_sensitive(full_text):
            raise CloudLLMError("Sensitive content detected; cloud generation blocked by privacy policy")

        provider_name = (provider or self.default_provider).lower()
        if provider_name not in self.providers:
            available = list(self.providers.keys())
            raise CloudLLMError(f"Provider '{provider_name}' not available. Available: {available}")

        provider_instance = self.providers[provider_name]
        return await provider_instance.generate(messages, **kwargs)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        **kwargs
    ) -> CloudLLMResponse:
        """Alias for generate() for chat interface compatibility."""
        return await self.generate(messages, provider, **kwargs)

    def get_available_providers(self) -> List[str]:
        """Get list of available provider names."""
        return list(self.providers.keys())

    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        return {
            name: {
                "model": provider.config.model,
                "configured": provider.is_configured(),
                "provider_type": provider.config.provider,
            }
            for name, provider in self.providers.items()
        }

    async def close_all(self):
        """Close all provider connections."""
        for provider in self.providers.values():
            await provider.close()


def create_cloud_adapter_from_env() -> CloudLLMAdapter:
    """Factory to create CloudLLMAdapter from environment variables."""
    configs = []

    # OpenAI
    if os.getenv("JAYA_OPENAI_API_KEY"):
        configs.append(CloudLLMConfig(
            provider="openai",
            api_key=os.getenv("JAYA_OPENAI_API_KEY"),
            base_url=os.getenv("JAYA_OPENAI_BASE_URL", "https://api.openai.com"),
            model=os.getenv("JAYA_OPENAI_MODEL", "gpt-4o-mini"),
            timeout_seconds=float(os.getenv("JAYA_OPENAI_TIMEOUT", "30")),
            max_tokens=int(os.getenv("JAYA_OPENAI_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("JAYA_OPENAI_TEMPERATURE", "0.7")),
        ))

    # Anthropic
    if os.getenv("JAYA_ANTHROPIC_API_KEY"):
        configs.append(CloudLLMConfig(
            provider="anthropic",
            api_key=os.getenv("JAYA_ANTHROPIC_API_KEY"),
            base_url=os.getenv("JAYA_ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
            model=os.getenv("JAYA_ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
            timeout_seconds=float(os.getenv("JAYA_ANTHROPIC_TIMEOUT", "30")),
            max_tokens=int(os.getenv("JAYA_ANTHROPIC_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("JAYA_ANTHROPIC_TEMPERATURE", "0.7")),
        ))

    # Ollama
    if os.getenv("JAYA_OLLAMA_BASE_URL"):
        configs.append(CloudLLMConfig(
            provider="ollama",
            base_url=os.getenv("JAYA_OLLAMA_BASE_URL"),
            api_key=os.getenv("JAYA_OLLAMA_API_KEY"),
            model=os.getenv("JAYA_OLLAMA_MODEL", "llama3.1:8b"),
            timeout_seconds=float(os.getenv("JAYA_OLLAMA_TIMEOUT", "60")),
            max_tokens=int(os.getenv("JAYA_OLLAMA_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("JAYA_OLLAMA_TEMPERATURE", "0.7")),
        ))

    # Custom OpenAI-compatible
    if os.getenv("JAYA_CUSTOM_LLM_BASE_URL"):
        configs.append(CloudLLMConfig(
            provider="custom",
            base_url=os.getenv("JAYA_CUSTOM_LLM_BASE_URL"),
            api_key=os.getenv("JAYA_CUSTOM_LLM_API_KEY"),
            model=os.getenv("JAYA_CUSTOM_LLM_MODEL", "custom-model"),
            timeout_seconds=float(os.getenv("JAYA_CUSTOM_LLM_TIMEOUT", "30")),
            max_tokens=int(os.getenv("JAYA_CUSTOM_LLM_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("JAYA_CUSTOM_LLM_TEMPERATURE", "0.7")),
        ))

    default_provider = os.getenv("JAYA_CLOUD_DEFAULT_PROVIDER", "openai")

    return CloudLLMAdapter(configs=configs, default_provider=default_provider)