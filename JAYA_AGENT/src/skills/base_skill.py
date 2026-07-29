"""Capability-gated skill registration and dispatch for JAYA_AGENT."""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from collections.abc import Callable, Mapping
from typing import Any

from security.capability_sandbox import (
    CapabilityDenied,
    CapabilitySandbox,
    require_active_capability,
)

logger = logging.getLogger(__name__)


def _matches_declared_type(value: Any, declared: Any) -> bool:
    if declared in (str, "str"):
        return isinstance(value, str)
    if declared in (int, "int"):
        return isinstance(value, int) and not isinstance(value, bool)
    if declared in (float, "number"):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared in (bool, "bool"):
        return isinstance(value, bool)
    return isinstance(value, str)


def skill_action(
    name: str,
    description: str,
    params: Mapping[str, Any] | None = None,
    *,
    capability: str,
    resource_param: str | None = None,
    resource_prefix: str = "",
    fixed_resources: tuple[str, ...] = (),
    timeout_seconds: float | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare an action and require an active OS capability on direct calls."""

    if not name or not description or not capability:
        raise ValueError("Skill action metadata must be explicit")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_guard(*args: Any, **kwargs: Any) -> Any:
                require_active_capability(capability)
                return await func(*args, **kwargs)

            wrapped: Callable[..., Any] = async_guard
        else:

            @functools.wraps(func)
            def sync_guard(*args: Any, **kwargs: Any) -> Any:
                require_active_capability(capability)
                return func(*args, **kwargs)

            wrapped = sync_guard

        wrapped._is_skill_action = True  # type: ignore[attr-defined]
        wrapped._action_name = name  # type: ignore[attr-defined]
        wrapped._action_description = description  # type: ignore[attr-defined]
        wrapped._action_params = dict(params or {})  # type: ignore[attr-defined]
        wrapped._capability = capability  # type: ignore[attr-defined]
        wrapped._resource_param = resource_param  # type: ignore[attr-defined]
        wrapped._resource_prefix = resource_prefix  # type: ignore[attr-defined]
        wrapped._fixed_resources = tuple(fixed_resources)  # type: ignore[attr-defined]
        wrapped._timeout_seconds = timeout_seconds  # type: ignore[attr-defined]
        return wrapped

    return decorator


class Skill:
    """Base class for JAYA_AGENT skills."""

    name: str = "base_skill"
    description: str = "Base skill capability"

    def iter_actions(self) -> list[Callable[..., Any]]:
        """Return callable actions with complete security metadata."""

        actions: list[Callable[..., Any]] = []
        for attribute_name in dir(self):
            attribute = getattr(self, attribute_name)
            if callable(attribute) and getattr(
                attribute,
                "_is_skill_action",
                False,
            ):
                actions.append(attribute)
        return actions

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Generate tool schemas including required capability metadata."""

        schemas: list[dict[str, Any]] = []
        for action in self.iter_actions():
            properties: dict[str, dict[str, str]] = {}
            required: list[str] = []
            for parameter_name, parameter_type in getattr(
                action,
                "_action_params",
            ).items():
                if parameter_type in (int, float, "int", "number"):
                    json_type = "number"
                elif parameter_type in (bool, "bool"):
                    json_type = "boolean"
                else:
                    json_type = "string"
                properties[parameter_name] = {
                    "type": json_type,
                    "description": f"Parameter {parameter_name}",
                }
                required.append(parameter_name)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": (
                            f"{self.name}_{getattr(action, '_action_name')}"
                        ),
                        "description": getattr(
                            action,
                            "_action_description",
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        },
                        "x-jaya-capability": getattr(action, "_capability"),
                        "x-jaya-explicit-grant-required": True,
                    },
                }
            )
        return schemas


class SkillRegistry:
    """Discover and dispatch skills only through the OS capability sandbox."""

    _skills: dict[str, Skill] = {}
    _sandbox: CapabilitySandbox = CapabilitySandbox()

    @classmethod
    def configure_sandbox(cls, sandbox: CapabilitySandbox) -> None:
        """Inject the policy-owned sandbox used by all subsequent actions."""

        if not isinstance(sandbox, CapabilitySandbox):
            raise TypeError("Skill registry requires a CapabilitySandbox")
        cls._sandbox = sandbox

    @classmethod
    def clear(cls) -> None:
        """Clear registrations; intended for deterministic startup and tests."""

        cls._skills.clear()

    @classmethod
    def register(cls, skill_instance: Skill) -> None:
        """Register a skill only when every action has an allowlisted policy."""

        if not isinstance(skill_instance, Skill):
            raise TypeError("Registered object must derive from Skill")
        for action in skill_instance.iter_actions():
            capability = str(getattr(action, "_capability", ""))
            if capability not in cls._sandbox.allowed_actions:
                raise ValueError(
                    f"Skill action capability '{capability}' is not allowlisted"
                )
            resource_param = getattr(action, "_resource_param", None)
            params = getattr(action, "_action_params", {})
            if resource_param is not None and resource_param not in params:
                raise ValueError(
                    "Capability resource parameter is absent from tool schema"
                )
            if resource_param is None and not getattr(
                action,
                "_fixed_resources",
                (),
            ):
                raise ValueError("Skill action must declare an explicit resource")
        cls._skills[skill_instance.name] = skill_instance
        logger.info("Registered capability-gated skill: %s", skill_instance.name)

    @classmethod
    def get_all_tool_schemas(cls) -> list[dict[str, Any]]:
        """Collect schemas from registered skills."""

        schemas: list[dict[str, Any]] = []
        for skill in cls._skills.values():
            schemas.extend(skill.get_tool_schemas())
        return schemas

    @classmethod
    async def execute_action(
        cls,
        tool_name: str,
        kwargs: Mapping[str, Any],
        *,
        grant_token: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Authorize, execute, and return a signed redacted receipt."""

        if not isinstance(tool_name, str) or not 1 <= len(tool_name) <= 200:
            return {
                "success": False,
                "error_code": "INVALID_TOOL_NAME",
                "error": "Tool name must be a bounded string",
            }
        if not isinstance(kwargs, Mapping) or any(
            not isinstance(key, str) for key in kwargs
        ):
            return {
                "success": False,
                "error_code": "INVALID_TOOL_ARGUMENTS",
                "error": "Tool arguments must be a string-keyed mapping",
            }
        action = cls._find_action(tool_name)
        if action is None:
            return {
                "success": False,
                "error_code": "TOOL_NOT_FOUND",
                "error": "Requested tool is not registered",
            }
        expected_params = set(getattr(action, "_action_params", {}))
        received_params = set(kwargs)
        if received_params != expected_params:
            return {
                "success": False,
                "error_code": "INVALID_TOOL_ARGUMENTS",
                "error": "Tool arguments do not match its declared schema",
            }
        declared_params = getattr(action, "_action_params", {})
        if any(
            not _matches_declared_type(kwargs[name], declared)
            for name, declared in declared_params.items()
        ):
            return {
                "success": False,
                "error_code": "INVALID_TOOL_ARGUMENT_TYPES",
                "error": "Tool argument types do not match its schema",
            }

        capability = str(getattr(action, "_capability"))
        resources = list(getattr(action, "_fixed_resources", ()))
        resource_param = getattr(action, "_resource_param", None)
        if resource_param is not None:
            raw_resource = kwargs[resource_param]
            resources.append(
                f"{getattr(action, '_resource_prefix', '')}{raw_resource}"
            )

        async def invoke() -> Any:
            if inspect.iscoroutinefunction(action):
                return await action(**dict(kwargs))
            return await asyncio.to_thread(action, **dict(kwargs))

        try:
            execution = await cls._sandbox.execute(
                grant_token=grant_token,
                action=capability,
                resources=tuple(resources),
                idempotency_key=idempotency_key,
                request_payload={
                    "tool": tool_name,
                    "arguments": dict(kwargs),
                },
                operation=invoke,
                timeout_seconds=getattr(action, "_timeout_seconds", None),
            )
            return {
                "success": True,
                "result": execution.result,
                "replayed": execution.replayed,
                "receipt": execution.receipt.to_dict(),
            }
        except CapabilityDenied as exc:
            logger.warning(
                "Tool action denied: tool=%s code=%s",
                tool_name,
                exc.code,
            )
            return {
                "success": False,
                "error_code": exc.code,
                "error": exc.safe_message,
            }

    @classmethod
    def _find_action(cls, tool_name: str) -> Callable[..., Any] | None:
        for skill in cls._skills.values():
            for action in skill.iter_actions():
                full_name = (
                    f"{skill.name}_{getattr(action, '_action_name')}"
                )
                if hmac_compare(tool_name, full_name):
                    return action
        return None


def hmac_compare(left: str, right: str) -> bool:
    """Compare dispatcher identifiers without data-dependent early exit."""

    import hmac

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
