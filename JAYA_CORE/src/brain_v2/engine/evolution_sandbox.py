"""Fail-closed subprocess sandbox for evolution candidates."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class SandboxFailureCode(str, Enum):
    CODE_LIMIT = "code_limit"
    CONFIGURATION_ERROR = "configuration_error"
    EXECUTION_ERROR = "execution_error"
    INPUT_LIMIT = "input_limit"
    INVALID_OUTPUT = "invalid_output"
    OUTPUT_LIMIT = "output_limit"
    POLICY_REJECTED = "policy_rejected"
    RESOURCE_LIMIT = "resource_limit"
    TIMEOUT = "timeout"
    WORKER_ERROR = "worker_error"


@dataclass(frozen=True)
class SandboxResult:
    ok: bool
    code_digest: str
    duration_ms: float
    outcome: Dict[str, Any] = field(default_factory=dict)
    function_spec: Dict[str, Any] = field(default_factory=dict)
    worker_pid: Optional[int] = None
    failure_code: Optional[SandboxFailureCode] = None
    failure_message: str = ""

    def failure_payload(self) -> Dict[str, Any]:
        return {
            "code": (
                self.failure_code.value
                if self.failure_code is not None
                else SandboxFailureCode.WORKER_ERROR.value
            ),
            "message": self.failure_message,
            "code_digest": self.code_digest,
        }


class EvolutionSandbox:
    """Execute restricted evolution code outside the JAYA runtime process."""

    def __init__(
        self,
        *,
        timeout_s: float = 1.0,
        memory_limit_mb: int = 128,
        cpu_time_s: int = 1,
        max_code_bytes: int = 16_384,
        max_output_bytes: int = 65_536,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("sandbox timeout_s must be positive")
        if memory_limit_mb < 64:
            raise ValueError("sandbox memory_limit_mb must be at least 64")
        if cpu_time_s < 1:
            raise ValueError("sandbox cpu_time_s must be at least 1")
        if max_code_bytes < 128:
            raise ValueError("sandbox max_code_bytes is too small")
        if max_output_bytes < 1_024:
            raise ValueError("sandbox max_output_bytes is too small")

        self.timeout_s = float(timeout_s)
        self.memory_limit_mb = int(memory_limit_mb)
        self.cpu_time_s = int(cpu_time_s)
        self.max_code_bytes = int(max_code_bytes)
        self.max_output_bytes = int(max_output_bytes)
        self._worker_path = Path(__file__).with_name(
            "evolution_sandbox_worker.py"
        )
        self._runs = 0
        self._rejections = 0
        self._timeouts = 0

    def run_experiment(self, code: str) -> SandboxResult:
        return self._run(mode="experiment", code=code)

    def validate_morphic(
        self,
        code: str,
        *,
        expected_function: str,
    ) -> SandboxResult:
        return self._run(
            mode="morphic",
            code=code,
            expected_function=expected_function,
        )

    def status(self) -> Dict[str, Any]:
        return {
            "runs": self._runs,
            "rejections": self._rejections,
            "timeouts": self._timeouts,
            "timeout_s": self.timeout_s,
            "memory_limit_mb": self.memory_limit_mb,
            "cpu_time_s": self.cpu_time_s,
            "max_code_bytes": self.max_code_bytes,
            "max_output_bytes": self.max_output_bytes,
            "worker": str(self._worker_path),
        }

    def _run(
        self,
        *,
        mode: str,
        code: str,
        expected_function: Optional[str] = None,
    ) -> SandboxResult:
        started = time.perf_counter()
        code_digest = self._digest(code)
        if not isinstance(code, str):
            return self._failure(
                SandboxFailureCode.POLICY_REJECTED,
                "candidate code must be a string",
                code_digest,
                started,
            )
        if len(code.encode("utf-8")) > self.max_code_bytes:
            return self._failure(
                SandboxFailureCode.CODE_LIMIT,
                "candidate code exceeds sandbox byte limit",
                code_digest,
                started,
            )
        if not self._worker_path.is_file():
            return self._failure(
                SandboxFailureCode.CONFIGURATION_ERROR,
                "sandbox worker is unavailable",
                code_digest,
                started,
            )
        if os.name not in {"nt", "posix"}:
            return self._failure(
                SandboxFailureCode.CONFIGURATION_ERROR,
                f"unsupported sandbox platform: {os.name}",
                code_digest,
                started,
            )

        request = {
            "mode": mode,
            "code": code,
            "expected_function": expected_function,
            "memory_limit_mb": self.memory_limit_mb,
            "cpu_time_s": self.cpu_time_s,
        }
        request_bytes = json.dumps(
            request,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        process: Optional[subprocess.Popen[bytes]] = None
        job: Optional[Tuple[Any, int]] = None
        sandbox_dir = tempfile.TemporaryDirectory(
            prefix="jaya-evolution-sandbox-",
            ignore_cleanup_errors=True,
        )
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(self._worker_path),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=sandbox_dir.name,
                env=self._minimal_environment(),
                close_fds=True,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if os.name == "nt"
                    else 0
                ),
                start_new_session=os.name != "nt",
            )
            if os.name == "nt":
                job = self._assign_windows_job(process)
            stdout, stderr = process.communicate(
                input=request_bytes,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            self._timeouts += 1
            if process is not None:
                process.kill()
                process.communicate()
            return self._failure(
                SandboxFailureCode.TIMEOUT,
                f"candidate exceeded {self.timeout_s:.3f}s timeout",
                code_digest,
                started,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
            return self._failure(
                SandboxFailureCode.CONFIGURATION_ERROR,
                f"sandbox worker could not start securely: {exc}",
                code_digest,
                started,
            )
        finally:
            if job is not None:
                kernel32, job_handle = job
                kernel32.CloseHandle(job_handle)
            sandbox_dir.cleanup()

        self._runs += 1
        if process is None:
            return self._failure(
                SandboxFailureCode.CONFIGURATION_ERROR,
                "sandbox process was not created",
                code_digest,
                started,
            )
        if len(stdout) > self.max_output_bytes:
            return self._failure(
                SandboxFailureCode.OUTPUT_LIMIT,
                "sandbox output exceeds byte limit",
                code_digest,
                started,
            )
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace")[:1_000]
            return self._failure(
                SandboxFailureCode.RESOURCE_LIMIT,
                message or f"sandbox worker exited with {process.returncode}",
                code_digest,
                started,
            )

        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            return self._failure(
                SandboxFailureCode.INVALID_OUTPUT,
                f"sandbox returned invalid JSON: {exc}",
                code_digest,
                started,
            )
        if not isinstance(payload, dict):
            return self._failure(
                SandboxFailureCode.INVALID_OUTPUT,
                "sandbox response must be an object",
                code_digest,
                started,
            )
        if payload.get("ok") is not True:
            failure = payload.get("failure")
            if not isinstance(failure, dict):
                failure = {}
            raw_code = str(
                failure.get("code")
                or SandboxFailureCode.WORKER_ERROR.value
            )
            try:
                failure_code = SandboxFailureCode(raw_code)
            except ValueError:
                failure_code = SandboxFailureCode.WORKER_ERROR
            return self._failure(
                failure_code,
                str(failure.get("message") or "sandbox rejected candidate"),
                code_digest,
                started,
            )

        outcome = payload.get("outcome")
        function_spec = payload.get("function_spec")
        if outcome is not None and not isinstance(outcome, dict):
            return self._failure(
                SandboxFailureCode.INVALID_OUTPUT,
                "sandbox outcome must be an object",
                code_digest,
                started,
            )
        if function_spec is not None and not isinstance(function_spec, dict):
            return self._failure(
                SandboxFailureCode.INVALID_OUTPUT,
                "sandbox function spec must be an object",
                code_digest,
                started,
            )
        return SandboxResult(
            ok=True,
            code_digest=code_digest,
            duration_ms=self._duration_ms(started),
            outcome=dict(outcome or {}),
            function_spec=dict(function_spec or {}),
            worker_pid=(
                int(payload["worker_pid"])
                if isinstance(payload.get("worker_pid"), int)
                else None
            ),
        )

    def _failure(
        self,
        code: SandboxFailureCode,
        message: str,
        code_digest: str,
        started: float,
    ) -> SandboxResult:
        self._rejections += 1
        return SandboxResult(
            ok=False,
            code_digest=code_digest,
            duration_ms=self._duration_ms(started),
            failure_code=code,
            failure_message=message,
        )

    def _assign_windows_job(
        self,
        process: subprocess.Popen[bytes],
    ) -> Tuple[Any, int]:
        import ctypes
        from ctypes import wintypes

        class LargeInteger(ctypes.Structure):
            _fields_ = [("QuadPart", ctypes.c_longlong)]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", LargeInteger),
                ("PerJobUserTimeLimit", LargeInteger),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
        ]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise RuntimeError(
                f"CreateJobObjectW failed: {ctypes.get_last_error()}"
            )

        info = ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = (
            0x00000002  # JOB_OBJECT_LIMIT_PROCESS_TIME
            | 0x00000008  # JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | 0x00000100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        info.BasicLimitInformation.PerProcessUserTimeLimit.QuadPart = (
            self.cpu_time_s * 10_000_000
        )
        info.BasicLimitInformation.ActiveProcessLimit = 1
        info.ProcessMemoryLimit = self.memory_limit_mb * 1024 * 1024

        if not kernel32.SetInformationJobObject(
            job,
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(job)
            raise RuntimeError(f"SetInformationJobObject failed: {error}")
        if not kernel32.AssignProcessToJobObject(job, int(process._handle)):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(job)
            raise RuntimeError(f"AssignProcessToJobObject failed: {error}")
        return kernel32, int(job)

    @staticmethod
    def _minimal_environment() -> Dict[str, str]:
        allowed = (
            "COMSPEC",
            "LANG",
            "LC_ALL",
            "SYSTEMROOT",
            "TMP",
            "TEMP",
            "WINDIR",
        )
        environment = {
            key: os.environ[key]
            for key in allowed
            if key in os.environ
        }
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        return environment

    @staticmethod
    def _digest(code: Any) -> str:
        data = code.encode("utf-8") if isinstance(code, str) else repr(code).encode()
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _duration_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1_000.0, 4)
