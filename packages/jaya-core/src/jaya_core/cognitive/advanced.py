"""
Advanced Cognitive Capabilities for JAYA_CORE.

Provides:
- Function calling / tool use framework
- Structured output parsing
- Chain-of-thought reasoning
- ReAct (Reasoning + Acting) pattern
- Multi-step planning and execution
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from jaya_core.observability import get_structured_logger, trace_function
from jaya_core.security import get_audit_logger, require_capability

logger = get_structured_logger(__name__, component="advanced_cognitive")
audit_logger = get_audit_logger()


# ============================================================================
# Function Calling Framework
# ============================================================================

class ParameterType(Enum):
    """JSON Schema parameter types."""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class FunctionParameter:
    """Function parameter definition."""
    name: str
    type: ParameterType
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None
    items: Optional["FunctionParameter"] = None  # For arrays
    properties: Optional[Dict[str, "FunctionParameter"]] = None  # For objects


@dataclass
class FunctionSchema:
    """Function schema for tool calling."""
    name: str
    description: str
    parameters: Dict[str, FunctionParameter] = field(default_factory=dict)
    returns: Optional[ParameterType] = None
    
    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema format."""
        props = {}
        required = []
        
        for name, param in self.parameters.items():
            prop = {
                "type": param.type.value,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            if param.type == ParameterType.ARRAY and param.items:
                prop["items"] = param.items.to_json_schema() if hasattr(param.items, 'to_json_schema') else {"type": param.items.type.value}
            if param.type == ParameterType.OBJECT and param.properties:
                prop["properties"] = {k: v.to_json_schema() if hasattr(v, 'to_json_schema') else {"type": v.type.value} for k, v in param.properties.items()}
            
            props[name] = prop
            if param.required:
                required.append(name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        }
    
    @classmethod
    def from_json_schema(cls, schema: Dict[str, Any]) -> "FunctionSchema":
        """Create from JSON Schema."""
        func_schema = schema.get("function", schema)
        params = {}
        
        for name, param_schema in func_schema.get("parameters", {}).get("properties", {}).items():
            param_type = ParameterType(param_schema.get("type", "string"))
            params[name] = FunctionParameter(
                name=name,
                type=param_type,
                description=param_schema.get("description", ""),
                required=name in func_schema.get("parameters", {}).get("required", []),
                default=param_schema.get("default"),
                enum=param_schema.get("enum"),
            )
        
        return cls(
            name=func_schema["name"],
            description=func_schema.get("description", ""),
            parameters=params,
        )


@dataclass
class FunctionCall:
    """Represents a function call request."""
    name: str
    arguments: Dict[str, Any]
    call_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "call_id": self.call_id,
        }


@dataclass
class FunctionResult:
    """Represents a function call result."""
    call_id: str
    name: str
    result: Any
    error: Optional[str] = None
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }
    
    @property
    def success(self) -> bool:
        return self.error is None


class FunctionRegistry:
    """Registry for available functions/tools."""
    
    def __init__(self):
        self._functions: Dict[str, Callable] = {}
        self._schemas: Dict[str, FunctionSchema] = {}
        self._categories: Dict[str, Set[str]] = {}
    
    def register(
        self,
        func: Callable,
        schema: FunctionSchema,
        category: str = "general",
    ):
        """Register a function with its schema."""
        self._functions[schema.name] = func
        self._schemas[schema.name] = schema
        
        if category not in self._categories:
            self._categories[category] = set()
        self._categories[category].add(schema.name)
        
        logger.info(f"Function registered: {schema.name}", name=schema.name, category=category)
    
    def unregister(self, name: str):
        """Unregister a function."""
        if name in self._functions:
            del self._functions[name]
        if name in self._schemas:
            del self._schemas[name]
        for cat in self._categories.values():
            cat.discard(name)
    
    def get_function(self, name: str) -> Optional[Callable]:
        """Get function by name."""
        return self._functions.get(name)
    
    def get_schema(self, name: str) -> Optional[FunctionSchema]:
        """Get function schema by name."""
        return self._schemas.get(name)
    
    def get_all_schemas(self) -> List[FunctionSchema]:
        """Get all function schemas."""
        return list(self._schemas.values())
    
    def get_schemas_by_category(self, category: str) -> List[FunctionSchema]:
        """Get schemas for a category."""
        names = self._categories.get(category, set())
        return [self._schemas[name] for name in names if name in self._schemas]
    
    def list_categories(self) -> List[str]:
        """List all categories."""
        return list(self._categories.keys())


# Global function registry
_function_registry: Optional[FunctionRegistry] = None


def get_function_registry() -> FunctionRegistry:
    """Get global function registry."""
    global _function_registry
    if _function_registry is None:
        _function_registry = FunctionRegistry()
    return _function_registry


def register_function(
    schema: FunctionSchema,
    category: str = "general",
):
    """Decorator to register a function."""
    def decorator(func: Callable) -> Callable:
        get_function_registry().register(func, schema, category)
        return func
    return decorator


# ============================================================================
# Built-in Functions
# ============================================================================

@register_function(
    FunctionSchema(
        name="get_current_time",
        description="Get the current date and time",
        parameters={},
        returns=ParameterType.STRING,
    ),
    category="system",
)
def get_current_time() -> str:
    """Get current date and time."""
    from datetime import datetime
    return datetime.now().isoformat()


@register_function(
    FunctionSchema(
        name="calculate",
        description="Perform mathematical calculation",
        parameters={
            "expression": FunctionParameter(
                name="expression",
                type=ParameterType.STRING,
                description="Mathematical expression to evaluate (e.g., '2 + 3 * 4')",
                required=True,
            ),
        },
        returns=ParameterType.NUMBER,
    ),
    category="math",
)
def calculate(expression: str) -> float:
    """Safely evaluate mathematical expression."""
    # Only allow safe operations
    allowed_chars = set("0123456789+-*/.() ")
    if not all(c in allowed_chars for c in expression):
        raise ValueError("Expression contains invalid characters")
    
    # Use eval with restricted globals
    result = eval(expression, {"__builtins__": {}}, {})
    return float(result)


@register_function(
    FunctionSchema(
        name="read_file",
        description="Read contents of a file",
        parameters={
            "path": FunctionParameter(
                name="path",
                type=ParameterType.STRING,
                description="File path to read",
                required=True,
            ),
            "encoding": FunctionParameter(
                name="encoding",
                type=ParameterType.STRING,
                description="File encoding",
                required=False,
                default="utf-8",
            ),
        },
        returns=ParameterType.STRING,
    ),
    category="file",
)
def read_file(path: str, encoding: str = "utf-8") -> str:
    """Read file contents."""
    from pathlib import Path
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return file_path.read_text(encoding=encoding)


@register_function(
    FunctionSchema(
        name="write_file",
        description="Write content to a file",
        parameters={
            "path": FunctionParameter(
                name="path",
                type=ParameterType.STRING,
                description="File path to write",
                required=True,
            ),
            "content": FunctionParameter(
                name="content",
                type=ParameterType.STRING,
                description="Content to write",
                required=True,
            ),
            "encoding": FunctionParameter(
                name="encoding",
                type=ParameterType.STRING,
                description="File encoding",
                required=False,
                default="utf-8",
            ),
        },
        returns=ParameterType.BOOLEAN,
    ),
    category="file",
)
def write_file(path: str, content: str, encoding: str = "utf-8") -> bool:
    """Write content to file."""
    from pathlib import Path
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding=encoding)
    return True


@register_function(
    FunctionSchema(
        name="list_directory",
        description="List contents of a directory",
        parameters={
            "path": FunctionParameter(
                name="path",
                type=ParameterType.STRING,
                description="Directory path",
                required=True,
            ),
            "recursive": FunctionParameter(
                name="recursive",
                type=ParameterType.BOOLEAN,
                description="List recursively",
                required=False,
                default=False,
            ),
        },
        returns=ParameterType.ARRAY,
    ),
    category="file",
)
def list_directory(path: str, recursive: bool = False) -> List[Dict[str, Any]]:
    """List directory contents."""
    from pathlib import Path
    dir_path = Path(path)
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    
    result = []
    if recursive:
        for item in dir_path.rglob("*"):
            result.append({
                "name": item.name,
                "path": str(item),
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            })
    else:
        for item in dir_path.iterdir():
            result.append({
                "name": item.name,
                "path": str(item),
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            })
    return result


@register_function(
    FunctionSchema(
        name="web_search",
        description="Search the web for information",
        parameters={
            "query": FunctionParameter(
                name="query",
                type=ParameterType.STRING,
                description="Search query",
                required=True,
            ),
            "max_results": FunctionParameter(
                name="max_results",
                type=ParameterType.INTEGER,
                description="Maximum number of results",
                required=False,
                default=5,
            ),
        },
        returns=ParameterType.ARRAY,
    ),
    category="web",
)
def web_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search the web using DuckDuckGo."""
    import requests
    from urllib.parse import quote
    
    url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1&skip_disambig=1"
    response = requests.get(url, timeout=10)
    data = response.json()
    
    results = []
    if data.get("Abstract"):
        results.append({
            "title": data.get("Heading", "Result"),
            "snippet": data["Abstract"],
            "url": data.get("AbstractURL", ""),
        })
    
    for topic in data.get("RelatedTopics", [])[:max_results]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append({
                "title": topic.get("Text", "")[:100],
                "snippet": topic.get("Text", ""),
                "url": topic.get("FirstURL", ""),
            })
    
    return results[:max_results]


# ============================================================================
# Function Calling Engine
# ============================================================================

class FunctionCallingEngine:
    """Engine for executing function calls from LLM output."""
    
    def __init__(self, registry: FunctionRegistry = None):
        self.registry = registry or get_function_registry()
        self._call_history: List[FunctionResult] = []
    
    def parse_function_calls(self, text: str) -> List[FunctionCall]:
        """Parse function calls from LLM output."""
        calls = []
        
        # Try to find JSON function calls
        # Pattern: {"name": "func", "arguments": {...}}
        json_pattern = r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"arguments"\s*:\s*(\{.*?\})\s*\}'
        
        for match in re.finditer(json_pattern, text, re.DOTALL):
            name = match.group(1)
            args_str = match.group(2)
            try:
                arguments = json.loads(args_str)
                calls.append(FunctionCall(
                    name=name,
                    arguments=arguments,
                    call_id=f"call_{len(calls)}",
                ))
            except json.JSONDecodeError:
                continue
        
        # Also try OpenAI-style tool_calls format
        tool_calls_pattern = r'"tool_calls"\s*:\s*\[(.*?)\]'
        for match in re.finditer(tool_calls_pattern, text, re.DOTALL):
            try:
                tool_calls = json.loads(f"[{match.group(1)}]")
                for tc in tool_calls:
                    if tc.get("type") == "function":
                        func = tc.get("function", {})
                        calls.append(FunctionCall(
                            name=func.get("name", ""),
                            arguments=json.loads(func.get("arguments", "{}")),
                            call_id=tc.get("id", f"call_{len(calls)}"),
                        ))
            except json.JSONDecodeError:
                continue
        
        return calls
    
    def execute_function(self, call: FunctionCall) -> FunctionResult:
        """Execute a single function call."""
        start_time = time.perf_counter()
        
        func = self.registry.get_function(call.name)
        if not func:
            return FunctionResult(
                call_id=call.call_id,
                name=call.name,
                result=None,
                error=f"Function not found: {call.name}",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )
        
        schema = self.registry.get_schema(call.name)
        
        try:
            # Validate arguments against schema
            if schema:
                self._validate_arguments(call.arguments, schema)
            
            # Execute function
            result = func(**call.arguments)
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            func_result = FunctionResult(
                call_id=call.call_id,
                name=call.name,
                result=result,
                duration_ms=duration_ms,
            )
            
            self._call_history.append(func_result)
            return func_result
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            func_result = FunctionResult(
                call_id=call.call_id,
                name=call.name,
                result=None,
                error=str(e),
                duration_ms=duration_ms,
            )
            self._call_history.append(func_result)
            return func_result
    
    def execute_multiple(self, calls: List[FunctionCall]) -> List[FunctionResult]:
        """Execute multiple function calls."""
        return [self.execute_function(call) for call in calls]
    
    def _validate_arguments(self, arguments: Dict[str, Any], schema: FunctionSchema):
        """Validate function arguments against schema."""
        # Check required parameters
        for name, param in schema.parameters.items():
            if param.required and name not in arguments:
                raise ValueError(f"Missing required parameter: {name}")
            
            if name in arguments:
                value = arguments[name]
                # Type validation
                if param.type == ParameterType.INTEGER and not isinstance(value, int):
                    raise ValueError(f"Parameter {name} must be integer")
                elif param.type == ParameterType.NUMBER and not isinstance(value, (int, float)):
                    raise ValueError(f"Parameter {name} must be number")
                elif param.type == ParameterType.STRING and not isinstance(value, str):
                    raise ValueError(f"Parameter {name} must be string")
                elif param.type == ParameterType.BOOLEAN and not isinstance(value, bool):
                    raise ValueError(f"Parameter {name} must be boolean")
                elif param.type == ParameterType.ARRAY and not isinstance(value, list):
                    raise ValueError(f"Parameter {name} must be array")
                elif param.type == ParameterType.OBJECT and not isinstance(value, dict):
                    raise ValueError(f"Parameter {name} must be object")
                
                # Enum validation
                if param.enum and value not in param.enum:
                    raise ValueError(f"Parameter {name} must be one of: {param.enum}")
    
    def get_call_history(self) -> List[FunctionResult]:
        """Get function call history."""
        return self._call_history.copy()
    
    def clear_history(self):
        """Clear call history."""
        self._call_history.clear()


# ============================================================================
# Structured Output Parser
# ============================================================================

class StructuredOutputParser:
    """Parse structured output from LLM."""
    
    @staticmethod
    def parse_json(text: str, schema: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from text."""
        # Try to find JSON object
        json_pattern = r'\{.*\}'
        matches = list(re.finditer(json_pattern, text, re.DOTALL))
        
        for match in reversed(matches):  # Try last match first (most complete)
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue
        
        return None
    
    @staticmethod
    def parse_function_calls(text: str) -> List[FunctionCall]:
        """Parse function calls from text."""
        engine = FunctionCallingEngine()
        return engine.parse_function_calls(text)
    
    @staticmethod
    def extract_thinking(text: str) -> tuple[str, str]:
        """Extract thinking/reasoning from text."""
        # Look for <thinking> or <reasoning> tags
        thinking_pattern = r'<(thinking|reasoning)>(.*?)</\1>'
        match = re.search(thinking_pattern, text, re.DOTALL | re.IGNORECASE)
        
        if match:
            thinking = match.group(2).strip()
            # Remove thinking tags from text
            clean_text = re.sub(thinking_pattern, '', text, flags=re.DOTALL | re.IGNORECASE).strip()
            return clean_text, thinking
        
        return text, ""


# ============================================================================
# ReAct (Reasoning + Acting) Engine
# ============================================================================

@dataclass
class ReActStep:
    """Single step in ReAct loop."""
    step_number: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[str] = None


class ReActEngine:
    """
    ReAct (Reasoning + Acting) Engine.
    
    Implements the ReAct pattern: Thought -> Action -> Observation -> ...
    """
    
    def __init__(
        self,
        function_engine: FunctionCallingEngine = None,
        max_steps: int = 10,
    ):
        self.function_engine = function_engine or FunctionCallingEngine()
        self.max_steps = max_steps
        self.steps: List[ReActStep] = []
    
    def run(
        self,
        question: str,
        generate_thought: Callable[[str, List[ReActStep]], str],
        generate_action: Callable[[str, List[ReActStep]], Optional[FunctionCall]],
        generate_final: Callable[[str, List[ReActStep]], str],
    ) -> str:
        """
        Run ReAct loop.
        
        Args:
            question: The question/task to solve
            generate_thought: Function to generate thought given context
            generate_action: Function to generate action (function call) given thought
            generate_final: Function to generate final answer
            
        Returns:
            Final answer
        """
        self.steps = []
        context = f"Question: {question}\n\n"
        
        for step_num in range(1, self.max_steps + 1):
            # Generate thought
            thought = generate_thought(context, self.steps)
            
            # Generate action
            action_call = generate_action(thought, self.steps)
            
            step = ReActStep(
                step_number=step_num,
                thought=thought,
            )
            
            if action_call:
                step.action = action_call.name
                step.action_input = action_call.arguments
                
                # Execute action
                result = self.function_engine.execute_function(action_call)
                
                if result.success:
                    step.observation = str(result.result)
                else:
                    step.observation = f"Error: {result.error}"
                
                # Update context
                context += f"Thought {step_num}: {thought}\n"
                context += f"Action {step_num}: {action_call.name}({json.dumps(action_call.arguments)})\n"
                context += f"Observation {step_num}: {step.observation}\n\n"
            else:
                # No action - generate final answer
                step.is_final = True
                step.final_answer = generate_final(context, self.steps)
                self.steps.append(step)
                return step.final_answer
            
            self.steps.append(step)
        
        # Max steps reached
        return generate_final(context, self.steps)
    
    def get_trace(self) -> List[Dict[str, Any]]:
        """Get execution trace."""
        return [
            {
                "step": s.step_number,
                "thought": s.thought,
                "action": s.action,
                "action_input": s.action_input,
                "observation": s.observation,
                "is_final": s.is_final,
                "final_answer": s.final_answer,
            }
            for s in self.steps
        ]


# ============================================================================
# Chain-of-Thought Reasoning
# ============================================================================

@dataclass
class CoTStep:
    """Chain-of-thought reasoning step."""
    step: int
    reasoning: str
    confidence: float = 1.0


class ChainOfThoughtEngine:
    """Chain-of-thought reasoning engine."""
    
    def __init__(self, max_steps: int = 10):
        self.max_steps = max_steps
        self.steps: List[CoTStep] = []
    
    def reason(
        self,
        problem: str,
        generate_step: Callable[[str, List[CoTStep]], CoTStep],
        should_continue: Callable[[List[CoTStep]], bool] = None,
    ) -> str:
        """
        Perform chain-of-thought reasoning.
        
        Args:
            problem: The problem to solve
            generate_step: Function to generate next reasoning step
            should_continue: Function to determine if reasoning should continue
            
        Returns:
            Final conclusion
        """
        self.steps = []
        context = f"Problem: {problem}\n\n"
        
        for i in range(1, self.max_steps + 1):
            step = generate_step(context, self.steps)
            self.steps.append(step)
            
            context += f"Step {i}: {step.reasoning}\n"
            
            # Check if should continue
            if should_continue and not should_continue(self.steps):
                break
            
            # Check for conclusion markers
            if any(marker in step.reasoning.lower() for marker in 
                   ["therefore", "conclusion", "answer is", "final answer"]):
                break
        
        # Generate final answer from reasoning
        return self._synthesize_answer(context)
    
    def _synthesize_answer(self, context: str) -> str:
        """Synthesize final answer from reasoning trace."""
        # In practice, this would call an LLM to synthesize
        # For now, return the last step's reasoning
        if self.steps:
            return self.steps[-1].reasoning
        return "Unable to reach conclusion."
    
    def get_trace(self) -> List[Dict[str, Any]]:
        """Get reasoning trace."""
        return [
            {"step": s.step, "reasoning": s.reasoning, "confidence": s.confidence}
            for s in self.steps
        ]


# ============================================================================
# Multi-Step Planner
# ============================================================================

@dataclass
class PlanStep:
    """Single step in a plan."""
    step_id: str
    description: str
    action: str  # Function name or "reasoning"
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed
    result: Any = None
    error: Optional[str] = None


@dataclass
class ExecutionPlan:
    """Multi-step execution plan."""
    plan_id: str
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending, running, completed, failed


class MultiStepPlanner:
    """Planner for multi-step tasks with dependencies."""
    
    def __init__(self, function_engine: FunctionCallingEngine = None):
        self.function_engine = function_engine or FunctionCallingEngine()
        self.plans: Dict[str, ExecutionPlan] = {}
    
    def create_plan(
        self,
        goal: str,
        steps: List[Dict[str, Any]],
    ) -> ExecutionPlan:
        """Create execution plan from step definitions."""
        import uuid
        
        plan = ExecutionPlan(
            plan_id=str(uuid.uuid4())[:8],
            goal=goal,
        )
        
        for i, step_def in enumerate(steps):
            step = PlanStep(
                step_id=step_def.get("id", f"step_{i}"),
                description=step_def["description"],
                action=step_def["action"],
                parameters=step_def.get("parameters", {}),
                depends_on=step_def.get("depends_on", []),
            )
            plan.steps.append(step)
        
        self.plans[plan.plan_id] = plan
        return plan
    
    def execute_plan(self, plan_id: str) -> ExecutionPlan:
        """Execute a plan respecting dependencies."""
        plan = self.plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        
        plan.status = "running"
        completed = set()
        
        # Topological sort by dependencies
        remaining = {s.step_id: s for s in plan.steps}
        
        while remaining:
            # Find steps with all dependencies met
            ready = [
                s for s in remaining.values()
                if all(dep in completed for dep in s.depends_on)
            ]
            
            if not ready:
                # Circular dependency or missing dependency
                for s in remaining.values():
                    s.status = "failed"
                    s.error = "Unmet dependencies or circular dependency"
                plan.status = "failed"
                break
            
            for step in ready:
                step.status = "running"
                
                try:
                    if step.action == "reasoning":
                        # Just mark as completed for reasoning steps
                        step.result = f"Reasoning: {step.description}"
                        step.status = "completed"
                    else:
                        # Execute function
                        call = FunctionCall(
                            name=step.action,
                            arguments=step.parameters,
                            call_id=f"{plan_id}_{step.step_id}",
                        )
                        result = self.function_engine.execute_function(call)
                        
                        if result.success:
                            step.result = result.result
                            step.status = "completed"
                        else:
                            step.error = result.error
                            step.status = "failed"
                            plan.status = "failed"
                            break
                
                except Exception as e:
                    step.error = str(e)
                    step.status = "failed"
                    plan.status = "failed"
                    break
                
                completed.add(step.step_id)
                del remaining[step.step_id]
        
        if plan.status == "running":
            plan.status = "completed"
        
        return plan
    
    def get_plan_status(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get plan status."""
        return self.plans.get(plan_id)


# ============================================================================
# Integration with Cognitive Model Adapter
# ============================================================================

class AdvancedCognitiveAdapter:
    """
    Advanced cognitive adapter with function calling, ReAct, CoT, and planning.
    """
    
    def __init__(self, base_adapter=None):
        self.base_adapter = base_adapter
        self.function_engine = FunctionCallingEngine()
        self.react_engine = ReActEngine(self.function_engine)
        self.cot_engine = ChainOfThoughtEngine()
        self.planner = MultiStepPlanner(self.function_engine)
        self.output_parser = StructuredOutputParser()
    
    def generate_with_tools(
        self,
        prompt: str,
        context: Dict[str, Any] = None,
        available_functions: List[str] = None,
    ) -> Dict[str, Any]:
        """Generate response with function calling capability."""
        # This would integrate with the base adapter's generate method
        # For now, return structure for function calling
        
        if available_functions is None:
            available_functions = list(self.function_engine.registry._functions.keys())
        
        schemas = [
            self.function_engine.registry.get_schema(name).to_json_schema()
            for name in available_functions
            if self.function_engine.registry.get_schema(name)
        ]
        
        return {
            "prompt": prompt,
            "context": context,
            "available_functions": schemas,
            "function_engine": self.function_engine,
        }
    
    def run_react(
        self,
        question: str,
        llm_generate: Callable[[str], str],
    ) -> str:
        """Run ReAct loop with LLM."""
        
        def generate_thought(ctx, steps):
            prompt = f"{ctx}\nThink step by step about how to answer. What should you do next?"
            return llm_generate(prompt)
        
        def generate_action(thought, steps):
            prompt = f"{thought}\n\nBased on this thought, what function should you call? Return JSON with name and arguments."
            response = llm_generate(prompt)
            calls = self.output_parser.parse_function_calls(response)
            return calls[0] if calls else None
        
        def generate_final(ctx, steps):
            prompt = f"{ctx}\n\nBased on all observations, provide the final answer."
            return llm_generate(prompt)
        
        return self.react_engine.run(question, generate_thought, generate_action, generate_final)
    
    def run_chain_of_thought(
        self,
        problem: str,
        llm_generate: Callable[[str], str],
    ) -> str:
        """Run chain-of-thought reasoning with LLM."""
        
        def generate_step(ctx, steps):
            prompt = f"{ctx}\nContinue reasoning step by step."
            reasoning = llm_generate(prompt)
            return CoTStep(step=len(steps) + 1, reasoning=reasoning)
        
        def should_continue(steps):
            if not steps:
                return True
            last = steps[-1].reasoning.lower()
            return not any(marker in last for marker in 
                          ["therefore", "conclusion", "answer is", "final answer"])
        
        return self.cot_engine.reason(problem, generate_step, should_continue)
    
    def create_and_execute_plan(
        self,
        goal: str,
        steps: List[Dict[str, Any]],
    ) -> ExecutionPlan:
        """Create and execute a multi-step plan."""
        plan = self.planner.create_plan(goal, steps)
        return self.planner.execute_plan(plan.plan_id)


# ============================================================================
# Default Instance
# ============================================================================

_advanced_cognitive: Optional[AdvancedCognitiveAdapter] = None


def get_advanced_cognitive() -> AdvancedCognitiveAdapter:
    """Get global advanced cognitive adapter."""
    global _advanced_cognitive
    if _advanced_cognitive is None:
        _advanced_cognitive = AdvancedCognitiveAdapter()
    return _advanced_cognitive