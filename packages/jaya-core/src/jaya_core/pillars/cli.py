"""Official command-line interface for the persistent pillar registry."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .models import PillarError, PillarStatus
from .registry import DynamicPillarRegistry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the JAYA dynamic pillar catalog")
    parser.add_argument("--db", required=True, help="Persistent SQLite database path")
    parser.add_argument(
        "--manifest",
        action="append",
        required=True,
        help="Baseline manifest path; may be repeated",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List all persisted pillars")
    show = subparsers.add_parser("show", help="Show one pillar")
    show.add_argument("pillar_id")

    register = subparsers.add_parser("register", help="Register one non-active candidate")
    register.add_argument("--candidate", required=True)
    register.add_argument("--idempotency-key", required=True)
    register.add_argument("--actor", required=True)

    transition = subparsers.add_parser("transition", help="Transition a pillar lifecycle state")
    transition.add_argument("pillar_id")
    transition.add_argument("status", choices=[item.value for item in PillarStatus])
    transition.add_argument("--expected-revision", required=True, type=int)
    transition.add_argument("--evidence", action="append", default=[])
    transition.add_argument("--approval-reference")
    transition.add_argument("--actor", required=True)

    events = subparsers.add_parser("events", help="Read immutable audit events")
    events.add_argument("pillar_id")
    subparsers.add_parser("health", help="Check database integrity and catalog availability")
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        registry = DynamicPillarRegistry(
            database_path=Path(args.db),
            manifest_paths=tuple(Path(item) for item in args.manifest),
        )
        if args.command == "list":
            _print(registry.catalog_snapshot())
        elif args.command == "show":
            _print(registry.get(args.pillar_id).to_dict())
        elif args.command == "register":
            record, created = registry.register_candidate_file(
                args.candidate,
                idempotency_key=args.idempotency_key,
                actor=args.actor,
            )
            _print({"created": created, "pillar": record.to_dict()})
        elif args.command == "transition":
            record = registry.transition_status(
                args.pillar_id,
                PillarStatus(args.status),
                expected_revision=args.expected_revision,
                evidence_refs=args.evidence,
                approval_reference=args.approval_reference,
                actor=args.actor,
            )
            _print(record.to_dict())
        elif args.command == "events":
            _print({"events": registry.events(args.pillar_id)})
        elif args.command == "health":
            healthy = registry.health_check()
            _print({"ready": healthy, "code": "READY" if healthy else "STORAGE_UNAVAILABLE"})
            return 0 if healthy else 2
        return 0
    except PillarError as exc:
        print(
            json.dumps(
                {"error": {"code": exc.code, "message": str(exc)}},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
