#!/usr/bin/env python3
"""Run production memory and reasoning vertical slices across ten pillars."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CORE_SRC = _ROOT / "packages" / "jaya-core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))

from jaya_core.cognitive.runtime import JayaCoreRuntime  # noqa: E402
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402

_MINIMUM_KEY_BYTES = 32


class DemoConfigurationError(RuntimeError):
    """Raised when explicit demo configuration is invalid."""


@dataclass(frozen=True, slots=True)
class DemoRuntimeConfig:
    base_url: str
    model_name: str
    approval_key: bytes
    timeout_seconds: float
    node_id: str
    evidence_file: Path
    content: str
    weights: dict[str, float]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--objective-id", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--memory-record-id", required=True)
    parser.add_argument("--memory-event-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--base-score", type=float, required=True)
    parser.add_argument("--confidence", type=float, required=True)
    parser.add_argument("--decay-rate", type=float, required=True)
    parser.add_argument("--constraint", action="append", required=True)
    parser.add_argument(
        "--weight",
        action="append",
        required=True,
        metavar="NAME=VALUE",
    )
    parser.add_argument("--candidate-limit", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    return parser


def _environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        message = f"{name} must be configured"
        raise DemoConfigurationError(message)
    return value


def _weights(values: list[str]) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for item in values:
        name, separator, raw_value = item.partition("=")
        name = name.strip()
        if not separator or not name or name in parsed:
            message = "each --weight must be a unique NAME=VALUE"
            raise DemoConfigurationError(message)
        parsed[name] = float(raw_value)
    return parsed


def _configuration(
    args: argparse.Namespace,
) -> DemoRuntimeConfig:
    base_url = _environment("JAYA_OLLAMA_BASE_URL")
    model_name = _environment("JAYA_LOCAL_PILLAR_MODEL")
    approval_key = _environment("JAYA_LINEAGE_SIGNING_KEY").encode("utf-8")
    timeout_seconds = float(_environment("JAYA_LOCAL_MODEL_TIMEOUT_SECONDS"))
    node_id = os.environ.get("JAYA_NODE_ID", "").strip() or platform.node().strip()
    if not node_id:
        message = "JAYA_NODE_ID is required when host identity is unavailable"
        raise DemoConfigurationError(message)
    if len(approval_key) < _MINIMUM_KEY_BYTES:
        message = "JAYA_LINEAGE_SIGNING_KEY must contain at least 32 bytes"
        raise DemoConfigurationError(message)
    evidence_file = args.evidence_file.expanduser().resolve(strict=True)
    if not evidence_file.is_file():
        message = "--evidence-file must reference a readable file"
        raise DemoConfigurationError(message)
    content = evidence_file.read_text(encoding="utf-8")
    return DemoRuntimeConfig(
        base_url=base_url,
        model_name=model_name,
        approval_key=approval_key,
        timeout_seconds=timeout_seconds,
        node_id=node_id,
        evidence_file=evidence_file,
        content=content,
        weights=_weights(args.weight),
    )


def main() -> int:
    args = _parser().parse_args()
    try:
        config = _configuration(args)
    except (DemoConfigurationError, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"status": "INVALID_CONFIG", "error": str(exc)}), file=sys.stderr)
        return 2

    data_dir = args.data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    runtime = JayaCoreRuntime(
        db_path=data_dir / "core.sqlite3",
        local_pillar_data_dir=data_dir / "pillars",
        lineage_signing_key=config.approval_key,
        ollama_base_url=config.base_url,
        local_model_name=config.model_name,
        local_model_timeout_seconds=config.timeout_seconds,
        node_id=config.node_id,
    )
    started = time.perf_counter()
    observed_at = time.time()
    try:
        memory_result = runtime.execute_integrated_memory_cycle(
            {
                "source_ref": args.source_ref,
                "content": config.content,
                "namespace": args.namespace,
                "record_id": args.memory_record_id,
                "event_id": args.memory_event_id,
                "session_id": args.session_id,
                "goal_id": args.objective_id,
                "owner_id": args.owner_id,
                "policy": args.policy,
                "base_score": args.base_score,
                "confidence": args.confidence,
                "observed_at": observed_at,
                "evaluated_at": observed_at,
                "decay_rate": args.decay_rate,
                "sequence_number": 1,
            }
        )
        reasoning_result = runtime.execute_integrated_reasoning_cycle(
            {
                "source_ref": args.source_ref,
                "title": args.title,
                "content": config.content,
                "topic": args.topic,
                "query": args.query,
                "constraints": args.constraint,
                "candidate_limit": args.candidate_limit,
                "seed": args.seed,
                "goal": args.goal,
                "owner_id": args.owner_id,
                "objective_id": args.objective_id,
                "weights": config.weights,
            }
        )
    except LocalPillarError as exc:
        print(
            json.dumps({"status": "FAILED", "code": exc.code, "error": str(exc)}),
            file=sys.stderr,
        )
        return 3
    finally:
        runtime.close()

    report = {
        "demo": "integrated_reasoning_cycle",
        "status": "INTEGRATED_VERTICAL_SLICES_COMPLETED",
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "node_id": config.node_id,
            "model": config.model_name,
            "provider_url": config.base_url,
        },
        "input": {
            "evidence_file": str(config.evidence_file),
            "source_ref": args.source_ref,
            "topic": args.topic,
            "query": args.query,
            "goal": args.goal,
            "objective_id": args.objective_id,
        },
        "result": {
            "memory_cycle": memory_result,
            "reasoning_cycle": reasoning_result,
        },
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": report["status"], "artifact": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
