"""Fail-closed process interlock for JAYA_AGENT.

Arbitrary source execution is intentionally unsupported. Process execution is
available only through immutable profiles registered by trusted startup code
and still requires a signed, consented capability grant.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .capability_sandbox import (
    CapabilityDenied,
    CapabilitySandbox,
    ProcessProfile,
)


class SandboxInterlock:
    """Delegate fixed no-shell process profiles to the JAYA OS sandbox."""

    def __init__(
        self,
        *,
        sandbox: CapabilitySandbox | None = None,
        process_profiles: Mapping[str, ProcessProfile] | None = None,
        timeout_sec: float = 10.0,
        max_ram_mb: int = 256,
    ) -> None:
        if not 0.01 <= timeout_sec <= 10.0:
            raise ValueError("Process timeout must be between 0.01 and 10 seconds")
        if not 32 <= max_ram_mb <= 1024:
            raise ValueError("RAM policy must be between 32 and 1024 MiB")
        self.sandbox = sandbox or CapabilitySandbox()
        self.timeout_sec = timeout_sec
        self.max_ram_mb = max_ram_mb
        for name, profile in (process_profiles or {}).items():
            self.sandbox.register_process_profile(name, profile)

    def execute_safe_code(self, code: str) -> dict[str, Any]:
        """Reject the legacy arbitrary-code API regardless of content."""

        del code
        return {
            "success": False,
            "error_code": "ARBITRARY_CODE_DENIED",
            "error": (
                "Arbitrary source execution is disabled; use a reviewed "
                "process profile with an explicit capability grant"
            ),
        }

    async def execute_process_profile(
        self,
        profile_name: str,
        *,
        grant_token: str | None,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        """Execute a pre-registered profile and return redacted evidence."""

        try:
            execution = await self.sandbox.execute_process_profile(
                grant_token=grant_token,
                profile_name=profile_name,
                idempotency_key=idempotency_key,
                timeout_seconds=self.timeout_sec,
            )
            return {
                "success": True,
                "result": execution.result,
                "replayed": execution.replayed,
                "receipt": execution.receipt.to_dict(),
            }
        except CapabilityDenied as exc:
            return {
                "success": False,
                "error_code": exc.code,
                "error": exc.safe_message,
            }
