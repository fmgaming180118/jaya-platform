"""Canonical, side-effect-free configuration for JAYA Research.

Importing this module never creates directories, opens databases, or mutates
process environment variables. Legacy ``config.UPPER_CASE`` access remains
available through a lazy, read-only adapter.
"""

from __future__ import annotations

import math
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:-]{0,252}$")
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})

_MODEL_SPECS = {
    "reasoning": ("NVIDIA_REASONING_MODEL", "reasoning_model", "nvidia/nemotron-super-120b"),
    "chat": ("NVIDIA_CHAT_MODEL", "chat_model", "nvidia/nemotron-super-120b"),
    "coding": ("NVIDIA_CODING_MODEL", "coding_model", "nvidia/nemotron-super-120b"),
    "vision": ("NVIDIA_VISION_MODEL", "vision_model", "nvidia/neva-22b"),
    "image_gen": ("NVIDIA_IMAGE_GEN_MODEL", "image_gen_model", "black-forest-labs/flux.1-dev"),
    "video_summary": ("NVIDIA_VIDEO_SUMMARY_MODEL", "video_summary_model", "nvidia/video-search-and-summarization"),
    "tts": ("NVIDIA_TTS_MODEL", "tts_model", "nvidia/riva-tts-fastpitch"),
    "stt": ("NVIDIA_STT_MODEL", "stt_model", "nvidia/parakeet-ctc-0.6b"),
    "embedding": ("NVIDIA_EMBEDDING_MODEL", "embedding_model", "nvidia/nv-embedqa-e5-v5"),
    "rerank": ("NVIDIA_RERANK_MODEL", "rerank_model", "nvidia/nv-rerankqa-mistral-4b-v3"),
    "guardrails": ("NVIDIA_GUARDRAILS_MODEL", "guardrails_model", "nvidia/llama-guard-3-8b"),
}
_PATH_DEFAULTS = {
    "VECTOR_STORE_PATH": "vector_store.json",
    "EVOLUTION_MEMORY_PATH": "evolution_memory.json",
    "DISCOVERY_MEMORY_PATH": "discovery_memory.json",
    "KNOWLEDGE_GRAPH_PATH": "knowledge_graph.json",
    "NATIVE_MEMORY_PATH": "native_memory.json",
    "EVOLUTION_BACKUPS_DIR": "evolution/backups",
    "LANGUAGE_EVOLUTION_DIR": "language_evolution",
    "CRUCIBLE_DIR": "crucible",
    "VIDEO_CACHE_DIR": "video_cache",
    "VOICE_PROFILES_DIR": "voice_profiles",
    "VOICE_SAMPLES_DIR": "voice_samples",
    "VOICE_MODELS_DIR": "models",
    "WORKSPACES_DIR": "workspaces",
    "EXPERIMENTS_DIR": "experiments",
    "PAPERS_TEMP_DIR": "papers_temp",
    "SEED_DATASET_PATH": "seed_dataset.json",
    "TOKENIZER_PATH": "tokenizer.json",
    "JAYA_RESEARCH_JOB_DB": "research_jobs.db",
    "JAYA_RESEARCH_SETTINGS_DB": "agentic_jarvis.db",
}
_LEGACY_MODELS = {
    "NVIDIA_REASONING_MODEL": "reasoning",
    "NVIDIA_CHAT_MODEL": "chat",
    "NVIDIA_CODING_MODEL": "coding",
    "NVIDIA_VISION_MODEL": "vision",
    "NVIDIA_IMAGE_GEN_MODEL": "image_gen",
    "NVIDIA_VIDEO_SUMMARY_MODEL": "video_summary",
    "NVIDIA_TTS_MODEL": "tts",
    "NVIDIA_STT_MODEL": "stt",
    "NVIDIA_EMBEDDING_MODEL": "embedding",
    "NVIDIA_RERANK_MODEL": "rerank",
    "NVIDIA_GUARDRAILS_MODEL": "guardrails",
}


class ResearchConfigurationError(ValueError):
    """Raised when Research configuration cannot be proven safe."""


def _error(field_name: str, requirement: str) -> ResearchConfigurationError:
    # Never echo supplied values: an invalid value may contain a credential.
    return ResearchConfigurationError(
        f"Invalid Research setting {field_name!r}: {requirement}"
    )


def _env(environment: Mapping[str, str], key: str, default: Any = None) -> Any:
    value = environment.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise _error(key, "environment values must be strings")
    return value.strip() or default


def _nested(source: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value: Any = source
    for part in key.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return default
        value = value[part]
    return default if value is None else value


def _yaml(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Research config file not found: {path}")
        return {}
    if not path.is_file():
        raise ResearchConfigurationError(
            f"Research config source is not a file: {path.name}"
        )
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ResearchConfigurationError(
            f"Unable to load Research config source: {path.name}"
        ) from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ResearchConfigurationError(
            f"Research config source must contain a mapping: {path.name}"
        )
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise _error(name, f"must be an integer from {minimum} to {maximum}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise _error(name, f"must be an integer from {minimum} to {maximum}") from exc
    if not minimum <= parsed <= maximum:
        raise _error(name, f"must be from {minimum} to {maximum}")
    return parsed


def _floating(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise _error(name, f"must be a number from {minimum} to {maximum}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise _error(name, f"must be a number from {minimum} to {maximum}") from exc
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise _error(name, f"must be a finite number from {minimum} to {maximum}")
    return parsed


def _boolean(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise _error(name, "must be a boolean")


def _model(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise _error(name, "must be a model identifier")
    normalized = value.strip()
    if (
        not _MODEL_ID.fullmatch(normalized)
        or ".." in normalized
        or "://" in normalized
        or normalized.startswith(("/", "\\"))
    ):
        raise _error(name, "must be a 1-200 character provider/model identifier")
    return normalized


def _url(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise _error(name, "must be an HTTP(S) URL")
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise _error(name, "must be an HTTP(S) URL without credentials")
    loopback = parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not loopback:
        raise _error(name, "must use HTTPS unless it targets loopback")
    try:
        port = parsed.port
    except ValueError as exc:
        raise _error(name, "contains an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise _error(name, "contains an invalid port")
    return normalized


def _contained(root: Path, value: Any, name: str, default: Path) -> Path:
    requested = default if value in (None, "") else Path(str(value)).expanduser()
    candidate = requested if requested.is_absolute() else root / requested
    safe_root = root.resolve(strict=False)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(safe_root)
    except ValueError as exc:
        raise _error(name, f"must remain inside {safe_root.name}") from exc
    return resolved


@dataclass(frozen=True, slots=True)
class ResearchSettings:
    """Validated immutable settings shared by every Research subsystem."""

    base_dir: Path
    root_dir: Path
    data_dir: Path
    api_host: str
    api_port: int
    nvidia_api_key: str | None = field(repr=False)
    nvidia_base_url: str
    nvidia_vlm_endpoint: str
    nvidia_llama31_base_url: str
    semantic_scholar_base_url: str
    models: Mapping[str, str]
    research_reasoning_model: str
    research_writing_model: str
    research_max_queries: int
    research_max_iterations: int
    model_temperature: float
    model_max_tokens: int
    rag_chunk_size: int
    rag_chunk_overlap: int
    rag_embed_batch_size: int
    rag_embed_dimension: int
    rag_rerank_enabled: bool
    paths: Mapping[str, Path]
    reports_dir: Path
    research_config: Mapping[str, Any] = field(repr=False, compare=False)

    @classmethod
    def load(
        cls,
        *,
        environment: Mapping[str, str] | None = None,
        base_dir: str | Path | None = None,
        config_path: str | Path | None = None,
        nim_config_path: str | Path | None = None,
    ) -> "ResearchSettings":
        env = os.environ if environment is None else environment
        default_workspace = Path(__file__).resolve().parents[5]
        base = Path(base_dir or default_workspace).resolve()
        root = base if base_dir is None else base.parent
        configured_research_path = config_path or _env(
            env, "JAYA_RESEARCH_CONFIG_PATH"
        )
        research_path = Path(
            configured_research_path
            or base / "configs" / "research" / "research_config.yaml"
        ).resolve()
        research = _yaml(
            research_path,
            required=configured_research_path is not None,
        )
        configured_nim_path = nim_config_path or _env(env, "JAYA_NIM_CONFIG_PATH")
        if configured_nim_path is None:
            root_nim = root / "nvidia_nim_config.yaml"
            nim_path = root_nim if root_nim.exists() else base / "nvidia_nim_config.yaml"
        else:
            nim_path = Path(configured_nim_path)
        nim = _yaml(nim_path.resolve(), required=configured_nim_path is not None)

        api = _nested(nim, "api_settings", {})
        nim_models = _nested(nim, "models", {})
        rag = _nested(research, "rag", {})
        nim_rag = _nested(nim, "rag_settings", {})
        research_models = _nested(research, "models", {})
        for name, value in {
            "api_settings": api,
            "models": nim_models,
            "research.models": research_models,
            "rag": rag,
            "rag_settings": nim_rag,
        }.items():
            if not isinstance(value, Mapping):
                raise _error(name, "must be a mapping")

        data_dir = _contained(
            base,
            _env(env, "JAYA_DATA_DIR"),
            "JAYA_DATA_DIR",
            base / "data" / "jaya-research" if base_dir is None else base / "data",
        )

        def choose(key: str, *fallbacks: Any) -> Any:
            value = _env(env, key)
            if value is not None:
                return value
            return next((item for item in fallbacks if item is not None), None)

        base_url = _url(
            choose("NVIDIA_BASE_URL", api.get("base_url"), "https://integrate.api.nvidia.com/v1"),
            "NVIDIA_BASE_URL",
        )
        vlm_url = _url(
            choose("NVIDIA_VLM_ENDPOINT", api.get("vlm_endpoint"), f"{base_url}/chat/completions"),
            "NVIDIA_VLM_ENDPOINT",
        )
        llama_url = _url(
            choose("NVIDIA_LLAMA31_BASE_URL", base_url),
            "NVIDIA_LLAMA31_BASE_URL",
        )
        semantic_url = _url(
            choose("SEMANTIC_SCHOLAR_BASE_URL", "https://api.semanticscholar.org/graph/v1/paper"),
            "SEMANTIC_SCHOLAR_BASE_URL",
        )
        models = {
            name: _model(choose(env_key, nim_models.get(yaml_key), default), env_key)
            for name, (env_key, yaml_key, default) in _MODEL_SPECS.items()
        }
        reasoning_model = _model(
            choose(
                "RESEARCH_REASONING_MODEL",
                _nested(research_models, "reasoning.name"),
                models["reasoning"],
            ),
            "RESEARCH_REASONING_MODEL",
        )
        writing_model = _model(
            choose(
                "RESEARCH_WRITING_MODEL",
                _nested(research_models, "writing.name"),
                models["chat"],
            ),
            "RESEARCH_WRITING_MODEL",
        )
        max_queries = _integer(
            choose("JAYA_RESEARCH_MAX_QUERIES", _nested(research, "research.max_queries"), 10),
            "JAYA_RESEARCH_MAX_QUERIES",
            1,
            100,
        )
        max_iterations = _integer(
            choose("JAYA_RESEARCH_MAX_ITERATIONS", _nested(research, "research.max_iterations"), 3),
            "JAYA_RESEARCH_MAX_ITERATIONS",
            1,
            20,
        )
        temperature = _floating(
            choose(
                "JAYA_RESEARCH_MODEL_TEMPERATURE",
                _nested(research_models, "reasoning.temperature"),
                api.get("temperature"),
                0.2,
            ),
            "JAYA_RESEARCH_MODEL_TEMPERATURE",
            0.0,
            2.0,
        )
        max_tokens = _integer(
            choose(
                "JAYA_RESEARCH_MODEL_MAX_TOKENS",
                _nested(research_models, "reasoning.max_tokens"),
                api.get("max_tokens"),
                4096,
            ),
            "JAYA_RESEARCH_MODEL_MAX_TOKENS",
            1,
            131_072,
        )
        chunk_size = _integer(
            choose("RAG_CHUNK_SIZE", rag.get("chunk_size"), nim_rag.get("chunk_size"), 512),
            "RAG_CHUNK_SIZE",
            64,
            8192,
        )
        chunk_overlap = _integer(
            choose("RAG_CHUNK_OVERLAP", rag.get("chunk_overlap"), nim_rag.get("chunk_overlap"), 128),
            "RAG_CHUNK_OVERLAP",
            0,
            8191,
        )
        if chunk_overlap >= chunk_size:
            raise _error("RAG_CHUNK_OVERLAP", "must be smaller than RAG_CHUNK_SIZE")
        embed_batch = _integer(
            choose("RAG_EMBED_BATCH_SIZE", nim_rag.get("embed_batch_size"), 32),
            "RAG_EMBED_BATCH_SIZE",
            1,
            1024,
        )
        embed_dimension = _integer(
            choose(
                "RAG_EMBED_DIMENSION",
                _nested(research_models, "embedding.dimensions"),
                nim_rag.get("embed_dimension"),
                1024,
            ),
            "RAG_EMBED_DIMENSION",
            1,
            65_536,
        )
        rerank = _boolean(
            choose("RAG_RERANK_ENABLED", rag.get("rerank"), nim_rag.get("rerank_enabled"), False),
            "RAG_RERANK_ENABLED",
        )
        paths = {
            name: _contained(data_dir, _env(env, name), name, data_dir / relative)
            for name, relative in _PATH_DEFAULTS.items()
        }
        reports = _contained(
            data_dir,
            choose("JAYA_RESEARCH_REPORTS_DIR", _nested(research, "output.reports_dir"), "reports"),
            "JAYA_RESEARCH_REPORTS_DIR",
            data_dir / "reports",
        )
        host = str(choose("JAYA_RESEARCH_HOST", "127.0.0.1"))
        if not _HOST.fullmatch(host):
            raise _error("JAYA_RESEARCH_HOST", "must be a hostname or IP literal")
        port = _integer(
            choose("JAYA_RESEARCH_PORT", env.get("PORT"), 8000),
            "JAYA_RESEARCH_PORT",
            1,
            65_535,
        )
        return cls(
            base_dir=base,
            root_dir=root,
            data_dir=data_dir,
            api_host=host,
            api_port=port,
            nvidia_api_key=_env(env, "NVIDIA_API_KEY"),
            nvidia_base_url=base_url,
            nvidia_vlm_endpoint=vlm_url,
            nvidia_llama31_base_url=llama_url,
            semantic_scholar_base_url=semantic_url,
            models=MappingProxyType(models),
            research_reasoning_model=reasoning_model,
            research_writing_model=writing_model,
            research_max_queries=max_queries,
            research_max_iterations=max_iterations,
            model_temperature=temperature,
            model_max_tokens=max_tokens,
            rag_chunk_size=chunk_size,
            rag_chunk_overlap=chunk_overlap,
            rag_embed_batch_size=embed_batch,
            rag_embed_dimension=embed_dimension,
            rag_rerank_enabled=rerank,
            paths=MappingProxyType(paths),
            reports_dir=reports,
            research_config=_freeze(research),
        )
    def ensure_runtime_directories(self) -> None:
        """Create validated runtime directories explicitly during startup."""
        file_paths = {
            self.paths["VECTOR_STORE_PATH"],
            self.paths["EVOLUTION_MEMORY_PATH"],
            self.paths["DISCOVERY_MEMORY_PATH"],
            self.paths["KNOWLEDGE_GRAPH_PATH"],
            self.paths["NATIVE_MEMORY_PATH"],
            self.paths["SEED_DATASET_PATH"],
            self.paths["TOKENIZER_PATH"],
            self.paths["JAYA_RESEARCH_JOB_DB"],
            self.paths["JAYA_RESEARCH_SETTINGS_DB"],
        }
        directories = {self.data_dir, self.reports_dir}
        directories.update(path.parent for path in file_paths)
        directories.update(path for path in self.paths.values() if path not in file_paths)
        for path in sorted(directories, key=str):
            path.mkdir(parents=True, exist_ok=True)

    def research_config_dict(self) -> dict[str, Any]:
        return _thaw(self.research_config)

    def get(self, key: str, default: Any = None) -> Any:
        return _nested(self.research_config, key, default)

    def get_prompt(self, prompt_name: str, **values: Any) -> str:
        template = self.get(f"prompts.{prompt_name}", "")
        if not isinstance(template, str):
            raise _error(f"prompts.{prompt_name}", "must be text")
        try:
            return template.format(**values)
        except (KeyError, ValueError) as exc:
            raise ResearchConfigurationError(
                f"Unable to render Research prompt {prompt_name!r}"
            ) from exc

    def redacted(self) -> dict[str, Any]:
        return {
            "base_dir": str(self.base_dir),
            "data_dir": str(self.data_dir),
            "api_host": self.api_host,
            "api_port": self.api_port,
            "nvidia_base_url": self.nvidia_base_url,
            "nvidia_api_key_configured": bool(self.nvidia_api_key),
            "research_reasoning_model": self.research_reasoning_model,
            "research_writing_model": self.research_writing_model,
            "rag_chunk_size": self.rag_chunk_size,
            "rag_chunk_overlap": self.rag_chunk_overlap,
            "rag_embed_dimension": self.rag_embed_dimension,
        }

    @property
    def nvidia_embedding_model(self) -> str:
        return self.models["embedding"]

    def __getattr__(self, name: str) -> Any:
        if name == "BASE_DIR":
            return self.base_dir
        if name == "ROOT_DIR":
            return self.root_dir
        if name == "DATA_DIR":
            return self.data_dir
        if name == "NVIDIA_API_KEY":
            return self.nvidia_api_key
        endpoints = {
            "NVIDIA_BASE_URL": self.nvidia_base_url,
            "NVIDIA_VLM_ENDPOINT": self.nvidia_vlm_endpoint,
            "NVIDIA_LLAMA31_BASE_URL": self.nvidia_llama31_base_url,
            "SEMANTIC_SCHOLAR_BASE_URL": self.semantic_scholar_base_url,
        }
        if name in endpoints:
            return endpoints[name]
        if name in _LEGACY_MODELS:
            return self.models[_LEGACY_MODELS[name]]
        rag_values = {
            "RAG_CHUNK_SIZE": self.rag_chunk_size,
            "RAG_CHUNK_OVERLAP": self.rag_chunk_overlap,
            "RAG_EMBED_BATCH_SIZE": self.rag_embed_batch_size,
            "RAG_EMBED_DIMENSION": self.rag_embed_dimension,
            "RAG_RERANK_ENABLED": self.rag_rerank_enabled,
        }
        if name in rag_values:
            return rag_values[name]
        if name in self.paths:
            return str(self.paths[name])
        raise AttributeError(name)


_settings: ResearchSettings | None = None
_settings_lock = threading.Lock()


def get_settings(
    *,
    reload: bool = False,
    environment: Mapping[str, str] | None = None,
    base_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    nim_config_path: str | Path | None = None,
) -> ResearchSettings:
    """Return settings, caching only the default process instance."""
    custom = any(
        value is not None
        for value in (environment, base_dir, config_path, nim_config_path)
    )
    if custom:
        return ResearchSettings.load(
            environment=environment,
            base_dir=base_dir,
            config_path=config_path,
            nim_config_path=nim_config_path,
        )
    global _settings
    with _settings_lock:
        if reload or _settings is None:
            _settings = ResearchSettings.load()
        return _settings


def reset_settings_cache() -> None:
    global _settings
    with _settings_lock:
        _settings = None


class Config:
    """Read-only lazy adapter for legacy ``config.UPPER_CASE`` consumers."""

    __slots__ = ("_explicit_settings",)

    def __init__(self, settings: ResearchSettings | None = None) -> None:
        object.__setattr__(self, "_explicit_settings", settings)

    @property
    def settings(self) -> ResearchSettings:
        return self._explicit_settings or get_settings()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.settings, name)

    def __repr__(self) -> str:
        return f"Config({self.settings.redacted()!r})"


config = Config()
