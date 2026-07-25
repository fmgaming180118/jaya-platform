"""
Base Skill System for JAYA_AGENT.
Implements @skill_action decorator, Hermes-style JSON schema auto-generation,
and dynamic tool dispatching.
"""

import inspect
import json
import logging
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger(__name__)


def skill_action(name: str, description: str, params: Optional[Dict[str, Any]] = None):
    """
    Decorator to mark a skill method as a callable agent tool action.
    """
    def decorator(func: Callable):
        func._is_skill_action = True
        func._action_name = name
        func._action_description = description
        func._action_params = params or {}
        return func
    return decorator


class Skill:
    """Base class for all JAYA_AGENT skills."""
    name: str = "base_skill"
    description: str = "Base skill capability"

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Auto-generates Hermes 3 / OpenAI compatible JSON schemas for all decorated actions.
        """
        schemas = []
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if callable(attr) and getattr(attr, "_is_skill_action", False):
                action_name = getattr(attr, "_action_name")
                desc = getattr(attr, "_action_description")
                params = getattr(attr, "_action_params")

                # Build JSON Schema
                properties = {}
                required = []
                for p_name, p_type in params.items():
                    properties[p_name] = {
                        "type": "string" if p_type in (str, "str") else "number" if p_type in (int, float, "int", "number") else "boolean" if p_type in (bool, "bool") else "string",
                        "description": f"Parameter {p_name}"
                    }
                    required.append(p_name)

                schemas.append({
                    "type": "function",
                    "function": {
                        "name": f"{self.name}_{action_name}",
                        "description": desc,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required
                        }
                    }
                })
        return schemas


class SkillRegistry:
    """Registry for discovering, listing, and executing agent skills."""
    _skills: Dict[str, Skill] = {}

    @classmethod
    def register(cls, skill_instance: Skill):
        """Registers a skill instance."""
        cls._skills[skill_instance.name] = skill_instance
        print(f"[SKILL REGISTRY] Registered skill: {skill_instance.name}")

    @classmethod
    def get_all_tool_schemas(cls) -> List[Dict[str, Any]]:
        """Collects JSON schemas from all registered skills."""
        all_schemas = []
        for skill in cls._skills.values():
            all_schemas.extend(skill.get_tool_schemas())
        return all_schemas

    @classmethod
    async def execute_action(cls, tool_name: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a registered tool action by name (e.g. 'file_skill_read_file').
        """
        for skill in cls._skills.values():
            for attr_name in dir(skill):
                attr = getattr(skill, attr_name)
                if callable(attr) and getattr(attr, "_is_skill_action", False):
                    full_name = f"{skill.name}_{getattr(attr, '_action_name')}"
                    if full_name == tool_name:
                        try:
                            if inspect.iscoroutinefunction(attr):
                                res = await attr(**kwargs)
                            else:
                                res = attr(**kwargs)
                            return {"success": True, "result": res}
                        except Exception as e:
                            return {"success": False, "error": str(e)}

        return {"success": False, "error": f"Tool '{tool_name}' not found in SkillRegistry."}
