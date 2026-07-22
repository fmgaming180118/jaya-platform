"""
Fase 3 — EpisodicMemory: Memory Architecture Setara JARVIS
============================================================

Tiga komponen memori yang membuat JAYA mengingat Bos lintas hari, sesi, dan topik:

  3.1  EpisodicMemory       — SQLite long-term memory per sesi percakapan.
  3.2  UserProfileEngine    — Profil pengguna dinamis yang diperbarui inkremental.
  3.3  NarrativeCompressor  — Kompresi percakapan panjang + injeksi konteks ke sesi baru.

Architecture
------------
  Semua data disimpan di satu file SQLite ringan (< 5 MB normal usage).
  Zero external dependencies — hanya stdlib Python + sqlite3.
  
  Flow per sesi:
    START  → load_session_context() → inject ke system prompt SLMEngine
    DURING → update_profile_incremental() on each turn
    END    → save_session_summary() + compress_if_needed()
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("EpisodicMemory")

DEFAULT_MEMORY_DB = str(Path(__file__).resolve().parents[4] / "data" / "episodic_memory.db")

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class SessionSummary:
    """Ringkasan satu sesi percakapan yang disimpan ke long-term memory."""
    session_id: str
    timestamp: float
    user_messages: List[str]
    assistant_messages: List[str]
    topics: List[str]             # topik yang terdeteksi dalam sesi ini
    key_facts: List[str]          # fakta penting yang disampaikan
    summary_text: str             # ringkasan naratif
    turn_count: int = 0
    domain: str = "conversation"  # domain dominan sesi ini


@dataclass
class UserProfile:
    """Profil pengguna dinamis yang diperbarui lintas sesi."""
    user_id: str = "boss"
    name: str = "Bos"
    research_topics: List[str] = field(default_factory=list)
    current_chapter: str = ""         # BAB berapa yang sedang dikerjakan
    thesis_topic: str = ""            # topik skripsi
    deadlines: List[Dict[str, str]] = field(default_factory=list)
    preferred_language: str = "id"    # bahasa preferensi
    work_style: str = "collaborative" # gaya kerja: collaborative / direct / detailed
    domain_expertise: Dict[str, float] = field(default_factory=dict)  # domain → confidence
    last_seen: float = 0.0
    session_count: int = 0
    total_turns: int = 0
    interests: List[str] = field(default_factory=list)
    custom_facts: Dict[str, str] = field(default_factory=dict)  # fakta bebas tentang user

    def to_context_string(self) -> str:
        """Bangun string konteks personal untuk diinjeksi ke system prompt."""
        lines = [f"Nama pengguna: {self.name}"]
        if self.thesis_topic:
            lines.append(f"Topik skripsi: {self.thesis_topic}")
        if self.current_chapter:
            lines.append(f"Sedang mengerjakan: {self.current_chapter}")
        if self.research_topics:
            lines.append(f"Topik riset: {', '.join(self.research_topics[:5])}")
        if self.deadlines:
            dl = self.deadlines[-1]
            lines.append(f"Deadline terdekat: {dl.get('task', '')} — {dl.get('date', '')}")
        if self.interests:
            lines.append(f"Minat: {', '.join(self.interests[:3])}")
        for k, v in list(self.custom_facts.items())[:3]:
            lines.append(f"{k}: {v}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3.1 — EpisodicMemory: Long-Term Session Memory
# ---------------------------------------------------------------------------

class EpisodicMemory:
    """
    Pillar 31 — Episodic Long-Term Memory.

    Menyimpan ringkasan setiap sesi percakapan ke SQLite dan mengambil
    memori relevan pada awal sesi baru.

    JAYA akan mengingat:
      - "Bos sudah di BAB III skripsi, deadline 15 Agustus."
      - "Tiga sesi lalu kita debug masalah Retrofit timeout di Android."
      - "Minggu lalu Bos minta penjelasan federated learning."
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodic_sessions (
                session_id   TEXT PRIMARY KEY,
                timestamp    REAL NOT NULL,
                domain       TEXT DEFAULT 'conversation',
                turn_count   INTEGER DEFAULT 0,
                summary_text TEXT NOT NULL,
                topics_json  TEXT DEFAULT '[]',
                key_facts_json TEXT DEFAULT '[]',
                compressed   INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS session_turns (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL,
                turn_index   INTEGER NOT NULL,
                role         TEXT NOT NULL,
                content      TEXT NOT NULL,
                timestamp    REAL NOT NULL,
                FOREIGN KEY(session_id) REFERENCES episodic_sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_session_turns_sid
                ON session_turns(session_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_timestamp
                ON episodic_sessions(timestamp DESC);
        """)
        self._conn.commit()

    # -- Write ---------------------------------------------------------------

    def save_session(self, summary: SessionSummary) -> None:
        """Simpan ringkasan sesi ke long-term memory."""
        self._conn.execute("""
            INSERT OR REPLACE INTO episodic_sessions
                (session_id, timestamp, domain, turn_count,
                 summary_text, topics_json, key_facts_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            summary.session_id,
            summary.timestamp,
            summary.domain,
            summary.turn_count,
            summary.summary_text,
            json.dumps(summary.topics, ensure_ascii=False),
            json.dumps(summary.key_facts, ensure_ascii=False),
        ))

        # Simpan turns individual (untuk compressed recall)
        for i, (u, a) in enumerate(zip(summary.user_messages, summary.assistant_messages)):
            for role, content in [("user", u), ("assistant", a)]:
                self._conn.execute("""
                    INSERT INTO session_turns
                        (session_id, turn_index, role, content, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (summary.session_id, i, role, content, summary.timestamp))
        self._conn.commit()
        logger.info("[EpisodicMemory] Saved session %s (%d turns)", summary.session_id, summary.turn_count)

    # -- Read ----------------------------------------------------------------

    def get_recent_sessions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Ambil ringkasan N sesi terbaru."""
        rows = self._conn.execute("""
            SELECT session_id, timestamp, domain, turn_count, summary_text,
                   topics_json, key_facts_json
            FROM episodic_sessions
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()
        results = []
        for r in rows:
            results.append({
                "session_id": r[0],
                "timestamp": r[1],
                "domain": r[2],
                "turn_count": r[3],
                "summary_text": r[4],
                "topics": json.loads(r[5] or "[]"),
                "key_facts": json.loads(r[6] or "[]"),
                "age_hours": round((time.time() - r[1]) / 3600, 1),
            })
        return results

    def retrieve_relevant(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Cari memori episodik yang relevan untuk query saat ini.
        Menggunakan keyword matching sederhana terhadap summary + topics.
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\w+', query_lower))
        sessions = self.get_recent_sessions(limit=20)
        scored = []
        for s in sessions:
            score = 0
            text = (s["summary_text"] + " " + " ".join(s["topics"])).lower()
            for word in query_words:
                if len(word) > 2 and word in text:
                    score += 1
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]

    def build_recall_context(self, query: str = "", max_sessions: int = 3) -> str:
        """
        Bangun teks konteks memori episodik untuk diinjeksi ke system prompt.
        Digunakan setiap awal sesi baru agar JAYA 'ingat' Bos.
        """
        recent = self.get_recent_sessions(limit=max_sessions)
        if not recent:
            return ""

        lines = ["[Memori Lintas Sesi JAYA]"]
        for s in recent:
            age = s["age_hours"]
            age_str = f"{age:.0f} jam lalu" if age < 24 else f"{age/24:.0f} hari lalu"
            lines.append(f"• ({age_str}) {s['summary_text']}")
            if s["key_facts"]:
                for fact in s["key_facts"][:2]:
                    lines.append(f"  → {fact}")
        return "\n".join(lines)

    def session_count(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM episodic_sessions"
        ).fetchone()[0]


# ---------------------------------------------------------------------------
# 3.2 — UserProfileEngine: Dynamic User Profile
# ---------------------------------------------------------------------------

# Pola NLP ringan untuk ekstraksi informasi dari percakapan
_THESIS_PATTERNS = [
    (r"skripsi\s+(?:saya\s+)?(?:tentang|mengenai|soal)\s+([\w\s]+)", "thesis_topic"),
    (r"(?:bab|chapter)\s+([ivxIVX\d]+)\s+(?:skripsi|penelitian)", "current_chapter"),
    (r"deadline\s+(?:nya\s+)?(?:tanggal\s+)?(\d{1,2}\s+\w+\s*(?:\d{4})?)", "deadline"),
    (r"(?:nama\s+saya|saya\s+(?:adalah|bernama))\s+(\w+)", "name"),
    (r"federated\s+learning", "thesis_keyword"),
    (r"machine\s+learning", "thesis_keyword"),
    (r"deep\s+learning", "thesis_keyword"),
    (r"blockchain", "thesis_keyword"),
    (r"iot|internet\s+of\s+things", "thesis_keyword"),
    (r"(?:android|kotlin|python|java)\s+(?:developer|programming)", "code_interest"),
]

_DOMAIN_TO_EXPERTISE = {
    "thesis": "research",
    "code": "programming",
    "math": "mathematics",
    "conversation": "general",
}


class UserProfileEngine:
    """
    Pillar 32 — Dynamic User Profile Engine.

    Membangun dan memperbarui profil pengguna secara inkremental dari
    setiap percakapan. Profil digunakan untuk:
      - Personalisasi system prompt
      - Anticipate kebutuhan pengguna
      - Membuat respons lebih kontekstual dan hangat
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_tables()
        self._profile: Optional[UserProfile] = None

    def _ensure_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_profile (
                user_id   TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
        """)
        self._conn.commit()

    def load(self, user_id: str = "boss") -> UserProfile:
        """Muat profil dari DB, atau buat profil baru jika belum ada."""
        row = self._conn.execute(
            "SELECT profile_json FROM user_profile WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            try:
                data = json.loads(row[0])
                profile = UserProfile(
                    user_id=data.get("user_id", user_id),
                    name=data.get("name", "Bos"),
                    research_topics=data.get("research_topics", []),
                    current_chapter=data.get("current_chapter", ""),
                    thesis_topic=data.get("thesis_topic", ""),
                    deadlines=data.get("deadlines", []),
                    preferred_language=data.get("preferred_language", "id"),
                    work_style=data.get("work_style", "collaborative"),
                    domain_expertise=data.get("domain_expertise", {}),
                    last_seen=data.get("last_seen", 0.0),
                    session_count=data.get("session_count", 0),
                    total_turns=data.get("total_turns", 0),
                    interests=data.get("interests", []),
                    custom_facts=data.get("custom_facts", {}),
                )
                self._profile = profile
                logger.debug("[UserProfileEngine] Profile loaded for %s", user_id)
                return profile
            except Exception as e:
                logger.warning("[UserProfileEngine] Profile parse error: %s", e)
        # Brand new profile
        self._profile = UserProfile(user_id=user_id)
        return self._profile

    def save(self) -> None:
        """Simpan profil yang diperbarui ke DB."""
        if self._profile is None:
            return
        self._profile.last_seen = time.time()
        data = asdict(self._profile)
        self._conn.execute("""
            INSERT OR REPLACE INTO user_profile(user_id, profile_json, updated_at)
            VALUES (?, ?, ?)
        """, (self._profile.user_id, json.dumps(data, ensure_ascii=False), time.time()))
        self._conn.commit()

    def update_from_turn(self, user_text: str, assistant_text: str = "", domain: str = "conversation") -> List[str]:
        """
        Update profil inkremental dari satu turn percakapan.
        Return list of string perubahan yang terdeteksi.
        """
        if self._profile is None:
            self.load()
        profile = self._profile
        changes = []
        text = user_text.lower()

        for pattern, field_name in _THESIS_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip() if match.lastindex else pattern.split("\\")[0]

                if field_name == "thesis_topic" and value and value not in profile.thesis_topic:
                    profile.thesis_topic = value[:100]
                    changes.append(f"thesis_topic={value}")

                elif field_name == "current_chapter" and value:
                    chapter_str = f"BAB {value.upper()}"
                    if chapter_str != profile.current_chapter:
                        profile.current_chapter = chapter_str
                        changes.append(f"current_chapter={chapter_str}")

                elif field_name == "deadline" and value:
                    entry = {"task": "Skripsi", "date": value.strip()}
                    if entry not in profile.deadlines:
                        profile.deadlines.append(entry)
                        profile.deadlines = profile.deadlines[-5:]  # keep last 5
                        changes.append(f"deadline={value}")

                elif field_name == "name" and value and len(value) < 30:
                    if profile.name == "Bos":
                        profile.name = value.capitalize()
                        changes.append(f"name={profile.name}")

                elif field_name == "thesis_keyword":
                    kw = match.group(0).strip().title()
                    if kw not in profile.research_topics:
                        profile.research_topics.append(kw)
                        profile.research_topics = list(dict.fromkeys(profile.research_topics))[:10]
                        changes.append(f"research_topic+={kw}")

        # Domain expertise tracking
        exp_key = _DOMAIN_TO_EXPERTISE.get(domain, domain)
        if exp_key:
            current = profile.domain_expertise.get(exp_key, 0.0)
            profile.domain_expertise[exp_key] = min(1.0, current + 0.02)

        # Turn tracking
        profile.total_turns += 1

        if changes:
            self.save()
            logger.info("[UserProfileEngine] Profile updated: %s", changes)

        return changes

    def increment_session(self) -> None:
        if self._profile:
            self._profile.session_count += 1
            self.save()

    def set_custom_fact(self, key: str, value: str) -> None:
        """Simpan fakta bebas tentang pengguna."""
        if self._profile:
            self._profile.custom_facts[key] = value
            self._profile.custom_facts = dict(
                list(self._profile.custom_facts.items())[-20:]
            )
            self.save()

    @property
    def profile(self) -> Optional[UserProfile]:
        return self._profile


# ---------------------------------------------------------------------------
# 3.3 — NarrativeCompressor: Otomatis ringkaskan percakapan panjang
# ---------------------------------------------------------------------------

class NarrativeCompressor:
    """
    Narrative Compression untuk percakapan panjang.

    Mengubah daftar turns percakapan menjadi ringkasan naratif padat
    yang dapat diinjeksi sebagai konteks ke sesi berikutnya.

    Strategi kompresi (tanpa LLM) menggunakan:
      1. Ekstraksi kalimat kunci berdasarkan panjang & keunikan.
      2. Deteksi topik dari kata-kata signifikan.
      3. Ekstraksi fakta dari pola kalimat khusus.
    """

    MAX_SUMMARY_LENGTH = 400   # karakter maks ringkasan satu sesi
    MIN_TURNS_TO_COMPRESS = 4  # minimal turn sebelum kompresi diperlukan

    def extract_key_facts(self, turns: List[Dict[str, str]]) -> List[str]:
        """Ekstrak fakta kunci dari daftar turns {role, content}."""
        facts = []
        user_messages = [t["content"] for t in turns if t.get("role") == "user"]

        # Pola fakta kunci dari percakapan Indonesia
        fact_patterns = [
            (r"(skripsi.{0,60}(?:tentang|mengenai).{0,60})", "skripsi"),
            (r"(bab\s+[ivxIVX\d]+.{0,60})", "bab"),
            (r"(deadline.{0,60})", "deadline"),
            (r"(bug.{0,80})", "bug"),
            (r"(error.{0,80})", "error"),
            (r"(masalah.{0,80})", "masalah"),
            (r"(solusi.{0,80})", "solusi"),
            (r"(berhasil.{0,60})", "berhasil"),
            (r"(selesai.{0,60})", "selesai"),
        ]

        for msg in user_messages:
            for pattern, tag in fact_patterns:
                match = re.search(pattern, msg, re.IGNORECASE)
                if match:
                    fact = match.group(1).strip()[:100]
                    if fact and fact not in facts:
                        facts.append(fact)
                if len(facts) >= 5:
                    break

        return facts[:5]

    def extract_topics(self, turns: List[Dict[str, str]]) -> List[str]:
        """Ekstrak topik utama dari percakapan."""
        all_text = " ".join(t["content"] for t in turns)

        topic_keywords = {
            "Skripsi": ["skripsi", "thesis", "penelitian", "bab", "abstrak"],
            "Kotlin/Android": ["kotlin", "android", "activity", "viewmodel", "retrofit"],
            "Python": ["python", "pip", "flask", "django", "numpy"],
            "Federated Learning": ["federated", "fl", "privasi", "terdistribusi"],
            "Machine Learning": ["machine learning", "neural", "training", "model"],
            "Debugging": ["bug", "error", "exception", "crash", "debug"],
            "Matematika": ["integral", "derivatif", "matriks", "statistik", "aljabar"],
            "Percakapan": ["halo", "kabar", "gimana", "apa", "cerita"],
        }

        found = []
        text_lower = all_text.lower()
        for topic, keywords in topic_keywords.items():
            if any(kw in text_lower for kw in keywords):
                found.append(topic)

        return found[:4]

    def compress(
        self,
        session_id: str,
        turns: List[Dict[str, str]],
        domain: str = "conversation",
    ) -> SessionSummary:
        """
        Kompres satu sesi percakapan menjadi SessionSummary.

        Parameters
        ----------
        session_id: ID unik sesi.
        turns: List of {"role": "user"|"assistant", "content": str}.
        domain: Domain dominan sesi.
        """
        user_msgs = [t["content"] for t in turns if t.get("role") == "user"]
        asst_msgs = [t["content"] for t in turns if t.get("role") == "assistant"]

        topics = self.extract_topics(turns)
        key_facts = self.extract_key_facts(turns)

        # Bangun ringkasan naratif
        turn_count = len(user_msgs)
        topic_str = ", ".join(topics) if topics else "percakapan umum"

        # Ambil pesan pengguna pertama & terakhir sebagai anchor
        first_msg = user_msgs[0][:60] if user_msgs else ""
        last_msg = user_msgs[-1][:60] if len(user_msgs) > 1 else ""

        if key_facts:
            facts_str = "; ".join(key_facts[:2])
            summary_text = (
                f"Sesi {turn_count} turn, topik: {topic_str}. "
                f"Dimulai dengan: \"{first_msg}\". "
                f"Fakta kunci: {facts_str}."
            )
        else:
            summary_text = (
                f"Sesi {turn_count} turn membahas {topic_str}. "
                f"Dimulai: \"{first_msg}\"."
            )
            if last_msg and last_msg != first_msg:
                summary_text += f" Diakhiri: \"{last_msg}\"."

        summary_text = summary_text[:self.MAX_SUMMARY_LENGTH]

        return SessionSummary(
            session_id=session_id,
            timestamp=time.time(),
            user_messages=user_msgs,
            assistant_messages=asst_msgs,
            topics=topics,
            key_facts=key_facts,
            summary_text=summary_text,
            turn_count=turn_count,
            domain=domain,
        )

    def build_injection_context(
        self,
        episodic: EpisodicMemory,
        user_profile: Optional[UserProfile],
        current_query: str = "",
    ) -> str:
        """
        Bangun teks konteks lengkap untuk diinjeksi ke system prompt:
          1. Profil pengguna
          2. Memori episodik relevan
          3. Sesi terbaru
        """
        sections = []

        # Profil pengguna
        if user_profile:
            profile_ctx = user_profile.to_context_string()
            if profile_ctx.strip():
                sections.append(f"[Profil Pengguna]\n{profile_ctx}")

        # Memori episodik relevan (jika ada query)
        if current_query:
            relevant = episodic.retrieve_relevant(current_query, limit=2)
            if relevant:
                mem_lines = ["[Memori Relevan]"]
                for m in relevant:
                    age = m["age_hours"]
                    age_str = f"{age:.0f} jam lalu" if age < 24 else f"{age/24:.1f} hari lalu"
                    mem_lines.append(f"• ({age_str}) {m['summary_text']}")
                sections.append("\n".join(mem_lines))

        # Sesi-sesi terbaru (max 3)
        recall = episodic.build_recall_context(max_sessions=3)
        if recall:
            sections.append(recall)

        return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# MemoryManager — Facade untuk semua komponen memori Fase 3
# ---------------------------------------------------------------------------

class MemoryManager:
    """
    Fase 3 facade: mengelola EpisodicMemory, UserProfileEngine, dan NarrativeCompressor
    dalam satu antarmuka yang mudah digunakan oleh SLMEngine dan server.
    
    Usage:
        mm = MemoryManager()
        mm.start_session()                          # awal sesi
        ctx = mm.get_context_for_prompt(query)      # inject ke system prompt
        mm.on_turn(user_msg, assistant_msg, domain) # tiap turn
        mm.end_session(turns)                       # akhir sesi, simpan memori
    """

    def __init__(self, db_path: str = DEFAULT_MEMORY_DB) -> None:
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")

        self._episodic = EpisodicMemory(self._conn)
        self._profile_engine = UserProfileEngine(self._conn)
        self._compressor = NarrativeCompressor()

        # Load user profile immediately
        self._profile_engine.load()

        # Session state
        self._current_session_id: str = ""
        self._session_turns: List[Dict[str, str]] = []
        self._session_domain: str = "conversation"

        logger.info("[MemoryManager] Initialized | db=%s | sessions=%d",
                    db_path, self._episodic.session_count())

    def start_session(self, session_id: Optional[str] = None) -> str:
        """Mulai sesi baru. Return session_id."""
        ts = time.time()
        self._current_session_id = session_id or hashlib.sha256(
            str(ts).encode()
        ).hexdigest()[:12]
        self._session_turns = []
        self._session_domain = "conversation"
        self._profile_engine.increment_session()
        logger.info("[MemoryManager] Session started: %s", self._current_session_id)
        return self._current_session_id

    def get_context_for_prompt(self, query: str = "") -> str:
        """
        Dapatkan konteks memori lengkap untuk diinjeksi ke system prompt SLMEngine.
        Dipanggil sekali di awal setiap sesi atau per-request jika diperlukan.
        """
        return self._compressor.build_injection_context(
            self._episodic,
            self._profile_engine.profile,
            current_query=query,
        )

    def on_turn(self, user_text: str, assistant_text: str = "", domain: str = "conversation") -> List[str]:
        """
        Dipanggil setiap turn percakapan.
        Update profil secara inkremental + catat turn ke session buffer.
        Return daftar perubahan profil yang terdeteksi.
        """
        self._session_turns.append({"role": "user", "content": user_text})
        if assistant_text:
            self._session_turns.append({"role": "assistant", "content": assistant_text})
        self._session_domain = domain  # update ke domain terbaru
        changes = self._profile_engine.update_from_turn(user_text, assistant_text, domain)
        return changes

    def end_session(self, extra_turns: Optional[List[Dict[str, str]]] = None) -> Optional[SessionSummary]:
        """
        Akhiri sesi saat ini:
          1. Kompres semua turns menjadi SessionSummary.
          2. Simpan ke EpisodicMemory.
          3. Return summary.
        """
        all_turns = self._session_turns.copy()
        if extra_turns:
            all_turns.extend(extra_turns)
        if not all_turns:
            return None

        summary = self._compressor.compress(
            session_id=self._current_session_id,
            turns=all_turns,
            domain=self._session_domain,
        )
        self._episodic.save_session(summary)
        self._session_turns = []
        logger.info("[MemoryManager] Session %s ended: %d turns → memory saved",
                    self._current_session_id, summary.turn_count)
        return summary

    def remember(self, key: str, value: str) -> None:
        """Tool: Simpan fakta khusus tentang pengguna."""
        self._profile_engine.set_custom_fact(key, value)

    @property
    def profile(self) -> Optional[UserProfile]:
        return self._profile_engine.profile

    @property
    def episodic(self) -> EpisodicMemory:
        return self._episodic

    def status(self) -> Dict[str, Any]:
        p = self._profile_engine.profile
        return {
            "session_id": self._current_session_id,
            "session_turns": len(self._session_turns),
            "total_sessions": self._episodic.session_count(),
            "user_name": p.name if p else "Unknown",
            "thesis_topic": p.thesis_topic if p else "",
            "current_chapter": p.current_chapter if p else "",
            "research_topics": p.research_topics if p else [],
            "db_path": self._db_path,
        }

    def __del__(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
