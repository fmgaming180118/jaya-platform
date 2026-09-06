#!/usr/bin/env python3
"""Run a real P27 fact-change, restart, and failure-path demonstration."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.cognitive.runtime import JayaCoreRuntime  # noqa: E402
from jaya_core.pillars.foundation_capabilities import (  # noqa: E402
    TEMPORAL_CAPABILITY_ID,
)
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402


def _runtime(root: Path) -> JayaCoreRuntime:
    return JayaCoreRuntime(
        db_path=root / "core.sqlite3",
        local_pillar_data_dir=root / "pillars",
        node_id=f"{root.name}-node",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", default=str(ROOT / "artifacts" / "demo-temporal-weighting")
    )
    args = parser.parse_args()
    data_dir = Path(args.data_dir).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex
    now = time.time()
    old_id = f"release-v1-{suffix}"
    current_id = f"release-v2-{suffix}"
    runtime = _runtime(data_dir)
    try:
        runtime.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID,
            {
                "action": "add",
                "record_id": old_id,
                "source_ref": "demo:release:v1",
                "base_score": 0.95,
                "observed_at": now - 3_600,
                "payload": {"release": "v1", "evidence": "demo changelog v1"},
            },
        )
        runtime.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID,
            {
                "action": "add",
                "record_id": current_id,
                "source_ref": "demo:release:v2",
                "base_score": 0.8,
                "observed_at": now,
                "supersedes": old_id,
                "valid_until": now + 86_400,
                "retention_until": now + 172_800,
                "payload": {"release": "v2", "evidence": "demo changelog v2"},
            },
        )
        runtime.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID,
            {
                "action": "set_legal_hold",
                "event_id": f"hold-{old_id}",
                "record_id": old_id,
                "enabled": True,
                "reason": "preserve superseded release evidence",
                "changed_at": now,
            },
        )
        try:
            runtime.execute_local_pillar(
                TEMPORAL_CAPABILITY_ID,
                {
                    "action": "add",
                    "record_id": f"invalid-{suffix}",
                    "source_ref": "demo:invalid-window",
                    "base_score": 0.5,
                    "observed_at": now,
                    "valid_until": now - 1,
                    "payload": {"release": "invalid"},
                },
            )
        except LocalPillarError as exc:
            failure_code = exc.code
        else:
            failure_code = "UNEXPECTED_SUCCESS"
    finally:
        runtime.close()

    restarted = _runtime(data_dir)
    try:
        ranked = restarted.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID,
            {"action": "rank", "decay_rate": 0.05, "now": now},
        )
        history = restarted.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID,
            {"action": "history", "as_of": now, "limit": 1_000},
        )
    finally:
        restarted.close()
    selected_history = [
        item for item in history.data["records"] if item["record_id"] in {old_id, current_id}
    ]
    print(
        json.dumps(
            {
                "status": "DEMO_COMPLETED",
                "database": str(data_dir / "pillars" / "temporal_weighting.sqlite3"),
                "restart_ranked_record": next(
                    item for item in ranked.data["records"] if item["record_id"] == current_id
                ),
                "auditable_history": selected_history,
                "invalid_window_failure": failure_code,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
