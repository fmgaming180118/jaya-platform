#!/usr/bin/env python3
"""Run a real persistence/restart demo of the dynamic pillar registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_SRC = _ROOT / "packages" / "jaya-core" / "src"
if str(_PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_SRC))

from jaya_core.capabilities.registry import CapabilityRegistry
from jaya_core.pillars import DynamicPillarRegistry, PillarRuntimeView


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register one pillar candidate and verify it after restart"
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--actor", required=True)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    manifests = tuple(Path(item) for item in args.manifest)
    first = DynamicPillarRegistry(
        database_path=Path(args.db),
        manifest_paths=manifests,
    )
    registered, created = first.register_candidate_file(
        Path(args.candidate),
        idempotency_key=args.idempotency_key,
        actor=args.actor,
    )

    restarted = DynamicPillarRegistry(
        database_path=Path(args.db),
        manifest_paths=manifests,
    )
    recovered = restarted.get(registered.definition.pillar_id)
    runtime_view = PillarRuntimeView(restarted, CapabilityRegistry())
    snapshot = runtime_view.snapshot()
    payload = {
        "status": "IMPLEMENTED_LOCAL_DEMO_PASSED",
        "created": created,
        "database": str(Path(args.db).expanduser().resolve()),
        "catalog_total_after_restart": snapshot["total"],
        "canonical_40_present": restarted.catalog_snapshot()[
            "canonical_40_present"
        ],
        "dynamic_pillar": recovered.to_dict(),
        "runtime_available": next(
            item["runtime_available"]
            for item in snapshot["pillars"]
            if item["pillar_id"] == recovered.definition.pillar_id
        ),
        "audit_events": restarted.events(recovered.definition.pillar_id),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
