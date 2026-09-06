#!/usr/bin/env python3
"""Train a checksum-bound Pillar 22 model from an explicit local corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.brain_v2.model.ternary_transition import (  # noqa: E402
    TernaryModelError,
    train_ternary_transition_model,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train and calibrate a statistical ternary transition model"
    )
    parser.add_argument("--corpus", nargs="+", required=True, help="UTF-8 .md/.txt files or dirs")
    parser.add_argument("--output", required=True, help="Destination artifact JSON")
    parser.add_argument("--max-vocab", type=int, default=512)
    parser.add_argument("--holdout-ratio", type=float, default=0.2)
    parser.add_argument("--smoothing", type=float, default=0.5)
    parser.add_argument("--max-perplexity-ratio", type=float, default=2.0)
    parser.add_argument("--max-top1-accuracy-drop", type=float, default=0.2)
    parser.add_argument("--run-id")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = train_ternary_transition_model(
            args.corpus,
            args.output,
            max_vocab=args.max_vocab,
            holdout_ratio=args.holdout_ratio,
            smoothing=args.smoothing,
            max_perplexity_ratio=args.max_perplexity_ratio,
            max_top1_accuracy_drop=args.max_top1_accuracy_drop,
            run_id=args.run_id,
        )
    except TernaryModelError as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code, "message": str(exc)}))
        return 1
    payload = {
        "status": "TRAINED" if result.metrics["quality_gate_passed"] else "QUALITY_GATE_FAILED",
        "artifact": str(result.artifact_path),
        "artifact_sha256": result.artifact_sha256,
        "tokenizer_sha256": result.tokenizer_sha256,
        "dataset_sha256": result.dataset_sha256,
        "source_count": result.source_count,
        "train_sequences": result.train_sequences,
        "holdout_sequences": result.holdout_sequences,
        "metrics": result.metrics,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result.metrics["quality_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
