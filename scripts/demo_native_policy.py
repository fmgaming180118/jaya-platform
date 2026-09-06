"""Run a real persisted P15 policy decision through the selected provider."""

# ruff: noqa: EM101, TRY003

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path

from jaya_core.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyRequest,
    PolicyRisk,
    default_core_policy,
)
from jaya_core.providers import TrustedPolicyGate


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--brain-id", required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--capability", required=True)
    parser.add_argument("--risk", choices=[value.value for value in PolicyRisk], required=True)
    parser.add_argument("--payload", default="{}", help="JSON payload bound to the receipt")
    parser.add_argument(
        "--provider",
        choices=("auto", "python-reference", "trusted-rust"),
        default="auto",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    payload = json.loads(args.payload)
    if not isinstance(payload, dict):
        raise TypeError("payload must be a JSON object")
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    policy = default_core_policy(args.brain_id)
    gate = TrustedPolicyGate(args.provider)
    request = PolicyRequest(
        request_id=f"demo-{uuid.uuid4()}",
        actor_brain_id=args.brain_id,
        node_id=args.node_id,
        capability_id=args.capability,
        risk_class=PolicyRisk(args.risk),
        permissions=(),
        payload_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    args.database.parent.mkdir(parents=True, exist_ok=True)
    heart = EthicalHeart(args.database, policy, policy_gate=gate)
    try:
        decision = heart.evaluate(request)
    finally:
        heart.close()

    restarted = EthicalHeart(args.database, policy, policy_gate=gate)
    try:
        output = {
            "decision": decision.to_dict(),
            "provider": gate.profile(),
            "persistence": {
                "database": str(args.database.resolve()),
                "decision_count_after_restart": restarted.decision_count(),
                "audit_chain_valid_after_restart": restarted.audit_chain_valid(),
            },
        }
    finally:
        restarted.close()
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
