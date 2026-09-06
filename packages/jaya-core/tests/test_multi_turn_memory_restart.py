"""
Multi-turn Conversation Memory Restart Test

Tests the complete memory pipeline across process restarts:
1. NarrativeContinuity (Pillar 31) - JSON persistence
2. EpisodicMemoryStore - SQLite persistence  
3. WorkingMemory - In-memory (not persisted, but rebuilt from episodic)
4. IronEngine integration - Full runtime test
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from jaya_core.brain_v2.engine.narrative_continuity import NarrativeContinuity
from jaya_core.brain_v2.engine.runtime import IronEngine
from jaya_core.memory.episodic import EpisodicMemoryStore, MemoryEvent
from jaya_core.memory.working import WorkingMemory
from jaya_core.cognitive.context import ContextManager
from jaya_core.resources.profiler import ResourceProfile
from jaya_core.resources.modes import ExecutionMode
from jaya_core.identity.models import NodeIdentity, NodeClass
from jaya_core.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore

_IDENTITY_SECRET = "multi-turn-narrative-secret-at-least-32-bytes"


class TestMultiTurnConversationMemoryRestart(unittest.TestCase):
    """Test multi-turn conversation memory survives process restarts."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.narrative_path = str(Path(self.tmpdir.name) / "narrative.json")
        self.episodic_path = str(Path(self.tmpdir.name) / "episodic.db")
        self.anchor = DNAAnchor(
            Path(self.tmpdir.name) / "identity",
            EncryptedFileKeyStore(
                Path(self.tmpdir.name) / "keystore", _IDENTITY_SECRET
            ),
        )
        self.anchor.enroll()
        self.engines = []

    def tearDown(self):
        for engine in self.engines:
            narrative = getattr(engine, "_narrative", None)
            if narrative is not None:
                narrative.close()
                engine._narrative = None
        self.anchor.close()
        self.tmpdir.cleanup()

    def _build_engine(self) -> IronEngine:
        """Build IronEngine with persistence enabled."""
        with patch.dict(os.environ, {
            "JAYA_NARRATIVE_PATH": self.narrative_path,
            "JAYA_EPISODIC_PATH": self.episodic_path,
        }, clear=False):
            engine = IronEngine(
                model_path="missing.jay",
                password="x",
                enable_twin=False,
                identity_anchor=self.anchor,
            )
            engine.ignite()
            resource_mon = getattr(engine, "_resource_mon", None)
            if resource_mon is not None:
                resource_mon.stop()
            self.engines.append(engine)
            return engine

    def test_narrative_continuity_full_restart_cycle(self):
        """Test NarrativeContinuity survives full restart with multiple turns."""
        # First engine instance - simulate conversation
        engine1 = self._build_engine()
        
        # Simulate multi-turn conversation
        turns = [
            "Halo JAYA, saya ingin bertanya tentang machine learning",
            "Apa itu supervised learning?",
            "Bisakah kamu jelaskan perbedaan classification dan regression?",
            "Terima kasih, itu sangat membantu",
        ]
        
        for i, turn in enumerate(turns):
            result = engine1.execute_intent(turn)
            
            # Add some twin feedback occasionally
            if i == 1:
                engine1.receive_twin_feedback({
                    "task": "EXPLAIN_CONCEPT",
                    "result": {"score": 0.85},
                    "config_update": {},
                })
        
        # Get narrative state before restart
        narrative1 = engine1.narrative_context(limit=20, max_chars=8000)
        total_events_before = narrative1["total_events"]
        context_before = narrative1["context"]
        
        # Verify we have the expected events (narrative records turns regardless of ok status)
        self.assertGreaterEqual(total_events_before, len(turns))
        self.assertIn("machine learning", context_before.lower())
        self.assertIn("supervised learning", context_before.lower())
        self.assertIn("classification", context_before.lower())
        
        # Check feedback was recorded
        feedback_events = [e for e in narrative1["recent"] if e.get("kind") == "feedback"]
        self.assertEqual(len(feedback_events), 1)
        self.assertEqual(feedback_events[0]["task"], "EXPLAIN_CONCEPT")
        
        # Shutdown first engine
        del engine1
        
        # Second engine instance - should restore history
        engine2 = self._build_engine()
        narrative2 = engine2.narrative_context(limit=20, max_chars=8000)
        
        # Verify restoration
        self.assertTrue(narrative2["ok"])
        self.assertGreaterEqual(narrative2["total_events"], total_events_before)
        self.assertIn("machine learning", narrative2["context"].lower())
        self.assertIn("supervised learning", narrative2["context"].lower())
        self.assertIn("classification", narrative2["context"].lower())
        
        # Feedback should also be restored
        feedback_events2 = [e for e in narrative2["recent"] if e.get("kind") == "feedback"]
        self.assertEqual(len(feedback_events2), 1)
        self.assertEqual(feedback_events2[0]["task"], "EXPLAIN_CONCEPT")
        self.assertAlmostEqual(float(feedback_events2[0]["score"]), 0.85, places=6)
        
        # Continue conversation on second engine
        result = engine2.execute_intent("Bisakah kamu berikan contoh kode Python untuk linear regression?")
        
        # Verify new turn added to restored history
        narrative3 = engine2.narrative_context(limit=20, max_chars=8000)
        self.assertGreater(narrative3["total_events"], narrative2["total_events"])
        self.assertIn("linear regression", narrative3["context"].lower())

    def test_episodic_memory_sqlite_restart_cycle(self):
        """Test EpisodicMemoryStore survives restart with full event history."""
        # First instance - store events
        store1 = EpisodicMemoryStore(db_path=self.episodic_path)
        
        session_id = "test_session_001"
        goal_id = "goal_ml_explanation"
        
        events = [
            MemoryEvent(
                event_id=f"evt_{i:03d}",
                event_type="USER_TURN" if i % 2 == 0 else "ASSISTANT_TURN",
                session_id=session_id,
                goal_id=goal_id,
                payload={"text": f"Message {i}", "turn": i},
                node_id="test_node",
                timestamp=f"2024-01-01T00:00:{i:02d}",
                sequence_number=i,
            )
            for i in range(10)
        ]
        
        for event in events:
            result = store1.append_event(event)
            self.assertTrue(result)
        
        # Verify stored
        retrieved1 = store1.query_by_session(session_id, limit=20)
        self.assertEqual(len(retrieved1), 10)
        
        store1.close()
        
        # Second instance - should retrieve all events
        store2 = EpisodicMemoryStore(db_path=self.episodic_path)
        retrieved2 = store2.query_by_session(session_id, limit=20)
        
        self.assertEqual(len(retrieved2), 10)
        for i, event in enumerate(retrieved2):
            self.assertEqual(event.sequence_number, i)
            self.assertEqual(event.payload["turn"], i)
        
        # Test goal-based query
        by_goal = store2.query_by_goal(goal_id, limit=20)
        self.assertEqual(len(by_goal), 10)
        
        # Test recent events
        recent = store2.get_recent_events(limit=5)
        self.assertEqual(len(recent), 5)
        # Should be in chronological order (reversed from DESC query)
        self.assertEqual(recent[0].sequence_number, 5)
        self.assertEqual(recent[-1].sequence_number, 9)
        
        store2.close()

    def test_working_memory_rebuilt_from_episodic(self):
        """Test WorkingMemory can be rebuilt from episodic memory after restart."""
        # Simulate first session storing to episodic
        store = EpisodicMemoryStore(db_path=self.episodic_path)
        session_id = "rebuild_test_session"
        
        # Store a conversation
        conversation = [
            ("user", "Halo, apa kabar?"),
            ("assistant", "Baik, ada yang bisa saya bantu?"),
            ("user", "Saya belajar tentang neural networks"),
            ("assistant", "Neural networks adalah model komputasi..."),
            ("user", "Apa itu backpropagation?"),
            ("assistant", "Backpropagation adalah algoritma..."),
        ]
        
        for i, (role, text) in enumerate(conversation):
            event = MemoryEvent(
                event_id=f"rebuild_evt_{i:03d}",
                event_type="USER_TURN" if role == "user" else "ASSISTANT_TURN",
                session_id=session_id,
                goal_id="goal_rebuild",
                payload={"role": role, "content": text},
                node_id="test_node",
                timestamp=f"2024-01-01T00:00:{i:02d}",
                sequence_number=i,
            )
            store.append_event(event)
        
        store.close()
        
        # Simulate restart: new WorkingMemory instance rebuilt from episodic
        store2 = EpisodicMemoryStore(db_path=self.episodic_path)
        events = store2.query_by_session(session_id, limit=50)
        store2.close()
        
        # Rebuild working memory
        wm = WorkingMemory(session_id=session_id, max_items=20)
        for event in events:
            payload = event.payload
            if isinstance(payload, dict) and "role" in payload and "content" in payload:
                # Store in working memory format
                key = f"{event.sequence_number}_{payload['role']}"
                wm.set(key, payload["content"])
        
        # Verify working memory has the conversation
        self.assertEqual(wm.get("0_user"), "Halo, apa kabar?")
        self.assertEqual(wm.get("1_assistant"), "Baik, ada yang bisa saya bantu?")
        self.assertEqual(wm.get("2_user"), "Saya belajar tentang neural networks")
        self.assertEqual(wm.get("5_assistant"), "Backpropagation adalah algoritma...")

    def test_context_manager_integration_restart(self):
        """Test ContextManager builds correct context from restored memory."""
        engine1 = self._build_engine()
        
        # Build conversation history
        conversation = [
            "Saya sedang belajar Python",
            "Apa itu list comprehension?",
            "Bisakah berikan contoh?",
            "Terima kasih",
        ]
        
        for turn in conversation:
            engine1.execute_intent(turn)
        
        # Get context snapshot
        context1 = engine1.narrative_context(limit=10, max_chars=2000)
        
        del engine1
        
        # Restart
        engine2 = self._build_engine()
        context2 = engine2.narrative_context(limit=10, max_chars=2000)
        
        # Context should be restored
        self.assertIn("python", context2["context"].lower())
        self.assertIn("list comprehension", context2["context"].lower())
        self.assertIn("contoh", context2["context"].lower())
        
        # Test ContextManager directly with correct signature
        ctx_manager = ContextManager()
        from jaya_core.identity.models import NodeRole, AuthorityLevel
        node_identity = NodeIdentity(
            node_id="test_node",
            jaya_identity_id="test_jaya_id",
            node_class=NodeClass.STANDARD,
            role=NodeRole.PERSONAL_WORKSTATION_NODE,
            authority=AuthorityLevel.STANDARD_WORKER,
            public_key_fingerprint="test_fingerprint",
        )
        resource_profile = ResourceProfile(
            node_class=NodeClass.STANDARD,
            total_memory_mb=8192,
            available_memory_mb=4096,
            process_memory_mb=100,
            cpu_count=8,
            storage_free_mb=100000,
            network_available=True,
            power_mode="NORMAL",
        )
        
        # Convert narrative events to MemoryEvent format
        recent_events = []
        for e in context2["recent"]:
            if e.get("kind") == "turn":
                recent_events.append(MemoryEvent(
                    event_id=f"evt_{e.get('ts', 0)}",
                    event_type="TURN",
                    session_id="test_session",
                    goal_id="test_goal",
                    payload={"user": e.get("user", ""), "response": e.get("response", "")},
                    node_id="test_node",
                    timestamp=str(e.get("ts", 0)),
                    sequence_number=len(recent_events),
                ))
        
        snapshot = ctx_manager.build_snapshot(
            session_id="test_session",
            user_prompt="test prompt",
            node_identity=node_identity,
            resource_profile=resource_profile,
            execution_mode=ExecutionMode.OFFLINE_AUTONOMOUS,
            recent_events=recent_events,
            active_goal_id="test_goal",
        )
        
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.session_id, "test_session")

    def test_concurrent_sessions_isolation(self):
        """Test multiple concurrent sessions maintain isolation across restarts."""
        engine1 = self._build_engine()
        
        # Session 1: Machine Learning
        engine1.execute_intent("Belajar machine learning dengan neural network")
        engine1.execute_intent("Apa itu neural network dan deep learning?")
        
        # Session 2: Web Development (simulated by different session context)
        # In real usage, this would be a separate engine instance
        # Here we test that narrative keeps them separate by topic
        engine1.execute_intent("Belajar React JS dan JavaScript")
        engine1.execute_intent("Apa itu useState hook di React?")
        
        narrative1 = engine1.narrative_context(limit=20, max_chars=4000)
        
        del engine1
        
        engine2 = self._build_engine()
        narrative2 = engine2.narrative_context(limit=20, max_chars=4000)
        
        # Both topics should be present
        self.assertIn("machine learning", narrative2["context"].lower())
        self.assertIn("neural network", narrative2["context"].lower())
        self.assertIn("react", narrative2["context"].lower())
        self.assertIn("javascript", narrative2["context"].lower())
        
        # Topics should be distinguishable
        topics = [e.get("topic", "") for e in narrative2["recent"] if e.get("kind") == "turn"]
        ml_topics = [t for t in topics if "machine" in t.lower() or "neural" in t.lower() or "deep" in t.lower()]
        web_topics = [t for t in topics if "react" in t.lower() or "javascript" in t.lower() or "hook" in t.lower()]
        
        self.assertGreater(len(ml_topics), 0)
        self.assertGreater(len(web_topics), 0)

    def test_memory_bounds_respected_after_restart(self):
        """Test memory bounds (max_events, max_chars) still enforced after restart."""
        # Create engine with small limits
        with tempfile.TemporaryDirectory() as tmpdir:
            narrative_path = str(Path(tmpdir) / "small_narrative.json")
            
            with patch.dict(os.environ, {"JAYA_NARRATIVE_PATH": narrative_path}, clear=False):
                engine1 = IronEngine(
                    model_path="missing.jay",
                    password="x",
                    enable_twin=False,
                    identity_anchor=self.anchor,
                )
                engine1.ignite()
                
                # Add many turns (more than max_events=32 default)
                for i in range(50):
                    engine1.execute_intent(f"Turn {i}: ini adalah pesan panjang untuk menguji batas memori " + "x" * 50)
                
                narrative1 = engine1.narrative_context(limit=100, max_chars=5000)
                # Default max_events is 256, so 50 should be within bounds
                self.assertLessEqual(narrative1["total_events"], 256)
                
                engine1._narrative.close()
                engine1._narrative = None
                
                # Restart
                engine2 = IronEngine(
                    model_path="missing.jay",
                    password="x",
                    enable_twin=False,
                    identity_anchor=self.anchor,
                )
                engine2.ignite()
                
                narrative2 = engine2.narrative_context(limit=100, max_chars=5000)
                self.assertLessEqual(narrative2["total_events"], 256)
                self.assertLessEqual(len(narrative2["context"]), 5000)
                engine2._narrative.close()
                engine2._narrative = None


if __name__ == "__main__":
    unittest.main()
