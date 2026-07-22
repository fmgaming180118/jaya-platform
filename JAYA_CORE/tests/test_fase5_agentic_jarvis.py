"""
test_fase5_agentic_jarvis.py — Unit tests for AgenticJarvis (Fase 5 JAYA_CORE)

Tests cover:
  - HierarchicalTaskPlanner: create goal, autogenerate subtasks, status update
  - ProactiveEngine: deadline alerts, thesis nudges, subtask reminders
  - AgenticLoopController: ambiguity detection & destructive action confirmation
  - ArXivPatchEngine: micro-delta patching
  - JarvisAgentFacade: full process_input_gate & proactive integration
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
    ArXivPatchEngine,
    JarvisAgentFacade,
    GoalPlan,
    SubTask,
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
    def test_create_goal_and_subtasks(self, tmp_conn):
        planner = HierarchicalTaskPlanner(tmp_conn)
        plan = planner.create_goal("Selesaikan BAB III Skripsi", domain="thesis")
        assert plan.goal_title == "Selesaikan BAB III Skripsi"
        assert len(plan.subtasks) >= 3
        assert plan.progress_pct() == 0.0

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

    def test_thesis_nudge(self, tmp_conn):
        pe = ProactiveEngine(tmp_conn)
        alert = pe.check_proactive_nudge(user_name="Bos", thesis_topic="Federated Learning", current_chapter="BAB III")
        assert alert is not None
        assert alert.alert_type == "thesis_nudge"
        assert "BAB III" in alert.message


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


class TestArXivPatchEngine:
    def test_apply_micro_patch(self):
        engine = ArXivPatchEngine()
        res = engine.apply_micro_patch("Federated Learning v2", "Konten riset baru.")
        assert res["status"] == "applied"
        assert "arxiv_" in res["patch_id"]


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
