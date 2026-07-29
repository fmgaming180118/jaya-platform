"""Backward-compatible adapter for the canonical Research settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

try:
    from ..config import (
        ResearchConfigurationError,
        ResearchSettings,
        get_settings,
    )
except ImportError:  # ``PYTHONPATH=JAYA_RESEARCH/src`` compatibility
    from config import (  # type: ignore[no-redef]
        ResearchConfigurationError,
        ResearchSettings,
        get_settings,
    )


class ResearchConfig:
    """Legacy research-agent view backed by one validated settings object."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        settings: ResearchSettings | None = None,
    ) -> None:
        if settings is not None and (config_path is not None or environment is not None):
            raise ResearchConfigurationError(
                "Supply settings or configuration sources, not both"
            )
        if settings is not None:
            canonical = settings
        elif config_path is not None or environment is not None:
            canonical = get_settings(
                config_path=config_path,
                environment=environment,
            )
        else:
            canonical = get_settings()
        self.settings = canonical
        self.config_path = str(
            Path(config_path).resolve(strict=False)
            if config_path is not None
            else canonical.base_dir / "configs" / "research_config.yaml"
        )
        self.config = canonical.research_config_dict()
        self._max_queries = canonical.research_max_queries
        self._max_iterations = canonical.research_max_iterations

    def load_config(self) -> dict[str, Any]:
        return self.settings.research_config_dict()

    def get(self, key: str, default: Any = None) -> Any:
        value: Any = self.config
        for item in key.split("."):
            if not isinstance(value, Mapping) or item not in value:
                return default
            value = value[item]
        return default if value is None else value

    @property
    def max_queries(self) -> int:
        return self._max_queries

    @max_queries.setter
    def max_queries(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
            raise ResearchConfigurationError(
                "Invalid Research setting 'max_queries': must be from 1 to 100"
            )
        self._max_queries = value

    @property
    def max_iterations(self) -> int:
        return self._max_iterations

    @max_iterations.setter
    def max_iterations(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20:
            raise ResearchConfigurationError(
                "Invalid Research setting 'max_iterations': must be from 1 to 20"
            )
        self._max_iterations = value

    @property
    def reasoning_model(self) -> str:
        return self.settings.research_reasoning_model

    @property
    def writing_model(self) -> str:
        return self.settings.research_writing_model

    @property
    def embedding_model(self) -> str:
        return self.settings.nvidia_embedding_model

    @property
    def reports_dir(self) -> str:
        return str(self.settings.reports_dir)

    def get_prompt(self, prompt_name: str, **kwargs: Any) -> str:
        template = self.get(f"prompts.{prompt_name}", "")
        if not isinstance(template, str):
            raise ResearchConfigurationError(
                f"Invalid Research setting 'prompts.{prompt_name}': must be text"
            )
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError) as exc:
            raise ResearchConfigurationError(
                f"Unable to render Research prompt {prompt_name!r}"
            ) from exc


_config: ResearchConfig | None = None


def get_config(*, reload: bool = False) -> ResearchConfig:
    global _config
    if reload or _config is None:
        _config = ResearchConfig()
    return _config


def reset_config_cache() -> None:
    global _config
    _config = None


__all__ = [
    "ResearchConfig",
    "ResearchConfigurationError",
    "ResearchSettings",
    "get_config",
    "reset_config_cache",
]