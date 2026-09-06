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

_CORE_DIR = Path(__file__).resolve().parents[4]
_BAD_SECRET_PARTS = ("change-me", "changeme", "example", "password-here", "your-")
_HOST_PATTERN = re.compile(
    r"^(?=.{1,253}\.?$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}"
    r"[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}"
    r"[a-zA-Z0-9])?\.?$"
)
_SHA256_PATTERN = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


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


def _bounded_integer(
    source: Mapping[str, str],
    name: str,
    issues: list[str],
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = _read(source, name)
    try:
        value = int(raw) if raw else default
    except ValueError:
        issues.append(f"invalid:{name}")
        return default
    if not minimum <= value <= maximum:
        issues.append(f"invalid:{name}")
        return default
    return value


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
        _ = parsed.port
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
    model_required: bool
    identity_required: bool
    identity_key_secret: SecretValue
    identity_dir: Path
    privacy_required: bool
    privacy_key_secret: SecretValue
    zero_trust_required: bool
    cryptographic_skin_required: bool
    cryptographic_skin_secret: SecretValue
    hardware_lock_required: bool
    immune_system_required: bool
    quantum_security_required: bool
    quantum_policy_version: int
    quantum_asset_lifetime_days: int
    quantum_threat_horizon_year: int
    quantum_classical_cutoff_year: int
    data_dir: Path
    agentic_rag_path: Path
    narrative_path: Path
    narrative_max_payload_bytes: int
    lineage_signing_key: SecretValue
    twin_enabled: bool
    twin_shared_secret: SecretValue
    twin_allowed_peers: tuple[str, ...]
    ollama_base_url: str
    local_pillar_model: str
    local_model_timeout_seconds: float
    ternary_model_path: Path | None
    ternary_model_sha256: str
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
        model_required = _boolean(source, "JAYA_REQUIRE_MODEL", issues)
        identity_required = _boolean(source, "JAYA_REQUIRE_IDENTITY", issues)
        identity_key_secret = _secret(
            source,
            "JAYA_IDENTITY_KEY_SECRET",
            issues,
            required=identity_required,
            minimum=32,
        )
        privacy_required = production or _boolean(
            source, "JAYA_REQUIRE_PRIVACY", issues
        )
        privacy_key_secret = _secret(
            source,
            "JAYA_PRIVACY_KEY_SECRET",
            issues,
            required=privacy_required,
            minimum=32,
        )
        zero_trust_required = _boolean(source, "JAYA_REQUIRE_ZERO_TRUST", issues)
        if zero_trust_required and not identity_required:
            issues.append("invalid:JAYA_REQUIRE_ZERO_TRUST_REQUIRES_IDENTITY")
        if zero_trust_required and not privacy_required:
            issues.append("invalid:JAYA_REQUIRE_ZERO_TRUST_REQUIRES_PRIVACY")
        cryptographic_skin_required = _boolean(
            source, "JAYA_REQUIRE_CRYPTOGRAPHIC_SKIN", issues
        )
        cryptographic_skin_secret = _secret(
            source,
            "JAYA_CRYPTOGRAPHIC_SKIN_SECRET",
            issues,
            required=cryptographic_skin_required,
            minimum=32,
        )
        if cryptographic_skin_required and not identity_required:
            issues.append("invalid:JAYA_REQUIRE_CRYPTOGRAPHIC_SKIN_REQUIRES_IDENTITY")
        data_raw = _read(source, "JAYA_CORE_DATA_DIR")
        host_raw = _read(source, "JAYA_CORE_BIND_HOST")
        port_raw = _read(source, "JAYA_CORE_BIND_PORT")
        trusted_raw = _read(source, "JAYA_CORE_TRUSTED_HOSTS")
        if production:
            required_values = (
                ("JAYA_CORE_DATA_DIR", data_raw),
                ("JAYA_CORE_BIND_HOST", host_raw),
                ("JAYA_CORE_BIND_PORT", port_raw),
                ("JAYA_CORE_TRUSTED_HOSTS", trusted_raw),
            )
            issues.extend(
                f"missing:{name}" for name, value in required_values if not value
            )
            if model_required and not model_raw:
                issues.append("missing:JAYA_MODEL_PATH")
        hardware_lock_required = _boolean(source, "JAYA_REQUIRE_HARDWARE_LOCK", issues)
        if hardware_lock_required and not identity_required:
            issues.append("invalid:JAYA_REQUIRE_HARDWARE_LOCK_REQUIRES_IDENTITY")
        if hardware_lock_required and not cryptographic_skin_required:
            issues.append(
                "invalid:JAYA_REQUIRE_HARDWARE_LOCK_REQUIRES_CRYPTOGRAPHIC_SKIN"
            )
        immune_system_required = _boolean(
            source, "JAYA_REQUIRE_IMMUNE_SYSTEM", issues
        )
        if immune_system_required and not zero_trust_required:
            issues.append("invalid:JAYA_REQUIRE_IMMUNE_SYSTEM_REQUIRES_ZERO_TRUST")
        if immune_system_required and not cryptographic_skin_required:
            issues.append(
                "invalid:JAYA_REQUIRE_IMMUNE_SYSTEM_REQUIRES_CRYPTOGRAPHIC_SKIN"
            )
        quantum_security_required = _boolean(
            source, "JAYA_REQUIRE_QUANTUM_SECURITY", issues
        )
        if quantum_security_required and not cryptographic_skin_required:
            issues.append(
                "invalid:JAYA_REQUIRE_QUANTUM_SECURITY_REQUIRES_CRYPTOGRAPHIC_SKIN"
            )
        quantum_policy_version = _bounded_integer(
            source,
            "JAYA_QUANTUM_POLICY_VERSION",
            issues,
            default=1,
            minimum=1,
            maximum=1_000_000,
        )
        quantum_asset_lifetime_days = _bounded_integer(
            source,
            "JAYA_QUANTUM_ASSET_LIFETIME_DAYS",
            issues,
            default=3_650,
            minimum=1,
            maximum=36_500,
        )
        quantum_threat_horizon_year = _bounded_integer(
            source,
            "JAYA_QUANTUM_THREAT_HORIZON_YEAR",
            issues,
            default=2035,
            minimum=2025,
            maximum=2200,
        )
        quantum_classical_cutoff_year = _bounded_integer(
            source,
            "JAYA_QUANTUM_CLASSICAL_CUTOFF_YEAR",
            issues,
            default=2028,
            minimum=2025,
            maximum=2200,
        )
        narrative_max_payload_bytes = _bounded_integer(
            source,
            "JAYA_NARRATIVE_MAX_PAYLOAD_BYTES",
            issues,
            default=65_536,
            minimum=1_024,
            maximum=1_048_576,
        )
        lineage_signing_key = _secret(
            source,
            "JAYA_LINEAGE_SIGNING_KEY",
            issues,
            required=False,
            minimum=32,
        )

        model_path = Path(
            model_raw or root / "data" / "models" / "jaya-core" / "JAYA_SOVEREIGN_V18.jay"
        ).expanduser()
        data_dir = Path(data_raw or root / "data" / "jaya-core").expanduser()
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
        twin_allowed_peers = _csv(source, "JAYA_TWIN_ALLOWED_PEERS")
        if production and twin_enabled and not twin_allowed_peers:
            issues.append("missing:JAYA_TWIN_ALLOWED_PEERS")
        if any(not _valid_host(peer) for peer in twin_allowed_peers):
            issues.append("invalid:JAYA_TWIN_ALLOWED_PEERS")
        node_id = _read(source, "JAYA_NODE_ID")
        if production and twin_enabled and not node_id:
            issues.append("missing:JAYA_NODE_ID")
        ollama_base_url = _read(source, "JAYA_OLLAMA_BASE_URL")
        local_pillar_model = _read(source, "JAYA_LOCAL_PILLAR_MODEL")
        if bool(ollama_base_url) != bool(local_pillar_model):
            issues.append("conflict:JAYA_OLLAMA_BASE_URL,JAYA_LOCAL_PILLAR_MODEL")
        if ollama_base_url:
            parsed_ollama = urlsplit(ollama_base_url)
            try:
                _ = parsed_ollama.port
            except ValueError:
                issues.append("invalid:JAYA_OLLAMA_BASE_URL")
            if (
                parsed_ollama.scheme not in {"http", "https"}
                or parsed_ollama.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed_ollama.path not in {"", "/"}
                or parsed_ollama.query
                or parsed_ollama.fragment
                or parsed_ollama.username
                or parsed_ollama.password
            ):
                issues.append("invalid:JAYA_OLLAMA_BASE_URL")
        try:
            local_model_timeout_seconds = float(
                _read(source, "JAYA_LOCAL_MODEL_TIMEOUT_SECONDS", "60")
            )
            if not 1.0 <= local_model_timeout_seconds <= 300.0:
                raise ValueError
        except ValueError:
            issues.append("invalid:JAYA_LOCAL_MODEL_TIMEOUT_SECONDS")
            local_model_timeout_seconds = 60.0
        ternary_model_raw = _read(source, "JAYA_TERNARY_MODEL_PATH")
        ternary_model_sha256 = _read(source, "JAYA_TERNARY_MODEL_SHA256").casefold()
        if ternary_model_sha256 and not _SHA256_PATTERN.fullmatch(ternary_model_sha256):
            issues.append("invalid:JAYA_TERNARY_MODEL_SHA256")
        ternary_model_path = (
            Path(ternary_model_raw).expanduser().resolve()
            if ternary_model_raw
            else None
        )
        if production and ternary_model_raw and not Path(ternary_model_raw).expanduser().is_absolute():
            issues.append("invalid:JAYA_TERNARY_MODEL_PATH")

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
        identity_dir = (
            Path(
                _read(
                    source,
                    "JAYA_IDENTITY_DIR",
                    str(data_root / "identity"),
                )
            )
            .expanduser()
            .resolve()
        )
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
                _read(
                    source,
                    "JAYA_NARRATIVE_PATH",
                    str(data_root / "narrative_continuity.sqlite3"),
                )
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
            ("JAYA_IDENTITY_DIR", identity_dir),
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
            model_required=model_required,
            identity_required=identity_required,
            identity_key_secret=identity_key_secret,
            identity_dir=identity_dir,
            privacy_required=privacy_required,
            privacy_key_secret=privacy_key_secret,
            zero_trust_required=zero_trust_required,
            cryptographic_skin_required=cryptographic_skin_required,
            cryptographic_skin_secret=cryptographic_skin_secret,
            hardware_lock_required=hardware_lock_required,
            immune_system_required=immune_system_required,
            quantum_security_required=quantum_security_required,
            quantum_policy_version=quantum_policy_version,
            quantum_asset_lifetime_days=quantum_asset_lifetime_days,
            quantum_threat_horizon_year=quantum_threat_horizon_year,
            quantum_classical_cutoff_year=quantum_classical_cutoff_year,
            data_dir=data_root,
            agentic_rag_path=agentic_rag,
            narrative_path=narrative,
            narrative_max_payload_bytes=narrative_max_payload_bytes,
            lineage_signing_key=lineage_signing_key,
            twin_enabled=twin_enabled,
            twin_shared_secret=twin_secret,
            twin_allowed_peers=twin_allowed_peers,
            ollama_base_url=ollama_base_url.rstrip("/"),
            local_pillar_model=local_pillar_model,
            local_model_timeout_seconds=local_model_timeout_seconds,
            ternary_model_path=ternary_model_path,
            ternary_model_sha256=ternary_model_sha256,
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
            "model_required": self.model_required,
            "identity_required": self.identity_required,
            "identity_secret_configured": bool(self.identity_key_secret),
            "identity_dir": str(self.identity_dir),
            "privacy_required": self.privacy_required,
            "privacy_secret_configured": bool(self.privacy_key_secret),
            "zero_trust_required": self.zero_trust_required,
            "cryptographic_skin_required": self.cryptographic_skin_required,
            "cryptographic_skin_secret_configured": bool(
                self.cryptographic_skin_secret
            ),
            "hardware_lock_required": self.hardware_lock_required,
            "immune_system_required": self.immune_system_required,
            "quantum_security_required": self.quantum_security_required,
            "quantum_policy_version": self.quantum_policy_version,
            "quantum_asset_lifetime_days": self.quantum_asset_lifetime_days,
            "quantum_threat_horizon_year": self.quantum_threat_horizon_year,
            "quantum_classical_cutoff_year": self.quantum_classical_cutoff_year,
            "data_dir": str(self.data_dir),
            "agentic_rag_path": str(self.agentic_rag_path),
            "narrative_path": str(self.narrative_path),
            "narrative_max_payload_bytes": self.narrative_max_payload_bytes,
            "lineage_signing_key_configured": bool(self.lineage_signing_key),
            "research_inbox_path": str(self.research_inbox_path),
            "twin_enabled": self.twin_enabled,
            "twin_secret_configured": bool(self.twin_shared_secret),
            "twin_allowed_peers": self.twin_allowed_peers,
            "ollama_base_url": self.ollama_base_url,
            "local_pillar_model_configured": bool(self.local_pillar_model),
            "local_model_timeout_seconds": self.local_model_timeout_seconds,
            "ternary_model_configured": self.ternary_model_path is not None,
            "ternary_model_checksum_configured": bool(self.ternary_model_sha256),
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
    def SOUL_PASSWORD(self) -> str:
        return self.soul_password.get_secret_value()

    @property
    def MODEL_PATH(self) -> str:
        return str(self.model_path)

    @property
    def DATA_DIR(self) -> Path:
        return self.data_dir

    @property
    def AGENTIC_RAG_PATH(self) -> str:
        return str(self.agentic_rag_path)

    @property
    def NARRATIVE_PATH(self) -> str:
        return str(self.narrative_path)

    @property
    def TWIN_SHARED_SECRET(self) -> str:
        return self.twin_shared_secret.get_secret_value()

    @property
    def NODE_ID(self) -> str:
        return self.node_id

    @property
    def RESEARCH_MEMORY_PATH(self) -> str:
        return str(self.research_inbox_path)


load_dotenv(dotenv_path=_CORE_DIR / ".env", override=False)
core_config = CoreConfig.from_env()
