"""Run isolated pytest processes so legacy ``src`` packages cannot collide."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OFFLINE_EXPRESSION = "not network and not hardware and not manual and not integration"


def _resolve_python() -> str:
    venv_python = (
        ROOT
        / ".venv"
        / ("Scripts" if os.name == "nt" else "bin")
        / ("python.exe" if os.name == "nt" else "python")
    )
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable


@dataclass(frozen=True)
class Component:
    name: str
    test_path: Path
    python_paths: tuple[Path, ...]
    environment: tuple[tuple[str, str], ...] = ()


COMPONENTS = (
    Component(
        "research",
        Path("packages/jaya-research/tests"),
        (
            Path("packages/jaya-research/src"),
            Path("packages/jaya-core/src"),
            Path("packages/jaya-agent/src"),
            Path("packages/jaya-os/src"),
            Path(),
        ),
        (
            ("JAYA_ENV", "test"),
            ("JAYA_HTTP_SECURITY_TEST_MODE", "1"),
        ),
    ),
    Component(
        "core",
        Path("packages/jaya-core/tests"),
        (
            Path("packages/jaya-core/src"),
            Path("packages/jaya-agent/src"),
            Path("packages/jaya-os/src"),
            Path(),
        ),
    ),
    Component(
        "agent",
        Path("packages/jaya-agent/tests"),
        (
            Path("packages/jaya-agent/src"),
            Path("packages/jaya-os/src"),
            Path("packages/jaya-core/src"),
            Path(),
        ),
    ),
    Component(
        "os",
        Path("packages/jaya-os/tests"),
        (
            Path("packages/jaya-os/src"),
            Path("packages/jaya-agent/src"),
            Path("packages/jaya-core/src"),
            Path(),
        ),
    ),
)


def _run_component(
    component: Component,
    *,
    collect_only: bool,
    offline: bool,
    quiet: bool,
    timeout_seconds: float,
) -> dict[str, object]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        str((ROOT / path).resolve()) for path in component.python_paths
    )
    environment.update(component.environment)
    python_executable = _resolve_python()
    command = [
        python_executable,
        "-m",
        "pytest",
        component.test_path.as_posix(),
        "-p",
        "no:cacheprovider",
    ]
    if collect_only:
        command.append("--collect-only")
    if offline:
        command.extend(["-m", OFFLINE_EXPRESSION])
    if quiet:
        command.append("-q")

    started_at = time.monotonic()
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        exit_code = process.returncode
        status = "PASSED" if exit_code == 0 else "FAILED"
        error_code = (
            "TEST_DISCOVERY_FAILED" if collect_only and exit_code != 0 else None
        )
        output_tail = _output_tail(process.stdout, process.stderr)
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        status = "TIMEOUT"
        error_code = "TEST_DISCOVERY_FAILED" if collect_only else "TEST_TIMEOUT"
        partial_output = "\n".join(
            part.decode(errors="replace") if isinstance(part, bytes) else (part or "")
            for part in (exc.stdout, exc.stderr)
        ).strip()
        output_tail = partial_output[-12_000:]
    return {
        "component": component.name,
        "status": status,
        "error_code": error_code,
        "exit_code": exit_code,
        "duration_seconds": round(time.monotonic() - started_at, 3),
        "command": command,
        "timeout_seconds": timeout_seconds,
        "output_tail": output_tail,
    }


def _output_tail(stdout: str | None, stderr: str | None) -> str:
    combined_output = "\n".join(
        part.strip() for part in (stdout, stderr) if part and part.strip()
    )
    return combined_output[-12_000:]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run JAYA tests in component-isolated Python processes."
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Only validate deterministic test discovery.",
    )
    parser.add_argument(
        "--include-external",
        action="store_true",
        help="Include network, hardware, manual, and integration tests.",
    )
    parser.add_argument(
        "--component",
        action="append",
        choices=[component.name for component in COMPONENTS],
        help="Limit execution to one or more components.",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=300.0,
        help="Maximum runtime for each isolated component process (default: 300).",
    )
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be greater than zero")

    selected = [
        component
        for component in COMPONENTS
        if not args.component or component.name in args.component
    ]
    results = [
        _run_component(
            component,
            collect_only=args.collect_only,
            offline=not args.include_external,
            quiet=args.quiet,
            timeout_seconds=args.timeout_seconds,
        )
        for component in selected
        if (ROOT / component.test_path).is_dir()
    ]
    print(json.dumps({"results": results}, indent=2))
    return 0 if results and all(item["exit_code"] == 0 for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
