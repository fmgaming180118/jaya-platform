"""
test_fase5_agentic_jarvis.py — Unit tests for AgenticJarvis (Fase 5 JAYA_CORE)

Tests cover:
  - HierarchicalTaskPlanner: create goal, domain-neutral decomposition, thesis via strategy
  - ProactiveEngine: deadline alerts, context nudges (domain-neutral), subtask reminders
  - AgenticLoopController: ambiguity detection & destructive action confirmation
  - KnowledgeDeltaBuilder: knowledge candidate creation (tidak mengembalikan 'applied')
  - JarvisAgentFacade: full process_input_gate & proactive integration

Mission boundary yang diverifikasi:
  - Generic goal dapat dipecah tanpa konteks thesis
  - KnowledgeDeltaBuilder mengembalikan INDEXED_IN_RESEARCH_STORE, bukan 'applied'
  - ProactiveEngine menerima active_contexts (domain-neutral), bukan thesis_topic/current_chapter
  - Thesis template tersedia via strategy, tidak hardcoded di Core
"""

import sys
import sqlite3
import pytest
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
jaya_core_dir = repo_root / "JAYA_CORE"
sys.path.insert(0, str(jaya_core_dir))

from src.brain_v2.soul.agentic_jarvis import (
    HierarchicalTaskPlanner,
    ProactiveEngine,
    AgenticLoopController,
    KnowledgeDeltaBuilder,
    ArXivPatchEngine,  # backward-compat alias — deprecated
    JarvisAgentFacade,
    GoalPlan,
    SubTask,
    ThesisGoalDecompositionStrategy,
)


@pytest.fixture
def tmp_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def tmp_facade(tmp_path):
    db_path = str(tmp_path / "test_jarvis.db")
    facade = JarvisAgentFacade(db_path=db_path)
    yield facade


class TestHierarchicalTaskPlanner:
    def test_create_goal_and_subtasks_thesis_via_strategy(self, tmp_conn):
        """Thesis subtasks tersedia karena ThesisGoalDecompositionStrategy didaftarkan."""
        planner = HierarchicalTaskPlanner(tmp_conn)
        plan = planner.create_goal("Selesaikan BAB III Skripsi", domain="thesis")
        assert plan.goal_title == "Selesaikan BAB III Skripsi"
        assert len(plan.subtasks) >= 3
        assert plan.progress_pct() == 0.0

    def test_generic_goal_decomposed_without_thesis_context(self, tmp_conn):
        """Mission boundary: generic goal HARUS dapat dipecah tanpa konteks thesis."""
        planner = HierarchicalTaskPlanner(tmp_conn)
        plan = planner.create_goal(
            "Analisis dampak perubahan iklim terhadap ketahanan pangan",
            domain="general",
        )
        assert plan.goal_title is not None
        assert len(plan.subtasks) >= 1
        # Pastikan sub-tasks tidak mengandung frasa spesifik thesis
        for st in plan.subtasks:
            assert "bab" not in st.title.lower()
            assert "skripsi" not in st.title.lower()

    def test_generic_goal_without_any_strategy_still_works(self, tmp_conn):
        """Core planner harus bekerja bahkan tanpa strategi apapun didaftarkan."""
        planner = HierarchicalTaskPlanner(tmp_conn, strategies=[])  # kosong
        plan = planner.create_goal("Tugas tanpa domain khusus", domain="general")
        assert len(plan.subtasks) >= 1

    def test_update_subtask_status(self, tmp_conn):
        planner = HierarchicalTaskPlanner(tmp_conn)
        plan = planner.create_goal("Koding Module Retrofit", domain="code")
        first_st = plan.subtasks[0]
        success = planner.update_subtask_status(first_st.task_id, "completed")
        assert success is True

    def test_get_active_goals(self, tmp_conn):
        planner = HierarchicalTaskPlanner(tmp_conn)
        planner.create_goal("Goal 1")
        active = planner.get_active_goals()
        assert len(active) == 1


class TestProactiveEngine:
    def test_deadline_alert(self, tmp_conn):
        pe = ProactiveEngine(tmp_conn)
        deadlines = [{"task": "Submit BAB I", "date": "25 Juli 2026"}]
        alert = pe.check_proactive_nudge(user_name="Bos", deadlines=deadlines)
        assert alert is not None
        assert alert.alert_type == "deadline"
        assert "Submit BAB I" in alert.message

    def test_context_nudge_domain_neutral(self, tmp_conn):
        """Mission boundary: ProactiveEngine menggunakan active_contexts (domain-neutral)."""
        pe = ProactiveEngine(tmp_conn)
        alert = pe.check_proactive_nudge(
            user_name="Bos",
            active_contexts={
                "domain": "thesis",
                "topic": "Federated Learning",
                "current_task": "BAB III",
            },
        )
        assert alert is not None
        assert alert.alert_type == "context_nudge"  # bukan thesis_nudge
        assert "BAB III" in alert.message
        assert "Federated Learning" in alert.message

    def test_context_nudge_works_for_any_domain(self, tmp_conn):
        """ProactiveEngine harus bekerja untuk domain selain thesis."""
        pe = ProactiveEngine(tmp_conn)
        alert = pe.check_proactive_nudge(
            user_name="Bos",
            active_contexts={
                "domain": "home_automation",
                "topic": "smart lighting",
                "current_task": "konfigurasi sensor",
            },
        )
        assert alert is not None
        assert alert.alert_type == "context_nudge"
        assert "smart lighting" in alert.message

    def test_no_nudge_without_trigger(self, tmp_conn):
        pe = ProactiveEngine(tmp_conn)
        alert = pe.check_proactive_nudge(user_name="Bos")
        assert alert is None


class TestAgenticLoopController:
    def test_destructive_confirmation(self):
        controller = AgenticLoopController()
        is_amb, is_dest, msg = controller.evaluate_intent("hapus semua data skripsi")
        assert is_dest is True
        assert "Konfirmasi Keamanan" in msg

    def test_ambiguous_short_prompt(self):
        controller = AgenticLoopController()
        is_amb, is_dest, msg = controller.evaluate_intent("bantu")
        assert is_amb is True
        assert "jelaskan detail" in msg

    def test_clear_prompt_passes(self):
        controller = AgenticLoopController()
        is_amb, is_dest, msg = controller.evaluate_intent("jelaskan metode federated learning pada iot")
        assert is_amb is False
        assert is_dest is False


class TestKnowledgeDeltaBuilder:
    def test_create_knowledge_delta_candidate_returns_indexed_status(self):
        """Mission boundary: status harus INDEXED_IN_RESEARCH_STORE, bukan 'applied'."""
        builder = KnowledgeDeltaBuilder()
        res = builder.create_knowledge_delta_candidate("Federated Learning v2", "Konten riset baru.")
        # Pastikan tidak mengembalikan 'applied' atau 'deployed'
        assert res["status"] == "INDEXED_IN_RESEARCH_STORE"
        assert res["status"] != "applied"
        assert res["status"] != "deployed"
        assert res["executable"] is False
        assert res["auto_installed"] is False
        assert res["human_review_required"] is True
        assert "kdelta_" in res["candidate_id"]

    def test_create_knowledge_delta_target_is_research_not_core(self):
        """Mission boundary: target adalah JAYA_RESEARCH_RAG, bukan JAYA_CORE."""
        builder = KnowledgeDeltaBuilder()
        res = builder.create_knowledge_delta_candidate("Paper X", "Content")
        assert res["target"] == "JAYA_RESEARCH_RAG"
        assert "JAYA_CORE" not in res["target"]


class TestArXivPatchEngineBackwardCompat:
    def test_deprecated_apply_micro_patch_still_works(self):
        """Backward compat: apply_micro_patch masih ada tapi mengembalikan status baru."""
        import warnings
        engine = ArXivPatchEngine()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = engine.apply_micro_patch("Federated Learning v2", "Konten riset baru.")
            # Harus mengeluarkan DeprecationWarning
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)
        # Status baru: bukan 'applied'
        assert res["status"] == "INDEXED_IN_RESEARCH_STORE"
        assert res["status"] != "applied"
        assert "patch_id" in res  # backward compat key


class TestJarvisAgentFacade:
    def test_input_gate_intercepts_destructive(self, tmp_facade):
        intercept, msg = tmp_facade.process_input_gate("drop table database")
        assert intercept is True
        assert "Konfirmasi Keamanan" in msg

    def test_input_gate_allows_normal(self, tmp_facade):
        intercept, msg = tmp_facade.process_input_gate("apa itu federated learning?")
        assert intercept is False

    def test_status(self, tmp_facade):
        st = tmp_facade.status()
        assert "active_goals_count" in st

    def test_get_proactive_nudge_with_domain_neutral_contexts(self, tmp_facade):
        """Facade menggunakan active_contexts (domain-neutral), bukan thesis_topic."""
        msg = tmp_facade.get_proactive_nudge_if_any(
            user_name="Bos",
            active_contexts={"domain": "research", "topic": "AI safety", "current_task": "literature review"},
        )
        assert msg is not None
        assert "AI safety" in msg

    def test_knowledge_delta_is_accessible_from_facade(self, tmp_facade):
        """Facade menyediakan knowledge_delta builder (bukan arxiv_patch untuk operasional baru)."""
        assert hasattr(tmp_facade, "knowledge_delta")
        res = tmp_facade.knowledge_delta.create_knowledge_delta_candidate("Test Paper", "Content")
        assert res["status"] == "INDEXED_IN_RESEARCH_STORE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
