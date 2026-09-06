#!/usr/bin/env python3
"""Run P30/P32 through three canonical local JAYA Core runtimes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
MIN_SECRET_LENGTH = 32
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.cognitive.runtime import JayaCoreRuntime  # noqa: E402
from jaya_core.pillars.distributed_capabilities import (  # noqa: E402
    COLLECTIVE_EVIDENCE_CAPABILITY_ID,
    TWIN_TRANSFER_CAPABILITY_ID,
)


class DemoInputError(ValueError):
    """Raised when demo inputs do not satisfy the public contract."""

    @classmethod
    def invalid_score(cls, field: str) -> DemoInputError:
        return cls(f"{field} must be within 0-1")

    @classmethod
    def invalid_secret(cls) -> DemoInputError:
        return cls("JAYA_TWIN_SHARED_SECRET must contain at least 32 characters")

    @classmethod
    def missing_files(cls) -> DemoInputError:
        return cls("state-file and evidence-file must exist")

    @classmethod
    def empty_state(cls) -> DemoInputError:
        return cls("state-file must not be empty")

    @classmethod
    def empty_evidence(cls) -> DemoInputError:
        return cls("evidence-file must contain UTF-8 text")

    @classmethod
    def transfer_mismatch(cls) -> DemoInputError:
        return cls("received twin artifact does not match input bytes")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transfer a real file and aggregate two consent-bound peer contributions"
    )
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--local-value", type=float, default=0.7)
    parser.add_argument("--peer-a-value", type=float, default=0.6)
    parser.add_argument("--peer-c-value", type=float, default=0.8)
    return parser.parse_args()


def _bounded_score(value: float, field: str) -> float:
    if not 0 <= value <= 1:
        raise DemoInputError.invalid_score(field)
    return value


def _validated_inputs(
    args: argparse.Namespace,
) -> tuple[str, Path, Path, str, dict[str, float]]:
    secret = os.environ.get("JAYA_TWIN_SHARED_SECRET")
    if secret is None or len(secret) < MIN_SECRET_LENGTH:
        raise DemoInputError.invalid_secret()
    state_file = args.state_file.expanduser().resolve()
    evidence_file = args.evidence_file.expanduser().resolve()
    if not state_file.is_file() or not evidence_file.is_file():
        raise DemoInputError.missing_files()
    if state_file.stat().st_size == 0:
        raise DemoInputError.empty_state()
    evidence_content = evidence_file.read_text(encoding="utf-8")
    if not evidence_content.strip():
        raise DemoInputError.empty_evidence()
    scores = {
        "local": _bounded_score(args.local_value, "local-value"),
        "node-a": _bounded_score(args.peer_a_value, "peer-a-value"),
        "node-c": _bounded_score(args.peer_c_value, "peer-c-value"),
    }
    return secret, state_file, evidence_file, evidence_content, scores


def _create_runtimes(run_root: Path, secret: str) -> dict[str, JayaCoreRuntime]:
    peers = ("node-a", "node-b", "node-c")
    return {
        node_id: JayaCoreRuntime(
            db_path=run_root / node_id / "core.sqlite3",
            local_pillar_data_dir=run_root / node_id / "pillars",
            node_id=node_id,
            twin_shared_secret=secret,
            twin_allowed_peers=tuple(peer for peer in peers if peer != node_id),
        )
        for node_id in peers
    }


def _seed_evidence(
    runtimes: dict[str, JayaCoreRuntime], evidence_file: Path, content: str, query: str
) -> str:
    for runtime in runtimes.values():
        runtime.advanced_pillar_capabilities.rag.execute(
            {
                "action": "ingest",
                "source_ref": f"file:{evidence_file.as_posix()}",
                "title": evidence_file.name,
                "content": content,
            }
        )
    return str(
        runtimes["node-b"].advanced_pillar_capabilities.rag.retrieve(query, 1)[0][
            "evidence_id"
        ]
    )


def _aggregate(
    runtimes: dict[str, JayaCoreRuntime], evidence_id: str, scores: dict[str, float]
) -> dict[str, object]:
    accepted = []
    for node_id in ("node-a", "node-c"):
        receipt = runtimes[node_id].execute_local_pillar(
            COLLECTIVE_EVIDENCE_CAPABILITY_ID,
            {
                "action": "issue_consent",
                "evidence_id": evidence_id,
                "max_privacy_budget": 0.1,
                "expires_at": time.time() + 300,
            },
        ).data["receipt"]
        packet = runtimes[node_id].execute_local_pillar(
            COLLECTIVE_EVIDENCE_CAPABILITY_ID,
            {
                "action": "create",
                "evidence_id": evidence_id,
                "value": scores[node_id],
                "trust": 0.9,
                "quality": 0.9,
                "privacy_budget": 0.1,
                "consent_receipt": receipt,
            },
        ).data["packet"]
        accepted.append(
            runtimes["node-b"].execute_local_pillar(
                COLLECTIVE_EVIDENCE_CAPABILITY_ID,
                {"action": "ingest", "packet": packet},
            ).data
        )
    collective = runtimes["node-b"].execute_local_pillar(
        COLLECTIVE_EVIDENCE_CAPABILITY_ID,
        {
            "action": "aggregate",
            "local_evidence_id": evidence_id,
            "local_value": scores["local"],
        },
    )
    return {
        "code": collective.code,
        "accepted_contributions": accepted,
        "evidence_id": evidence_id,
        "result": collective.data,
    }


def _transfer(
    runtimes: dict[str, JayaCoreRuntime], run_root: Path, state_file: Path, run_id: str
) -> dict[str, object]:
    twin_source = run_root / "node-a" / "pillars" / "twin-node" / state_file.name
    shutil.copy2(state_file, twin_source)
    endpoint = runtimes["node-b"].execute_local_pillar(
        TWIN_TRANSFER_CAPABILITY_ID, {"action": "start_receiver", "port": 0}
    ).data
    transfer = runtimes["node-a"].execute_local_pillar(
        TWIN_TRANSFER_CAPABILITY_ID,
        {
            "action": "send_batch",
            "host": endpoint["host"],
            "port": endpoint["port"],
            "transfer_id": f"demo-{run_id}",
            "source_path": twin_source.name,
            "target_node_id": "node-b",
            "brain_id": f"demo-brain-{run_id}",
            "destination_name": f"received-{state_file.name}",
        },
    )
    received_path = (
        run_root
        / "node-b"
        / "pillars"
        / "twin-node"
        / "received"
        / f"received-{state_file.name}"
    )
    if received_path.read_bytes() != state_file.read_bytes():
        raise DemoInputError.transfer_mismatch()
    return {
        "code": transfer.code,
        "transport": transfer.data["transport"],
        "receipt": transfer.data["receipt"],
        "input": str(state_file),
        "received_artifact": str(received_path),
        "bytes_verified": received_path.stat().st_size,
    }


def main() -> int:
    args = _arguments()
    secret, state_file, evidence_file, content, scores = _validated_inputs(args)
    run_id = uuid.uuid4().hex
    run_root = args.work_dir.expanduser().resolve() / run_id
    run_root.mkdir(parents=True)
    runtimes = _create_runtimes(run_root, secret)
    try:
        evidence_id = _seed_evidence(runtimes, evidence_file, content, args.query)
        report = {
            "status": "INTEGRATED_DISTRIBUTED_DEMO_COMPLETED",
            "run_id": run_id,
            "p030": _transfer(runtimes, run_root, state_file, run_id),
            "p032": _aggregate(runtimes, evidence_id, scores),
        }
        report_path = run_root / "integrated-distributed-report.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({**report, "report": str(report_path)}, indent=2, sort_keys=True))
        return 0
    finally:
        for runtime in runtimes.values():
            runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
