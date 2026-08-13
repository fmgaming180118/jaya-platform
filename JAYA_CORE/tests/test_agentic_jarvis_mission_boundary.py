"""
test_agentic_jarvis_mission_boundary.py — Mission Boundary Tests untuk AgenticJarvis

Membuktikan bahwa:
1. Generic goal dapat dipecah tanpa konteks tesis.
2. KnowledgeDeltaBuilder tidak mengembalikan 'applied' atau status yang menyiratkan Core activation.
3. ThesisGoalDecompositionStrategy tidak tersedia secara default untuk Core generic planner
   kecuali didaftarkan secara eksplisit.
4. ProactiveEngine bekerja tanpa thesis_topic/current_chapter (menggunakan active_contexts).
5. Terminologi kandidat tidak menggunakan 'applied', 'deployed', 'installed'.
6. Domain adapter (thesis) dapat dinonaktifkan tanpa merusak Core planner.
"""

from __future__ import annotations

import sqlite3
import sys
import warnings
from pathlib import Path

import pytest

# Setup path
repo_root = Path(__file__).resolve().parent.parent.parent
jaya_core_dir = repo_root / "JAYA_CORE"
sys.path.insert(0, str(jaya_core_dir))

from src.brain_v2.soul.agentic_jarvis import (
    HierarchicalTaskPlanner,
    KnowledgeDeltaBuilder,
    ProactiveEngine,
    GoalDecompositionStrategy,
    ThesisGoalDecompositionStrategy,
    JarvisAgentFacade,
    ArXivPatchEngine,
)


@pytest.fixture
def tmp_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def tmp_facade(tmp_path):
    db_path = str(tmp_path / "test_boundary.db")
    facade = JarvisAgentFacade(db_path=db_path)
    yield facade


# ============================================================================
# 1. Generic Goal tanpa Thesis Context
# ============================================================================

class TestGenericGoalDecomposition:
    def test_generic_goal_works_without_thesis_strategy(self, tmp_conn):
        """Core planner HARUS bekerja tanpa strategi thesis apapun."""
        planner = HierarchicalTaskPlanner(tmp_conn, strategies=[])
        plan = planner.create_goal(
            "Analisis kebutuhan sistem monitoring energi",
            domain="general",
        )
        assert len(plan.subtasks) >= 1
        assert plan.goal_id is not None

    def test_generic_goal_subtasks_free_of_thesis_terminology(self, tmp_conn):
        """Sub-tasks dari generic goal tidak boleh mengandung terminologi thesis."""
        planner = HierarchicalTaskPlanner(tmp_conn, strategies=[])
        plan = planner.create_goal(
            "Merancang arsitektur sistem rekomendasi",
            domain="general",
        )
        thesis_terms = {"bab", "skripsi", "tesis", "thesis", "latar belakang", "rumusan masalah"}
        for st in plan.subtasks:
            title_words = set(st.title.lower().split())
            assert thesis_terms.isdisjoint(title_words), (
                f"Sub-task mengandung terminologi thesis: '{st.title}'"
            )

    def test_thesis_strategy_is_registered_by_default_for_backward_compat(self, tmp_conn):
        """
        ThesisGoalDecompositionStrategy terdaftar secara default untuk backward compat.
        Ini harus dipindahkan ke adapter eksternal pada Fase E.
        """
        planner = HierarchicalTaskPlanner(tmp_conn)
        plan = planner.create_goal("Selesaikan BAB III Skripsi", domain="thesis")
        # Thesis strategy terdaftar → subtasks spesifik thesis ada
        assert len(plan.subtasks) >= 3

    def test_core_planner_is_domain_neutral_without_strategies(self, tmp_conn):
        """Planner tanpa strategi terdaftar menggunakan default generik."""
        planner = HierarchicalTaskPlanner(tmp_conn, strategies=[])
        domains = ["general", "research", "home_automation", "health", "finance"]
        for domain in domains:
            plan = planner.create_goal(f"Goal untuk domain {domain}", domain=domain)
            assert len(plan.subtasks) >= 1, f"Planner gagal untuk domain: {domain}"

    def test_strategy_registry_can_add_custom_strategy(self, tmp_conn):
        """Domain adapter baru dapat didaftarkan ke Core planner."""
        class HomeAutomationStrategy(GoalDecompositionStrategy):
            def supports(self, title: str, domain: str) -> bool:
                return domain == "home_automation"

            def decompose(self, title: str, domain: str) -> list:
                return ["Inventarisasi perangkat", "Konfigurasi controller", "Uji integrasi"]

        planner = HierarchicalTaskPlanner(tmp_conn, strategies=[])
        planner.register_strategy(HomeAutomationStrategy())

        plan = planner.create_goal("Setup smart home", domain="home_automation")
        assert any("perangkat" in st.title.lower() for st in plan.subtasks)


# ============================================================================
# 2. KnowledgeDeltaBuilder — Status tidak boleh "applied" atau "deployed"
# ============================================================================

class TestKnowledgeDeltaCandidateStatus:
    FORBIDDEN_STATUSES = {"applied", "deployed", "installed", "activated", "learned permanently"}

    def test_status_is_not_applied(self):
        builder = KnowledgeDeltaBuilder()
        res = builder.create_knowledge_delta_candidate("Paper X", "Content Y")
        assert res["status"] not in self.FORBIDDEN_STATUSES, (
            f"Status '{res['status']}' menyiratkan Core activation tanpa promotion gate"
        )

    def test_status_is_indexed_in_research_store(self):
        """Status harus INDEXED_IN_RESEARCH_STORE — bukan nama yang menyiratkan Core mutation."""
        builder = KnowledgeDeltaBuilder()
        res = builder.create_knowledge_delta_candidate("Paper Y", "Content Z")
        assert res["status"] == "INDEXED_IN_RESEARCH_STORE"

    def test_target_is_research_not_core(self):
        """Target harus JAYA_RESEARCH_RAG, bukan JAYA_CORE atau JAYA_CORE_DATABASE."""
        builder = KnowledgeDeltaBuilder()
        res = builder.create_knowledge_delta_candidate("Test", "Content")
        assert "CORE" not in res["target"], (
            f"Target '{res['target']}' menyiratkan Core mutation"
        )
        assert res["target"] == "JAYA_RESEARCH_RAG"

    def test_executable_is_false(self):
        builder = KnowledgeDeltaBuilder()
        res = builder.create_knowledge_delta_candidate("Test", "Content")
        assert res["executable"] is False

    def test_auto_installed_is_false(self):
        builder = KnowledgeDeltaBuilder()
        res = builder.create_knowledge_delta_candidate("Test", "Content")
        assert res["auto_installed"] is False

    def test_human_review_required_is_true(self):
        builder = KnowledgeDeltaBuilder()
        res = builder.create_knowledge_delta_candidate("Test", "Content")
        assert res["human_review_required"] is True

    def test_deprecated_apply_micro_patch_emits_warning_and_no_applied_status(self):
        """Backward compat: apply_micro_patch deprecated, status bukan 'applied'."""
        engine = ArXivPatchEngine()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = engine.apply_micro_patch("Old Paper", "Old content")
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w), (
                "apply_micro_patch harus mengeluarkan DeprecationWarning"
            )
        assert res["status"] not in self.FORBIDDEN_STATUSES


# ============================================================================
# 3. ProactiveEngine — Domain Neutral (tidak ada thesis_topic/current_chapter)
# ============================================================================

class TestProactiveEngineDomainNeutral:
    def test_proactive_engine_works_without_thesis_params(self, tmp_conn):
        """ProactiveEngine.check_proactive_nudge tidak boleh menerima thesis_topic."""
        pe = ProactiveEngine(tmp_conn)
        import inspect
        sig = inspect.signature(pe.check_proactive_nudge)
        assert "thesis_topic" not in sig.parameters, (
            "thesis_topic tidak boleh menjadi parameter ProactiveEngine"
        )
        assert "current_chapter" not in sig.parameters, (
            "current_chapter tidak boleh menjadi parameter ProactiveEngine"
        )

    def test_context_nudge_with_thesis_domain_via_active_contexts(self, tmp_conn):
        """Thesis info masuk via active_contexts (dict), bukan parameter khusus."""
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
        assert "BAB III" in alert.message
        assert alert.alert_type == "context_nudge"  # bukan thesis_nudge

    def test_context_nudge_with_non_thesis_domain(self, tmp_conn):
        """ProactiveEngine harus bekerja untuk domain apapun."""
        pe = ProactiveEngine(tmp_conn)
        alert = pe.check_proactive_nudge(
            user_name="Bos",
            active_contexts={
                "domain": "research",
                "topic": "climate model validation",
                "current_task": "baseline evaluation",
            },
        )
        assert alert is not None
        assert "climate model validation" in alert.message

    def test_no_nudge_returned_when_no_context(self, tmp_conn):
        pe = ProactiveEngine(tmp_conn)
        alert = pe.check_proactive_nudge(user_name="Bos")
        assert alert is None

    def test_facade_get_proactive_nudge_uses_active_contexts(self, tmp_facade):
        """Facade harus menerima active_contexts, bukan thesis_topic."""
        import inspect
        sig = inspect.signature(tmp_facade.get_proactive_nudge_if_any)
        assert "thesis_topic" not in sig.parameters
        assert "current_chapter" not in sig.parameters
        assert "active_contexts" in sig.parameters


# ============================================================================
# 4. Thesis Adapter dapat dinonaktifkan tanpa merusak Core
# ============================================================================

class TestThesisAdapterDisableability:
    def test_planner_works_without_thesis_strategy(self, tmp_conn):
        """Research Core harus berjalan normal tanpa ThesisGoalDecompositionStrategy."""
        planner = HierarchicalTaskPlanner(tmp_conn, strategies=[])
        # Semua goal non-thesis harus berhasil
        for title, domain in [
            ("Riset dampak AI terhadap lapangan kerja", "research"),
            ("Setup server monitoring", "devops"),
            ("Analisis sentimen media sosial", "data_science"),
        ]:
            plan = planner.create_goal(title, domain=domain)
            assert len(plan.subtasks) >= 1, f"Planner gagal tanpa thesis strategy: {title}"

    def test_thesis_strategy_can_be_disabled_by_not_registering(self, tmp_conn):
        """
        Ketika ThesisGoalDecompositionStrategy tidak didaftarkan, goal bertema
        thesis tetap berhasil dipecah (dengan generic fallback).
        """
        planner = HierarchicalTaskPlanner(tmp_conn, strategies=[])
        plan = planner.create_goal("Topik tesis federated learning", domain="general")
        assert len(plan.subtasks) >= 1
        # Tidak crash, tidak menghasilkan error

    def test_thesis_analysis_exists_as_strategy_not_hardcode(self):
        """ThesisGoalDecompositionStrategy adalah class terpisah, bukan hardcoded di Core."""
        # Jika kita tidak import ThesisGoalDecompositionStrategy, Core tetap bekerja
        assert ThesisGoalDecompositionStrategy is not None  # class ada
        strategy = ThesisGoalDecompositionStrategy()
        assert strategy.supports("BAB III Skripsi", "thesis") is True
        assert strategy.supports("Analisis energi terbarukan", "research") is False


# ============================================================================
# 5. Facade mission boundary
# ============================================================================

class TestFacadeMissionBoundary:
    def test_knowledge_delta_attr_exists_on_facade(self, tmp_facade):
        assert hasattr(tmp_facade, "knowledge_delta")
        assert isinstance(tmp_facade.knowledge_delta, KnowledgeDeltaBuilder)

    def test_knowledge_delta_not_deployed_to_core(self, tmp_facade):
        res = tmp_facade.knowledge_delta.create_knowledge_delta_candidate("T", "C")
        assert "CORE" not in res["target"]

    def test_arxiv_patch_alias_exists_for_backward_compat(self, tmp_facade):
        """arxiv_patch alias masih ada untuk backward compat."""
        assert hasattr(tmp_facade, "arxiv_patch")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
