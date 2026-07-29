"""Typed, fail-closed configuration for JAYA_CORE."""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

_CORE_DIR = Path(__file__).resolve().parent.parent
_BAD_SECRET_PARTS = ("change-me", "changeme", "example", "password-here", "your-")
_HOST_PATTERN = re.compile(
    r"^(?=.{1,253}\.?$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}"
    r"[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}"
    r"[a-zA-Z0-9])?\.?$"
)


class ConfigurationError(ValueError):
    """Configuration error that never echoes raw environment values."""

    def __init__(self, issues: list[str] | tuple[str, ...]) -> None:
        self.issues = tuple(issues)
        super().__init__("invalid JAYA_CORE configuration: " + ", ".join(issues))


class RuntimeEnvironment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class SecretValue:
    """Secret wrapper whose string and representation are always redacted."""

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        self.__value = value

    def get_secret_value(self) -> str:
        return self.__value

    def __bool__(self) -> bool:
        return bool(self.__value)

    def __repr__(self) -> str:
        return "SecretValue('**********')"

    def __str__(self) -> str:
        return "**********"


def _read(source: Mapping[str, str], name: str, default: str = "") -> str:
    raw = source.get(name)
    return default if raw is None or not raw.strip() else raw.strip()


def _environment(source: Mapping[str, str], issues: list[str]) -> RuntimeEnvironment:
    aliases = {
        "dev": RuntimeEnvironment.DEVELOPMENT,
        "development": RuntimeEnvironment.DEVELOPMENT,
        "local": RuntimeEnvironment.DEVELOPMENT,
        "test": RuntimeEnvironment.TEST,
        "testing": RuntimeEnvironment.TEST,
        "prod": RuntimeEnvironment.PRODUCTION,
        "production": RuntimeEnvironment.PRODUCTION,
    }
    primary_raw = _read(source, "JAYA_ENVIRONMENT")
    alias_raw = _read(source, "JAYA_ENV")
    primary = aliases.get(primary_raw.lower()) if primary_raw else None
    alias = aliases.get(alias_raw.lower()) if alias_raw else None
    if primary_raw and primary is None:
        issues.append("invalid:JAYA_ENVIRONMENT")
    if alias_raw and alias is None:
        issues.append("invalid:JAYA_ENV")
    if primary is not None and alias is not None and primary is not alias:
        issues.append("conflict:JAYA_ENVIRONMENT,JAYA_ENV")
    return primary or alias or RuntimeEnvironment.DEVELOPMENT


def _boolean(
    source: Mapping[str, str], name: str, issues: list[str], default: bool = False
) -> bool:
    raw = _read(source, name)
    if not raw:
        return default
    if raw.lower() in {"1", "true", "yes", "on"}:
        return True
    if raw.lower() in {"0", "false", "no", "off"}:
        return False
    issues.append(f"invalid:{name}")
    return default


def _secret(
    source: Mapping[str, str],
    name: str,
    issues: list[str],
    *,
    required: bool,
    minimum: int,
) -> SecretValue:
    value = _read(source, name)
    if not value:
        if required:
            issues.append(f"missing:{name}")
        return SecretValue("")
    if len(value) < minimum or any(
        part in value.casefold() for part in _BAD_SECRET_PARTS
    ):
        issues.append(f"invalid:{name}")
    return SecretValue(value)


def _csv(source: Mapping[str, str], name: str) -> tuple[str, ...]:
    values = (item.strip() for item in _read(source, name).split(","))
    return tuple(dict.fromkeys(item for item in values if item))


def _valid_host(value: str) -> bool:
    if not value:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return bool(_HOST_PATTERN.fullmatch(value))


def _valid_origin(origin: str, production: bool) -> bool:
    if origin == "*" or origin.endswith("/"):
        return False
    parsed = urlsplit(origin)
    if (
        not parsed.hostname
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        return False
    try:
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https" if production else parsed.scheme in {"http", "https"}
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class CoreConfig:
    """Immutable and testable source of truth for one Core process."""

    environment: RuntimeEnvironment
    core_dir: Path
    soul_password: SecretValue
    model_path: Path
    data_dir: Path
    agentic_rag_path: Path
    narrative_path: Path
    twin_enabled: bool
    twin_shared_secret: SecretValue
    node_id: str
    research_inbox_path: Path
    api_key: SecretValue
    bind_host: str
    bind_port: int
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    request_timeout_seconds: float

    @classmethod
    def from_env(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        core_dir: Path | None = None,
    ) -> CoreConfig:
        source = os.environ if environment is None else environment
        root = _CORE_DIR if core_dir is None else Path(core_dir).resolve()
        issues: list[str] = []
        runtime_environment = _environment(source, issues)
        production = runtime_environment is RuntimeEnvironment.PRODUCTION

        soul_password = _secret(
            source,
            "JAYA_SOUL_PASSWORD",
            issues,
            required=production,
            minimum=32 if production else 1,
        )
        api_key = _secret(
            source,
            "JAYA_CORE_API_KEY",
            issues,
            required=production,
            minimum=32,
        )
        model_raw = _read(source, "JAYA_MODEL_PATH")
        data_raw = _read(source, "JAYA_CORE_DATA_DIR")
        host_raw = _read(source, "JAYA_CORE_BIND_HOST")
        port_raw = _read(source, "JAYA_CORE_BIND_PORT")
        trusted_raw = _read(source, "JAYA_CORE_TRUSTED_HOSTS")
        if production:
            required_values = (
                ("JAYA_MODEL_PATH", model_raw),
                ("JAYA_CORE_DATA_DIR", data_raw),
                ("JAYA_CORE_BIND_HOST", host_raw),
                ("JAYA_CORE_BIND_PORT", port_raw),
                ("JAYA_CORE_TRUSTED_HOSTS", trusted_raw),
            )
            issues.extend(
                f"missing:{name}" for name, value in required_values if not value
            )

        model_path = Path(model_raw or root / "JAYA_SOVEREIGN_V18.jay").expanduser()
        data_dir = Path(data_raw or root / "data").expanduser()
        if production and not model_path.is_absolute():
            issues.append("invalid:JAYA_MODEL_PATH")
        if production and not data_dir.is_absolute():
            issues.append("invalid:JAYA_CORE_DATA_DIR")

        twin_enabled = _boolean(source, "JAYA_ENABLE_TWIN", issues)
        twin_secret = _secret(
            source,
            "JAYA_TWIN_SHARED_SECRET",
            issues,
            required=production and twin_enabled,
            minimum=32,
        )
        node_id = _read(source, "JAYA_NODE_ID")
        if production and twin_enabled and not node_id:
            issues.append("missing:JAYA_NODE_ID")

        bind_host = host_raw or "127.0.0.1"
        if not _valid_host(bind_host):
            issues.append("invalid:JAYA_CORE_BIND_HOST")
        try:
            bind_port = int(port_raw or "8765")
            if not 1 <= bind_port <= 65535:
                raise ValueError
        except ValueError:
            issues.append("invalid:JAYA_CORE_BIND_PORT")
            bind_port = 8765

        cors_origins = _csv(source, "JAYA_CORE_CORS_ORIGINS")
        if any(not _valid_origin(origin, production) for origin in cors_origins):
            issues.append("invalid:JAYA_CORE_CORS_ORIGINS")
        trusted_hosts = _csv(source, "JAYA_CORE_TRUSTED_HOSTS")
        if not trusted_hosts and not production:
            trusted_hosts = ("127.0.0.1", "localhost", "testserver")
        if any(host == "*" or not _valid_host(host) for host in trusted_hosts):
            issues.append("invalid:JAYA_CORE_TRUSTED_HOSTS")

        try:
            timeout = float(_read(source, "JAYA_CORE_REQUEST_TIMEOUT_SECONDS", "30"))
            if not 0.1 <= timeout <= 300:
                raise ValueError
        except ValueError:
            issues.append("invalid:JAYA_CORE_REQUEST_TIMEOUT_SECONDS")
            timeout = 30.0

        data_root = data_dir.resolve()
        agentic_rag = (
            Path(
                _read(
                    source, "JAYA_AGENTIC_RAG_PATH", str(data_root / "rag_runtime.db")
                )
            )
            .expanduser()
            .resolve()
        )
        narrative = (
            Path(
                _read(source, "JAYA_NARRATIVE_PATH", str(data_root / "narrative.json"))
            )
            .expanduser()
            .resolve()
        )
        legacy_inbox = _read(source, "JAYA_RESEARCH_MEMORY_PATH")
        research_inbox = (
            Path(
                _read(
                    source,
                    "JAYA_RESEARCH_INBOX_PATH",
                    legacy_inbox
                    or str(data_root / "research_inbox" / "research_memory.json"),
                )
            )
            .expanduser()
            .resolve()
        )
        owned_paths = (
            ("JAYA_AGENTIC_RAG_PATH", agentic_rag),
            ("JAYA_NARRATIVE_PATH", narrative),
            ("JAYA_RESEARCH_INBOX_PATH", research_inbox),
        )
        issues.extend(
            f"invalid:{name}"
            for name, path in owned_paths
            if not _is_within(path, data_root)
        )
        if issues:
            raise ConfigurationError(issues)
        return cls(
            environment=runtime_environment,
            core_dir=root,
            soul_password=soul_password,
            model_path=model_path.resolve(),
            data_dir=data_root,
            agentic_rag_path=agentic_rag,
            narrative_path=narrative,
            twin_enabled=twin_enabled,
            twin_shared_secret=twin_secret,
            node_id=node_id,
            research_inbox_path=research_inbox,
            api_key=api_key,
            bind_host=bind_host,
            bind_port=bind_port,
            cors_origins=cors_origins,
            trusted_hosts=trusted_hosts,
            request_timeout_seconds=timeout,
        )

    def validate(self) -> None:
        if self.environment is RuntimeEnvironment.PRODUCTION:
            if not self.soul_password or not self.api_key:
                raise ConfigurationError(("missing:production_secret",))
        elif not self.soul_password:
            logging.getLogger("CoreConfig").warning(
                "JAYA soul decryption is unavailable: "
                "JAYA_SOUL_PASSWORD is not configured"
            )

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "environment": self.environment.value,
            "model_path": str(self.model_path),
            "data_dir": str(self.data_dir),
            "agentic_rag_path": str(self.agentic_rag_path),
            "narrative_path": str(self.narrative_path),
            "research_inbox_path": str(self.research_inbox_path),
            "twin_enabled": self.twin_enabled,
            "twin_secret_configured": bool(self.twin_shared_secret),
            "node_id_configured": bool(self.node_id),
            "api_key_configured": bool(self.api_key),
            "soul_password_configured": bool(self.soul_password),
            "bind_host": self.bind_host,
            "bind_port": self.bind_port,
            "cors_origins": self.cors_origins,
            "trusted_hosts": self.trusted_hosts,
            "request_timeout_seconds": self.request_timeout_seconds,
        }

    @property
    def SOUL_PASSWORD(self) -> str:  # noqa: N802
        return self.soul_password.get_secret_value()

    @property
    def MODEL_PATH(self) -> str:  # noqa: N802
        return str(self.model_path)

    @property
    def DATA_DIR(self) -> Path:  # noqa: N802
        return self.data_dir

    @property
    def AGENTIC_RAG_PATH(self) -> str:  # noqa: N802
        return str(self.agentic_rag_path)

    @property
    def NARRATIVE_PATH(self) -> str:  # noqa: N802
        return str(self.narrative_path)

    @property
    def TWIN_SHARED_SECRET(self) -> str:  # noqa: N802
        return self.twin_shared_secret.get_secret_value()

    @property
    def NODE_ID(self) -> str:  # noqa: N802
        return self.node_id

    @property
    def RESEARCH_MEMORY_PATH(self) -> str:  # noqa: N802
        return str(self.research_inbox_path)


load_dotenv(dotenv_path=_CORE_DIR / ".env", override=False)
core_config = CoreConfig.from_env()
