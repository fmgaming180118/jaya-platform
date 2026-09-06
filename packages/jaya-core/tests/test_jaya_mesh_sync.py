"""
test_jaya_mesh_sync.py — Unit tests for JAYA Mesh Distributed Sync & Node Management.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "packages" / "jaya-core" / "src"))

from jaya_core.identity.models import AuthorityLevel, NodeClass, NodeIdentity, NodeRole
from jaya_core.mesh.node_manager import NodeRegistry
from jaya_core.mesh.sync_engine import MeshSyncEngine
from jaya_core.sync.contracts import NodeEvent
from jaya_core.sync.event_log import AppendOnlyEventLog


class TestNodeRegistry:
    def test_register_and_list_nodes(self):
        reg = NodeRegistry(heartbeat_timeout_seconds=5.0)
        id_central = NodeIdentity(
            node_id="central-01",
            jaya_identity_id="jaya-owner-01",
            node_class=NodeClass.CENTRAL,
            role=NodeRole.PRIMARY_COGNITIVE_NODE,
            authority=AuthorityLevel.CENTRAL_AUTHORITY,
        )
        id_edge = NodeIdentity(
            node_id="edge-phone-01",
            jaya_identity_id="jaya-owner-01",
            node_class=NodeClass.EDGE,
            role=NodeRole.PERSONAL_MOBILE_NODE,
            authority=AuthorityLevel.EDGE_OBSERVER,
        )

        reg.register_node(id_central, available_memory_mb=8192, capabilities=["reasoning.full", "3d.cad"])
        reg.register_node(id_edge, available_memory_mb=512, capabilities=["reasoning.lite"])

        active_all = reg.list_active_nodes()
        assert len(active_all) == 2

        active_central = reg.list_active_nodes(node_class=NodeClass.CENTRAL)
        assert len(active_central) == 1
        assert active_central[0].identity.node_id == "central-01"

        active_cad = reg.list_active_nodes(required_capability="3d.cad")
        assert len(active_cad) == 1
        assert active_cad[0].identity.node_id == "central-01"

        active_high_mem = reg.list_active_nodes(min_memory_mb=2048)
        assert len(active_high_mem) == 1
        assert active_high_mem[0].identity.node_id == "central-01"

    def test_node_heartbeat_timeout(self):
        reg = NodeRegistry(heartbeat_timeout_seconds=0.1)
        node_id = NodeIdentity(
            node_id="temp-edge",
            jaya_identity_id="jaya-owner-01",
            node_class=NodeClass.EDGE,
            role=NodeRole.PERSONAL_MOBILE_NODE,
            authority=AuthorityLevel.EDGE_OBSERVER,
        )

        reg.register_node(node_id)
        assert len(reg.list_active_nodes()) == 1

        time.sleep(0.15)
        assert len(reg.list_active_nodes()) == 0

        # Update heartbeat restores active state
        assert reg.update_heartbeat("temp-edge") is True
        assert len(reg.list_active_nodes()) == 1


class TestMeshSyncEngine:
    def test_sync_batch_and_deduplication(self):
        log_a = AppendOnlyEventLog(node_id="node-A")
        log_b = AppendOnlyEventLog(node_id="node-B")

        evt1 = log_a.append(event_type="MEMORY_UPDATE", payload={"key": "val1"})
        evt2 = log_a.append(event_type="GOAL_CREATED", payload={"goal": "test"})

        engine_a = MeshSyncEngine(local_node_id="node-A", local_event_log=log_a)
        batch = engine_a.create_sync_batch(target_node_id="node-B")

        engine_b = MeshSyncEngine(local_node_id="node-B", local_event_log=log_b)
        appended, skipped = engine_b.receive_sync_batch(batch)

        assert appended == 2
        assert skipped == 0
        assert len(log_b.get_events_since(0)) == 2

        # Re-sending same batch results in deduplication
        appended_dup, skipped_dup = engine_b.receive_sync_batch(batch)
        assert appended_dup == 0
        assert skipped_dup == 2

    def test_conflict_resolution_deterministic_tiebreaker(self):
        log = AppendOnlyEventLog(node_id="test")
        engine = MeshSyncEngine(local_node_id="test", local_event_log=log)

        evt_a = NodeEvent(
            event_id="evt-a",
            event_type="TEST",
            timestamp=100.0,
            node_id="node-alpha",
            sequence_number=5,
            payload={},
        )
        evt_b = NodeEvent(
            event_id="evt-b",
            event_type="TEST",
            timestamp=100.0,
            node_id="node-beta",
            sequence_number=5,
            payload={},
        )

        winner = engine.resolve_conflicting_events(evt_a, evt_b)
        assert winner.node_id == "node-beta"  # "node-beta" > "node-alpha"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
