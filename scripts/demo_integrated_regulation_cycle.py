#!/usr/bin/env python3
"""Run the canonical P6/P7/P10/P17 regulation slice with a real local model."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CORE_SRC = _ROOT / "packages" / "jaya-core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))

from jaya_core.cognitive.runtime import JayaCoreRuntime  # noqa: E402
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402
from jaya_core.pillars.regulation_capabilities import (  # noqa: E402
    SILENCE_CAPABILITY_ID,
)


class MissingDemoEnvironmentError(ValueError):
    """Raised when a required demo environment value is missing."""

    def __init__(self, name: str) -> None:
        super().__init__(f"{name} must be configured")


class InvalidDemoRuleError(TypeError):
    """Raised when a CLI rule is not a JSON object."""

    def __init__(self) -> None:
        super().__init__("each --rule-json must decode to an object")


class UnexpectedSilenceSuccessError(RuntimeError):
    """Raised if the deliberately blocked silence path executes."""

    def __init__(self) -> None:
        super().__init__("Cognitive Silence failure path unexpectedly succeeded")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--evidence-query", required=True)
    parser.add_argument("--claim", required=True)
    parser.add_argument("--exploration-request-id", required=True)
    parser.add_argument("--decision-id", required=True)
    parser.add_argument("--signal-id", required=True)
    parser.add_argument("--fact", action="append", required=True)
    parser.add_argument("--rule-json", action="append", required=True)
    parser.add_argument("--logic-query", required=True)
    parser.add_argument("--risk", type=float, required=True)
    parser.add_argument("--uncertainty", type=float, required=True)
    parser.add_argument("--novelty", type=float, required=True)
    parser.add_argument("--impact", type=float, required=True)
    parser.add_argument("--caution-delta", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    return parser


def _environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingDemoEnvironmentError(name)
    return value


def _rules(values: list[str]) -> list[dict[str, object]]:
    parsed: list[dict[str, object]] = []
    for value in values:
        rule = json.loads(value)
        if not isinstance(rule, dict):
            raise InvalidDemoRuleError
        parsed.append(rule)
    return parsed


def main() -> int:  # noqa: PLR0914, PLW0717
    args = _parser().parse_args()
    try:  # noqa: PLW0717
        base_url = _environment("JAYA_OLLAMA_BASE_URL")
        model = _environment("JAYA_LOCAL_PILLAR_MODEL")
        timeout = float(_environment("JAYA_LOCAL_MODEL_TIMEOUT_SECONDS"))
        evidence_file = args.evidence_file.expanduser().resolve(strict=True)
        content = evidence_file.read_text(encoding="utf-8")
        rules = _rules(args.rule_json)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INVALID_CONFIG", "error": str(exc)}), file=sys.stderr)
        return 2

    data_dir = args.data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    runtime = JayaCoreRuntime(
        db_path=data_dir / "core.sqlite3",
        local_pillar_data_dir=data_dir / "pillars",
        node_id=os.environ.get("JAYA_NODE_ID", "").strip() or platform.node(),
        ollama_base_url=base_url,
        local_model_name=model,
        local_model_timeout_seconds=timeout,
    )
    request = {
        "source_ref": args.source_ref,
        "title": args.title,
        "content": content,
        "topic": args.topic,
        "exploration_request_id": args.exploration_request_id,
        "decision_id": args.decision_id,
        "signal": {
            "source": "TASK",
            "caution_delta": args.caution_delta,
            "signal_id": args.signal_id,
        },
        "risk": args.risk,
        "uncertainty": args.uncertainty,
        "novelty": args.novelty,
        "impact": args.impact,
        "claim": args.claim,
        "facts": args.fact,
        "rules": rules,
        "evidence_query": args.evidence_query,
        "logic_query": args.logic_query,
        "seed": args.seed,
    }
    started = time.perf_counter()
    try:  # noqa: PLW0717
        runtime.execute_local_pillar(
            SILENCE_CAPABILITY_ID,
            {
                "action": "enter",
                "reason": "OWNER_STOP",
                "checkpoint": {"demo": "regulation-failure-path"},
                "request_id": f"{args.decision_id}-silence",
            },
        )
        try:
            runtime.execute_integrated_regulation_cycle(request)
        except LocalPillarError as exc:
            if exc.code != "COGNITIVE_SILENCE_ACTIVE":
                raise
            failure_path = exc.to_dict()
        else:
            raise UnexpectedSilenceSuccessError
        runtime.execute_local_pillar(
            SILENCE_CAPABILITY_ID,
            {
                "action": "exit",
                "wake_source": "OWNER_REQUEST",
                "request_id": f"{args.decision_id}-wake",
            },
        )
        result = runtime.execute_integrated_regulation_cycle(request)
    except LocalPillarError as exc:
        print(
            json.dumps({"status": "FAILED", "code": exc.code, "error": str(exc)}),
            file=sys.stderr,
        )
        return 3
    finally:
        runtime.close()

    restarted = JayaCoreRuntime(
        db_path=data_dir / "core.sqlite3",
        local_pillar_data_dir=data_dir / "pillars",
        node_id=os.environ.get("JAYA_NODE_ID", "").strip() or platform.node(),
        ollama_base_url=base_url,
        local_model_name=model,
        local_model_timeout_seconds=timeout,
    )
    try:
        replayed = restarted.execute_integrated_regulation_cycle(request)
    finally:
        restarted.close()

    report = {
        "demo": "integrated_regulation_cycle",
        "status": "INTEGRATED_REGULATION_DEMO_COMPLETED",
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "model": model,
            "provider_url": base_url,
        },
        "input": {
            "evidence_file": str(evidence_file),
            "source_ref": args.source_ref,
            "topic": args.topic,
            "decision_id": args.decision_id,
        },
        "failure_path": failure_path,
        "result": result,
        "restart_replay": {
            "exploration_status": replayed["exploration"]["status"],
            "review_status": replayed["socratic_review"]["status"],
        },
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": report["status"], "artifact": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
