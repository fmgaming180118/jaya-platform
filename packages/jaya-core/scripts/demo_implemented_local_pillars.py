#!/usr/bin/env python3
"""Run P25 and P29 through the canonical Core runtime with real local state."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars import DynamicPillarRegistry, PillarRuntimeView
from jaya_core.pillars.local_capabilities import (
    BINARY_DOT_CAPABILITY_ID,
    LINEAGE_CAPABILITY_ID,
    LocalPillarError,
)

BASELINE = SOURCE_ROOT / "jaya_core" / "contracts" / "40_pillars.yaml"


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exercise integrated P25/P29 vertical slices"
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--topic", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    topic = " ".join(str(args.topic).strip().split())
    if not 3 <= len(topic) <= 2_000:
        raise SystemExit("--topic must contain 3-2000 characters")
    raw_key = os.environ.get("JAYA_LINEAGE_SIGNING_KEY", "")
    if len(raw_key) < 32:
        raise SystemExit("JAYA_LINEAGE_SIGNING_KEY must be configured with at least 32 characters")

    output_parent = Path(args.output_dir).expanduser().resolve()
    run_root = output_parent / uuid.uuid4().hex
    run_root.mkdir(parents=True, exist_ok=False)
    registry = DynamicPillarRegistry(
        database_path=run_root / "pillar_registry.sqlite3",
        manifest_paths=(BASELINE,),
    )
    runtime = JayaCoreRuntime(
        db_path=run_root / "core.sqlite3",
        pillar_registry=registry,
        local_pillar_data_dir=run_root / "local-pillars",
        lineage_signing_key=raw_key.encode("utf-8"),
    )
    runtime.pillar_runtime_view = PillarRuntimeView(registry, runtime.capability_registry)
    generation_id = "demo-" + uuid.uuid4().hex
    try:
        appended = runtime.execute_local_pillar(
            LINEAGE_CAPABILITY_ID,
            {
                "action": "append",
                "generation_id": generation_id,
                "payload": {"topic": topic, "classification": "HYPOTHESIS"},
                "evidence_refs": ["input:demo-topic"],
                "approval_ref": "approval:local-demo",
            },
        )
        binary = runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {
                "action": "benchmark",
                "left": [1 if index % 3 else -1 for index in range(2_048)],
                "right": [1 if index % 5 else -1 for index in range(2_048)],
                "iterations": 100,
            },
        )
        snapshot = runtime.operational_snapshot()
        try:
            runtime.execute_local_pillar(
                BINARY_DOT_CAPABILITY_ID,
                {"left": [1], "right": [1], "unknown": True},
            )
        except LocalPillarError as exc:
            failure_path = exc.to_dict()
        else:
            raise RuntimeError("failure-path demo unexpectedly succeeded")
    finally:
        runtime.close()

    restarted = JayaCoreRuntime(
        db_path=run_root / "core.sqlite3",
        local_pillar_data_dir=run_root / "local-pillars",
        lineage_signing_key=raw_key.encode("utf-8"),
    )
    try:
        persisted = restarted.execute_local_pillar(LINEAGE_CAPABILITY_ID, {"action": "verify"})
    finally:
        restarted.close()

    report = {
        "status": "INTEGRATED_VERTICAL_SLICES_COMPLETED",
        "production_deployment": False,
        "topic": topic,
        "results": {
            "P025": {
                "append": appended.to_dict(),
                "restart_verification": persisted.to_dict(),
            },
            "P029": binary.to_dict(),
        },
        "runtime_capabilities": snapshot["local_pillar_capabilities"],
        "failure_path": failure_path,
        "artifacts": {
            "lineage_database": str(run_root / "local-pillars" / "digital_epigenetics.sqlite3"),
            "pillar_registry": str(run_root / "pillar_registry.sqlite3"),
        },
    }
    report_path = run_root / "integrated-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({**report, "report_path": str(report_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
