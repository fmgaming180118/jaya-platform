"""
Fase 5 — AgenticJarvis: Autonomous Agentic Intelligence (Setara JARVIS)
========================================================================

Empat modul yang melengkapi evolusi JAYA_CORE menjadi kecerdasan setara JARVIS:

  5.1  HierarchicalTaskPlanner  — Pecah goal besar ("Selesaikan BAB III") menjadi sub-tasks.
  5.2  ProactiveEngine          — Deteksi kebutuhan Bos & insiatif ingatkan deadline/tugas.
  5.3  AgenticLoopController    — Clarification & confirmation gate (tanya balik jika ambigu).
  5.4  ArXivPatchEngine         — Micro-delta knowledge update (< 5 MB) dari riset/paper.

Zero external dependencies — SQLite + standard library.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AgenticJarvis")

DEFAULT_AGENTIC_DB = str(Path(__file__).resolve().parents[4] / "data" / "agentic_jarvis.db")


# ---------------------------------------------------------------------------
# 5.1 — HierarchicalTaskPlanner
# ---------------------------------------------------------------------------

@dataclass
class SubTask:
    task_id: str
    parent_goal_id: str
    title: str
    description: str
    status: str = "pending"  # pending | in_progress | completed | failed
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class GoalPlan:
    goal_id: str
    goal_title: str
    domain: str
    subtasks: List[SubTask] = field(default_factory=list)
    status: str = "in_progress"  # in_progress | completed
    created_at: float = field(default_factory=time.time)

    def progress_pct(self) -> float:
        if not self.subtasks:
            return 100.0 if self.status == "completed" else 0.0
        done = sum(1 for st in self.subtasks if st.status == "completed")
        return round((done / len(self.subtasks)) * 100, 1)


class HierarchicalTaskPlanner:
    """
    Pecah tujuan besar pengguna menjadi sub-langkah konkret yang terlacak.

    Contoh:
      Goal: "Selesaikan BAB III Skripsi"
      Sub-tasks:
        1. Menyusun diagram arsitektur sistem
        2. Mendokumentasikan pengumpulan dataset
        3. Menulis alur algoritma federated learning
        4. Menyusun skenario pengujian eksperimen
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS planner_goals (
                goal_id     TEXT PRIMARY KEY,
                goal_title  TEXT NOT NULL,
                domain      TEXT DEFAULT 'general',
                status      TEXT DEFAULT 'in_progress',
                created_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS planner_subtasks (
                task_id        TEXT PRIMARY KEY,
                parent_goal_id TEXT NOT NULL,
                title          TEXT NOT NULL,
                description    TEXT DEFAULT '',
                status         TEXT DEFAULT 'pending',
                created_at     REAL NOT NULL,
                completed_at   REAL,
                FOREIGN KEY(parent_goal_id) REFERENCES planner_goals(goal_id)
            );
            CREATE INDEX IF NOT EXISTS idx_subtasks_parent
                ON planner_subtasks(parent_goal_id);
        """)
        self._conn.commit()

    def create_goal(self, title: str, domain: str = "general", subtask_titles: Optional[List[str]] = None) -> GoalPlan:
        """Buat goal baru beserta sub-tasks otomatis atau kustom."""
        goal_id = f"goal_{hash(title + str(time.time())) & 0xFFFFFF:06x}"
        self._conn.execute(
            "INSERT INTO planner_goals (goal_id, goal_title, domain, status, created_at) VALUES (?, ?, ?, 'in_progress', ?)",
            (goal_id, title, domain, time.time())
        )

        # Autogenerate subtasks if none provided
        if not subtask_titles:
            subtask_titles = self._autogenerate_subtasks(title, domain)

        subtasks = []
        for idx, st_title in enumerate(subtask_titles):
            st_id = f"{goal_id}_st{idx+1}"
            st = SubTask(
                task_id=st_id,
                parent_goal_id=goal_id,
                title=st_title,
                description=f"Langkah {idx+1} untuk mencapai: {title}"
            )
            subtasks.append(st)
            self._conn.execute(
                "INSERT INTO planner_subtasks (task_id, parent_goal_id, title, description, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
                (st.task_id, st.parent_goal_id, st.title, st.description, st.created_at)
            )

        self._conn.commit()
        plan = GoalPlan(goal_id=goal_id, goal_title=title, domain=domain, subtasks=subtasks)
        logger.info("[TaskPlanner] Created goal '%s' with %d subtasks", title, len(subtasks))
        return plan

    def _autogenerate_subtasks(self, title: str, domain: str) -> List[str]:
        """Tentukan template subtask standar berdasarkan domain dan judul."""
        title_lower = title.lower()
        if "bab 1" in title_lower or "bab i" in title_lower:
            return [
                "Menulis Latar Belakang Masalah & Urgensi Riset",
                "Merumuskan Identifikasi & Rumusan Masalah",
                "Menentukan Tujuan & Manfaat Penelitian",
                "Menyusun Batasan Masalah & Sistematika Penulisan",
            ]
        elif "bab 2" in title_lower or "bab ii" in title_lower:
            return [
                "Mengumpulkan Literatur & Jurnal Acuan Terbaru",
                "Menyusun Tinjauan Pustaka & Dasar Teori Utama",
                "Menganalisis Studi Komparatif Riset Terdahulu",
                "Menyusun Kerangka Pemikiran & Hipotesis",
            ]
        elif "bab 3" in title_lower or "bab iii" in title_lower or "metodologi" in title_lower:
            return [
                "Merancang Diagram Arsitektur & Diagram Alur Sistem",
                "Mendokumentasikan Spesifikasi Dataset & Perangkat",
                "Detail Metode & Algoritma Eksekusi yang Digunakan",
                "Menyusun Rencana Skenario Pengujian & Parameter Evaluasi",
            ]
        elif "bab 4" in title_lower or "bab iv" in title_lower or "hasil" in title_lower:
            return [
                "Mengolah Data Hasil Eksperimen & Pengujian",
                "Visualisasi Grafik & Tabel Perbandingan Performa",
                "Pembahasan & Analisis Implikasi Hasil",
            ]
        elif "code" in domain or "koding" in title_lower or "android" in title_lower:
            return [
                "Merancang Data Model & Arsitektur Kelas",
                "Implementasi Logic & Repository Backend",
                "Integrasi UI Component / Screen Layout",
                "Menjalankan Testing & Fixing Edge-case Bugs",
            ]

        # Generic default
        return [
            f"Analisis Kebutuhan Awal untuk '{title}'",
            f"Eksekusi Tahap Utama '{title}'",
            f"Review & Evaluasi Akhir '{title}'",
        ]

    def update_subtask_status(self, task_id: str, status: str) -> bool:
        """Perbarui status subtask (pending/in_progress/completed)."""
        now = time.time() if status == "completed" else None
        cursor = self._conn.execute(
            "UPDATE planner_subtasks SET status = ?, completed_at = ? WHERE task_id = ?",
            (status, now, task_id)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def get_active_goals(self) -> List[GoalPlan]:
        rows = self._conn.execute(
            "SELECT goal_id, goal_title, domain, status, created_at FROM planner_goals WHERE status = 'in_progress'"
        ).fetchall()
        goals = []
        for r in rows:
            gid, title, dom, stat, cat = r
            st_rows = self._conn.execute(
                "SELECT task_id, parent_goal_id, title, description, status, created_at, completed_at FROM planner_subtasks WHERE parent_goal_id = ?",
                (gid,)
            ).fetchall()
            subtasks = [
                SubTask(
                    task_id=st[0], parent_goal_id=st[1], title=st[2], description=st[3],
                    status=st[4], created_at=st[5], completed_at=st[6]
                ) for st in st_rows
            ]
            goals.append(GoalPlan(goal_id=gid, goal_title=title, domain=dom, subtasks=subtasks, status=stat, created_at=cat))
        return goals


# ---------------------------------------------------------------------------
# 5.2 — ProactiveEngine (Pillar 29)
# ---------------------------------------------------------------------------

@dataclass
class ProactiveAlert:
    alert_type: str  # deadline | subtask_reminder | thesis_nudge | proactive_greeting
    message: str
    priority: int = 1  # 1: normal, 2: high, 3: urgent
    created_at: float = field(default_factory=time.time)


class ProactiveEngine:
    """
    Pillar 29 — Proactive Intelligence Engine.

    Secara mandiri memeriksa kondisi pengguna dan menghasilkan reminder/nudge
    proaktif tanpa menunggu prompt eksplisit dari pengguna.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def check_proactive_nudge(
        self,
        user_name: str = "Bos",
        thesis_topic: str = "",
        current_chapter: str = "",
        deadlines: Optional[List[Dict[str, str]]] = None,
        active_goals: Optional[List[GoalPlan]] = None,
        idle_hours: float = 0.0,
    ) -> Optional[ProactiveAlert]:
        """
        Analisis konteks dan hasilkan pesan proaktif jika relevan.
        """
        # 1. Urgent deadline check
        if deadlines:
            for dl in deadlines:
                task = dl.get("task", "Tugas")
                date_str = dl.get("date", "")
                return ProactiveAlert(
                    alert_type="deadline",
                    message=f"Izin mengingatkan, {user_name}! Ada target **{task}** (Deadline: {date_str}). Mari kita progres hari ini!",
                    priority=3,
                )

        # 2. Unfinished chapter nudge
        if current_chapter and thesis_topic:
            return ProactiveAlert(
                alert_type="thesis_nudge",
                message=f"Halo {user_name}! Terakhir kita sedang membahas **{current_chapter}** tentang *{thesis_topic}*. Apakah mau dilanjutkan sekarang?",
                priority=2,
            )

        # 3. Active Goal subtask reminder
        if active_goals:
            for goal in active_goals:
                pending = [st for st in goal.subtasks if st.status != "completed"]
                if pending:
                    next_st = pending[0]
                    return ProactiveAlert(
                        alert_type="subtask_reminder",
                        message=f"{user_name}, untuk target **{goal.goal_title}**, langkah berikutnya adalah: *\"{next_st.title}\"*. Siap saya bantu?",
                        priority=2,
                    )

        # 4. Long idle welcome back
        if idle_hours > 24.0:
            return ProactiveAlert(
                alert_type="proactive_greeting",
                message=f"Selamat datang kembali, {user_name}! JAYA siap membantu riset, koding, atau tugas Anda hari ini.",
                priority=1,
            )

        return None


# ---------------------------------------------------------------------------
# 5.3 — AgenticLoopController (Clarification & Confirmation Gate)
# ---------------------------------------------------------------------------

class AgenticLoopController:
    """
    Bertanya balik saat instruksi ambigu, dan meminta konfirmasi
    sebelum tindakan berbahaya (destruktif).
    """

    AMBIGUOUS_KEYWORDS = ["bantu", "perbaiki", "buatkan", "proses", "kerjakan"]
    DESTRUCTIVE_KEYWORDS = ["hapus", "overwrite", "delete", "clear", "wipe", "drop", "reset"]

    def evaluate_intent(self, prompt: str) -> Tuple[bool, bool, str]:
        """
        Evaluasi apakah prompt ambigu atau destruktif.

        Returns
        -------
        Tuple[is_ambiguous, is_destructive, recommendation_text]
        """
        prompt_lower = prompt.lower().strip()
        words = prompt_lower.split()

        # Deteksi aksi destruktif
        is_destructive = any(kw in prompt_lower for kw in self.DESTRUCTIVE_KEYWORDS)
        if is_destructive:
            return (
                False,
                True,
                f"⚠️ **Konfirmasi Keamanan**: Tindakan ini berdampak permanen ({prompt}). Apakah Anda yakin ingin melanjutkan, Bos?"
            )

        # Deteksi instruksi ambigu (pesan sangat pendek tanpa detail)
        if len(words) <= 2 and any(kw in prompt_lower for kw in self.AMBIGUOUS_KEYWORDS):
            return (
                True,
                False,
                f"Saya siap membantu '{prompt}', Bos! Agar hasilnya presisi, bisakah Anda jelaskan detail atau konteks spesifik yang diinginkan?"
            )

        return False, False, ""


# ---------------------------------------------------------------------------
# 5.4 — ArXivPatchEngine (Micro-Delta Auto-Patching)
# ---------------------------------------------------------------------------

class ArXivPatchEngine:
    """
    Simulasi/Engine Micro-Delta Knowledge Patching (< 5 MB).
    Menerima paper/ringkasan baru dan menyuntikkannya ke RAG database.
    """

    def apply_micro_patch(self, patch_title: str, patch_content: str, rag_retriever: Any = None) -> Dict[str, Any]:
        """Terapkan patch pengetahuan ilmiah baru ke RAG vault."""
        patch_id = f"arxiv_{hash(patch_title) & 0xFFFFFF:06x}"
        result = {"patch_id": patch_id, "title": patch_title, "status": "applied"}
        if rag_retriever and hasattr(rag_retriever, "add_document"):
            try:
                rag_retriever.add_document(
                    doc_id=patch_id,
                    title=f"[ArXiv Delta] {patch_title}",
                    body=patch_content,
                    source="arxiv_auto_patch",
                )
                result["rag_indexed"] = True
            except Exception as ex:
                result["rag_error"] = str(ex)
        logger.info("[ArXivPatch] Applied micro-patch: %s", patch_title)
        return result


# ---------------------------------------------------------------------------
# JarvisAgentFacade — Unified Agentic Intelligence Engine
# ---------------------------------------------------------------------------

class JarvisAgentFacade:
    """
    Facade utama Fase 5 — Menggabungkan Task Planner, Proactive Engine,
    Agentic Loop Gate, dan ArXiv Patch Engine.
    """

    def __init__(self, db_path: str = DEFAULT_AGENTIC_DB) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)

        self.planner = HierarchicalTaskPlanner(self._conn)
        self.proactive = ProactiveEngine(self._conn)
        self.agentic_loop = AgenticLoopController()
        self.arxiv_patch = ArXivPatchEngine()

        logger.info("[JarvisAgentFacade] Initialized Fase 5 Agentic Engine | db=%s", db_path)

    def process_input_gate(self, prompt: str) -> Tuple[bool, str]:
        """
        Evaluasi input pengguna.
        Return (should_intercept, intercept_response_text).
        Jika should_intercept == True, respons langsung diberikan tanpa ke LLM.
        """
        is_ambiguous, is_destructive, message = self.agentic_loop.evaluate_intent(prompt)
        if is_ambiguous or is_destructive:
            return True, message
        return False, ""

    def get_proactive_nudge_if_any(
        self,
        user_name: str = "Bos",
        thesis_topic: str = "",
        current_chapter: str = "",
        deadlines: Optional[List[Dict[str, str]]] = None,
        idle_hours: float = 0.0,
    ) -> Optional[str]:
        """Dapatkan pesan proaktif jika ada trigger yang aktif."""
        active_goals = self.planner.get_active_goals()
        alert = self.proactive.check_proactive_nudge(
            user_name=user_name,
            thesis_topic=thesis_topic,
            current_chapter=current_chapter,
            deadlines=deadlines,
            active_goals=active_goals,
            idle_hours=idle_hours,
        )
        return alert.message if alert else None

    def status(self) -> Dict[str, Any]:
        return {
            "active_goals_count": len(self.planner.get_active_goals()),
            "db_path": self.db_path,
        }

    def __del__(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
