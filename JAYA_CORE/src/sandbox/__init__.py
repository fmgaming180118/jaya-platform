"""
Code Execution Sandbox Package for JAYA_CORE.

Provides secure code execution with multiple backends:
- Subprocess sandbox (basic isolation)
- Docker sandbox (stronger isolation)
- Language-specific helpers (Python, JavaScript)
- Security policies and capability gating
"""

from __future__ import annotations

from .execution import (
    ExecutionStatus,
    Language,
    ResourceLimits,
    ExecutionRequest,
    ExecutionResult,
    StreamChunk,
    SandboxBackend,
    SubprocessSandbox,
    DockerSandbox,
    SandboxManager,
    PythonSandbox,
    JavaScriptSandbox,
    SandboxSecurityPolicy,
    get_sandbox_manager,
    get_python_sandbox,
    get_javascript_sandbox,
)

__all__ = [
    "ExecutionStatus",
    "Language",
    "ResourceLimits",
    "ExecutionRequest",
    "ExecutionResult",
    "StreamChunk",
    "SandboxBackend",
    "SubprocessSandbox",
    "DockerSandbox",
    "SandboxManager",
    "PythonSandbox",
    "JavaScriptSandbox",
    "SandboxSecurityPolicy",
    "get_sandbox_manager",
    "get_python_sandbox",
    "get_javascript_sandbox",
]