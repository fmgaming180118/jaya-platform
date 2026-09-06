#!/usr/bin/env python3
"""Run the remaining 11 quarantined pillar prototypes against real inputs.

The demo intentionally does not register a capability or call IronEngine.  It
creates a unique sandbox, exercises filesystem/SQLite/algorithm paths, records
one structured failure, and writes a JSON evidence report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from jaya_core.brain_v2.engine.intent_engine import IntentEngine  # noqa: E402
from jaya_core.pillar_prototypes import (  # noqa: E402
    ActiveDreamingPrototype,
    BootstrapProposalPrototype,
    DynamicObjectivePrototype,
    HybridRoutePrototype,
    IntentExtrapolationPrototype,
    LegacyArtifactInspector,
    MediaObservationPrototype,
    MetaCognitivePrototype,
    PrototypeError,
    PrototypeResult,
    SemanticBridgePrototype,
    SpeculativeReasoningPrototype,
    VerifiedRestorePrototype,
    prototype_catalog,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exercise 11 local pillar prototypes")
    parser.add_argument("--output-dir", required=True, help="Parent directory for demo artifacts")
    parser.add_argument("--topic", required=True, help="Research topic used as real demo input")
    return parser


def _result(value: PrototypeResult) -> dict[str, object]:
    return asdict(value)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    topic = " ".join(str(args.topic).strip().split())
    if len(topic) < 3:
        raise SystemExit("--topic must contain at least 3 characters")
    output_parent = Path(args.output_dir).expanduser().resolve()
    run_root = output_parent / uuid.uuid4().hex
    run_root.mkdir(parents=True, exist_ok=False)

    media = run_root / "observation.png"
    media.write_bytes(b"\x89PNG\r\n\x1a\n" + topic.encode("utf-8"))
    backup = run_root / "backup.bin"
    backup.write_bytes(json.dumps({"topic": topic}, ensure_ascii=False).encode("utf-8"))
    backup_digest = "sha256:" + hashlib.sha256(backup.read_bytes()).hexdigest()
    legacy = run_root / "legacy.jay"
    legacy.write_bytes(b"JAYA" + bytes(124) + topic.encode("utf-8"))

    intent_path = run_root / "intent-model.json"
    intent = IntentEngine(storage_path=intent_path)
    intent.learn(f"teliti {topic}")
    restarted_intent = IntentEngine(storage_path=intent_path)

    results = {
        "P003": _result(
            ActiveDreamingPrototype().generate(
                topic=topic,
                evidence_refs=("artifact:backup.bin", "artifact:observation.png"),
            )
        ),
        "P004": _result(MediaObservationPrototype(run_root).observe(media)),
        "P009": _result(
            VerifiedRestorePrototype(run_root).restore(
                backup=backup,
                destination=run_root / "restored" / "state.bin",
                expected_digest=backup_digest,
            )
        ),
        "P019": _result(LegacyArtifactInspector(run_root).inspect(legacy)),
        "P026": _result(
            SemanticBridgePrototype().parse(
                text="concept:ResearchTopic -> artifact:backup.bin",
                source_ref="input:demo-topic",
            )
        ),
        "P028": _result(
            BootstrapProposalPrototype().propose(
                capability_gap=f"No integrated evaluator exists for {topic}",
                evidence_refs=("artifact:backup.bin",),
                acceptance_checks=("preserve provenance", "reject missing evidence"),
            )
        ),
        "P036": _result(
            SpeculativeReasoningPrototype().select(
                [
                    {
                        "candidate_id": "demo-candidate",
                        "score": 0.75,
                        "checks": {"input_digest": True, "schema": True},
                    }
                ]
            )
        ),
        "P037": _result(
            HybridRoutePrototype().select(
                request_kind="research",
                sensitivity="restricted",
                routes=(
                    {
                        "route_id": "local-rule-path",
                        "provider_type": "RULE_BASED",
                        "request_kinds": ("RESEARCH",),
                        "healthy": True,
                        "latency_ms": 1,
                    },
                ),
                allow_remote=False,
                maximum_latency_ms=100,
            )
        ),
        "P038": _result(
            MetaCognitivePrototype().evaluate(
                progress=(0.2, 0.5),
                steps_used=2,
                maximum_steps=5,
                target_reached=False,
            )
        ),
        "P039": _result(
            DynamicObjectivePrototype().propose(
                owner_goal=f"Research {topic} without exceeding owner scope",
                current_weights={"evidence": 0.7, "latency": 0.3},
                signals={"evidence": 0.5, "latency": -0.25},
                learning_rate=0.1,
            )
        ),
        "P040": _result(
            IntentExtrapolationPrototype().infer(
                partial="teliti",
                predictor=restarted_intent,
                consent=True,
                ttl_seconds=60,
            )
        ),
    }

    try:
        VerifiedRestorePrototype(run_root).restore(
            backup=backup,
            destination=run_root / "invalid-restore.bin",
            expected_digest="sha256:" + "0" * 64,
        )
    except PrototypeError as exc:
        failure_path = {"code": exc.code, "message": str(exc)}
    else:
        raise RuntimeError("failure-path demo unexpectedly succeeded")

    report = {
        "status": "PROTOTYPE_DEMO",
        "production_ready": False,
        "topic": topic,
        "catalog": prototype_catalog(),
        "results": results,
        "failure_path": failure_path,
        "artifact_root": str(run_root),
    }
    report_path = run_root / "prototype-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({**report, "report_path": str(report_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
