"""Fail-closed compatibility boundary for the retired Research sandbox.

Research may describe and package experiments, but it may not execute supplied
source code. Execution belongs to an injected, separately authorized runner.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from jaya_research.capability_boundary import ArbitraryExecutionRejected

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,127}$")
_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")


class LegacySandboxDisabledError(RuntimeError):
    """Raised when legacy local source execution is requested."""


class IsolatedArtifactRunner(Protocol):
    """Public runner interface implemented outside JAYA Research."""

    def run(
        self,
        *,
        artifact_id: str,
        artifact_sha256: str,
        profile: str,
        limits: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Execute a verified immutable artifact and return a signed receipt."""
        ...


class WindowsJobObjectSandbox:
    """Retired compatibility symbol; Research no longer creates processes."""

    def __init__(self, memory_limit_mb: int = 128) -> None:
        self.memory_limit_bytes = int(memory_limit_mb) * 1024 * 1024
        self.job_handle = None

    def assign_process(self, process_handle: Any) -> None:
        del process_handle
        raise LegacySandboxDisabledError(
            "Research cannot assign or launch host processes"
        )


class Sandbox:
    """Compatibility API that only delegates immutable artifacts."""

    def __init__(
        self,
        work_dir: str | Path = "sandbox_env",
        *,
        runner: IsolatedArtifactRunner | None = None,
    ) -> None:
        self.work_dir = Path(work_dir)
        self._runner = runner
        self.clang_path = None
        self.gcc_path = None
        self.wasmtime_available = False

    def run_artifact(
        self,
        *,
        artifact_id: str,
        artifact_sha256: str,
        profile: str,
        memory_limit_mb: int = 128,
        timeout_sec: float = 5.0,
    ) -> dict[str, Any]:
        """Delegate a digest-bound artifact to an injected isolated runner."""
        if self._runner is None:
            raise LegacySandboxDisabledError(
                "no authorized isolated artifact runner was injected"
            )
        if not _SAFE_ID.fullmatch(artifact_id):
            raise LegacySandboxDisabledError("invalid artifact_id")
        if not _SHA256.fullmatch(artifact_sha256):
            raise LegacySandboxDisabledError("invalid artifact_sha256")
        if not _SAFE_ID.fullmatch(profile):
            raise LegacySandboxDisabledError("invalid runner profile")
        if not 16 <= int(memory_limit_mb) <= 4096:
            raise LegacySandboxDisabledError("invalid memory limit")
        if not 0.1 <= float(timeout_sec) <= 300.0:
            raise LegacySandboxDisabledError("invalid timeout")
        receipt = self._runner.run(
            artifact_id=artifact_id,
            artifact_sha256=artifact_sha256.lower(),
            profile=profile,
            limits={
                "memory_limit_mb": int(memory_limit_mb),
                "timeout_sec": float(timeout_sec),
            },
        )
        if not isinstance(receipt, Mapping):
            raise LegacySandboxDisabledError("runner returned an invalid receipt")
        return dict(receipt)

    def run_isolated_python(self, python_code: str, **_: Any) -> dict[str, Any]:
        """Reject raw Python source before creating files or processes."""
        del python_code
        raise ArbitraryExecutionRejected(
            "raw Python execution is disabled; submit an immutable artifact"
        )

    def run_c_code(self, c_code: str, **_: Any) -> dict[str, Any]:
        """Reject raw C source before creating files or processes."""
        del c_code
        raise ArbitraryExecutionRejected(
            "raw C execution is disabled; submit an immutable artifact"
        )

    def run_wasm(self, wasm_bytes: bytes, **_: Any) -> dict[str, Any]:
        """Reject unverified bytecode before instantiating a runtime."""
        del wasm_bytes
        raise ArbitraryExecutionRejected(
            "raw WebAssembly execution is disabled; submit an immutable artifact"
        )

    def cleanup_workspace(self) -> None:
        """Compatibility no-op because this class never creates a workspace."""
        return None


if __name__ == "__main__":
    raise SystemExit(
        "Legacy Research source execution is disabled; use an artifact runner"
    )
