#!/usr/bin/env python3
"""Run one real Pure Logic request through Core runtime and SQLite storage."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_CORE_ROOT = _ROOT / "packages" / "jaya-core" / "src"
if str(_CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CORE_ROOT))
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

from jaya_core.cognitive.runtime import JayaCoreRuntime  # noqa: E402
from jaya_core.reasoning.pure_logic import PureLogicError  # noqa: E402
from jaya_core.resources.profiler import ResourceProfile, ResourceProfiler  # noqa: E402


class _ObservedProfiler:
    """Production profiler wrapper retaining the observation used by the demo."""

    def __init__(
        self,
        available_memory_mb: int | None,
        thermal_celsius: float | None,
    ) -> None:
        self._profiler = ResourceProfiler()
        self._available_memory_mb = available_memory_mb
        self._thermal_celsius = thermal_celsius
        self.last_profile: ResourceProfile | None = None

    def profile(self) -> ResourceProfile:
        self.last_profile = self._profiler.profile(
            override_available_mem_mb=self._available_memory_mb,
        )
        if self._thermal_celsius is not None:
            self.last_profile.thermal_celsius = self._thermal_celsius
            self.last_profile.sources["thermal"] = "explicit_demo_input"
        return self.last_profile


def _load_request(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read a valid UTF-8 JSON request: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("request payload must be a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--node-id", default=platform.node().strip())
    parser.add_argument("--available-memory-mb", type=int)
    parser.add_argument("--thermal-celsius", type=float)
    args = parser.parse_args()
    if not args.node_id:
        parser.error("--node-id is required when host identity is unavailable")
    args.database.parent.mkdir(parents=True, exist_ok=True)

    try:
        request = _load_request(args.input)
    except ValueError as exc:
        print(json.dumps({"status": "INVALID_INPUT", "message": str(exc)}))
        return 2

    if args.thermal_celsius is not None and not -50 <= args.thermal_celsius <= 200:
        parser.error("--thermal-celsius is outside the supported sensor range")
    profiler = _ObservedProfiler(
        args.available_memory_mb,
        args.thermal_celsius,
    )
    runtime = JayaCoreRuntime(
        db_path=args.database,
        node_id=args.node_id,
        resource_profiler=profiler,  # type: ignore[arg-type]
    )
    try:
        result = runtime.reason_logic(
            request_id=request.get("request_id"),
            facts=request.get("facts"),
            rules=request.get("rules"),
            query=request.get("query"),
        )
        output = {
            "status": "SUCCESS",
            "node_id": runtime.node_identity.node_id,
            "database": str(args.database.resolve()),
            "resource_profile": (
                profiler.last_profile.to_dict() if profiler.last_profile else None
            ),
            "homeostasis_state": runtime.homeostasis.state.value,
            "homeostasis_transitions": runtime.homeostasis.store.count(),
            "proof": result.to_dict(),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except PureLogicError as exc:
        print(
            json.dumps(
                {"status": exc.code.value, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 3
    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
