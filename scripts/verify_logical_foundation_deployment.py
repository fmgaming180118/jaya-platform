#!/usr/bin/env python3
"""Real-process deployment, monitoring, restart, backup, and rollback drill."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from jaya_core.operations.snapshot import CoreSnapshotManager  # noqa: E402


class DeploymentVerificationError(RuntimeError):
    """Raised when any live deployment evidence gate fails."""


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _request(
    url: str,
    *,
    api_key: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 2.0,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    data = None
    method = "GET"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
        method = "POST"
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            return int(response.status), body
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode("utf-8"))
        return int(exc.code), body


def _start_server(environment: dict[str, str]) -> subprocess.Popen[str]:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "run_jaya_core_server.py")],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creation_flags,
    )


def _wait_ready(process: subprocess.Popen[str], base_url: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15.0
    last_error = "server did not respond"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _, stderr = process.communicate(timeout=2)
            raise DeploymentVerificationError(
                f"Core process exited during startup: {stderr[-500:]}"
            )
        try:
            status, payload = _request(f"{base_url}/readyz")
            if status == 200 and payload.get("status") == "ready":
                return payload
            last_error = f"readiness returned {status}: {payload.get('status')}"
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = type(exc).__name__
        time.sleep(0.1)
    raise DeploymentVerificationError(f"Core readiness timed out: {last_error}")


def _stop_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    process.communicate(timeout=2)


def verify_deployment(work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    data_dir = work_dir / "data"
    data_dir.mkdir()
    port = _free_loopback_port()
    api_key = secrets.token_urlsafe(48)
    environment = os.environ.copy()
    environment.update(
        {
            "JAYA_ENVIRONMENT": "production",
            "JAYA_SOUL_PASSWORD": secrets.token_urlsafe(48),
            "JAYA_CORE_API_KEY": api_key,
            "JAYA_CORE_DATA_DIR": str(data_dir.resolve()),
            "JAYA_CORE_BIND_HOST": "127.0.0.1",
            "JAYA_CORE_BIND_PORT": str(port),
            "JAYA_CORE_TRUSTED_HOSTS": "127.0.0.1",
            "JAYA_NODE_ID": "deployment-verifier-node",
            "JAYA_REQUIRE_MODEL": "false",
            "JAYA_REQUIRE_IDENTITY": "false",
            "JAYA_REQUIRE_PRIVACY": "true",
            "JAYA_PRIVACY_KEY_SECRET": secrets.token_urlsafe(48),
            "JAYA_REQUIRE_ZERO_TRUST": "false",
        }
    )
    environment.pop("JAYA_MODEL_PATH", None)
    base_url = f"http://127.0.0.1:{port}"
    logic_request = {
        "request_id": "deployment-proof",
        "facts": ["core.started", "puzzle.logic.connected"],
        "rules": [
            {
                "id": "deployment-rule",
                "if": ["core.started", "puzzle.logic.connected"],
                "then": "foundation.operational",
            }
        ],
        "query": "foundation.operational",
    }

    first_process = _start_server(environment)
    try:
        readiness = _wait_ready(first_process, base_url)
        unauthorized_status, _ = _request(f"{base_url}/v1/metrics")
        logic_status, logic = _request(
            f"{base_url}/v1/logic/evaluate",
            api_key=api_key,
            payload=logic_request,
            timeout=5.0,
        )
        metrics_status, metrics = _request(
            f"{base_url}/v1/metrics",
            api_key=api_key,
        )
        if unauthorized_status != 401:
            raise DeploymentVerificationError("metrics authentication gate failed")
        if logic_status != 200 or logic.get("status") != "PROVED":
            raise DeploymentVerificationError("live Pure Logic request failed")
        if metrics_status != 200 or not metrics.get("runtime", {}).get("ready"):
            raise DeploymentVerificationError("live monitoring snapshot failed")
    finally:
        _stop_server(first_process)

    database = data_dir / "jaya_core_runtime.db"
    manager = CoreSnapshotManager(data_dir)
    backup = manager.create(database)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "DELETE FROM logic_proofs WHERE request_id = ?",
            (logic_request["request_id"],),
        )
        connection.commit()
    rollback = manager.rollback(backup)
    with closing(sqlite3.connect(database)) as connection:
        restored_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM logic_proofs WHERE request_id = ?",
                (logic_request["request_id"],),
            ).fetchone()[0]
        )
    if restored_count != 1:
        raise DeploymentVerificationError("rollback did not restore logic proof")

    second_process = _start_server(environment)
    try:
        _wait_ready(second_process, base_url)
        restart_status, restarted = _request(
            f"{base_url}/v1/logic/evaluate",
            api_key=api_key,
            payload=logic_request,
            timeout=5.0,
        )
        if restart_status != 200 or restarted.get("status") != "PROVED":
            raise DeploymentVerificationError("restart continuity failed")
    finally:
        _stop_server(second_process)

    return {
        "schema_version": 1,
        "status": "VERIFIED_LOCAL_PROCESS",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "production_config": "PASS",
            "real_http_process": "PASS",
            "authentication": "PASS",
            "readiness": "PASS",
            "logic": "PASS",
            "monitoring": "PASS",
            "backup_integrity": "PASS",
            "rollback": "PASS",
            "restart_continuity": "PASS",
        },
        "readiness_dependencies": readiness.get("dependencies", []),
        "logic_status": logic.get("status"),
        "metrics": {
            "requests_total": metrics.get("service", {}).get("requests_total"),
            "errors_total": metrics.get("service", {}).get("errors_total"),
            "logic_results": metrics.get("service", {}).get("logic_results"),
            "homeostasis_state": metrics.get("runtime", {}).get("homeostasis_state"),
        },
        "backup": backup.to_dict(),
        "rollback": rollback.to_dict(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="jaya-core-deployment-") as directory:
        try:
            report = verify_deployment(Path(directory))
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "status": "FAILED",
                        "error": type(exc).__name__,
                        "message": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
            return 1
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
