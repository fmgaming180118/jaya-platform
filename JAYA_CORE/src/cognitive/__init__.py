"""
JAYA Core Cognitive Module.

Provides advanced cognitive capabilities:
- Function calling / tool use framework
- Structured output parsing
- Chain-of-thought reasoning
- ReAct (Reasoning + Acting) pattern
- Multi-step planning and execution
"""

from __future__ import annotations

from .advanced import (
    ParameterType,
    FunctionParameter,
    FunctionSchema,
    FunctionCall,
    FunctionResult,
    FunctionRegistry,
    get_function_registry,
    register_function,
    FunctionCallingEngine,
    StructuredOutputParser,
    ReActStep,
    ReActEngine,
    CoTStep,
    ChainOfThoughtEngine,
    PlanStep,
    ExecutionPlan,
    MultiStepPlanner,
    AdvancedCognitiveAdapter,
    get_advanced_cognitive,
)

__all__ = [
    "ParameterType",
    "FunctionParameter",
    "FunctionSchema",
    "FunctionCall",
    "FunctionResult",
    "FunctionRegistry",
    "get_function_registry",
    "register_function",
    "FunctionCallingEngine",
    "StructuredOutputParser",
    "ReActStep",
    "ReActEngine",
    "CoTStep",
    "ChainOfThoughtEngine",
    "PlanStep",
    "ExecutionPlan",
    "MultiStepPlanner",
    "AdvancedCognitiveAdapter",
    "get_advanced_cognitive",
]
