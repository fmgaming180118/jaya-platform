"""
test_phase_g_mesh.py — Unit tests for Phase G: Distributed Node & JAYA Mesh.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

from src.identity.models import AuthorityLevel, NodeClass, NodeIdentity, NodeRole
from src.mesh.mission_autonomous import MissionNodeAutonomousRunner
from src.mesh.node_manager import NodeRegistry
from src.mesh.offline_sync import StandardNodeOfflineSyncManager
from src.mesh.sync_engine import MeshSyncEngine
from src.mesh.task_delegation import TaskDelegationEngine
from src.sync.event_log import AppendOnlyEventLog


class TestStandardNodeOfflineSyncManager:
    def test_record_offline_events_and_flush_on_reconnect(self):
        log_std = AppendOnlyEventLog()
        log_cent = AppendOnlyEventLog()
        engine_std = MeshSyncEngine("std-node-1", log_std)
        engine_cent = MeshSyncEngine("cent-node-1", log_cent)

        mgr = StandardNodeOfflineSyncManager("std-node-1", log_std, engine_std)

        # Record 2 events offline
        mgr.record_offline_event("NOTE_TAKEN", {"title": "Draft 1"})
        mgr.record_offline_event("LOCAL_CALC", {"value": 42})
        assert mgr.pending_offline_count == 2

        # Offline flush attempt fails gracefully
        res_off = mgr.flush_offline_events("cent-node-1")
        assert res_off.is_success is False

        # Connect & flush to Central engine
        mgr.set_connectivity(is_online=True, central_node_id="cent-node-1")
        res_flush = mgr.flush_offline_events(target_sync_engine=engine_cent)

        assert res_flush.is_success is True
        assert res_flush.events_flushed == 2
        assert mgr.pending_offline_count == 0


class TestTaskDelegationEngine:
    def test_delegate_reasoning_full_to_central_node(self):
        registry = NodeRegistry()
        central = NodeIdentity(
            node_id="central-main",
            jaya_identity_id="owner-1",
            node_class=NodeClass.CENTRAL,
            role=NodeRole.PRIMARY_COGNITIVE_NODE,
            authority=AuthorityLevel.CENTRAL_AUTHORITY,
        )
        edge = NodeIdentity(
            node_id="edge-sensor",
            jaya_identity_id="owner-1",
            node_class=NodeClass.EDGE,
            role=NodeRole.PERSONAL_MOBILE_NODE,
            authority=AuthorityLevel.EDGE_OBSERVER,
        )
        registry.register_node(central, available_memory_mb=16384, capabilities=["reasoning.full"])
        registry.register_node(edge, available_memory_mb=512, capabilities=["text.basic"])

        engine = TaskDelegationEngine(registry)
        receipt = engine.delegate_task("edge-sensor", required_capability="reasoning.full", min_memory_mb=2048)

        assert receipt.status == "COMPLETED"
        assert receipt.target_node_id == "central-main"
        assert receipt.signature.startswith("sig-sha256-")

    def test_delegation_fails_when_no_suitable_target(self):
        registry = NodeRegistry()
        edge = NodeIdentity(
            node_id="edge-only",
            jaya_identity_id="owner-1",
            node_class=NodeClass.EDGE,
            role=NodeRole.PERSONAL_MOBILE_NODE,
            authority=AuthorityLevel.EDGE_OBSERVER,
        )
        registry.register_node(edge, available_memory_mb=256, capabilities=["text.basic"])

        engine = TaskDelegationEngine(registry)
        receipt = engine.delegate_task("edge-only", required_capability="reasoning.full")
        assert receipt.status == "REJECTED_NO_SUITABLE_NODE"


class TestMissionNodeAutonomousRunner:
    def test_mission_node_runs_10min_autonomous_window(self):
        log = AppendOnlyEventLog()
        runner = MissionNodeAutonomousRunner("mission-node-77", log)

        report = runner.run_mission_window("mission-op-77", simulated_duration_seconds=600.0)

        assert report.status == "OFFLINE_AUTONOMOUS_SUCCESS"
        assert report.total_duration_seconds == 600.0
        assert report.decisions_count >= 3
        assert report.is_network_isolated is True
        assert log.get_cursor().last_sequence_number >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
