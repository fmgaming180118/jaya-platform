"""
demo_cognitive_kernel.py — End-to-end runnable demo for JAYA Core Portable Cognitive Kernel.

Executes 3 required scenarios without network, API keys, or large models.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Setup sys.path to root
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

from src.cognitive.contracts import UserRequest
from src.cognitive.runtime import JayaCoreRuntime
from src.identity.models import NodeClass
from src.resources.modes import ExecutionMode


def run_scenario_a(runtime: JayaCoreRuntime) -> dict:
    print("\n" + "=" * 60)
    print("SKENARIO A: Tugas Ringan Lokal ('Buat rencana untuk merapikan file proyek saya')")
    print("=" * 60)
    req = UserRequest(
        request_id="demo-scen-a-001",
        raw_prompt="Buat rencana untuk merapikan file proyek saya.",
        user_id="user_alex",
    )
    resp = runtime.process(req)
    out = resp.to_dict()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return out


def run_scenario_b(runtime: JayaCoreRuntime) -> dict:
    print("\n" + "=" * 60)
    print("SKENARIO B: Desain 3D ('Buat desain casing mini PC dengan airflow depan ke belakang')")
    print("=" * 60)
    req = UserRequest(
        request_id="demo-scen-b-001",
        raw_prompt="Buat desain casing mini PC dengan airflow depan ke belakang.",
        user_id="user_alex",
    )
    resp = runtime.process(req)
    out = resp.to_dict()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return out


def run_scenario_c() -> dict:
    print("\n" + "=" * 60)
    print("SKENARIO C: Offline Resource Kecil (Network=False, RAM=512MB, EDGE Node)")
    print("=" * 60)
    edge_runtime = JayaCoreRuntime(
        db_path=":memory:",
        node_id="edge-phone-01",
        node_class=NodeClass.EDGE,
    )
    # Simulate low memory & no network
    profile = edge_runtime.profiler.profile(
        override_total_mem_mb=1024,
        override_available_mem_mb=400,
        network_available=False,
        power_mode="SAVER",
    )
    mode = edge_runtime.mode_controller.auto_determine_mode(profile)

    req = UserRequest(
        request_id="demo-scen-c-001",
        raw_prompt="Bantu jelaskan cara kerja sistem memori lokal.",
        user_id="user_edge",
    )
    resp = edge_runtime.process(req)
    out = resp.to_dict()
    out["simulated_mode"] = mode.value
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return out


def main() -> None:
    print("MEMULAI DEMO JAYA CORE PORTABLE COGNITIVE KERNEL...")
    runtime = JayaCoreRuntime(db_path=":memory:", node_id="central-workstation")

    res_a = run_scenario_a(runtime)
    res_b = run_scenario_b(runtime)
    res_c = run_scenario_c()

    print("\n" + "=" * 60)
    print("RINGKASAN DEMO END-TO-END")
    print("=" * 60)
    print(f"Skenario A Status: {res_a['status']} | Intent: {res_a['intent_type']} | Mode: {res_a['execution_mode']}")
    print(f"Skenario B Status: {res_b['status']} | Intent: {res_b['intent_type']} | Missing Context: {res_b['metadata'].get('missing_context')}")
    print(f"Skenario C Status: {res_c['status']} | Mode: {res_c['execution_mode']} | Node Class: {res_c['metadata'].get('node_class')}")
    print("\nDemo selesai dengan sukses!")


if __name__ == "__main__":
    main()
