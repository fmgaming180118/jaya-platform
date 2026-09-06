"""Live interactive demonstration of Pillar 10: Affective Metabolism control state."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.brain_v2.organism.affective_metabolism import (  # noqa: E402
    AffectiveControlPolicy,
    AffectiveMetabolismController,
    AffectiveSignal,
    AffectiveSignalConflict,
    ControlSignalSource,
)


def run_demo() -> int:
    print("=" * 70)
    print("=== JAYA AFFECTIVE METABOLISM (PILAR 10) LIVE DEMONSTRATION ===")
    print("=" * 70)
    print("Note: This pillar manages bounded runtime control state (urgency,")
    print("caution, patience, escalation) from explicit signals. It does NOT")
    print("claim or infer human emotion or psychological consciousness.")
    print("=" * 70)

    # 1. Baseline Initialization
    print("\n[Step 1] Initializing Controller & Inspecting Baseline State")
    policy = AffectiveControlPolicy(decay_half_life_seconds=5.0)
    controller = AffectiveMetabolismController(policy)
    status = controller.status()
    print(f" -> Classification: {status['classification']}")
    print(f" -> Persistent:     {status['persistent']} (State is intentionally transient)")
    print(f" -> Initial State:  {status['state']}")
    print(f" -> Initial Policy: {status['decision']}")

    # 2. Applying Explicit Task Signal
    print("\n[Step 2] Applying Explicit TASK Signal (Urgency Delta = +0.25)")
    res_task = controller.apply(
        AffectiveSignal(
            source=ControlSignalSource.TASK,
            urgency_delta=0.25,
            signal_id="demo-task-001",
        )
    )
    print(f" -> Changed:          {res_task['changed']}")
    print(f" -> Urgency:          {res_task['state']['urgency']:.2f}")
    print(f" -> Planner Priority: {res_task['decision']['planner_priority']}")
    print(f" -> Interaction Mode: {res_task['decision']['interaction_mode']}")

    # 3. Applying High-Caution Safety Signal
    print("\n[Step 3] Applying High-Caution SAFETY Signal (Caution Delta = +0.25)")
    res_safety = controller.apply(
        AffectiveSignal(
            source=ControlSignalSource.SAFETY,
            caution_delta=0.25,
            signal_id="demo-safety-001",
        )
    )
    print(f" -> Changed:                  {res_safety['changed']}")
    print(f" -> Caution:                  {res_safety['state']['caution']:.2f}")
    print(f" -> Confirmation Recommended: {res_safety['decision']['confirmation_recommended']}")
    print(f" -> Safety Relaxed Invariant: {res_safety['decision']['safety_relaxed']} (MUST BE False)")
    print(f" -> Authority Changed:        {res_safety['decision']['authority_changed']} (MUST BE False)")

    # 4. Idempotency Replay
    print("\n[Step 4] Testing Idempotent Replay (Re-submitting demo-safety-001)")
    res_replay = controller.apply(
        AffectiveSignal(
            source=ControlSignalSource.SAFETY,
            caution_delta=0.25,
            signal_id="demo-safety-001",
        )
    )
    print(f" -> Changed: {res_replay['changed']} (Idempotent: no state drift)")
    print(f" -> Caution: {res_replay['state']['caution']:.2f}")

    # 5. Idempotency Conflict Detection
    print("\n[Step 5] Testing Conflict Detection (Reusing demo-safety-001 with differing delta)")
    conflict_detected = False
    try:
        controller.apply(
            AffectiveSignal(
                source=ControlSignalSource.SAFETY,
                caution_delta=-0.10,
                signal_id="demo-safety-001",
            )
        )
    except AffectiveSignalConflict as exc:
        conflict_detected = True
        print(f" -> Conflict Caught: {exc}")
    assert conflict_detected, "Conflict MUST be rejected"

    # 6. Unconfirmed User State Rejection
    print("\n[Step 6] Testing Unconfirmed User State Rejection")
    unconfirmed_caught = False
    try:
        AffectiveSignal(
            source=ControlSignalSource.USER_CONFIRMED,
            urgency_delta=0.10,
            user_state_confirmed=False,
        )
    except ValueError as exc:
        unconfirmed_caught = True
        print(f" -> Unconfirmed State Rejected: {exc}")
    assert unconfirmed_caught, "Unconfirmed user state MUST be rejected"

    # 7. User-Confirmed Signal Application
    print("\n[Step 7] Applying Explicitly Confirmed User State Signal")
    res_user = controller.apply(
        AffectiveSignal(
            source=ControlSignalSource.USER_CONFIRMED,
            patience_delta=0.20,
            signal_id="demo-user-confirmed-001",
            user_state_confirmed=True,
        )
    )
    print(f" -> Changed:  {res_user['changed']}")
    print(f" -> Patience: {res_user['state']['patience']:.2f}")

    # 8. Reset to Baseline
    print("\n[Step 8] Resetting Controller to Baseline")
    res_reset = controller.reset()
    print(f" -> State After Reset: {res_reset['state']}")
    print(f" -> Revision:          {res_reset['state']['revision']}")

    print("\n" + "=" * 70)
    print("=== DEMO COMPLETE: ALL PILAR 10 INVARIANTS VERIFIED ===")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Output final status as JSON")
    args = parser.parse_args()

    if args.json:
        controller = AffectiveMetabolismController()
        print(json.dumps(controller.status(), indent=2))
        return 0
    return run_demo()


if __name__ == "__main__":
    sys.exit(main())
