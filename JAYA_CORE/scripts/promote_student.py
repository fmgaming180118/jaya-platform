#!/usr/bin/env python3
"""Evaluate a distilled student promotion using authenticated CI evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

# Add JAYA_CORE to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.brain_v2.engine.evolution_evidence import EvidenceVerificationError
from src.brain_v2.engine.evolution_gate import (
    EvolutionCandidate,
    EvolutionGate,
    EvolutionGateConfigurationError,
    GateThresholds,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote a distilled student using signed evidence reports"
    )
    parser.add_argument(
        "--test-report",
        default="evolution/evidence/distilled-student-qwen-0.5b-v1-tests.json",
        help="signed JAYA test report JSON",
    )
    parser.add_argument(
        "--benchmark-report",
        default=(
            "evolution/evidence/"
            "distilled-student-qwen-0.5b-v1-benchmark.json"
        ),
        help="signed JAYA benchmark report JSON",
    )
    parser.add_argument(
        "--expected-commit",
        default=os.getenv("JAYA_EVOLUTION_EXPECTED_COMMIT", ""),
        help="expected source commit; defaults to JAYA_EVOLUTION_EXPECTED_COMMIT",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> bool:
    args = _build_parser().parse_args(argv)
    adapter_dir = Path("../JAYA_RESEARCH/data/distillation/student-qwen-0.5b")
    test_report_path = Path(args.test_report)
    benchmark_report_path = Path(args.benchmark_report)

    candidate = EvolutionCandidate(
        candidate_id="distilled-student-qwen-0.5b-v1",
        source_hash="nim-distillation-qwen2.5-0.5b-lora-r8",
        created_at=time.time(),
        candidate_payload=json.dumps(
            {
                "type": "distilled_student_model",
                "base_model": "Qwen/Qwen2.5-0.5B-Instruct",
                "teacher_model": "nvidia/nemotron-3-ultra-550b-a55b",
                "distillation_data": "student_training_data.jsonl",
                "epochs": 3,
                "lora_rank": 8,
                "lora_alpha": 16,
                "adapter_path": str(adapter_dir),
                "target": "edge_deploy",
                "expected_vram_mb": 500,
                "test_report": str(test_report_path),
                "benchmark_report": str(benchmark_report_path),
            },
            sort_keys=True,
        ),
        rollback_target="stable-v1",
        key_id="local",
    )
    thresholds = GateThresholds(
        min_perf_gain_pct=8.0,
        max_ram_delta_pct=5.0,
        max_cpu_delta_pct=10.0,
    )

    try:
        gate = EvolutionGate(thresholds=thresholds, require_signed=True)
        evidence = gate.verify_evidence_reports(
            test_report_path,
            benchmark_report_path,
            candidate=candidate,
            expected_commit=args.expected_commit or None,
        )
    except (EvolutionGateConfigurationError, EvidenceVerificationError) as exc:
        print(f"ERROR: verified promotion evidence unavailable: {exc}")
        return False

    candidate.expected_perf_gain_pct = evidence.observed_perf_gain_pct
    print(f"Verified commit: {evidence.metadata.get('commit')}")
    print(
        "Verified performance gain: "
        f"{evidence.observed_perf_gain_pct:.4f}%"
    )
    print(
        "Verified resource delta: "
        f"RAM={evidence.ram_delta_pct:.4f}% "
        f"CPU={evidence.cpu_delta_pct:.4f}%"
    )

    print("\nSigning candidate...")
    gate.sign_candidate(candidate)
    print(f"Signature: {candidate.signature[:32]}...")

    print("\nEvaluating candidate through Evolution Gate...")
    decision = gate.evaluate(candidate, evidence)
    print(f"\n{'=' * 50}")
    print(f"DECISION: {decision.code.value}")
    print(f"ACCEPTED: {decision.accepted}")
    print(f"REASON: {decision.reason}")
    print(f"DETAILS: {json.dumps(decision.details, indent=2)}")
    print(f"{'=' * 50}")

    output_dir = Path("evolution/candidates")
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_file = output_dir / f"{candidate.candidate_id}.json"
    candidate_file.write_text(
        json.dumps(candidate.to_dict(), indent=2),
        encoding="utf-8",
    )
    print(f"\nCandidate saved to: {candidate_file}")

    decision_file = output_dir / f"{candidate.candidate_id}_decision.json"
    decision_file.write_text(
        json.dumps(decision.to_dict(), indent=2),
        encoding="utf-8",
    )
    print(f"Decision saved to: {decision_file}")
    return decision.accepted


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
