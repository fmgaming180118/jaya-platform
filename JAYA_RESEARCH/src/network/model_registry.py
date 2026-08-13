"""Typed NVIDIA model-registry boundary used by the Research API."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from provider_errors import (
    ProviderError,
    ProviderInvalidResponseError,
    ProviderPolicy,
    execute_with_retry,
)

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{1,199}$")


class ModelRegistryConfigurationError(ValueError):
    """Raised when model registry configuration is unsafe."""


def validate_model_id(model_id: str) -> str:
    normalized = str(model_id or "").strip()
    if not _MODEL_ID.fullmatch(normalized):
        raise ModelRegistryConfigurationError(
            "Model id must contain 2-200 safe registry characters"
        )
    return normalized


def validate_provider_base_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    parsed = urlsplit(normalized)
    allow_test_http = (
        os.getenv("JAYA_ENV", "").strip().casefold() == "test"
        and os.getenv("JAYA_PROVIDER_ALLOW_INSECURE_TEST", "").strip() == "1"
    )
    if (
        parsed.scheme not in ({"https", "http"} if allow_test_http else {"https"})
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ModelRegistryConfigurationError(
            "Provider base URL must be an HTTPS URL without credentials/query"
        )
    return normalized


@dataclass(frozen=True)
class ModelRegistryResult:
    status: str
    configured_models: tuple[str, ...]
    provider_models: tuple[str, ...]
    provider_error: dict[str, object] | None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "configured_models": list(self.configured_models),
            "provider_models": list(self.provider_models),
            "provider_error": self.provider_error,
        }


class NVIDIARegistryService:
    """List provider models with explicit TLS, timeout, and retry policy."""

    PROVIDER = "nvidia_model_registry"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        configured_models: Iterable[str],
        policy: ProviderPolicy | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip() or None
        self.base_url = validate_provider_base_url(base_url)
        self.configured_models = tuple(
            sorted({validate_model_id(model) for model in configured_models})
        )
        if not self.configured_models:
            raise ModelRegistryConfigurationError(
                "At least one configured model is required"
            )
        self.policy = policy or ProviderPolicy.from_env("NVIDIA_MODEL_REGISTRY")
        self.client_factory = client_factory

    def _client(self) -> Any:
        if self.client_factory is not None:
            return self.client_factory(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.policy.read_timeout_seconds,
                max_retries=0,
            )
        from openai import OpenAI

        return OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.policy.read_timeout_seconds,
            max_retries=0,
        )

    def list_models(self) -> ModelRegistryResult:
        if self.api_key is None:
            return ModelRegistryResult(
                status="UNAVAILABLE_NO_CREDENTIAL",
                configured_models=self.configured_models,
                provider_models=(),
                provider_error=None,
            )

        client = self._client()

        def request_models() -> tuple[str, ...]:
            response = client.models.list()
            rows = getattr(response, "data", response)
            if not isinstance(rows, (list, tuple)):
                try:
                    rows = list(rows)
                except TypeError as exc:
                    raise ProviderInvalidResponseError(
                        self.PROVIDER,
                        "Provider model list was malformed",
                    ) from exc
            model_ids: set[str] = set()
            for row in rows:
                raw_id = getattr(row, "id", None)
                if raw_id is None and isinstance(row, dict):
                    raw_id = row.get("id")
                try:
                    model_ids.add(validate_model_id(str(raw_id or "")))
                except ModelRegistryConfigurationError as exc:
                    raise ProviderInvalidResponseError(
                        self.PROVIDER,
                        "Provider returned an invalid model identifier",
                    ) from exc
            return tuple(sorted(model_ids))

        try:
            provider_models = execute_with_retry(
                self.PROVIDER,
                request_models,
                self.policy,
            )
        except ProviderError as exc:
            return ModelRegistryResult(
                status="PROVIDER_ERROR",
                configured_models=self.configured_models,
                provider_models=(),
                provider_error=exc.to_dict(),
            )
        return ModelRegistryResult(
            status="AVAILABLE",
            configured_models=self.configured_models,
            provider_models=provider_models,
            provider_error=None,
        )

