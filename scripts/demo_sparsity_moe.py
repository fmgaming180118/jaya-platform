#!/usr/bin/env python3
"""Exercise Pillar 34 (Dynamic MoE Router) and Pillar 35 (Activation Sparsity).

Demonstrates:
1. Adaptive 1-of-N sparse expert routing under varying CPU/Memory loads.
2. Reinforcement feedback persistence adjusting expert selection bias.
3. Dynamic top-k neuron activation trimming under high load vs safety bump for risk tokens.
4. Minimal top-k gating during cognitive silence mode.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.brain_v2.engine.activation_sparsity import ActivationSparsityController  # noqa: E402
from jaya_core.brain_v2.engine.dynamic_moe import DynamicMoERouter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Pillar 34 & 35 Dynamic MoE and Sparsity Demo")
    parser.add_argument("--work-dir", type=Path, default=None, help="Directory for persistent state files")
    args = parser.parse_args()

    temp_ctx = None
    if args.work_dir is None:
        temp_ctx = tempfile.TemporaryDirectory(prefix="jaya_moe_demo_")
        work_dir = Path(temp_ctx.name)
    else:
        work_dir = args.work_dir.expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        moe_storage = work_dir / "dynamic_moe.json"
        sparsity_storage = work_dir / "activation_sparsity.json"

        moe = DynamicMoERouter(max_active_experts=2, storage_path=moe_storage)
        sparsity = ActivationSparsityController(default_topk=0.10, storage_path=sparsity_storage)

        # 1. Normal Load Routing
        route_normal = moe.route("find documents in archive", cpu_pct=25.0, mem_pct=30.0)
        topk_normal = sparsity.decide("find documents in archive", cpu_pct=25.0, mem_pct=30.0)

        # 2. High Pressure Load Routing (forces single expert + lowers activation top-k)
        route_heavy = moe.route("perform heavy synthesis", cpu_pct=92.0, mem_pct=88.0)
        topk_heavy = sparsity.decide("perform heavy synthesis", cpu_pct=92.0, mem_pct=88.0)

        # 3. High Risk Action Token (safety bump)
        topk_risk = sparsity.decide("delete temporary volume snapshot", cpu_pct=30.0, mem_pct=30.0)

        # 4. Cognitive Silence Mode (minimum active top-k)
        topk_silent = sparsity.decide("background heartbeat", is_silent=True)

        # 5. Reinforcement Feedback
        moe.apply_feedback(expert=route_normal["primary_expert"], outcome=0.8)
        moe_status_before = moe.status()

        # 6. Simulate Process Reboot and Verify Bias & Calibration Persistence
        rebooted_moe = DynamicMoERouter(max_active_experts=2, storage_path=moe_storage)
        rebooted_sparsity = ActivationSparsityController(default_topk=0.10, storage_path=sparsity_storage)

        output = {
            "demo": "Pillar 34 (Dynamic MoE) & Pillar 35 (Activation Sparsity)",
            "normal_load": {
                "active_experts": route_normal["active_count"],
                "primary_expert": route_normal["primary_expert"],
                "target_topk": topk_normal["target_topk"],
            },
            "heavy_pressure_load": {
                "active_experts": route_heavy["active_count"],
                "primary_expert": route_heavy["primary_expert"],
                "target_topk": topk_heavy["target_topk"],
            },
            "risk_action": {
                "target_topk": topk_risk["target_topk"],
                "reason": topk_risk["reason"],
            },
            "cognitive_silence": {
                "target_topk": topk_silent["target_topk"],
                "reason": topk_silent["reason"],
            },
            "persistence_after_reboot": {
                "moe_decisions": rebooted_moe.status()["decisions"],
                "moe_feedback_bias": rebooted_moe.status()["feedback_bias"],
                "sparsity_decisions": rebooted_sparsity.status()["decisions"],
            },
        }
        print(json.dumps(output, indent=2))
        return 0
    finally:
        if temp_ctx:
            temp_ctx.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
