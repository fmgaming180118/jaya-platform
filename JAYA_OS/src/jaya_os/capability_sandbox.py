"""Fail-closed capability authorization and bounded process execution.

JAYA OS owns authorization for system effects. Agent skills describe an
action, but cannot execute it unless this module installs a short-lived,
signed execution ticket in the current context.
"""

from __future__ import annotations

import asyncio
import base64
import contextvars
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Iterable, Mapping, TypeVar
from urllib.parse import urlsplit

T = TypeVar("T")

_TOKEN_VERSION = 1
_MIN_SIGNING_KEY_BYTES = 32
_MAX_GRANT_TTL_SECONDS = 3600.0
_MIN_IDEMPOTENCY_KEY_LENGTH = 12
_MAX_IDEMPOTENCY_KEY_LENGTH = 128
_MAX_AUDIT_RECORDS = 2_000
_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|authorization|bearer|password|secret|token)"
    r"\b\s*[:=]\s*[^\s,;]+"
)
_WINDOWS_PATH_PATTERN = re.compile(r"(?i)\b[a-z]:\\[^\r\n\t\"']+")
_POSIX_PATH_PATTERN = re.compile(r"(?<![\w:])/(?:[^/\s]+/)*[^/\s]*")


class CapabilityDenied(PermissionError):
    """A stable, non-secret authorization failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class ActionPolicy:
    """OS policy for one effectful action."""

    resource_kind: str
    consent_required: bool = False
    max_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.resource_kind not in {"path", "network", "process", "system"}:
            raise ValueError("Unsupported resource kind")
        if not 0.01 <= self.max_timeout_seconds <= 60.0:
            raise ValueError("Action timeout must be between 0.01 and 60 seconds")


@dataclass(frozen=True)
class _ExecutionTicket:
    action: str
    resources: tuple[str, ...]
    expires_at: float


ACTIVE_CAPABILITY: contextvars.ContextVar[_ExecutionTicket | None] = (
    contextvars.ContextVar("jaya_active_capability", default=None)
)


@dataclass(frozen=True)
class AuditReceipt:
    """Signed evidence that deliberately excludes raw secrets and resources."""

    receipt_id: str
    grant_digest: str
    subject_digest: str
    action: str
    resource_digests: tuple[str, ...]
    idempotency_digest: str
    request_digest: str
    consent_digest: str | None
    started_at: float
    finished_at: float
    duration_ms: float
    status: str
    result_digest: str | None
    error_code: str | None
    error_message: str | None
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityExecution:
    """Result returned by the sandbox dispatcher."""

    result: Any
    receipt: AuditReceipt
    replayed: bool = False


@dataclass
class _IdempotencyRecord:
    request_digest: str
    state: str
    execution: CapabilityExecution | None = None


@dataclass(frozen=True)
class ProcessProfile:
    """A pre-registered process invocation; callers cannot inject arguments."""

    executable: Path
    arguments: tuple[str, ...] = ()
    cwd: Path | None = None
    cwd_root: Path | None = None
    environment: Mapping[str, str] = field(default_factory=dict)
    max_output_bytes: int = 64 * 1024
    executable_sha256: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        executable = Path(self.executable).resolve(strict=True)
        if not executable.is_file():
            raise ValueError("Process executable must be a regular file")
        if self.cwd is None or self.cwd_root is None:
            raise ValueError("Process profile requires a contained cwd and root")
        cwd = Path(self.cwd).resolve(strict=True)
        cwd_root = Path(self.cwd_root).resolve(strict=True)
        if not cwd.is_dir() or not cwd_root.is_dir():
            raise ValueError("Process cwd and root must be existing directories")
        try:
            cwd.relative_to(cwd_root)
        except ValueError as exc:
            raise ValueError("Process cwd must remain inside its root") from exc
        if not 1 <= self.max_output_bytes <= 1024 * 1024:
            raise ValueError("Process output limit must be 1 byte to 1 MiB")
        arguments = tuple(str(argument) for argument in self.arguments)
        if len(arguments) > 32 or any(
            not argument or len(argument) > 4096 or "\x00" in argument
            for argument in arguments
        ):
            raise ValueError("Process arguments violate policy")
        environment: dict[str, str] = {}
        for key, value in self.environment.items():
            if (
                not isinstance(key, str)
                or not isinstance(value, str)
                or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", key)
                or re.search(r"TOKEN|KEY|SECRET|PASSWORD|AUTH", key)
                or "\x00" in value
                or len(value) > 4096
            ):
                raise ValueError("Process environment entry violates policy")
            environment[key] = value
        object.__setattr__(self, "executable", executable)
        object.__setattr__(self, "arguments", arguments)
        object.__setattr__(self, "cwd", cwd)
        object.__setattr__(self, "cwd_root", cwd_root)
        object.__setattr__(self, "environment", MappingProxyType(environment))
        object.__setattr__(self, "executable_sha256", _hash_file(executable))


DEFAULT_ACTION_POLICIES: dict[str, ActionPolicy] = {
    "file.read": ActionPolicy("path", max_timeout_seconds=5.0),
    "file.list": ActionPolicy("path", max_timeout_seconds=5.0),
    "file.write": ActionPolicy(
        "path",
        consent_required=True,
        max_timeout_seconds=5.0,
    ),
    "network.search": ActionPolicy("network", max_timeout_seconds=15.0),
    "process.execute": ActionPolicy(
        "process",
        consent_required=True,
        max_timeout_seconds=10.0,
    ),
    "system.status": ActionPolicy("system", max_timeout_seconds=2.0),
    "device.audio.output": ActionPolicy(
        "system",
        consent_required=True,
        max_timeout_seconds=10.0,
    ),
    "system.memory.optimize": ActionPolicy(
        "system",
        consent_required=True,
        max_timeout_seconds=10.0,
    ),
}


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CapabilityDenied(
            "INVALID_REQUEST",
            "Capability request is not serializable",
        ) from exc


def _digest(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise CapabilityDenied(
            "INVALID_GRANT",
            "Capability grant encoding is invalid",
        ) from exc


def _redact(value: object) -> str:
    text = str(value)
    text = _SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        text,
    )
    text = _WINDOWS_PATH_PATTERN.sub("[REDACTED]", text)
    text = _POSIX_PATH_PATTERN.sub("[REDACTED]", text)
    return text[:500]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


async def _read_stream_bounded(
    stream: asyncio.StreamReader,
    max_bytes: int,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await stream.read(min(64 * 1024, max_bytes - total + 1))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise CapabilityDenied(
                "PROCESS_OUTPUT_LIMIT",
                "Process output exceeded its configured limit",
            )
        chunks.append(chunk)


def require_active_capability(
    action: str,
    resources: Iterable[str] | None = None,
) -> None:
    """Reject direct/bypassed skill calls outside an authorized dispatcher."""

    ticket = ACTIVE_CAPABILITY.get()
    if ticket is None:
        raise CapabilityDenied(
            "CAPABILITY_CONTEXT_REQUIRED",
            "Action must run through the capability dispatcher",
        )
    if ticket.action != action:
        raise CapabilityDenied(
            "CAPABILITY_ACTION_MISMATCH",
            "Active capability does not authorize this action",
        )
    if time.time() >= ticket.expires_at:
        raise CapabilityDenied("GRANT_EXPIRED", "Capability grant has expired")
    if resources is not None and tuple(resources) != ticket.resources:
        raise CapabilityDenied(
            "CAPABILITY_RESOURCE_MISMATCH",
            "Active capability does not authorize these resources",
        )


class CapabilitySandbox:
    """Authorize allowlisted actions with expiry, consent, and idempotency."""

    def __init__(
        self,
        *,
        signing_key: bytes | None = None,
        action_policies: Mapping[str, ActionPolicy] | None = None,
        clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
        audit_limit: int = _MAX_AUDIT_RECORDS,
    ) -> None:
        key = signing_key or secrets.token_bytes(_MIN_SIGNING_KEY_BYTES)
        if len(key) < _MIN_SIGNING_KEY_BYTES:
            raise ValueError("Capability signing key must contain at least 32 bytes")
        if not 1 <= audit_limit <= _MAX_AUDIT_RECORDS:
            raise ValueError("Audit limit is outside the supported range")
        self._signing_key = bytes(key)
        self._policies = dict(action_policies or DEFAULT_ACTION_POLICIES)
        self._clock = clock
        self._monotonic_clock = monotonic_clock
        self._audit: deque[AuditReceipt] = deque(maxlen=audit_limit)
        self._idempotency: dict[tuple[str, str], _IdempotencyRecord] = {}
        self._grant_uses: dict[str, int] = {}
        self._process_profiles: dict[str, ProcessProfile] = {}
        self._lock = asyncio.Lock()

    @property
    def allowed_actions(self) -> frozenset[str]:
        return frozenset(self._policies)

    def issue_grant(
        self,
        *,
        subject: str,
        actions: Iterable[str],
        resources: Mapping[str, Iterable[str]],
        ttl_seconds: float,
        max_uses: int = 1,
        consented_actions: Iterable[str] = (),
        consent_reference: str | None = None,
    ) -> str:
        """Create a bounded grant from trusted policy and consent input."""

        clean_subject = subject.strip()
        if not clean_subject or len(clean_subject) > 200:
            raise ValueError("Grant subject must contain 1 to 200 characters")
        if not 0 < ttl_seconds <= _MAX_GRANT_TTL_SECONDS:
            raise ValueError("Grant TTL must be within 1 hour")
        if not 1 <= max_uses <= 1_000:
            raise ValueError("Grant max_uses must be between 1 and 1000")

        action_set = frozenset(str(action) for action in actions)
        if not action_set:
            raise ValueError("Grant must include at least one action")
        if action_set.difference(self._policies):
            raise ValueError("Grant contains an action outside the OS allowlist")

        consent_set = frozenset(str(action) for action in consented_actions)
        required_consents = {
            action for action in action_set if self._policies[action].consent_required
        }
        if not consent_set.issubset(action_set):
            raise ValueError("Consent actions must be included in grant actions")
        if not required_consents.issubset(consent_set):
            raise ValueError("Explicit consent is required for this grant")
        if consent_set and (
            consent_reference is None
            or not consent_reference.strip()
            or len(consent_reference) > 200
        ):
            raise ValueError("Consented grants require a bounded consent reference")

        canonical_resources: dict[str, list[str]] = {}
        for action in sorted(action_set):
            scopes = list(resources.get(action, ()))
            if not scopes:
                raise ValueError(f"Grant action '{action}' requires resource scopes")
            canonical_resources[action] = sorted(
                {self._canonicalize_scope(action, scope) for scope in scopes}
            )

        now = self._clock()
        payload = {
            "v": _TOKEN_VERSION,
            "grant_id": str(uuid.uuid4()),
            "subject": clean_subject,
            "actions": sorted(action_set),
            "resources": canonical_resources,
            "issued_at": now,
            "expires_at": now + ttl_seconds,
            "max_uses": max_uses,
            "consented_actions": sorted(consent_set),
            "consent_digest": (
                _digest(consent_reference.strip()) if consent_reference else None
            ),
            "nonce": secrets.token_hex(16),
        }
        encoded = _b64encode(_canonical_json(payload))
        return f"{encoded}.{self._sign(encoded.encode('ascii'))}"

    def register_process_profile(self, name: str, profile: ProcessProfile) -> None:
        """Register a fixed executable/argument tuple outside prompt control."""

        if not isinstance(profile, ProcessProfile):
            raise TypeError("Process profile must use the reviewed schema")
        clean_name = name.strip()
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", clean_name):
            raise ValueError("Process profile name is invalid")
        if clean_name in self._process_profiles:
            raise ValueError("Process profile is already registered")
        self._process_profiles[clean_name] = profile

    async def execute(
        self,
        *,
        grant_token: str | None,
        action: str,
        resources: Iterable[str],
        idempotency_key: str | None,
        request_payload: Any,
        operation: Callable[[], Awaitable[T]],
        timeout_seconds: float | None = None,
    ) -> CapabilityExecution:
        """Authorize and execute an async operation once per request."""

        started_at = self._clock()
        started_monotonic = self._monotonic_clock()
        payload: dict[str, Any] | None = None
        canonical_resources: tuple[str, ...] = ()
        request_digest = _digest(_canonical_json(request_payload))
        idempotency_digest = _digest(idempotency_key or "")

        try:
            payload = self._verify_grant(grant_token)
            policy = self._policies.get(action)
            if policy is None:
                raise CapabilityDenied(
                    "ACTION_NOT_ALLOWED",
                    "Action is not present in the OS allowlist",
                )
            if action not in payload["actions"]:
                raise CapabilityDenied(
                    "ACTION_NOT_GRANTED",
                    "Capability grant does not include this action",
                )
            canonical_resources = tuple(
                self._canonicalize_resource(action, resource) for resource in resources
            )
            if not canonical_resources:
                raise CapabilityDenied(
                    "RESOURCE_REQUIRED",
                    "Action requires an explicit resource",
                )
            self._verify_resource_scopes(
                action,
                canonical_resources,
                payload["resources"][action],
            )
            if policy.consent_required and action not in payload["consented_actions"]:
                raise CapabilityDenied(
                    "CONSENT_REQUIRED",
                    "Action requires explicit consent",
                )
            clean_key = self._verify_idempotency_key(idempotency_key)

            grant_id = str(payload["grant_id"])
            record_key = (grant_id, clean_key)
            async with self._lock:
                existing = self._idempotency.get(record_key)
                if existing is not None:
                    if existing.request_digest != request_digest:
                        raise CapabilityDenied(
                            "IDEMPOTENCY_CONFLICT",
                            "Idempotency key was already used for another request",
                        )
                    if existing.state == "running":
                        raise CapabilityDenied(
                            "IDEMPOTENCY_IN_PROGRESS",
                            "The idempotent request is already in progress",
                        )
                    if existing.execution is None:
                        raise CapabilityDenied(
                            "IDEMPOTENCY_FAILED",
                            "The idempotent request previously failed",
                        )
                    replay_receipt = self._make_receipt(
                        payload=payload,
                        action=action,
                        resources=canonical_resources,
                        idempotency_digest=idempotency_digest,
                        request_digest=request_digest,
                        started_at=started_at,
                        started_monotonic=started_monotonic,
                        status="REPLAYED",
                        result_digest=(existing.execution.receipt.result_digest),
                    )
                    return CapabilityExecution(
                        result=existing.execution.result,
                        receipt=replay_receipt,
                        replayed=True,
                    )
                uses = self._grant_uses.get(grant_id, 0)
                if uses >= int(payload["max_uses"]):
                    raise CapabilityDenied(
                        "GRANT_EXHAUSTED",
                        "Capability grant has no remaining uses",
                    )
                self._grant_uses[grant_id] = uses + 1
                self._idempotency[record_key] = _IdempotencyRecord(
                    request_digest=request_digest,
                    state="running",
                )

            requested_timeout = (
                policy.max_timeout_seconds
                if timeout_seconds is None
                else timeout_seconds
            )
            if requested_timeout <= 0:
                raise CapabilityDenied(
                    "INVALID_TIMEOUT",
                    "Execution timeout must be greater than zero",
                )
            timeout = min(requested_timeout, policy.max_timeout_seconds)
            context_token = ACTIVE_CAPABILITY.set(
                _ExecutionTicket(
                    action=action,
                    resources=canonical_resources,
                    expires_at=(
                        time.time()
                        + max(
                            0.0,
                            float(payload["expires_at"]) - self._clock(),
                        )
                    ),
                )
            )
            try:
                result = await asyncio.wait_for(operation(), timeout=timeout)
            finally:
                ACTIVE_CAPABILITY.reset(context_token)

            receipt = self._make_receipt(
                payload=payload,
                action=action,
                resources=canonical_resources,
                idempotency_digest=idempotency_digest,
                request_digest=request_digest,
                started_at=started_at,
                started_monotonic=started_monotonic,
                status="SUCCEEDED",
                result_digest=_digest(_canonical_json(result)),
            )
            execution = CapabilityExecution(result=result, receipt=receipt)
            async with self._lock:
                self._idempotency[record_key] = _IdempotencyRecord(
                    request_digest=request_digest,
                    state="succeeded",
                    execution=execution,
                )
            return execution
        except asyncio.TimeoutError as exc:
            error = CapabilityDenied(
                "ACTION_TIMEOUT",
                "Authorized action exceeded its execution timeout",
            )
            self._record_failure(
                payload,
                action,
                canonical_resources,
                idempotency_digest,
                request_digest,
                started_at,
                started_monotonic,
                error,
            )
            await self._mark_failed(payload, idempotency_key, request_digest)
            raise error from exc
        except CapabilityDenied as error:
            self._record_failure(
                payload,
                action,
                canonical_resources,
                idempotency_digest,
                request_digest,
                started_at,
                started_monotonic,
                error,
            )
            await self._mark_failed(payload, idempotency_key, request_digest)
            raise
        except Exception as exc:
            error = CapabilityDenied(
                "ACTION_FAILED",
                f"Authorized action failed ({type(exc).__name__})",
            )
            self._record_failure(
                payload,
                action,
                canonical_resources,
                idempotency_digest,
                request_digest,
                started_at,
                started_monotonic,
                error,
            )
            await self._mark_failed(payload, idempotency_key, request_digest)
            raise error from exc

    async def execute_process_profile(
        self,
        *,
        grant_token: str | None,
        profile_name: str,
        idempotency_key: str | None,
        timeout_seconds: float | None = None,
    ) -> CapabilityExecution:
        """Execute only a pre-registered process profile without a shell."""

        profile = self._process_profiles.get(profile_name)
        if profile is None:
            raise CapabilityDenied(
                "PROCESS_PROFILE_NOT_ALLOWED",
                "Process profile is not present in the OS allowlist",
            )
        resource = f"process://{profile_name}"

        async def run_process() -> dict[str, Any]:
            require_active_capability("process.execute", (resource,))
            if _hash_file(profile.executable) != profile.executable_sha256:
                raise CapabilityDenied(
                    "PROCESS_PROFILE_INTEGRITY",
                    "Process executable no longer matches its reviewed digest",
                )
            process = await asyncio.create_subprocess_exec(
                str(profile.executable),
                *profile.arguments,
                cwd=str(profile.cwd),
                env=dict(profile.environment),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert process.stdout is not None
            assert process.stderr is not None
            stdout_task = asyncio.create_task(
                _read_stream_bounded(process.stdout, profile.max_output_bytes)
            )
            stderr_task = asyncio.create_task(
                _read_stream_bounded(process.stderr, profile.max_output_bytes)
            )
            try:
                stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
                returncode = await process.wait()
            except BaseException:
                stdout_task.cancel()
                stderr_task.cancel()
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                await asyncio.gather(
                    stdout_task,
                    stderr_task,
                    return_exceptions=True,
                )
                raise
            return {
                "returncode": returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "profile": profile_name,
            }

        return await self.execute(
            grant_token=grant_token,
            action="process.execute",
            resources=(resource,),
            idempotency_key=idempotency_key,
            request_payload={"profile": profile_name},
            operation=run_process,
            timeout_seconds=timeout_seconds,
        )

    def audit_receipts(self) -> tuple[AuditReceipt, ...]:
        """Return immutable redacted audit evidence."""

        return tuple(self._audit)

    def verify_receipt(self, receipt: AuditReceipt) -> bool:
        unsigned = asdict(receipt)
        signature = str(unsigned.pop("signature"))
        expected = self._sign(_canonical_json(unsigned))
        return hmac.compare_digest(signature, expected)

    def _verify_grant(self, token: str | None) -> dict[str, Any]:
        if token is None or not token.strip():
            raise CapabilityDenied(
                "CAPABILITY_GRANT_REQUIRED",
                "A signed capability grant is required",
            )
        parts = token.split(".")
        if len(parts) != 2:
            raise CapabilityDenied(
                "INVALID_GRANT",
                "Capability grant format is invalid",
            )
        encoded, provided_signature = parts
        expected_signature = self._sign(encoded.encode("ascii"))
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise CapabilityDenied(
                "INVALID_GRANT_SIGNATURE",
                "Capability grant signature is invalid",
            )
        try:
            payload = json.loads(_b64decode(encoded))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CapabilityDenied(
                "INVALID_GRANT",
                "Capability grant payload is invalid",
            ) from exc
        required = {
            "v",
            "grant_id",
            "subject",
            "actions",
            "resources",
            "issued_at",
            "expires_at",
            "max_uses",
            "consented_actions",
            "consent_digest",
            "nonce",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise CapabilityDenied(
                "INVALID_GRANT",
                "Capability grant fields are invalid",
            )
        if payload["v"] != _TOKEN_VERSION:
            raise CapabilityDenied(
                "INVALID_GRANT_VERSION",
                "Capability grant version is unsupported",
            )
        try:
            uuid.UUID(str(payload["grant_id"]))
            expires_at = float(payload["expires_at"])
            issued_at = float(payload["issued_at"])
            max_uses = int(payload["max_uses"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise CapabilityDenied(
                "INVALID_GRANT",
                "Capability grant metadata is invalid",
            ) from exc
        now = self._clock()
        if issued_at > now + 5.0:
            raise CapabilityDenied(
                "GRANT_NOT_YET_VALID",
                "Capability grant is not yet valid",
            )
        if expires_at <= now:
            raise CapabilityDenied("GRANT_EXPIRED", "Capability grant has expired")
        if expires_at - issued_at > _MAX_GRANT_TTL_SECONDS + 0.001:
            raise CapabilityDenied(
                "INVALID_GRANT",
                "Capability grant lifetime exceeds policy",
            )
        if not 1 <= max_uses <= 1_000:
            raise CapabilityDenied(
                "INVALID_GRANT",
                "Capability grant use limit is invalid",
            )
        actions = payload["actions"]
        if (
            not isinstance(actions, list)
            or not actions
            or any(action not in self._policies for action in actions)
            or not isinstance(payload["resources"], dict)
        ):
            raise CapabilityDenied(
                "INVALID_GRANT",
                "Capability grant scope is invalid",
            )
        return payload

    def _canonicalize_scope(self, action: str, raw_scope: object) -> str:
        policy = self._policies[action]
        scope = str(raw_scope).strip()
        if policy.resource_kind == "path":
            recursive = scope.endswith("/**") or scope.endswith("\\**")
            raw_path = scope[:-3] if recursive else scope
            path = Path(raw_path)
            if not path.is_absolute():
                raise ValueError("File capability scopes must be absolute paths")
            canonical = os.path.normcase(str(path.resolve(strict=False)))
            return f"path:{canonical}{'/**' if recursive else ''}"
        if policy.resource_kind == "network":
            return self._canonical_network(scope)
        if policy.resource_kind == "process":
            if not re.fullmatch(
                r"process://[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}",
                scope,
            ):
                raise ValueError("Process scope must name a registered profile")
            return scope
        if not re.fullmatch(
            r"system://[a-zA-Z0-9][a-zA-Z0-9/_.-]{0,127}",
            scope,
        ):
            raise ValueError("System scope is invalid")
        return scope

    def _canonicalize_resource(self, action: str, raw_resource: object) -> str:
        if self._policies[action].resource_kind == "path":
            path = Path(str(raw_resource).strip())
            if not path.is_absolute():
                raise CapabilityDenied(
                    "ABSOLUTE_PATH_REQUIRED",
                    "File actions require an absolute path",
                )
            return f"path:{os.path.normcase(str(path.resolve(strict=False)))}"
        try:
            return self._canonicalize_scope(action, raw_resource)
        except ValueError as exc:
            raise CapabilityDenied(
                "INVALID_RESOURCE",
                "Action resource is invalid",
            ) from exc

    @staticmethod
    def _canonical_network(value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Network scopes must be credential-free HTTPS URLs")
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ValueError("Localhost is not an allowed network scope")
        origin = f"https://{hostname}"
        if parsed.port not in (None, 443):
            origin += f":{parsed.port}"
        return origin + parsed.path.rstrip("/")

    def _verify_resource_scopes(
        self,
        action: str,
        resources: tuple[str, ...],
        scopes: Iterable[str],
    ) -> None:
        allowed = tuple(scopes)
        for resource in resources:
            if self._policies[action].resource_kind == "path":
                permitted = any(
                    self._path_scope_contains(scope, resource) for scope in allowed
                )
            else:
                permitted = resource in allowed
            if not permitted:
                raise CapabilityDenied(
                    "RESOURCE_NOT_GRANTED",
                    "Action resource is outside the granted allowlist",
                )

    @staticmethod
    def _path_scope_contains(scope: str, resource: str) -> bool:
        if not scope.startswith("path:") or not resource.startswith("path:"):
            return False
        scope_value = scope[5:]
        resource_value = resource[5:]
        if not scope_value.endswith("/**"):
            return hmac.compare_digest(scope_value, resource_value)
        try:
            Path(resource_value).relative_to(Path(scope_value[:-3]))
            return True
        except ValueError:
            return False

    @staticmethod
    def _verify_idempotency_key(value: str | None) -> str:
        if value is None:
            raise CapabilityDenied(
                "IDEMPOTENCY_KEY_REQUIRED",
                "Action requires an idempotency key",
            )
        clean = value.strip()
        if not (
            _MIN_IDEMPOTENCY_KEY_LENGTH <= len(clean) <= _MAX_IDEMPOTENCY_KEY_LENGTH
        ) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", clean):
            raise CapabilityDenied(
                "INVALID_IDEMPOTENCY_KEY",
                "Idempotency key format is invalid",
            )
        return clean

    async def _mark_failed(
        self,
        payload: Mapping[str, Any] | None,
        idempotency_key: str | None,
        request_digest: str,
    ) -> None:
        if payload is None or not idempotency_key:
            return
        key = (str(payload.get("grant_id", "")), idempotency_key.strip())
        async with self._lock:
            existing = self._idempotency.get(key)
            if existing is not None and existing.request_digest == request_digest:
                existing.state = "failed"

    def _record_failure(
        self,
        payload: Mapping[str, Any] | None,
        action: str,
        resources: tuple[str, ...],
        idempotency_digest: str,
        request_digest: str,
        started_at: float,
        started_monotonic: float,
        error: CapabilityDenied,
    ) -> None:
        self._make_receipt(
            payload=payload,
            action=action,
            resources=resources,
            idempotency_digest=idempotency_digest,
            request_digest=request_digest,
            started_at=started_at,
            started_monotonic=started_monotonic,
            status=(
                "FAILED"
                if error.code
                in {
                    "ACTION_FAILED",
                    "ACTION_TIMEOUT",
                    "PROCESS_OUTPUT_LIMIT",
                    "PROCESS_PROFILE_INTEGRITY",
                }
                else "DENIED"
            ),
            error_code=error.code,
            error_message=_redact(error.safe_message),
        )

    def _make_receipt(
        self,
        *,
        payload: Mapping[str, Any] | None,
        action: str,
        resources: tuple[str, ...],
        idempotency_digest: str,
        request_digest: str,
        started_at: float,
        started_monotonic: float,
        status: str,
        result_digest: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AuditReceipt:
        finished_at = self._clock()
        unsigned = {
            "receipt_id": str(uuid.uuid4()),
            "grant_digest": _digest(
                str(payload.get("grant_id", "")) if payload else ""
            ),
            "subject_digest": _digest(
                str(payload.get("subject", "")) if payload else ""
            ),
            "action": action,
            "resource_digests": tuple(_digest(item) for item in resources),
            "idempotency_digest": idempotency_digest,
            "request_digest": request_digest,
            "consent_digest": payload.get("consent_digest") if payload else None,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": round(
                (self._monotonic_clock() - started_monotonic) * 1000,
                3,
            ),
            "status": status,
            "result_digest": result_digest,
            "error_code": error_code,
            "error_message": error_message,
        }
        receipt = AuditReceipt(
            **unsigned,
            signature=self._sign(_canonical_json(unsigned)),
        )
        self._audit.append(receipt)
        return receipt

    def _sign(self, value: bytes) -> str:
        return hmac.new(self._signing_key, value, hashlib.sha256).hexdigest()
