"""Security and abuse tests for the JAYA OS capability sandbox."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

os_source = Path(__file__).resolve().parents[1] / "src"
if str(os_source) not in sys.path:
    sys.path.insert(0, str(os_source))

from jaya_os.capability_sandbox import (
    CapabilityDenied,
    CapabilitySandbox,
    ProcessProfile,
    require_active_capability,
)

SIGNING_KEY = b"capability-test-signing-key-0001"


def _run(coroutine):
    return asyncio.run(coroutine)


def _read_grant(
    sandbox: CapabilitySandbox,
    path: Path,
    *,
    ttl_seconds: float = 30,
    max_uses: int = 1,
) -> str:
    return sandbox.issue_grant(
        subject="security-test",
        actions=("fs.read",),
        resources={"fs.read": (str(path),)},
        ttl_seconds=ttl_seconds,
        max_uses=max_uses,
    )


async def _read_operation(path: Path, counter: list[int] | None = None) -> str:
    canonical = f"path:{os.path.normcase(str(path.resolve()))}"
    require_active_capability("fs.read", (canonical,))
    if counter is not None:
        counter[0] += 1
    return path.read_text(encoding="utf-8")


def test_scoped_grant_executes_and_receipt_contains_only_digests(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.txt"
    path.write_text("grounded", encoding="utf-8")
    sandbox = CapabilitySandbox(signing_key=SIGNING_KEY)
    grant = _read_grant(sandbox, path)

    execution = _run(
        sandbox.execute(
            grant_token=grant,
            action="fs.read",
            resources=(str(path),),
            idempotency_key="read-document-0001",
            request_payload={"path": str(path), "token": "super-secret"},
            operation=lambda: _read_operation(path),
        )
    )

    assert execution.result == "grounded"
    assert execution.receipt.status == "SUCCEEDED"
    assert sandbox.verify_receipt(execution.receipt)
    serialized = json.dumps(execution.receipt.to_dict())
    assert str(path) not in serialized
    assert "super-secret" not in serialized


def test_missing_tampered_and_expired_grants_are_denied(tmp_path: Path) -> None:
    path = tmp_path / "document.txt"
    path.write_text("evidence", encoding="utf-8")
    now = [100.0]
    sandbox = CapabilitySandbox(
        signing_key=SIGNING_KEY,
        clock=lambda: now[0],
    )
    grant = _read_grant(sandbox, path, ttl_seconds=1)

    with pytest.raises(CapabilityDenied, match="signed capability"):
        _run(
            sandbox.execute(
                grant_token=None,
                action="fs.read",
                resources=(str(path),),
                idempotency_key="missing-grant-001",
                request_payload={},
                operation=lambda: _read_operation(path),
            )
        )

    tampered = grant[:-1] + ("0" if grant[-1] != "0" else "1")
    with pytest.raises(CapabilityDenied, match="signature"):
        _run(
            sandbox.execute(
                grant_token=tampered,
                action="fs.read",
                resources=(str(path),),
                idempotency_key="tampered-grant-1",
                request_payload={},
                operation=lambda: _read_operation(path),
            )
        )

    active = _run(
        sandbox.execute(
            grant_token=grant,
            action="fs.read",
            resources=(str(path),),
            idempotency_key="fake-clock-active-1",
            request_payload={"state": "active"},
            operation=lambda: _read_operation(path),
        )
    )
    assert active.result == "evidence"

    now[0] = 102.0
    with pytest.raises(CapabilityDenied, match="expired"):
        _run(
            sandbox.execute(
                grant_token=grant,
                action="fs.read",
                resources=(str(path),),
                idempotency_key="expired-grant-01",
                request_payload={},
                operation=lambda: _read_operation(path),
            )
        )


def test_path_traversal_and_relative_path_are_denied(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    sandbox = CapabilitySandbox(signing_key=SIGNING_KEY)
    grant = sandbox.issue_grant(
        subject="security-test",
        actions=("fs.read",),
        resources={"fs.read": (f"{allowed}/**",)},
        ttl_seconds=30,
        max_uses=2,
    )

    for key, resource in (
        ("traversal-test-01", allowed / ".." / "outside.txt"),
        ("relative-path-01", Path("outside.txt")),
    ):
        with pytest.raises(CapabilityDenied):
            _run(
                sandbox.execute(
                    grant_token=grant,
                    action="fs.read",
                    resources=(str(resource),),
                    idempotency_key=key,
                    request_payload={"resource": str(resource)},
                    operation=lambda: _read_operation(outside),
                )
            )


def test_write_and_process_grants_require_signed_consent(tmp_path: Path) -> None:
    sandbox = CapabilitySandbox(signing_key=SIGNING_KEY)
    with pytest.raises(ValueError, match="Explicit consent"):
        sandbox.issue_grant(
            subject="security-test",
            actions=("fs.write",),
            resources={"fs.write": (str(tmp_path / "output.txt"),)},
            ttl_seconds=30,
        )
    with pytest.raises(ValueError, match="consent reference"):
        sandbox.issue_grant(
            subject="security-test",
            actions=("process.execute",),
            resources={"process.execute": ("process://version",)},
            ttl_seconds=30,
            consented_actions=("process.execute",),
        )


def test_idempotent_replay_does_not_execute_twice_and_conflict_is_denied(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.txt"
    path.write_text("once", encoding="utf-8")
    sandbox = CapabilitySandbox(signing_key=SIGNING_KEY)
    grant = _read_grant(sandbox, path, max_uses=2)
    counter = [0]

    async def invoke(payload: dict[str, object]):
        return await sandbox.execute(
            grant_token=grant,
            action="fs.read",
            resources=(str(path),),
            idempotency_key="idempotent-read-01",
            request_payload=payload,
            operation=lambda: _read_operation(path, counter),
        )

    first = _run(invoke({"version": 1}))
    replay = _run(invoke({"version": 1}))
    assert first.result == replay.result == "once"
    assert replay.replayed is True
    assert replay.receipt.status == "REPLAYED"
    assert replay.receipt.receipt_id != first.receipt.receipt_id
    assert sandbox.verify_receipt(replay.receipt)
    assert counter == [1]

    with pytest.raises(CapabilityDenied, match="another request"):
        _run(invoke({"version": 2}))


def test_timeout_is_bounded_and_audited(tmp_path: Path) -> None:
    path = tmp_path / "document.txt"
    path.write_text("slow", encoding="utf-8")
    sandbox = CapabilitySandbox(signing_key=SIGNING_KEY)
    grant = _read_grant(sandbox, path)

    async def slow_operation() -> str:
        await asyncio.sleep(0.1)
        return "too late"

    with pytest.raises(CapabilityDenied) as captured:
        _run(
            sandbox.execute(
                grant_token=grant,
                action="fs.read",
                resources=(str(path),),
                idempotency_key="timeout-test-0001",
                request_payload={},
                operation=slow_operation,
                timeout_seconds=0.01,
            )
        )
    assert captured.value.code == "ACTION_TIMEOUT"
    receipt = sandbox.audit_receipts()[-1]
    assert receipt.error_code == "ACTION_TIMEOUT"
    assert sandbox.verify_receipt(receipt)


def test_fixed_process_profile_runs_without_shell_and_unknown_is_denied() -> None:
    with pytest.raises(ValueError, match="inside its root"):
        ProcessProfile(
            executable=Path(sys.executable),
            arguments=("--version",),
            cwd=Path.cwd().parent,
            cwd_root=Path.cwd(),
        )
    with pytest.raises(ValueError, match="environment entry"):
        ProcessProfile(
            executable=Path(sys.executable),
            arguments=("--version",),
            cwd=Path.cwd(),
            cwd_root=Path.cwd(),
            environment={"API_TOKEN": "must-not-reach-child"},
        )

    sandbox = CapabilitySandbox(signing_key=SIGNING_KEY)
    with pytest.raises(CapabilityDenied) as captured:
        _run(
            sandbox.execute_process_profile(
                grant_token=None,
                profile_name="arbitrary-command",
                idempotency_key="unknown-profile-01",
            )
        )
    assert captured.value.code == "PROCESS_PROFILE_NOT_ALLOWED"

    profile = ProcessProfile(
        executable=Path(sys.executable),
        arguments=("--version",),
        cwd=Path.cwd(),
        cwd_root=Path.cwd(),
    )
    sandbox.register_process_profile("python-version", profile)
    with pytest.raises(ValueError, match="already registered"):
        sandbox.register_process_profile("python-version", profile)

    grant = sandbox.issue_grant(
        subject="security-test",
        actions=("process.execute",),
        resources={"process.execute": ("process://python-version",)},
        ttl_seconds=30,
        consented_actions=("process.execute",),
        consent_reference="human-approved-version-check",
    )
    execution = _run(
        sandbox.execute_process_profile(
            grant_token=grant,
            profile_name="python-version",
            idempotency_key="python-version-001",
        )
    )
    assert execution.result["returncode"] == 0
    assert "Python" in (execution.result["stdout"] + execution.result["stderr"])
    assert sandbox.verify_receipt(execution.receipt)

    limited_profile = ProcessProfile(
        executable=Path(sys.executable),
        arguments=("--help",),
        cwd=Path.cwd(),
        cwd_root=Path.cwd(),
        max_output_bytes=64,
    )
    sandbox.register_process_profile("python-help-limited", limited_profile)
    limited_grant = sandbox.issue_grant(
        subject="security-test",
        actions=("process.execute",),
        resources={"process.execute": ("process://python-help-limited",)},
        ttl_seconds=30,
        consented_actions=("process.execute",),
        consent_reference="human-approved-output-limit-test",
    )
    with pytest.raises(CapabilityDenied) as output_error:
        _run(
            sandbox.execute_process_profile(
                grant_token=limited_grant,
                profile_name="python-help-limited",
                idempotency_key="python-output-limit-01",
            )
        )
    assert output_error.value.code == "PROCESS_OUTPUT_LIMIT"


def test_failed_action_receipt_redacts_secret_and_path(tmp_path: Path) -> None:
    path = tmp_path / "sensitive.txt"
    path.write_text("private", encoding="utf-8")
    sandbox = CapabilitySandbox(signing_key=SIGNING_KEY)
    grant = _read_grant(sandbox, path)

    async def failing_operation() -> str:
        canonical = f"path:{os.path.normcase(str(path.resolve()))}"
        require_active_capability("fs.read", (canonical,))
        raise RuntimeError(f"token=do-not-log path={path}")

    with pytest.raises(CapabilityDenied) as captured:
        _run(
            sandbox.execute(
                grant_token=grant,
                action="fs.read",
                resources=(str(path),),
                idempotency_key="redacted-failure-01",
                request_payload={
                    "token": "request-secret",
                    "path": str(path),
                },
                operation=failing_operation,
            )
        )
    assert captured.value.code == "ACTION_FAILED"
    receipt = sandbox.audit_receipts()[-1]
    serialized = json.dumps(receipt.to_dict())
    assert receipt.status == "FAILED"
    assert receipt.error_message == "Authorized action failed (RuntimeError)"
    assert "do-not-log" not in serialized
    assert "request-secret" not in serialized
    assert str(path) not in serialized
    assert sandbox.verify_receipt(receipt)


def test_network_scope_requires_https_and_exact_host() -> None:
    sandbox = CapabilitySandbox(signing_key=SIGNING_KEY)
    with pytest.raises(ValueError, match="HTTPS"):
        sandbox.issue_grant(
            subject="security-test",
            actions=("web.search",),
            resources={"web.search": ("http://example.com",)},
            ttl_seconds=30,
        )

    grant = sandbox.issue_grant(
        subject="security-test",
        actions=("web.search",),
        resources={"web.search": ("https://api.duckduckgo.com",)},
        ttl_seconds=30,
    )

    async def operation() -> str:
        require_active_capability(
            "web.search",
            ("https://evil.example",),
        )
        return "unexpected"

    with pytest.raises(CapabilityDenied):
        _run(
            sandbox.execute(
                grant_token=grant,
                action="web.search",
                resources=("https://evil.example",),
                idempotency_key="network-scope-001",
                request_payload={},
                operation=operation,
            )
        )
