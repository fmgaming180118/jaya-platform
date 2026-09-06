"""Rigorous persistence and restart survival tests for Batch 1 pillars:
- Pillar 30: Twin Protocol
- Pillar 32: Collective Pulse
- Pillar 34: Dynamic MoE Router
- Pillar 35: Activation Sparsity Controller
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jaya_core.brain_v2.engine.activation_sparsity import ActivationSparsityController
from jaya_core.brain_v2.engine.collective_pulse import CollectivePulse
from jaya_core.brain_v2.engine.dynamic_moe import DynamicMoERouter
from jaya_core.brain_v2.extensions.twin.twin_protocol import TwinProtocol


class TestBatch1Persistence(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._temp_dir.name)

    def tearDown(self):
        self._temp_dir.cleanup()

    # ------------------------------------------------------------------
    # Pillar 30 — Twin Protocol Persistence
    # ------------------------------------------------------------------
    def test_twin_protocol_persistence_survives_restart(self):
        storage_a = self.tmp / "twin_a.json"
        storage_b = self.tmp / "twin_b.json"

        # 1. Instance 1 sends packets and ingests
        proto_a = TwinProtocol(node_id="node-a", shared_secret="sec123", storage_path=storage_a)
        proto_b = TwinProtocol(node_id="node-b", shared_secret="sec123", storage_path=storage_b)

        pkt1 = proto_a.create_sync_packet(peer_id="node-b", state={"step": 1})
        ok1, reason1, state1 = proto_b.verify_sync_packet(pkt1, expected_peer_id="node-b", expected_sender="node-a")
        self.assertTrue(ok1)
        self.assertEqual(reason1, "ok")
        self.assertEqual(state1["step"], 1)

        pkt2 = proto_a.create_sync_packet(peer_id="node-b", state={"step": 2})
        ok2, reason2, state2 = proto_b.verify_sync_packet(pkt2, expected_peer_id="node-b", expected_sender="node-a")
        self.assertTrue(ok2)
        self.assertEqual(reason2, "ok")

        # Verify on-disk file was created
        self.assertTrue(storage_a.exists())
        self.assertTrue(storage_b.exists())

        # 2. Simulate complete restart by creating fresh instances from storage
        rebooted_a = TwinProtocol(node_id="node-a", shared_secret="sec123", storage_path=storage_a)
        rebooted_b = TwinProtocol(node_id="node-b", shared_secret="sec123", storage_path=storage_b)

        self.assertGreaterEqual(rebooted_a.status()["tx_seq"], 2)
        self.assertEqual(rebooted_b.status()["last_seq_by_peer"].get("node-a"), 2)

        # Replay of pkt1 or pkt2 must be rejected across process restart
        replay_ok, replay_reason, _ = rebooted_b.verify_sync_packet(
            pkt1, expected_peer_id="node-b", expected_sender="node-a"
        )
        self.assertFalse(replay_ok)
        self.assertIn(replay_reason, ("replay_nonce", "stale_seq"))

        # Stale seq (old sequence packet) rejected
        stale_pkt = dict(pkt2)
        stale_pkt["nonce"] = "new-random-nonce-xyz"
        stale_ok, stale_reason, _ = rebooted_b.verify_sync_packet(
            stale_pkt, expected_peer_id="node-b", expected_sender="node-a"
        )
        self.assertFalse(stale_ok)

        # Fresh sequence (seq=3) generated from rebooted_a must succeed
        pkt3 = rebooted_a.create_sync_packet(peer_id="node-b", state={"step": 3})
        self.assertEqual(pkt3["seq"], 3)
        ok3, reason3, state3 = rebooted_b.verify_sync_packet(
            pkt3, expected_peer_id="node-b", expected_sender="node-a"
        )
        self.assertTrue(ok3)
        self.assertEqual(state3["step"], 3)

    # ------------------------------------------------------------------
    # Pillar 32 — Collective Pulse Persistence
    # ------------------------------------------------------------------
    def test_collective_pulse_persistence_survives_restart(self):
        storage = self.tmp / "pulse.json"
        pulse = CollectivePulse(max_events=100, storage_path=storage)

        # Ingest turns and peer signals
        pulse.ingest_turn("search files", activation_topk=0.08, primary_expert="search", is_online=True)
        pulse.ingest_peer_signal("peer-1", trust=0.9, novelty=0.4, cohesion=0.85, is_online=True)
        pulse.ingest_peer_signal("peer-2", trust=0.85, novelty=0.5, cohesion=0.80, is_online=True)

        snapshot1 = pulse.pulse()
        metrics1 = pulse.export_metrics()
        self.assertEqual(snapshot1["mode"], "collective_sync")
        self.assertIn("jaya_collective_pulse_score", metrics1)
        self.assertTrue(storage.exists())

        # Simulate process reboot
        rebooted_pulse = CollectivePulse(max_events=100, storage_path=storage)
        snapshot2 = rebooted_pulse.pulse()
        metrics2 = rebooted_pulse.export_metrics()

        self.assertEqual(snapshot2["mode"], snapshot1["mode"])
        self.assertEqual(snapshot2["events_considered"], snapshot1["events_considered"])
        self.assertAlmostEqual(snapshot2["pulse_score"], snapshot1["pulse_score"], places=3)
        self.assertEqual(metrics2.get("jaya_collective_events_total"), 3.0)

    # ------------------------------------------------------------------
    # Pillar 34 — Dynamic MoE Router Persistence
    # ------------------------------------------------------------------
    def test_dynamic_moe_persistence_survives_restart(self):
        storage = self.tmp / "dynamic_moe.json"
        router = DynamicMoERouter(max_active_experts=2, storage_path=storage)

        # Route several requests and record feedback
        r1 = router.route("prove theorem and verify logic consistency", logic_expr=["PROVE", "x"], cpu_pct=20.0, mem_pct=25.0)
        self.assertEqual(r1["primary_expert"], "logic")

        router.apply_feedback(expert="logic", outcome=0.35)
        router.apply_feedback(expert="action", outcome=-0.10)

        status1 = router.status()
        self.assertTrue(storage.exists())

        # Simulate process reboot
        rebooted_router = DynamicMoERouter(max_active_experts=2, storage_path=storage)
        status2 = rebooted_router.status()

        self.assertEqual(status2["decisions"], status1["decisions"])
        self.assertEqual(status2["feedback_count"], status1["feedback_count"])
        self.assertAlmostEqual(status2["feedback_bias"]["logic"], status1["feedback_bias"]["logic"], places=3)
        self.assertAlmostEqual(status2["feedback_bias"]["action"], status1["feedback_bias"]["action"], places=3)

    # ------------------------------------------------------------------
    # Pillar 35 — Activation Sparsity Controller Persistence
    # ------------------------------------------------------------------
    def test_activation_sparsity_persistence_survives_restart(self):
        storage = self.tmp / "activation_sparsity.json"
        controller = ActivationSparsityController(default_topk=0.10, storage_path=storage)

        d1 = controller.decide("delete system database", cpu_pct=90.0, mem_pct=85.0)
        d2 = controller.decide("hello world", cpu_pct=10.0, mem_pct=15.0)
        self.assertTrue(storage.exists())

        status1 = controller.status()
        self.assertEqual(status1["decisions"], 2)

        # Simulate process reboot
        rebooted = ActivationSparsityController(default_topk=0.10, storage_path=storage)
        status2 = rebooted.status()

        self.assertEqual(status2["decisions"], 2)
        self.assertEqual(status2["last_decision"]["text_sample"], d2["text_sample"])


if __name__ == "__main__":
    unittest.main()
