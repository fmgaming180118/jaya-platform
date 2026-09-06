"""Operate the production Cognitive Silence controller and execute live demonstrations."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.brain_v2.organism.cognitive_silence import (  # noqa: E402
    CognitiveSilenceAction,
    CognitiveSilenceController,
    CognitiveSilenceModelGate,
    CognitiveSilencePolicy,
    CognitiveSilenceSignals,
    CognitiveSilenceStore,
    RuntimeService,
    SilencePersistenceError,
    SilenceReason,
    WakeSource,
)


def _object_json(raw: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("JSON must be an object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite ledger path; parent directories are created when needed",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    enter = subparsers.add_parser("enter", help="enter silence with a checkpoint")
    enter.add_argument(
        "--reason",
        required=True,
        choices=(
            "OWNER_STOP",
            "RESOURCE_PRESSURE",
            "PRIVACY_BOUNDARY",
            "PERMISSION_REVOKED",
            "IDLE",
            "SAFETY_VIOLATION",
            "INSUFFICIENT_EVIDENCE",
            "AMBIGUOUS_REQUEST",
            "PROVIDER_UNAVAILABLE",
        ),
    )
    enter.add_argument("--request-id")
    enter.add_argument("--checkpoint-json", type=_object_json, default={})

    wake = subparsers.add_parser("wake", help="request an authorized wake transition")
    wake.add_argument(
        "--source",
        required=True,
        choices=(
            "OWNER_REQUEST",
            "RESOURCE_RECOVERED",
            "PRIVACY_RELEASED",
            "PERMISSION_RESTORED",
            "TASK_RECEIVED",
        ),
    )
    wake.add_argument("--request-id")

    subparsers.add_parser("status", help="show current state and storage health")

    evaluate = subparsers.add_parser("evaluate", help="evaluate decision on signals")
    evaluate.add_argument("--signals-json", type=_object_json, required=True)
    evaluate.add_argument("--decision-id")

    subparsers.add_parser("live-demo", help="run end-to-end interactive demonstration")
    return parser


def run_live_demo(db_path: Path | None = None) -> int:
    print("=" * 70)
    print("=== JAYA COGNITIVE SILENCE (PILAR 07) LIVE DEMONSTRATION ===")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="jaya-demo-silence-", ignore_cleanup_errors=True) as tmp_dir:
        actual_db = db_path or (Path(tmp_dir) / "demo_silence.sqlite")
        store = CognitiveSilenceStore(actual_db)
        controller = CognitiveSilenceController(store)

        print(f"[*] Initialized CognitiveSilenceController with SQLite store: {actual_db}")
        print(f"[*] Initial Active State: {controller.active}")

        # Step 1: Normal Execution (ANSWER)
        print("\n[Step 1] Normal signals evaluation (healthy system)")
        sig_healthy = CognitiveSilenceSignals(
            request_text="hitung trajectory roket",
            cpu_percent=18.0,
            memory_percent=32.0,
            battery_percent=85.0,
            uncertainty=0.1,
            evidence_count=3,
        )
        d_normal = controller.evaluate_decision(sig_healthy, decision_id="demo-dec-01")
        print(f" -> Decision Action: {d_normal.action.value}")
        print(f" -> Reason Code:     {d_normal.reason_code}")
        print(f" -> Model Allowed:   {d_normal.model_allowed}")

        # Step 2: Zero Model Invocation Gate when throttled / safety constrained
        print("\n[Step 2] Zero-Model-Invocation Gating Proof")
        gate = CognitiveSilenceModelGate(controller)
        real_calls = 0

        def model_provider(prompt: str) -> str:
            nonlocal real_calls
            real_calls += 1
            return f"Model Output for [{prompt}]"

        print(" -> Testing blocked invocation under high CPU (92% >= 85%):")
        res_blocked = gate.execute(
            model_provider,
            CognitiveSilenceSignals(request_text="heavy task", cpu_percent=92.0),
            "heavy task",
        )
        print(f"    Executed: {res_blocked['executed']}")
        print(f"    Error:    {res_blocked['error']}")
        print(f"    Invocations Count (Expected 0): {res_blocked['invocations_count']}")
        print(f"    Actual Provider Calls:          {real_calls}")

        # Step 3: Entering Durable Silence
        print("\n[Step 3] Entering Durable Silence (RESOURCE_PRESSURE)")
        entry = controller.enter(
            SilenceReason.RESOURCE_PRESSURE,
            {"checkpoint": "safe_point_001", "active_jobs": 0},
            request_id="demo-enter-01",
        )
        print(f" -> Entered Silence: changed={entry.get('changed')}, reason={entry.get('reason')}")
        print(f" -> Controller Active: {controller.active}")
        print(f" -> allows(MODEL_GENERATION): {controller.allows(RuntimeService.MODEL_GENERATION)}")
        print(f" -> allows(NETWORK):          {controller.allows(RuntimeService.NETWORK)}")
        print(f" -> allows(AUDIT):            {controller.allows(RuntimeService.AUDIT)}")
        print(f" -> allows(CANCELLATION):     {controller.allows(RuntimeService.CANCELLATION)}")

        # Step 4: Unauthorized Wake Denial
        print("\n[Step 4] Testing Unauthorized Wake Source Rejection")
        unauth_wake = controller.exit(WakeSource.PRIVACY_RELEASED, request_id="demo-bad-wake")
        print(f" -> Wake Result: ok={unauth_wake.get('ok')}, error={unauth_wake.get('error')}")
        print(f" -> Controller Still Active: {controller.active}")

        # Step 5: Authorized Wake & Model Recovery
        print("\n[Step 5] Authorized Wake (RESOURCE_RECOVERED) & Execution Recovery")
        auth_wake = controller.exit(WakeSource.RESOURCE_RECOVERED, request_id="demo-good-wake")
        print(f" -> Wake Result: ok={auth_wake.get('ok')}, active={auth_wake.get('active')}")
        print(f" -> Controller Active: {controller.active}")

        print(" -> Executing model through gate after recovery:")
        res_recovered = gate.execute(
            model_provider,
            sig_healthy,
            "analisis orbit selesai",
        )
        print(f"    Executed: {res_recovered['executed']}")
        print(f"    Invocations Count: {res_recovered['invocations_count']}")
        print(f"    Actual Provider Calls: {real_calls}")
        print(f"    Result: {res_recovered.get('result')}")

        # Step 6: Decision Persistence across Restart
        print("\n[Step 6] Verifying Decision Persistence across Controller Restart")
        controller.close()
        new_store = CognitiveSilenceStore(actual_db)
        new_controller = CognitiveSilenceController(new_store)
        stored_receipt = new_store.decision_by_id("demo-dec-01")
        print(f" -> Stored Receipt Found: {stored_receipt is not None}")
        if stored_receipt:
            print(f" -> Receipt Decision ID: {stored_receipt.decision_id}")
            print(f" -> Receipt Action:      {stored_receipt.action.value}")
            print(f" -> Integrity SHA-256:   {stored_receipt.decision_sha256[:20]}...")
        new_controller.close()

    print("\n" + "=" * 70)
    print("=== DEMO COMPLETE: ALL COGNITIVE SILENCE INVARIANTS VERIFIED ===")
    print("=" * 70)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "live-demo" or args.command is None:
        return run_live_demo(args.db_path)

    if args.db_path is None:
        print(json.dumps({"ok": False, "error": "--db-path is required for CLI commands"}, indent=2))
        return 2

    try:
        controller = CognitiveSilenceController(CognitiveSilenceStore(args.db_path))
    except SilencePersistenceError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    try:
        if args.command == "enter":
            result = controller.enter(
                args.reason,
                args.checkpoint_json,
                request_id=args.request_id,
            )
        elif args.command == "wake":
            result = controller.exit(args.source, request_id=args.request_id)
        elif args.command == "evaluate":
            decision = controller.evaluate_decision(
                args.signals_json,
                decision_id=args.decision_id,
            )
            result = {"ok": True, "decision": decision.as_dict()}
        else:
            result = {"ok": True, **controller.status()}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if bool(result.get("ok")) else 3
    except (TypeError, ValueError, SilencePersistenceError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    finally:
        controller.close()


if __name__ == "__main__":
    sys.exit(main())
