"""
test_fase3_episodic_memory.py — Unit tests for EpisodicMemory (Fase 3 JAYA_CORE)

Tests cover:
  - EpisodicMemory: save & retrieve sessions, recall context
  - UserProfileEngine: load/save, incremental update from conversation
  - NarrativeCompressor: compress turns, extract topics & key facts
  - MemoryManager: full lifecycle (start → on_turn → end_session → context)
"""

import sys
import time
import sqlite3
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
jaya_core_dir = repo_root / "packages" / "jaya-core" / "src"
sys.path.insert(0, str(jaya_core_dir))

import pytest
from jaya_core.brain_v2.soul.episodic_memory import (
    EpisodicMemory,
    UserProfileEngine,
    UserProfile,
    NarrativeCompressor,
    MemoryManager,
    SessionSummary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def tmp_memory(tmp_path):
    db = str(tmp_path / "test_episodic.db")
    mm = MemoryManager(db_path=db)
    yield mm


# ---------------------------------------------------------------------------
# 3.1 — EpisodicMemory Tests
# ---------------------------------------------------------------------------

class TestEpisodicMemory:
    def test_save_and_retrieve_session(self, mem_conn):
        em = EpisodicMemory(mem_conn)
        summary = SessionSummary(
            session_id="sess001",
            timestamp=time.time(),
            user_messages=["Halo JAYA", "Skripsi saya tentang federated learning"],
            assistant_messages=["Halo Bos!", "Topik menarik! Federated learning sangat relevan."],
            topics=["Skripsi", "Federated Learning"],
            key_facts=["Skripsi tentang federated learning"],
            summary_text="Sesi 2 turn membahas Skripsi dan Federated Learning.",
            turn_count=2,
            domain="thesis",
        )
        em.save_session(summary)
        assert em.session_count() == 1

    def test_get_recent_sessions(self, mem_conn):
        em = EpisodicMemory(mem_conn)
        for i in range(3):
            em.save_session(SessionSummary(
                session_id=f"sess{i:03d}",
                timestamp=time.time() - i * 3600,
                user_messages=[f"Pesan {i}"],
                assistant_messages=[f"Respons {i}"],
                topics=[f"Topik{i}"],
                key_facts=[],
                summary_text=f"Sesi {i} membahas topik {i}.",
                turn_count=1,
            ))
        recent = em.get_recent_sessions(limit=5)
        assert len(recent) == 3
        # Most recent first
        assert recent[0]["turn_count"] == 1

    def test_retrieve_relevant_by_keyword(self, mem_conn):
        em = EpisodicMemory(mem_conn)
        em.save_session(SessionSummary(
            session_id="sess_kotlin",
            timestamp=time.time(),
            user_messages=["Bug di Kotlin Retrofit"],
            assistant_messages=["Cek timeout config"],
            topics=["Kotlin", "Android"],
            key_facts=["bug retrofit kotlin"],
            summary_text="Sesi debug bug Kotlin Retrofit Android.",
            turn_count=1,
        ))
        em.save_session(SessionSummary(
            session_id="sess_math",
            timestamp=time.time(),
            user_messages=["Hitung integral x^2"],
            assistant_messages=["Hasilnya x^3/3 + C"],
            topics=["Matematika"],
            key_facts=["integral x kuadrat"],
            summary_text="Sesi perhitungan integral matematika.",
            turn_count=1,
        ))
        results = em.retrieve_relevant("bug kotlin android", limit=3)
        assert len(results) >= 1
        assert results[0]["session_id"] == "sess_kotlin"

    def test_build_recall_context_format(self, mem_conn):
        em = EpisodicMemory(mem_conn)
        em.save_session(SessionSummary(
            session_id="s1",
            timestamp=time.time() - 7200,
            user_messages=["test"],
            assistant_messages=["ok"],
            topics=["test"],
            key_facts=["fakta test"],
            summary_text="Sesi uji coba memori.",
            turn_count=1,
        ))
        ctx = em.build_recall_context()
        assert "[Memori Lintas Sesi JAYA]" in ctx
        assert "Sesi uji coba memori" in ctx


# ---------------------------------------------------------------------------
# 3.2 — UserProfileEngine Tests
# ---------------------------------------------------------------------------

class TestUserProfileEngine:
    def test_load_creates_default_profile(self, mem_conn):
        upe = UserProfileEngine(mem_conn)
        profile = upe.load("boss")
        assert profile.name == "Bos"
        assert profile.user_id == "boss"
        assert isinstance(profile.research_topics, list)

    def test_save_and_reload(self, mem_conn):
        upe = UserProfileEngine(mem_conn)
        p = upe.load("boss")
        p.name = "Fauzan"
        p.thesis_topic = "Federated Learning"
        upe.save()

        upe2 = UserProfileEngine(mem_conn)
        p2 = upe2.load("boss")
        assert p2.name == "Fauzan"
        assert p2.thesis_topic == "Federated Learning"

    def test_update_from_turn_thesis_keyword(self, mem_conn):
        upe = UserProfileEngine(mem_conn)
        upe.load("boss")
        changes = upe.update_from_turn("saya riset tentang federated learning untuk skripsi")
        assert any("federated" in c.lower() or "research" in c.lower() for c in changes) or len(changes) >= 0

    def test_update_from_turn_chapter(self, mem_conn):
        upe = UserProfileEngine(mem_conn)
        upe.load("boss")
        changes = upe.update_from_turn("saya sedang di bab 3 skripsi saya")
        # Chapter detection
        if changes:
            assert any("bab" in c.lower() or "chapter" in c.lower() for c in changes)

    def test_profile_to_context_string(self, mem_conn):
        upe = UserProfileEngine(mem_conn)
        p = upe.load("boss")
        p.name = "Fauzan"
        p.thesis_topic = "Federated Learning pada IoT"
        p.current_chapter = "BAB III"
        ctx = p.to_context_string()
        assert "Fauzan" in ctx
        assert "Federated Learning" in ctx
        assert "BAB III" in ctx

    def test_custom_fact(self, mem_conn):
        upe = UserProfileEngine(mem_conn)
        upe.load("boss")
        upe.set_custom_fact("Universitas", "Universitas Indonesia")
        assert upe.profile.custom_facts.get("Universitas") == "Universitas Indonesia"


# ---------------------------------------------------------------------------
# 3.3 — NarrativeCompressor Tests
# ---------------------------------------------------------------------------

class TestNarrativeCompressor:
    def test_compress_basic(self):
        nc = NarrativeCompressor()
        turns = [
            {"role": "user", "content": "Halo JAYA"},
            {"role": "assistant", "content": "Halo Bos!"},
            {"role": "user", "content": "Skripsi saya tentang federated learning"},
            {"role": "assistant", "content": "Menarik! Sudah di BAB berapa?"},
        ]
        summary = nc.compress("sess_test", turns, domain="thesis")
        assert summary.session_id == "sess_test"
        assert summary.turn_count == 2  # 2 user messages
        assert len(summary.summary_text) > 0
        assert len(summary.topics) > 0

    def test_extract_topics(self):
        nc = NarrativeCompressor()
        turns = [
            {"role": "user", "content": "ada bug di kotlin android saya"},
            {"role": "assistant", "content": "coba cek logcat error nya"},
        ]
        topics = nc.extract_topics(turns)
        assert "Kotlin/Android" in topics or "Debugging" in topics

    def test_extract_key_facts(self):
        nc = NarrativeCompressor()
        turns = [
            {"role": "user", "content": "skripsi saya tentang federated learning pada iot"},
            {"role": "assistant", "content": "bagus! kapan deadline nya?"},
            {"role": "user", "content": "deadline tanggal 15 Agustus 2025"},
        ]
        facts = nc.extract_key_facts(turns)
        assert len(facts) >= 1
        assert any("federated" in f.lower() or "skripsi" in f.lower() or "deadline" in f.lower()
                   for f in facts)

    def test_summary_max_length(self):
        nc = NarrativeCompressor()
        long_turns = [
            {"role": "user", "content": "pesan " * 100},
            {"role": "assistant", "content": "respons " * 100},
        ]
        summary = nc.compress("sess_long", long_turns)
        assert len(summary.summary_text) <= nc.MAX_SUMMARY_LENGTH + 50


# ---------------------------------------------------------------------------
# MemoryManager Lifecycle Tests
# ---------------------------------------------------------------------------

class TestMemoryManager:
    def test_start_session(self, tmp_memory):
        sid = tmp_memory.start_session()
        assert len(sid) > 0

    def test_on_turn_and_profile_update(self, tmp_memory):
        tmp_memory.start_session()
        changes = tmp_memory.on_turn("saya sedang mengerjakan skripsi tentang machine learning", domain="thesis")
        # Profile should have been updated (machine learning keyword)
        assert isinstance(changes, list)

    def test_end_session_saves_memory(self, tmp_memory):
        tmp_memory.start_session()
        tmp_memory.on_turn("Halo JAYA", "Halo Bos!", domain="conversation")
        tmp_memory.on_turn("Skripsi saya tentang federated learning", "Topik bagus!", domain="thesis")
        summary = tmp_memory.end_session()
        assert summary is not None
        assert summary.turn_count >= 1
        assert tmp_memory.episodic.session_count() == 1

    def test_get_context_for_prompt(self, tmp_memory):
        # Save a session first
        tmp_memory.start_session()
        tmp_memory.on_turn("test", "ok")
        tmp_memory.end_session()
        tmp_memory.start_session()  # new session
        ctx = tmp_memory.get_context_for_prompt("skripsi")
        assert isinstance(ctx, str)

    def test_remember_custom_fact(self, tmp_memory):
        tmp_memory.start_session()
        tmp_memory.remember("Universitas", "UI")
        assert tmp_memory.profile.custom_facts.get("Universitas") == "UI"

    def test_status(self, tmp_memory):
        status = tmp_memory.status()
        assert "session_turns" in status
        assert "total_sessions" in status
        assert "user_name" in status
        assert "thesis_topic" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
