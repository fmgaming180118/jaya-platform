"""Compatibility tool for allowlisted process profiles; raw shell is forbidden."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from jaya_research.capability_boundary import (
    CapabilityGateway,
    request_capability,
    require_profile,
)
from jaya_research.tools.base import BaseTool


class CommandInput(BaseModel):
    """Structured input containing a profile identifier, never shell text."""

    profile: str = Field(
        ...,
        description="Pre-registered Agent/OS execution profile identifier.",
    )
    arguments: dict[str, Any] = Field(default_factory=dict)


class CmdRunnerTool(BaseTool):
    """Route a fixed execution profile through an injected capability gateway."""

    def __init__(self, capability_gateway: CapabilityGateway | None = None) -> None:
        self._capability_gateway = capability_gateway

    @property
    def name(self) -> str:
        return "system_run_command"

    @property
    def description(self) -> str:
        return (
            "Runs a pre-registered process profile through an authorized "
            "capability gateway; arbitrary shell commands are rejected."
        )

    @property
    def parameters(self) -> type[BaseModel]:
        return CommandInput

    def execute(
        self,
        profile: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_profile = require_profile(profile)
        return dict(
            request_capability(
                self._capability_gateway,
                action="process.profile.run",
                arguments={
                    "profile": safe_profile,
                    "arguments": dict(arguments or {}),
                },
            )
        )
