#!/usr/bin/env python3
"""Train and execute the real Pillar 22 vertical slice through JayaCoreRuntime."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.brain_v2.model.ternary_transition import (  # noqa: E402
    train_ternary_transition_model,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime  # noqa: E402
from jaya_core.pillars import DynamicPillarRegistry, PillarRuntimeView  # noqa: E402
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402
from jaya_core.pillars.ternary_capability import TERNARY_CAPABILITY_ID  # noqa: E402

BASELINE = CORE_SRC / "jaya_core" / "contracts" / "40_pillars.yaml"
_QUALITY_GATE_ERROR = "trained artifact did not pass its configured quality gate"
_FAILURE_PATH_ERROR = "invalid-input failure path unexpectedly succeeded"


def main() -> int:  # noqa: PLR0914
    parser = argparse.ArgumentParser(description="Run the integrated P22 demo")
    parser.add_argument("--corpus", default=str(ROOT / "docs" / "pillars"))
    parser.add_argument(
        "--output-dir", default=str(ROOT / "artifacts" / "demo-integrated-ternary")
    )
    parser.add_argument("--text", default="model ternary digunakan untuk")
    parser.add_argument("--iterations", type=int, default=200)
    args = parser.parse_args()

    run_root = Path(args.output_dir).expanduser().resolve() / uuid.uuid4().hex
    run_root.mkdir(parents=True, exist_ok=False)
    artifact = run_root / "p22-ternary-transition.json"
    training = train_ternary_transition_model(
        (args.corpus,),
        artifact,
        max_vocab=512,
        max_perplexity_ratio=2.0,
        max_top1_accuracy_drop=0.2,
        run_id=f"p22-demo-{run_root.name}",
    )
    if training.metrics["quality_gate_passed"] is not True:
        raise RuntimeError(_QUALITY_GATE_ERROR)

    registry = DynamicPillarRegistry(
        database_path=run_root / "pillar_registry.sqlite3",
        manifest_paths=(BASELINE,),
    )
    runtime = JayaCoreRuntime(
        db_path=run_root / "core.sqlite3",
        local_pillar_data_dir=run_root / "pillar-capabilities",
        pillar_registry=registry,
        ternary_model_path=artifact,
        ternary_model_sha256=training.artifact_sha256,
    )
    runtime.pillar_runtime_view = PillarRuntimeView(registry, runtime.capability_registry)
    request_id = f"benchmark-{uuid.uuid4().hex}"
    try:
        prediction = runtime.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {"action": "predict", "text": args.text, "top_k": 5},
        )
        benchmark = runtime.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {
                "action": "benchmark",
                "request_id": request_id,
                "text": args.text,
                "top_k": 5,
                "iterations": args.iterations,
                "timeout_seconds": 30.0,
            },
        )
        p22 = next(
            item
            for item in runtime.operational_snapshot()["pillars"]["pillars"]
            if item["pillar_id"] == "P022"
        )
        try:
            runtime.execute_local_pillar(
                TERNARY_CAPABILITY_ID,
                {"action": "predict", "text": "", "top_k": 5},
            )
        except LocalPillarError as exc:
            failure_path = exc.to_dict()
        else:
            raise RuntimeError(_FAILURE_PATH_ERROR)
    finally:
        runtime.close()

    restarted = JayaCoreRuntime(
        db_path=run_root / "core.sqlite3",
        local_pillar_data_dir=run_root / "pillar-capabilities",
        ternary_model_path=artifact,
        ternary_model_sha256=training.artifact_sha256,
    )
    try:
        persisted = restarted.execute_local_pillar(
            TERNARY_CAPABILITY_ID,
            {"action": "receipt", "request_id": request_id},
        )
    finally:
        restarted.close()

    report = {
        "status": "INTEGRATED_TERNARY_PRECISION_COMPLETED",
        "pillar": "P022",
        "training": {
            "artifact_sha256": training.artifact_sha256,
            "tokenizer_sha256": training.tokenizer_sha256,
            "dataset_sha256": training.dataset_sha256,
            "source_count": training.source_count,
            "train_sequences": training.train_sequences,
            "holdout_sequences": training.holdout_sequences,
            "metrics": training.metrics,
        },
        "prediction": prediction.to_dict(),
        "benchmark": benchmark.to_dict(),
        "restart_receipt": persisted.to_dict(),
        "runtime_pillar": p22,
        "failure_path": failure_path,
    }
    report_path = run_root / "integrated-ternary-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({**report, "report_path": str(report_path)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
