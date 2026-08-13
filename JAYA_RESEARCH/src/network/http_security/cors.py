"""Strict CORS configuration validation."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .errors import configuration_error

_HEADER_TOKEN_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_HOST_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _normalized_hostname(hostname: str) -> str:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ascii_host = hostname.encode("idna").decode("ascii").casefold()
        except UnicodeError as exc:
            raise configuration_error("CORS origin contains an invalid host") from exc
        if len(ascii_host) > 253 or not all(
            _HOST_LABEL_PATTERN.fullmatch(label)
            for label in ascii_host.rstrip(".").split(".")
        ):
            raise configuration_error("CORS origin contains an invalid host")
        return ascii_host.rstrip(".")
    if address.version == 6:
        return f"[{address.compressed}]"
    return address.compressed


@dataclass(frozen=True)
class CorsPolicy:
    """Validated, allowlist-only values for Starlette ``CORSMiddleware``."""

    allow_origins: tuple[str, ...]
    allow_credentials: bool = True
    allow_methods: tuple[str, ...] = ("GET", "POST", "DELETE", "OPTIONS")
    allow_headers: tuple[str, ...] = (
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "X-API-Key",
        "X-Request-ID",
    )

    def __post_init__(self) -> None:
        origins = tuple(self._validate_origin(origin) for origin in self.allow_origins)
        if not origins:
            raise configuration_error("At least one CORS origin is required")
        if len(origins) != len(set(origins)):
            raise configuration_error("Duplicate CORS origins are not allowed")

        methods = tuple(str(method).strip().upper() for method in self.allow_methods)
        if not methods or any(
            method == "*" or not _HEADER_TOKEN_PATTERN.fullmatch(method)
            for method in methods
        ):
            raise configuration_error("CORS methods must be explicit HTTP tokens")

        headers = tuple(str(header).strip() for header in self.allow_headers)
        if not headers or any(
            header == "*" or not _HEADER_TOKEN_PATTERN.fullmatch(header)
            for header in headers
        ):
            raise configuration_error("CORS headers must be explicit header names")

        object.__setattr__(self, "allow_origins", origins)
        object.__setattr__(self, "allow_methods", methods)
        object.__setattr__(self, "allow_headers", headers)

    @staticmethod
    def _validate_origin(origin: str) -> str:
        raw_origin = str(origin or "").strip()
        if (
            not raw_origin
            or len(raw_origin) > 2048
            or "*" in raw_origin
            or any(
                character.isspace() or ord(character) < 32 for character in raw_origin
            )
        ):
            raise configuration_error("CORS origins must be explicit allowlist values")
        parsed = urlsplit(raw_origin)
        try:
            port = parsed.port
        except ValueError as exc:
            raise configuration_error("CORS origin contains an invalid port") from exc
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise configuration_error(
                "CORS origins must contain only an http(s) scheme, host, and port"
            )
        host = _normalized_hostname(parsed.hostname)
        normalized = f"{parsed.scheme.casefold()}://{host}"
        if port is not None:
            normalized = f"{normalized}:{port}"
        return normalized

    @classmethod
    def from_csv(
        cls,
        raw_origins: str,
        *,
        allow_credentials: bool = True,
    ) -> CorsPolicy:
        """Build a policy from a comma-separated environment-style value."""
        return cls(
            allow_origins=tuple(
                origin.strip()
                for origin in str(raw_origins or "").split(",")
                if origin.strip()
            ),
            allow_credentials=allow_credentials,
        )

    def as_middleware_kwargs(self) -> dict[str, object]:
        """Return safe keyword arguments for Starlette ``CORSMiddleware``."""
        return {
            "allow_origins": list(self.allow_origins),
            "allow_credentials": self.allow_credentials,
            "allow_methods": list(self.allow_methods),
            "allow_headers": list(self.allow_headers),
        }
