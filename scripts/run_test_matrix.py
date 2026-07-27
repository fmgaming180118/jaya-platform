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


@dataclass(frozen=True)
class Component:
    name: str
    test_path: Path
    python_paths: tuple[Path, ...]
    environment: tuple[tuple[str, str], ...] = ()


COMPONENTS = (
    Component(
        "research",
        Path("JAYA_RESEARCH/tests"),
        (Path("JAYA_RESEARCH/src"), Path("JAYA_RESEARCH"), Path(".")),
        (
            ("JAYA_ENV", "test"),
            ("JAYA_HTTP_SECURITY_TEST_MODE", "1"),
        ),
    ),
    Component(
        "core",
        Path("JAYA_CORE/tests"),
        (Path("JAYA_CORE"), Path(".")),
    ),
    Component(
        "agent",
        Path("JAYA_AGENT/tests"),
        (Path("JAYA_AGENT"), Path(".")),
    ),
    Component(
        "os",
        Path("JAYA_OS/tests"),
        (Path("JAYA_OS"), Path(".")),
    ),
)


def _run_component(
    component: Component,
    *,
    collect_only: bool,
    offline: bool,
    quiet: bool,
) -> dict[str, object]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        str((ROOT / path).resolve()) for path in component.python_paths
    )
    environment.update(component.environment)
    command = [
        sys.executable,
        "-m",
        "pytest",
        component.test_path.as_posix(),
    ]
    if collect_only:
        command.append("--collect-only")
    if offline:
        command.extend(["-m", OFFLINE_EXPRESSION])
    if quiet:
        command.append("-q")

    started_at = time.monotonic()
    process = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=False,
        text=True,
    )
    return {
        "component": component.name,
        "exit_code": process.returncode,
        "duration_seconds": round(time.monotonic() - started_at, 3),
        "command": command,
    }


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
    args = parser.parse_args()

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
        )
        for component in selected
        if (ROOT / component.test_path).is_dir()
    ]
    print(json.dumps({"results": results}, indent=2))
    return 0 if results and all(item["exit_code"] == 0 for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
