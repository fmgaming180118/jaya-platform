#!/usr/bin/env python3
"""Run real P15 allow, deny, approval-required, and approved invocations."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT / "JAYA_CORE"
for import_root in (ROOT, CORE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from src.brain_v2.engine.jaya_ir import IRInstruction, JayaIRGraph, OpCode  # noqa: E402
from src.brain_v2.engine.jaya_ir_exec import JayaIRExecutor  # noqa: E402
from src.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    EncryptedFileKeyStore,
)
from src.brain_v2.soul.ethical_heart import (  # noqa: E402
    EthicalHeart,
    PolicyBundle,
    PolicyEffect,
    PolicyRisk,
    PolicyRule,
    create_owner_approval,
)
from src.capabilities.puzzle import (  # noqa: E402
    CapabilityPuzzleRegistry,
    PuzzleManifest,
)


class _ReceiptPuzzle:
    def __init__(self, capability_id: str) -> None:
        self.capability_id = capability_id
        self.calls = 0

    def health_check(self) -> bool:
        return True

    def invoke(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        return {
            "capability_id": self.capability_id,
            "accepted_payload_sha256": _payload_digest(payload),
            "call_number": self.calls,
        }


def _payload_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _graph(capability_id: str, payload: dict[str, object]) -> JayaIRGraph:
    return JayaIRGraph(
        instructions=(
            IRInstruction(
                opcode=OpCode.CALL_CAPABILITY,
                args=(
                    capability_id,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
                target="result",
            ),
            IRInstruction(opcode=OpCode.RETURN, args=("result",)),
        ),
        source="p15-real-demo",
    )


def run_demo(workspace: Path) -> dict[str, object]:
    started = time.perf_counter()
    secret = secrets.token_urlsafe(48)
    identity_root = workspace / "identity"
    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", secret),
    )
    identity, _ = anchor.enroll()
    owner_private = Ed25519PrivateKey.generate()
    owner_public = owner_private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    policy = PolicyBundle(
        policy_id="demo.owner-policy",
        version=1,
        brain_id=identity.brain_id,
        rules=(
            PolicyRule(
                rule_id="allow.demo-read",
                effect=PolicyEffect.ALLOW,
                capability_ids=("demo.read",),
                risk_classes=(PolicyRisk.READ_ONLY,),
                reason_code="DEMO_READ_ALLOWED",
            ),
            PolicyRule(
                rule_id="deny.demo-delete",
                effect=PolicyEffect.DENY,
                risk_classes=(PolicyRisk.DESTRUCTIVE,),
                reason_code="DEMO_DESTRUCTIVE_DENIED",
            ),
        ),
        default_effect=PolicyEffect.REQUIRE_APPROVAL,
        default_reason_code="DEMO_OWNER_APPROVAL_REQUIRED",
    )
    heart = EthicalHeart(
        workspace / "ethical-heart.db",
        policy,
        approval_public_keys={"demo-human-owner": owner_public},
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose,
            digest,
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    registry = CapabilityPuzzleRegistry()
    puzzles: dict[str, _ReceiptPuzzle] = {}
    for capability_id, risk in (
        ("demo.read", "READ_ONLY"),
        ("demo.delete", "DESTRUCTIVE"),
        ("demo.switch", "PHYSICAL_ACTION"),
    ):
        puzzle = _ReceiptPuzzle(capability_id)
        puzzles[capability_id] = puzzle
        registry.attach(
            PuzzleManifest(
                puzzle_id=f"puzzle.{capability_id}",
                capability_id=capability_id,
                version="1.0.0",
                risk_class=risk,
            ),
            puzzle,
        )
    executor = JayaIRExecutor(
        puzzle_registry=registry,
        policy_engine=heart,
        actor_brain_id=identity.brain_id,
        node_id="demo-policy-node",
    )
    switch_payload = {"state": "on"}
    try:
        allowed = executor.execute_graph(_graph("demo.read", {"item": "status"}))
        denied = executor.execute_graph(_graph("demo.delete", {"target": "all"}))
        required = executor.execute_graph(_graph("demo.switch", switch_payload))
        now = datetime.now(timezone.utc)
        approval = create_owner_approval(
            approver_id="demo-human-owner",
            actor_brain_id=identity.brain_id,
            capability_id="demo.switch",
            payload_sha256=_payload_digest(switch_payload),
            policy_id=policy.policy_id,
            policy_version=policy.version,
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=2)).isoformat(),
            signer=owner_private.sign,
        )
        approved = executor.execute_graph(
            _graph("demo.switch", switch_payload),
            approvals={"demo.switch": approval},
        )
        report = {
            "status": "VERIFIED_LOCAL",
            "brain_id": identity.brain_id,
            "outcomes": {
                "allow": allowed.get("ok") is True,
                "deny": denied.get("error"),
                "require_approval": required.get("error"),
                "approved": approved.get("ok") is True,
            },
            "adapter_calls": {
                capability: puzzle.calls for capability, puzzle in puzzles.items()
            },
            "decision_count": heart.decision_count(),
            "audit_chain_valid": heart.audit_chain_valid(
                require_attestation=True
            ),
            "approved_policy_receipt": (
                approved.get("result", {}).get("policy_receipt")
            ),
            "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
        }
    finally:
        registry.close()
        heart.close()
        anchor.close()
    report["storage_bytes"] = (workspace / "ethical-heart.db").stat().st_size
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args()
    if args.workspace:
        args.workspace.mkdir(parents=True, exist_ok=True)
        report = run_demo(args.workspace.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="jaya-p15-demo-") as directory:
            report = run_demo(Path(directory))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    outcomes = report["outcomes"]
    passed = (
        report["status"] == "VERIFIED_LOCAL"
        and outcomes["allow"] is True
        and outcomes["deny"] == "policy_denied"
        and outcomes["require_approval"] == "approval_required"
        and outcomes["approved"] is True
        and report["audit_chain_valid"] is True
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
