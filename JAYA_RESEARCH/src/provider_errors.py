"""Shared provider trust-boundary errors and bounded retry policy.

Provider clients must raise these exceptions instead of returning error text as
research content.  The exceptions intentionally expose only safe metadata; raw
response bodies and credentials must stay out of logs and API responses.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import sys
import time
import urllib.error
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

import requests

T = TypeVar("T")

if __name__ == "provider_errors":
    sys.modules.setdefault("src.provider_errors", sys.modules[__name__])
elif __name__ == "src.provider_errors":
    sys.modules.setdefault("provider_errors", sys.modules[__name__])


class ProviderError(RuntimeError):
    """Base class for failures at an external provider boundary."""

    code = "provider_error"
    retryable = False

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        status_code: Optional[int] = None,
        retry_after_seconds: Optional[float] = None,
        cause_type: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.cause_type = cause_type
        super().__init__(f"{provider}: {message}")

    def to_dict(self) -> dict[str, object]:
        """Return a safe, serializable representation without provider bodies."""
        payload: dict[str, object] = {
            "provider": self.provider,
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        if self.retry_after_seconds is not None:
            payload["retry_after_seconds"] = self.retry_after_seconds
        return payload


class ProviderAuthError(ProviderError):
    code = "provider_auth_error"


class ProviderQuotaError(ProviderError):
    code = "provider_quota_error"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout_error"
    retryable = True


class ProviderNetworkError(ProviderError):
    code = "provider_network_error"
    retryable = True


class ProviderInvalidResponseError(ProviderError):
    code = "provider_invalid_response_error"


def _env_number(
    provider_prefix: str,
    suffix: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    provider_name = f"{provider_prefix}_{suffix}" if provider_prefix else suffix
    global_name = (
        provider_name
        if provider_prefix == "PROVIDER"
        else f"PROVIDER_{suffix}"
    )
    raw_value = os.getenv(
        provider_name,
        os.getenv(global_name, str(default)),
    )
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{provider_name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{provider_name} must be between {minimum:g} and {maximum:g}"
        )
    return value


def _env_integer(
    provider_prefix: str,
    suffix: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = _env_number(
        provider_prefix,
        suffix,
        float(default),
        minimum=float(minimum),
        maximum=float(maximum),
    )
    if not value.is_integer():
        provider_name = f"{provider_prefix}_{suffix}"
        raise ValueError(f"{provider_name} must be an integer")
    return int(value)


@dataclass(frozen=True)
class ProviderPolicy:
    """Timeout and retry limits shared by provider adapters."""

    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 30.0
    max_attempts: int = 3
    retry_base_delay_seconds: float = 0.25
    retry_max_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if not 0.1 <= self.connect_timeout_seconds <= 120:
            raise ValueError("connect_timeout_seconds must be between 0.1 and 120")
        if not 0.1 <= self.read_timeout_seconds <= 600:
            raise ValueError("read_timeout_seconds must be between 0.1 and 600")
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if not 0 <= self.retry_base_delay_seconds <= 60:
            raise ValueError("retry_base_delay_seconds must be between 0 and 60")
        if not 0 <= self.retry_max_delay_seconds <= 60:
            raise ValueError("retry_max_delay_seconds must be between 0 and 60")
        if self.retry_base_delay_seconds > self.retry_max_delay_seconds:
            raise ValueError(
                "retry_base_delay_seconds cannot exceed retry_max_delay_seconds"
            )

    @classmethod
    def from_env(cls, provider_prefix: str = "PROVIDER") -> "ProviderPolicy":
        prefix = provider_prefix.strip().upper()
        return cls(
            connect_timeout_seconds=_env_number(
                prefix,
                "CONNECT_TIMEOUT_SECONDS",
                5.0,
                minimum=0.1,
                maximum=120,
            ),
            read_timeout_seconds=_env_number(
                prefix,
                "READ_TIMEOUT_SECONDS",
                30.0,
                minimum=0.1,
                maximum=600,
            ),
            max_attempts=_env_integer(
                prefix,
                "MAX_ATTEMPTS",
                3,
                minimum=1,
                maximum=10,
            ),
            retry_base_delay_seconds=_env_number(
                prefix,
                "RETRY_BASE_DELAY_SECONDS",
                0.25,
                minimum=0,
                maximum=60,
            ),
            retry_max_delay_seconds=_env_number(
                prefix,
                "RETRY_MAX_DELAY_SECONDS",
                2.0,
                minimum=0,
                maximum=60,
            ),
        )

    @property
    def requests_timeout(self) -> tuple[float, float]:
        return self.connect_timeout_seconds, self.read_timeout_seconds


def _retry_after_seconds(response: object) -> Optional[float]:
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, min(float(value), 60.0))
    except (TypeError, ValueError):
        return None


def error_for_http_status(
    provider: str,
    status_code: int,
    *,
    response: object = None,
) -> ProviderError:
    """Map an HTTP status to a stable provider error category."""
    retry_after = _retry_after_seconds(response)
    common = {
        "status_code": status_code,
        "retry_after_seconds": retry_after,
    }
    if status_code in {401, 403}:
        return ProviderAuthError(
            provider,
            "Provider rejected authentication or authorization",
            **common,
        )
    if status_code == 429:
        return ProviderQuotaError(
            provider,
            "Provider quota or rate limit was exceeded",
            **common,
        )
    if status_code in {408, 504}:
        return ProviderTimeoutError(
            provider,
            "Provider request timed out",
            **common,
        )
    if status_code >= 500:
        return ProviderNetworkError(
            provider,
            "Provider is temporarily unavailable",
            **common,
        )
    return ProviderInvalidResponseError(
        provider,
        "Provider rejected the request",
        **common,
    )


def ensure_http_success(provider: str, response: object) -> None:
    """Raise a typed error for a non-success HTTP response."""
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        raise ProviderInvalidResponseError(
            provider,
            "Provider response did not include an HTTP status",
        )
    if not 200 <= status_code < 300:
        raise error_for_http_status(provider, status_code, response=response)


def classify_provider_error(provider: str, error: BaseException) -> ProviderError:
    """Convert SDK, requests, and urllib failures into the shared hierarchy."""
    if isinstance(error, ProviderError):
        return error

    status_code = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    if not isinstance(status_code, int):
        status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int) and isinstance(error, urllib.error.HTTPError):
        status_code = error.code
    if isinstance(status_code, int):
        return error_for_http_status(provider, status_code, response=response)

    error_name = type(error).__name__
    if error_name in {"AuthenticationError", "PermissionDeniedError"}:
        return ProviderAuthError(
            provider,
            "Provider rejected authentication or authorization",
            cause_type=error_name,
        )
    if error_name == "RateLimitError":
        return ProviderQuotaError(
            provider,
            "Provider quota or rate limit was exceeded",
            cause_type=error_name,
        )
    if error_name in {"APITimeoutError", "ReadTimeout", "ConnectTimeout"}:
        return ProviderTimeoutError(
            provider,
            "Provider request timed out",
            cause_type=error_name,
        )
    if error_name in {"APIConnectionError", "ConnectError"}:
        return ProviderNetworkError(
            provider,
            "Could not connect to provider",
            cause_type=error_name,
        )

    if isinstance(
        error,
        (
            TimeoutError,
            socket.timeout,
            requests.exceptions.Timeout,
        ),
    ):
        return ProviderTimeoutError(
            provider,
            "Provider request timed out",
            cause_type=error_name,
        )
    if isinstance(
        error,
        (
            ConnectionError,
            socket.gaierror,
            ssl.SSLError,
            requests.exceptions.ConnectionError,
        ),
    ):
        return ProviderNetworkError(
            provider,
            "Could not connect to provider",
            cause_type=error_name,
        )
    if isinstance(error, urllib.error.URLError):
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            return ProviderTimeoutError(
                provider,
                "Provider request timed out",
                cause_type=error_name,
            )
        return ProviderNetworkError(
            provider,
            "Could not connect to provider",
            cause_type=error_name,
        )
    if isinstance(
        error,
        (
            json.JSONDecodeError,
            UnicodeDecodeError,
            requests.exceptions.JSONDecodeError,
        ),
    ):
        return ProviderInvalidResponseError(
            provider,
            "Provider returned malformed data",
            cause_type=error_name,
        )
    return ProviderError(
        provider,
        "Provider request failed",
        cause_type=error_name,
    )


def execute_with_retry(
    provider: str,
    operation: Callable[[], T],
    policy: ProviderPolicy,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run a provider operation with deterministic, bounded retry behavior."""
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation()
        except Exception as raw_error:
            error = classify_provider_error(provider, raw_error)
            if not error.retryable or attempt >= policy.max_attempts:
                raise error from raw_error

            delay = min(
                policy.retry_base_delay_seconds * (2 ** (attempt - 1)),
                policy.retry_max_delay_seconds,
            )
            if error.retry_after_seconds is not None:
                delay = min(
                    max(delay, error.retry_after_seconds),
                    policy.retry_max_delay_seconds,
                )
            if delay > 0:
                sleep(delay)

    raise AssertionError("Provider retry loop exited unexpectedly")


def select_primary_error(errors: list[ProviderError]) -> ProviderError:
    """Select the most actionable error after independent fallbacks fail."""
    if not errors:
        raise ValueError("errors must not be empty")
    priority = {
        ProviderAuthError: 0,
        ProviderQuotaError: 1,
        ProviderTimeoutError: 2,
        ProviderNetworkError: 3,
        ProviderInvalidResponseError: 4,
        ProviderError: 5,
    }
    return min(errors, key=lambda item: priority.get(type(item), 99))
