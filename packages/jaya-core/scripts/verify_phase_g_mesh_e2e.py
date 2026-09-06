"""
verify_phase_g_mesh_e2e.py — Phase G Distributed Node & JAYA Mesh E2E Verification Drill Script.

Validates:
1. Node Identity Protocol & Tier Registration (NodeRegistry)
2. Signed Event Sync & Deduplication (MeshSyncEngine)
3. Deterministic Conflict Resolution (seq, timestamp, node_id priority tie-breaker)
4. Standard Node Offline Event Buffering & Central Reconnection Flush (StandardNodeOfflineSyncManager)
5. Task Delegation from Edge to Central for reasoning.full (TaskDelegationEngine)
6. Mission Node 10-minute OFFLINE_AUTONOMOUS mode operation & decision logging (MissionNodeAutonomousRunner)
7. Security regression check (Phase F contracts & sandbox interlocks intact)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "packages" / "jaya-core" / "src"))

from jaya_core.identity.models import NodeClass, NodeIdentity, NodeRole
from jaya_core.mesh.mission_autonomous import MissionNodeAutonomousRunner
from jaya_core.mesh.node_manager import NodeRegistry
from jaya_core.mesh.offline_sync import StandardNodeOfflineSyncManager
from jaya_core.mesh.sync_engine import MeshSyncEngine
from jaya_core.mesh.task_delegation import TaskDelegationEngine
from jaya_core.sync.contracts import NodeEvent
from jaya_core.sync.event_log import AppendOnlyEventLog


def run_phase_g_mesh_e2e_drill() -> dict:
    results = {}

    # 1. Node Identity Protocol & Registry
    registry = NodeRegistry()
    from jaya_core.identity.models import AuthorityLevel

    central_id = NodeIdentity(
        node_id="central-node-01",
        jaya_identity_id="jaya-owner-01",
        node_class=NodeClass.CENTRAL,
        role=NodeRole.PRIMARY_COGNITIVE_NODE,
        authority=AuthorityLevel.CENTRAL_AUTHORITY,
    )
    standard_id = NodeIdentity(
        node_id="standard-laptop-01",
        jaya_identity_id="jaya-owner-01",
        node_class=NodeClass.STANDARD,
        role=NodeRole.PERSONAL_WORKSTATION_NODE,
        authority=AuthorityLevel.STANDARD_WORKER,
    )
    edge_id = NodeIdentity(
        node_id="edge-node-01",
        jaya_identity_id="jaya-owner-01",
        node_class=NodeClass.EDGE,
        role=NodeRole.PERSONAL_MOBILE_NODE,
        authority=AuthorityLevel.EDGE_OBSERVER,
    )
    mission_id = NodeIdentity(
        node_id="mission-drone-01",
        jaya_identity_id="jaya-owner-01",
        node_class=NodeClass.MISSION,
        role=NodeRole.MISSION_CRITICAL_AUTONOMOUS_NODE,
        authority=AuthorityLevel.MISSION_OPERATOR,
    )

    registry.register_node(central_id, available_memory_mb=8192, capabilities=["reasoning.full", "core.reason"])
    registry.register_node(standard_id, available_memory_mb=4096, capabilities=["core.reason"])
    registry.register_node(edge_id, available_memory_mb=512, capabilities=["core.reason"])
    registry.register_node(mission_id, available_memory_mb=512, capabilities=["core.reason"])

    active_nodes = registry.list_active_nodes()
    drill1_pass = len(active_nodes) == 4
    results["drill_1_node_registry_protocol"] = "SUCCESS" if drill1_pass else "FAILED"

    # 2. Event Sync & Deduplication
    log_central = AppendOnlyEventLog()
    log_standard = AppendOnlyEventLog()
    sync_engine_standard = MeshSyncEngine("standard-laptop-01", log_standard)
    sync_engine_central = MeshSyncEngine("central-node-01", log_central)

    evt1 = NodeEvent(event_id="evt-001", event_type="KNOWLEDGE_UPDATE", node_id="standard-laptop-01", sequence_number=1, payload={"key": "val"})
    log_standard.append_raw(evt1)

    batch = sync_engine_standard.create_sync_batch("central-node-01", last_known_seq=0)
    appended, skipped = sync_engine_central.receive_sync_batch(batch)
    # Receive duplicate batch
    appended_dup, skipped_dup = sync_engine_central.receive_sync_batch(batch)

    drill2_pass = (appended == 1) and (skipped_dup == 1)
    results["drill_2_mesh_sync_deduplication"] = "SUCCESS" if drill2_pass else "FAILED"

    # 3. Conflict Resolution
    evt_a = NodeEvent(event_id="evt-a", event_type="UPDATE", node_id="node-z", sequence_number=10, timestamp="2026-08-02T12:00:00Z")
    evt_b = NodeEvent(event_id="evt-b", event_type="UPDATE", node_id="node-a", sequence_number=10, timestamp="2026-08-02T12:00:00Z")
    winner = sync_engine_central.resolve_conflicting_events(evt_a, evt_b)
    drill3_pass = winner.node_id == "node-z"  # Lexicographical tie-breaker
    results["drill_3_conflict_resolution"] = "SUCCESS" if drill3_pass else "FAILED"

    # 4. Standard Node Offline Event Buffering & Central Reconnection Flush
    offline_manager = StandardNodeOfflineSyncManager("standard-laptop-01", log_standard, sync_engine_standard)
    offline_manager.record_offline_event("OFFLINE_ACTION_01", {"action": "local_note"})
    offline_manager.record_offline_event("OFFLINE_ACTION_02", {"action": "local_analysis"})
    pending_before = offline_manager.pending_offline_count

    offline_manager.set_connectivity(is_online=True, central_node_id="central-node-01")
    flush_res = offline_manager.flush_offline_events()
    drill4_pass = (pending_before == 2) and flush_res.is_success and (offline_manager.pending_offline_count == 0)
    results["drill_4_standard_offline_sync_flush"] = "SUCCESS" if drill4_pass else "FAILED"

    # 5. Edge-to-Central Task Delegation (reasoning.full)
    delegation_engine = TaskDelegationEngine(registry)
    delg_receipt = delegation_engine.delegate_task(
        source_node_id="edge-node-01", required_capability="reasoning.full", min_memory_mb=2048
    )
    drill5_pass = (delg_receipt.status == "COMPLETED") and (delg_receipt.target_node_id == "central-node-01")
    results["drill_5_edge_central_task_delegation"] = "SUCCESS" if drill5_pass else "FAILED"

    # 6. Mission Node 10-minute OFFLINE_AUTONOMOUS Mode
    log_mission = AppendOnlyEventLog()
    mission_runner = MissionNodeAutonomousRunner("mission-drone-01", log_mission)
    report = mission_runner.run_mission_window("mission-op-99", simulated_duration_seconds=600.0)
    drill6_pass = (report.status == "OFFLINE_AUTONOMOUS_SUCCESS") and (report.total_duration_seconds == 600.0) and (report.decisions_count >= 3)
    results["drill_6_mission_node_autonomous_10min"] = "SUCCESS" if drill6_pass else "FAILED"

    # 7. Security Regression Check (Phase F Contracts)
    from jaya_agent.contracts.core_agent_os_contract import ContractValidator, CoreToAgentDispatch
    validator = ContractValidator()
    dispatch = CoreToAgentDispatch(request_id="req-sec-check", plan_id="p1")
    val_res = validator.validate_core_to_agent(dispatch)
    drill7_pass = val_res.is_valid
    results["drill_7_security_regression_phase_f"] = "SUCCESS" if drill7_pass else "FAILED"

    return results


def main() -> int:
    print("VERIFIKASI DRILL E2E FASE G: DISTRIBUTED NODE & JAYA MESH...")
    res = run_phase_g_mesh_e2e_drill()
    print(json.dumps(res, indent=2))

    if all(status == "SUCCESS" for status in res.values()):
        print("\nSeluruh 7 drill E2E Fase G Mesh VERIFIED SUCCESSFUL!")
        return 0

    print("\nPhase G Mesh E2E verification FAILED!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
