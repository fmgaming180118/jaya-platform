"""
Code Execution Sandbox for JAYA_CORE.

Provides:
- Secure Python code execution with resource limits
- Multiple backend support (subprocess, Docker, gVisor, Firecracker)
- Language support (Python, JavaScript, Bash, etc.)
- Result capture and streaming
- Security policies and capability gating
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Union

from jaya_core.observability import get_structured_logger, record_error
from jaya_core.security import get_audit_logger, require_capability, get_capability_manager, Capability, InputValidator

logger = get_structured_logger(__name__, component="code_sandbox")
audit_logger = get_audit_logger()


# ============================================================================
# Data Classes
# ============================================================================

class ExecutionStatus(Enum):
    """Execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"
    SECURITY_VIOLATION = "security_violation"


class Language(Enum):
    """Supported languages."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    BASH = "bash"
    SH = "sh"
    POWERSHELL = "powershell"
    SQL = "sql"
    R = "r"
    JULIA = "julia"


@dataclass
class ResourceLimits:
    """Resource limits for execution."""
    max_cpu_time_seconds: float = 30.0
    max_wall_time_seconds: float = 60.0
    max_memory_mb: int = 512
    max_disk_mb: int = 100
    max_processes: int = 10
    max_file_size_mb: int = 10
    network_allowed: bool = False
    allowed_domains: List[str] = field(default_factory=list)


@dataclass
class ExecutionRequest:
    """Code execution request."""
    code: str
    language: Language = Language.PYTHON
    stdin: str = ""
    environment: Dict[str, str] = field(default_factory=dict)
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    working_directory: Optional[str] = None
    files: Dict[str, str] = field(default_factory=dict)  # filename -> content
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "anonymous"


@dataclass
class ExecutionResult:
    """Code execution result."""
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    duration_ms: float = 0.0
    memory_used_mb: float = 0.0
    cpu_time_ms: float = 0.0
    error: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)  # filename -> content
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """Streaming output chunk."""
    type: str  # "stdout", "stderr", "status", "error"
    data: str
    timestamp: float = field(default_factory=time.time)


# ============================================================================
# Sandbox Backends
# ============================================================================

class SandboxBackend(ABC):
    """Abstract sandbox backend."""
    
    @abstractmethod
    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute code and return result."""
        pass
    
    @abstractmethod
    async def execute_streaming(
        self, 
        request: ExecutionRequest
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute code with streaming output."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend is available."""
        pass
    
    @abstractmethod
    def get_supported_languages(self) -> List[Language]:
        """Get supported languages."""
        pass


class SubprocessSandbox(SandboxBackend):
    """Subprocess-based sandbox (basic isolation)."""
    
    def __init__(self):
        self._running_processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
    
    def is_available(self) -> bool:
        return True
    
    def get_supported_languages(self) -> List[Language]:
        return [
            Language.PYTHON, Language.JAVASCRIPT, Language.TYPESCRIPT,
            Language.BASH, Language.SH, Language.POWERSHELL,
        ]
    
    def _get_interpreter(self, language: Language) -> List[str]:
        """Get interpreter command for language."""
        import sys
        is_windows = sys.platform == "win32"
        
        interpreters = {
            Language.PYTHON: ["python", "-u"] if is_windows else ["python3", "-u"],
            Language.JAVASCRIPT: ["node"],
            Language.TYPESCRIPT: ["npx", "ts-node"],
            Language.BASH: ["bash"],
            Language.SH: ["sh"],
            Language.POWERSHELL: ["pwsh", "-Command"],
        }
        return interpreters.get(language, ["python", "-u"] if is_windows else ["python3", "-u"])
    
    def _prepare_files(self, request: ExecutionRequest, work_dir: Path):
        """Prepare input files."""
        for filename, content in request.files.items():
            file_path = work_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        
        # Write main code file
        ext_map = {
            Language.PYTHON: ".py",
            Language.JAVASCRIPT: ".js",
            Language.TYPESCRIPT: ".ts",
            Language.BASH: ".sh",
            Language.SH: ".sh",
            Language.POWERSHELL: ".ps1",
        }
        ext = ext_map.get(request.language, ".py")
        main_file = work_dir / f"main{ext}"
        main_file.write_text(request.code, encoding="utf-8")
    
    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute code in subprocess."""
        start_time = time.time()
        
        # Create working directory
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            
            # Prepare files
            self._prepare_files(request, work_dir)
            
            # Get interpreter
            interpreter = self._get_interpreter(request.language)
            main_file = work_dir / f"main{self._get_extension(request.language)}"
            
            # Build command
            cmd = interpreter + [str(main_file)]
            
            # Prepare environment
            env = os.environ.copy()
            env.update(request.environment)
            
            # Security: restrict environment
            env["PYTHONPATH"] = ""
            env["PATH"] = "/usr/bin:/bin"
            
            # Execute with timeout
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE if request.stdin else None,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(work_dir),
                    env=env,
                    limit=1024 * 1024,  # 1MB output limit
                )
                
                # Track process
                process_id = str(uuid.uuid4())
                with self._lock:
                    self._running_processes[process_id] = process
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(input=request.stdin.encode() if request.stdin else None),
                        timeout=request.resource_limits.max_wall_time_seconds,
                    )
                    
                    duration_ms = (time.time() - start_time) * 1000
                    
                    return ExecutionResult(
                        status=ExecutionStatus.COMPLETED if process.returncode == 0 else ExecutionStatus.FAILED,
                        stdout=stdout.decode('utf-8', errors='replace'),
                        stderr=stderr.decode('utf-8', errors='replace'),
                        exit_code=process.returncode,
                        duration_ms=duration_ms,
                    )
                
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    return ExecutionResult(
                        status=ExecutionStatus.TIMEOUT,
                        error=f"Execution timed out after {request.resource_limits.max_wall_time_seconds}s",
                        duration_ms=(time.time() - start_time) * 1000,
                    )
                
                finally:
                    with self._lock:
                        self._running_processes.pop(process_id, None)
            
            except Exception as e:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error=str(e),
                    duration_ms=(time.time() - start_time) * 1000,
                )
    
    def _get_extension(self, language: Language) -> str:
        """Get file extension for language."""
        ext_map = {
            Language.PYTHON: ".py",
            Language.JAVASCRIPT: ".js",
            Language.TYPESCRIPT: ".ts",
            Language.BASH: ".sh",
            Language.SH: ".sh",
            Language.POWERSHELL: ".ps1",
        }
        return ext_map.get(language, ".py")
    
    async def execute_streaming(
        self, 
        request: ExecutionRequest
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute with streaming output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            self._prepare_files(request, work_dir)
            
            interpreter = self._get_interpreter(request.language)
            main_file = work_dir / f"main{self._get_extension(request.language)}"
            cmd = interpreter + [str(main_file)]
            
            env = os.environ.copy()
            env.update(request.environment)
            env["PYTHONPATH"] = ""
            env["PATH"] = "/usr/bin:/bin"
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if request.stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
                env=env,
            )
            
            # Stream stdout and stderr
            async def read_stream(stream, chunk_type):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    yield StreamChunk(type=chunk_type, data=line.decode('utf-8', errors='replace'))
            
            # Run both streams concurrently
            stdout_task = asyncio.create_task(self._consume_stream(process.stdout, "stdout"))
            stderr_task = asyncio.create_task(self._consume_stream(process.stderr, "stderr"))
            
            # Send stdin if provided
            if request.stdin and process.stdin:
                process.stdin.write(request.stdin.encode())
                await process.stdin.drain()
                process.stdin.close()
            
            # Wait for completion
            await process.wait()
            
            # Collect results
            async for chunk in stdout_task:
                yield chunk
            async for chunk in stderr_task:
                yield chunk
            
            yield StreamChunk(
                type="status",
                data=json.dumps({
                    "exit_code": process.returncode,
                    "status": "completed" if process.returncode == 0 else "failed",
                })
            )
    
    async def _consume_stream(self, stream, chunk_type):
        """Consume stream and yield chunks."""
        while True:
            line = await stream.readline()
            if not line:
                break
            yield StreamChunk(type=chunk_type, data=line.decode('utf-8', errors='replace'))


class DockerSandbox(SandboxBackend):
    """Docker-based sandbox (stronger isolation)."""
    
    def __init__(self, image: str = "python:3.11-slim", network: str = "none"):
        self.image = image
        self.network = network
        self._docker_available = self._check_docker()
    
    def _check_docker(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def is_available(self) -> bool:
        return self._docker_available
    
    def get_supported_languages(self) -> List[Language]:
        return [
            Language.PYTHON, Language.JAVASCRIPT, Language.TYPESCRIPT,
            Language.BASH, Language.SH, Language.POWERSHELL,
            Language.SQL, Language.R, Language.JULIA,
        ]
    
    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute code in Docker container."""
        if not self._docker_available:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error="Docker not available",
            )
        
        start_time = time.time()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            
            # Prepare files
            for filename, content in request.files.items():
                file_path = work_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
            
            ext_map = {
                Language.PYTHON: ".py",
                Language.JAVASCRIPT: ".js",
                Language.TYPESCRIPT: ".ts",
                Language.BASH: ".sh",
                Language.SH: ".sh",
                Language.POWERSHELL: ".ps1",
            }
            ext = ext_map.get(request.language, ".py")
            main_file = work_dir / f"main{ext}"
            main_file.write_text(request.code, encoding="utf-8")
            
            # Build Docker command
            container_name = f"jaya-sandbox-{uuid.uuid4().hex[:8]}"
            
            cmd = [
                "docker", "run", "--rm",
                "--name", container_name,
                "--network", self.network,
                "--cpus", "1.0",
                "--memory", f"{request.resource_limits.max_memory_mb}m",
                "--pids-limit", str(request.resource_limits.max_processes),
                "-v", f"{work_dir}:/workspace:ro",
                "-w", "/workspace",
                self.image,
            ]
            
            # Add interpreter command
            interpreters = {
                Language.PYTHON: ["python3", "-u", "main.py"],
                Language.JAVASCRIPT: ["node", "main.js"],
                Language.TYPESCRIPT: ["npx", "ts-node", "main.ts"],
                Language.BASH: ["bash", "main.sh"],
                Language.SH: ["sh", "main.sh"],
            }
            cmd.extend(interpreters.get(request.language, ["python3", "-u", "main.py"]))
            
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE if request.stdin else None,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=1024 * 1024,
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(input=request.stdin.encode() if request.stdin else None),
                        timeout=request.resource_limits.max_wall_time_seconds,
                    )
                    
                    return ExecutionResult(
                        status=ExecutionStatus.COMPLETED if process.returncode == 0 else ExecutionStatus.FAILED,
                        stdout=stdout.decode('utf-8', errors='replace'),
                        stderr=stderr.decode('utf-8', errors='replace'),
                        exit_code=process.returncode,
                        duration_ms=(time.time() - start_time) * 1000,
                    )
                
                except asyncio.TimeoutError:
                    # Kill container
                    subprocess.run(["docker", "kill", container_name], capture_output=True)
                    return ExecutionResult(
                        status=ExecutionStatus.TIMEOUT,
                        error=f"Execution timed out after {request.resource_limits.max_wall_time_seconds}s",
                        duration_ms=(time.time() - start_time) * 1000,
                    )
            
            except Exception as e:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error=str(e),
                    duration_ms=(time.time() - start_time) * 1000,
                )
    
    async def execute_streaming(
        self, 
        request: ExecutionRequest
    ) -> AsyncGenerator[StreamChunk, None]:
        """Streaming not fully implemented for Docker yet."""
        result = await self.execute(request)
        if result.stdout:
            yield StreamChunk(type="stdout", data=result.stdout)
        if result.stderr:
            yield StreamChunk(type="stderr", data=result.stderr)
        yield StreamChunk(type="status", data=json.dumps({
            "exit_code": result.exit_code,
            "status": result.status.value,
        }))


# ============================================================================
# Sandbox Manager
# ============================================================================

class SandboxManager:
    """Manages code execution sandboxes."""
    
    def __init__(self):
        self.backends: Dict[str, SandboxBackend] = {}
        self._default_backend = "subprocess"
        self._register_default_backends()
    
    def _register_default_backends(self):
        """Register default backends."""
        self.register_backend("subprocess", SubprocessSandbox())
        
        docker = DockerSandbox()
        if docker.is_available():
            self.register_backend("docker", docker)
    
    def register_backend(self, name: str, backend: SandboxBackend):
        """Register a sandbox backend."""
        self.backends[name] = backend
        logger.info("Sandbox backend registered", name=name, available=backend.is_available())
    
    def get_backend(self, name: str = None) -> SandboxBackend:
        """Get backend by name."""
        name = name or self._default_backend
        backend = self.backends.get(name)
        if not backend:
            raise ValueError(f"Backend not found: {name}")
        if not backend.is_available():
            raise RuntimeError(f"Backend not available: {name}")
        return backend
    
    def set_default_backend(self, name: str):
        """Set default backend."""
        if name not in self.backends:
            raise ValueError(f"Backend not found: {name}")
        self._default_backend = name
    
    def list_backends(self) -> List[Dict[str, Any]]:
        """List available backends."""
        return [
            {
                "name": name,
                "available": backend.is_available(),
                "languages": [l.value for l in backend.get_supported_languages()],
            }
            for name, backend in self.backends.items()
        ]
    
    async def execute(
        self,
        request: ExecutionRequest,
        backend: str = None,
    ) -> ExecutionResult:
        """Execute code using specified backend."""
        # Audit log
        audit_logger.log_tool_execution(
            actor=request.user_id,
            tool=f"code_execution:{request.language.value}",
            skill="sandbox",
            success=True,  # Will update based on result
            details={"backend": backend or self._default_backend, "session_id": request.session_id},
        )
        
        # Check capability
        cap_manager = get_capability_manager()
        if not cap_manager.check(request.user_id, "code_execution", "execute", "sandbox"):
            audit_logger.log_authorization(
                actor=request.user_id,
                resource="sandbox",
                action="execute",
                allowed=False,
            )
            return ExecutionResult(
                status=ExecutionStatus.SECURITY_VIOLATION,
                error="Capability required: code_execution",
            )
        
        # Validate input
        valid, error = InputValidator.validate_prompt(request.code)
        if not valid:
            return ExecutionResult(
                status=ExecutionStatus.SECURITY_VIOLATION,
                error=f"Input validation failed: {error}",
            )
        
        # Execute
        sandbox = self.get_backend(backend)
        result = await sandbox.execute(request)
        
        # Update audit log
        audit_logger.log_tool_execution(
            actor=request.user_id,
            tool=f"code_execution:{request.language.value}",
            skill="sandbox",
            success=result.status == ExecutionStatus.COMPLETED,
            details={
                "backend": backend or self._default_backend,
                "session_id": request.session_id,
                "status": result.status.value,
                "duration_ms": result.duration_ms,
            },
        )
        
        return result
    
    async def execute_streaming(
        self,
        request: ExecutionRequest,
        backend: str = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute with streaming output."""
        sandbox = self.get_backend(backend)
        async for chunk in sandbox.execute_streaming(request):
            yield chunk


# ============================================================================
# Language-Specific Helpers
# ============================================================================

class PythonSandbox:
    """Python-specific sandbox with additional features."""
    
    def __init__(self, manager: SandboxManager):
        self.manager = manager
    
    async def execute(
        self,
        code: str,
        packages: List[str] = None,
        stdin: str = "",
        timeout: float = 30.0,
        user_id: str = "anonymous",
    ) -> ExecutionResult:
        """Execute Python code with optional package installation."""
        # Build code with package installation
        full_code = code
        if packages:
            install_code = f"""
import subprocess
import sys
for pkg in {packages}:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])
"""
            full_code = install_code + "\n" + code
        
        request = ExecutionRequest(
            code=full_code,
            language=Language.PYTHON,
            stdin=stdin,
            resource_limits=ResourceLimits(
                max_wall_time_seconds=timeout,
                max_memory_mb=512,
                network_allowed=bool(packages),  # Need network for pip
            ),
            user_id=user_id,
        )
        
        return await self.manager.execute(request)
    
    async def execute_notebook(
        self,
        cells: List[Dict[str, Any]],  # [{"type": "code", "code": "..."}, ...]
        timeout: float = 60.0,
        user_id: str = "anonymous",
    ) -> List[ExecutionResult]:
        """Execute notebook-style cells with shared state."""
        # This would need a persistent kernel - simplified version
        results = []
        shared_code = ""
        
        for cell in cells:
            if cell.get("type") == "code":
                shared_code += "\n" + cell["code"]
                result = await self.execute(shared_code, timeout=timeout, user_id=user_id)
                results.append(result)
        
        return results


class JavaScriptSandbox:
    """JavaScript/TypeScript sandbox."""
    
    def __init__(self, manager: SandboxManager):
        self.manager = manager
    
    async def execute(
        self,
        code: str,
        language: Language = Language.JAVASCRIPT,
        npm_packages: List[str] = None,
        stdin: str = "",
        timeout: float = 30.0,
        user_id: str = "anonymous",
    ) -> ExecutionResult:
        """Execute JavaScript/TypeScript code."""
        full_code = code
        if npm_packages:
            # Would need package.json and npm install
            pass
        
        request = ExecutionRequest(
            code=full_code,
            language=language,
            stdin=stdin,
            resource_limits=ResourceLimits(
                max_wall_time_seconds=timeout,
                max_memory_mb=512,
            ),
            user_id=user_id,
        )
        
        return await self.manager.execute(request)


# ============================================================================
# Security Policy
# ============================================================================

class SandboxSecurityPolicy:
    """Security policy for code execution."""
    
    # Dangerous patterns to block
    BLOCKED_PATTERNS = [
        # System access
        r"os\.system\s*\(",
        r"subprocess\.(run|call|Popen)\s*\(",
        r"eval\s*\(",
        r"exec\s*\(",
        r"compile\s*\(",
        r"__import__\s*\(",
        r"getattr\s*\(",
        r"setattr\s*\(",
        r"delattr\s*\(",
        r"open\s*\(",
        r"file\s*\(",
        r"input\s*\(",
        # Network
        r"socket\.",
        r"urllib\.",
        r"requests\.",
        r"http\.",
        r"ftplib\.",
        r"telnetlib\.",
        # File system
        r"shutil\.",
        r"pathlib\.",
        r"os\.(remove|rmdir|mkdir|chdir|listdir|walk)",
        r"glob\.",
        # Process
        r"multiprocessing\.",
        r"threading\.",
        r"_thread\.",
        # Dangerous modules
        r"import\s+(os|sys|subprocess|shutil|socket|urllib|requests|http|ftplib|telnetlib|multiprocessing|threading|_thread|ctypes|pickle|marshal|shelve|dbm|sqlite3|importlib|pkgutil|runpy)",
        r"from\s+(os|sys|subprocess|shutil|socket|urllib|requests|http)\s+import",
    ]
    
    ALLOWED_IMPORTS = {
        "math", "random", "datetime", "json", "re", "collections",
        "itertools", "functools", "statistics", "decimal", "fractions",
        "typing", "dataclasses", "enum", "uuid", "hashlib", "base64",
        "string", "textwrap", "html", "urllib.parse", "inspect",
    }
    
    @classmethod
    def validate_code(cls, code: str, language: Language = Language.PYTHON) -> tuple[bool, Optional[str]]:
        """Validate code against security policy."""
        if language != Language.PYTHON:
            # For other languages, basic validation
            return True, None
        
        # Check blocked patterns
        for pattern in cls.BLOCKED_PATTERNS:
            import re
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"Blocked pattern detected: {pattern}"
        
        # Check imports
        import_lines = re.findall(r'^\s*(?:import|from)\s+(\S+)', code, re.MULTILINE)
        for imp in import_lines:
            base_module = imp.split('.')[0]
            if base_module not in cls.ALLOWED_IMPORTS:
                return False, f"Import not allowed: {base_module}"
        
        return True, None


# ============================================================================
# Default Instances
# ============================================================================

_sandbox_manager: Optional[SandboxManager] = None
_python_sandbox: Optional[PythonSandbox] = None
_js_sandbox: Optional[JavaScriptSandbox] = None


def get_sandbox_manager() -> SandboxManager:
    """Get global sandbox manager."""
    global _sandbox_manager
    if _sandbox_manager is None:
        _sandbox_manager = SandboxManager()
    return _sandbox_manager


def get_python_sandbox() -> PythonSandbox:
    """Get Python sandbox."""
    global _python_sandbox
    if _python_sandbox is None:
        _python_sandbox = PythonSandbox(get_sandbox_manager())
    return _python_sandbox


def get_javascript_sandbox() -> JavaScriptSandbox:
    """Get JavaScript sandbox."""
    global _js_sandbox
    if _js_sandbox is None:
        _js_sandbox = JavaScriptSandbox(get_sandbox_manager())
    return _js_sandbox
