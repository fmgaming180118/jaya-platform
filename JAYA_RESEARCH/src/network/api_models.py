"""Bounded request/response contracts for the JAYA Research API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_WORKSPACE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"


class _ApiModel(BaseModel):
    """Reject undeclared fields so clients cannot assume ignored behavior."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResearchRequest(_ApiModel):
    topic: str = Field(min_length=1, max_length=1_000)
    focus_areas: str = Field(default="", max_length=2_000)
    max_queries: int = Field(default=5, ge=1, le=20)
    workspace_id: str = Field(default="default", pattern=_WORKSPACE_PATTERN)


class ChatRequest(_ApiModel):
    message: str = Field(min_length=1, max_length=8_000)
    context_files: list[str] = Field(default_factory=list, max_length=20)
    workspace_id: str = Field(default="default", pattern=_WORKSPACE_PATTERN)

    @field_validator("message")
    @classmethod
    def message_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must contain non-whitespace text")
        return value


class DebateRequest(_ApiModel):
    topic: str = Field(min_length=1, max_length=1_000)
    rounds: int = Field(default=3, ge=1, le=10)
    persona_1: str = Field(default="Optimist", min_length=1, max_length=100)
    persona_2: str = Field(default="Skeptic", min_length=1, max_length=100)
    analyze_frames: bool = True


class VideoIngestRequest(_ApiModel):
    url: str = Field(min_length=1, max_length=2_048)
    workspace_id: str = Field(default="default", pattern=_WORKSPACE_PATTERN)
    title: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=2_048)


class IngestRequest(_ApiModel):
    """A bounded inline source stored as an immutable workspace artifact."""

    text: str = Field(min_length=1, max_length=2_000_000)
    metadata: dict[str, Any] | None = None
    workspace_id: str = Field(default="default", pattern=_WORKSPACE_PATTERN)
    license_id: str = Field(default="UNKNOWN", min_length=1, max_length=128)

    @field_validator("text")
    @classmethod
    def text_must_contain_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must contain non-whitespace content")
        return value


class IngestResponse(_ApiModel):
    status: str
    chunks_added: int = Field(ge=0)
    workspace_id: str
    message: str | None = None
    source_id: str
    source_uri: str
    source_sha256: str
    duplicate: bool = False
    promotable: bool = False


class RecursiveResearchRequest(_ApiModel):
    query: str = Field(min_length=1, max_length=8_000)
    depth: int = Field(default=3, ge=1, le=5)
    workspace_id: str = Field(default="default", pattern=_WORKSPACE_PATTERN)
    max_sources_per_level: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def query_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must contain non-whitespace text")
        return value


class RecursiveResearchResponse(_ApiModel):
    query: str
    synthesis: str
    sources: list[dict[str, Any]]
    citations: list[dict[str, Any]] = Field(default_factory=list)
    depth_reached: int = Field(ge=0)
    workspace_id: str
    status: str
    promotable: bool = False
    artifact_uri: str
    artifact_sha256: str
