"""Phase 1 gate for Pillar 30: Twin Protocol.

Validates:
1. Signed handshake accepts only trusted, fresh payloads.
2. Replay and tamper attempts are rejected.
3. Sync packets enforce monotonic sequence per peer.
4. Runtime integration supports handshake + sync exchange.
"""

import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, cast
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.runtime import IronEngine
from src.brain_v2.extensions.twin.twin_protocol import TwinProtocol


class _FakeResourceMonitor:
    def __init__(self, cpu: float = 30.0, mem: float = 35.0):
        self._cpu = cpu
        self._mem = mem

    def readings(self) -> Dict[str, float]:
        return {"cpu_pct": self._cpu, "mem_pct": self._mem}

    def status(self) -> Dict[str, Any]:
        return {
            "running": False,
            "psutil": False,
            "readings": self.readings(),
            "reading_count": 0,
            "silence_active": False,
        }


class _FakeHybrid:
    def __init__(self, online: bool):
        self._online = bool(online)

    @property
    def is_online(self) -> bool:
        return self._online


class TestTwinProtocolModule(unittest.TestCase):
    def setUp(self):
        self.secret = "unit-test-shared-secret"
        self.protocol_a = TwinProtocol(node_id="node-a", shared_secret=self.secret)
        self.protocol_b = TwinProtocol(node_id="node-b", shared_secret=self.secret)

    def test_handshake_roundtrip(self):
        handshake = self.protocol_a.create_handshake(peer_id="node-b")
        ok, reason = self.protocol_b.verify_handshake(
            payload=handshake,
            expected_peer_id="node-b",
            expected_sender="node-a",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_handshake_replay_rejected(self):
        handshake = self.protocol_a.create_handshake(peer_id="node-b")
        ok_first, _ = self.protocol_b.verify_handshake(
            payload=handshake,
            expected_peer_id="node-b",
            expected_sender="node-a",
        )
        ok_second, reason_second = self.protocol_b.verify_handshake(
            payload=handshake,
            expected_peer_id="node-b",
            expected_sender="node-a",
        )
        self.assertTrue(ok_first)
        self.assertFalse(ok_second)
        self.assertEqual(reason_second, "replay_nonce")

    def test_handshake_tamper_rejected(self):
        handshake = self.protocol_a.create_handshake(
            peer_id="node-b",
            capabilities={"narrative": True},
        )
        handshake["capabilities"] = {"narrative": False}

        ok, reason = self.protocol_b.verify_handshake(
            payload=handshake,
            expected_peer_id="node-b",
            expected_sender="node-a",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "bad_signature")

    def test_sync_packet_stale_sequence_rejected(self):
        packet_1 = self.protocol_a.create_sync_packet(peer_id="node-b", state={"x": 1})
        packet_2 = self.protocol_a.create_sync_packet(peer_id="node-b", state={"x": 2})

        ok_2, reason_2, _ = self.protocol_b.verify_sync_packet(
            payload=packet_2,
            expected_peer_id="node-b",
            expected_sender="node-a",
        )
        ok_1, reason_1, _ = self.protocol_b.verify_sync_packet(
            payload=packet_1,
            expected_peer_id="node-b",
            expected_sender="node-a",
        )

        self.assertTrue(ok_2)
        self.assertEqual(reason_2, "ok")
        self.assertFalse(ok_1)
        self.assertEqual(reason_1, "stale_seq")


class TestRuntimeTwinProtocolIntegration(unittest.TestCase):
    def _build_engine(self, node_id: str, secret: str, online: bool = True) -> IronEngine:
        with patch.dict(
            os.environ,
            {"JAYA_NODE_ID": node_id, "JAYA_TWIN_SHARED_SECRET": secret},
            clear=False,
        ):
            engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
            engine.ignite()

        resource_mon = getattr(engine, "_resource_mon", None)
        if resource_mon is not None:
            resource_mon.stop()

        setattr(engine, "_resource_mon", _FakeResourceMonitor())
        setattr(engine, "_hybrid", _FakeHybrid(online=online))
        return engine

    def test_runtime_handshake_and_sync_exchange(self):
        secret = "runtime-shared-secret"
        engine_a = self._build_engine(node_id="node-a", secret=secret, online=True)
        engine_b = self._build_engine(node_id="node-b", secret=secret, online=True)

        hs = engine_a.twin_handshake(peer_id="node-b")
        self.assertTrue(hs["ok"])

        verified = engine_b.verify_twin_handshake(
            hs["handshake"],
            expected_sender="node-a",
        )
        self.assertTrue(verified["ok"])

        packet = engine_a.create_twin_sync_packet(peer_id="node-b")
        self.assertTrue(packet["ok"])

        ingest = engine_b.ingest_twin_sync_packet(
            packet["packet"],
            expected_sender="node-a",
        )
        self.assertTrue(ingest["ok"])
        self.assertEqual(ingest["reason"], "ok")

    def test_runtime_status_exposes_twin_protocol(self):
        engine = self._build_engine(node_id="node-z", secret="status-secret", online=True)
        status = engine.status()

        self.assertIn("twin_protocol", status)
        self.assertIsInstance(status["twin_protocol"], dict)

    def test_sync_ingest_updates_collective_peer_signal(self):
        secret = "collective-sync-secret"
        engine_a = self._build_engine(node_id="node-a", secret=secret, online=True)
        engine_b = self._build_engine(node_id="node-b", secret=secret, online=True)

        packet = engine_a.create_twin_sync_packet(peer_id="node-b")
        ingest = engine_b.ingest_twin_sync_packet(
            packet["packet"],
            expected_sender="node-a",
        )
        self.assertTrue(ingest["ok"])

        status_b = engine_b.status()
        pulse = status_b.get("collective_pulse")
        self.assertIsInstance(pulse, dict)
        if not isinstance(pulse, dict):
            self.fail("collective_pulse status must be dict")

        pulse_map = cast(Dict[str, Any], pulse)
        by_kind_raw = pulse_map.get("by_kind", {})
        by_kind = cast(Dict[str, Any], by_kind_raw) if isinstance(by_kind_raw, dict) else {}
        peer_raw = by_kind.get("peer", 0)
        peer_count = int(peer_raw) if isinstance(peer_raw, (int, float, str)) else 0
        self.assertGreaterEqual(peer_count, 1)

    def test_sync_ingest_rejects_invalid_state_payload(self):
        secret = "zero-trust-sync-secret"
        engine_a = self._build_engine(node_id="node-a", secret=secret, online=True)
        engine_b = self._build_engine(node_id="node-b", secret=secret, online=True)

        malicious_state: Dict[str, Any] = {
            "is_silent": False,
            "topk_ratio": "not-a-number",
            "loyalty_score": 0.8,
            "moe_primary_expert": "logic",
            "collective_pulse": {
                "avg_trust": 0.9,
                "avg_novelty": 0.3,
                "avg_cohesion": 0.8,
                "pulse_score": 0.85,
                "mode": "collective_sync",
                "online_ratio": 1.0,
                "events_considered": 8,
            },
            "timestamp": 12345.0,
        }

        packet = engine_a.create_twin_sync_packet(
            peer_id="node-b",
            state_override=malicious_state,
        )
        self.assertTrue(packet["ok"])

        ingest = engine_b.ingest_twin_sync_packet(
            packet["packet"],
            expected_sender="node-a",
        )
        self.assertFalse(ingest["ok"])
        self.assertTrue(str(ingest.get("reason", "")).startswith("zero_trust:"))


if __name__ == "__main__":
    unittest.main()
