import json
import logging
import math
import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AgenticRAG")

class AgenticRAG:
    """
    Pillar 33: Agentic RAG
    Sistem ingatan empiris mandiri yang sangat ringan.
    Menyimpan fakta, nama, solusi masalah, dan konteks lingkungan JAYA saat berpindah device.
    Zero-Dependency: Menggunakan SQLite3 FTS5 (Full Text Search) bawaan Python.
    """
    def __init__(self, db_path: str = "rag_vault.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Membuat tabel Virtual FTS5 yang sangat cepat untuk pencarian teks."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            # FTS5 for fast text search without heavy vector DBs
            conn.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS rag_memory USING fts5(
                    topic,
                    content,
                    source,
                    timestamp UNINDEXED,
                    importance UNINDEXED
                )
            ''')
            # Table for tracking when Jaya needs to tidy up
            conn.execute('''
                CREATE TABLE IF NOT EXISTS memory_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    last_tidy_up REAL,
                    total_chunks INTEGER
                )
            ''')
            # Table for Semantic Graph (Pillar 33 - Graph RAG)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS semantic_graph (
                    source_node TEXT,
                    relation TEXT,
                    target_node TEXT,
                    weight REAL DEFAULT 1.0,
                    UNIQUE(source_node, relation, target_node)
                )
            ''')
            # Table for lightweight procedural memory capsules (Stage 2)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS procedural_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    language TEXT DEFAULT 'id',
                    source TEXT DEFAULT 'manual',
                    confidence REAL DEFAULT 0.75,
                    timestamp REAL,
                    usage_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    last_used REAL DEFAULT 0
                )
            ''')
            self._ensure_procedural_schema(conn)
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_procedural_trigger
                ON procedural_memory(trigger)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_procedural_language
                ON procedural_memory(language)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_procedural_last_used
                ON procedural_memory(last_used)
            ''')
            # Table for adaptive policy history (Stage 6)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS adaptive_policy_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    source TEXT DEFAULT 'runtime',
                    base_clarify_threshold REAL,
                    base_decay_hours REAL,
                    recommended_clarify_threshold REAL,
                    recommended_decay_hours REAL,
                    clarify_mode TEXT,
                    decay_mode TEXT,
                    reasons_json TEXT,
                    snapshot_json TEXT
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_policy_history_timestamp
                ON adaptive_policy_history(timestamp)
            ''')
            conn.commit()

    def _ensure_procedural_schema(self, conn: sqlite3.Connection) -> None:
        """Ensure newer procedural-memory columns exist on old databases."""
        try:
            cursor = conn.execute("PRAGMA table_info(procedural_memory)")
            columns = {str(row[1]) for row in cursor.fetchall()}
        except Exception:
            return

        if "usage_count" not in columns:
            conn.execute("ALTER TABLE procedural_memory ADD COLUMN usage_count INTEGER DEFAULT 0")
        if "success_count" not in columns:
            conn.execute("ALTER TABLE procedural_memory ADD COLUMN success_count INTEGER DEFAULT 0")
        if "failure_count" not in columns:
            conn.execute("ALTER TABLE procedural_memory ADD COLUMN failure_count INTEGER DEFAULT 0")
        if "last_used" not in columns:
            conn.execute("ALTER TABLE procedural_memory ADD COLUMN last_used REAL DEFAULT 0")

    @staticmethod
    def _tokenize_terms(text: str) -> List[str]:
        if not isinstance(text, str):
            return []
        clean = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        return [w for w in clean.split() if len(w) > 2]

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _safe_float(value: Any, fallback: float) -> float:
        try:
            parsed = float(value)
        except Exception:
            return float(fallback)
        if not math.isfinite(parsed):
            return float(fallback)
        return parsed

    @staticmethod
    def _decay_factor(age_seconds: float, half_life_hours: float) -> float:
        if half_life_hours <= 0:
            return 1.0
        tau = half_life_hours * 3600.0
        return math.exp(-max(0.0, age_seconds) / tau)

    @staticmethod
    def _decay_half_life_hours() -> float:
        raw = os.getenv("JAYA_PROCEDURE_DECAY_HOURS", "120")
        try:
            value = float(raw)
        except Exception:
            return 120.0
        return max(12.0, min(value, 24.0 * 30.0))

    @staticmethod
    def _resolve_procedure_max_items(override: Optional[int] = None) -> int:
        if override is not None:
            return max(16, min(int(override), 2048))
        raw = os.getenv("JAYA_PROCEDURE_MAX_ITEMS", "256")
        try:
            value = int(raw)
        except Exception:
            return 256
        return max(16, min(value, 2048))

    @staticmethod
    def _resolve_stale_days(override: Optional[float] = None) -> float:
        if override is not None:
            return max(7.0, min(float(override), 365.0))
        raw = os.getenv("JAYA_PROCEDURE_STALE_DAYS", "60")
        try:
            value = float(raw)
        except Exception:
            return 60.0
        return max(7.0, min(value, 365.0))

    @staticmethod
    def _resolve_min_health(override: Optional[float] = None) -> float:
        if override is not None:
            return max(0.0, min(float(override), 1.0))
        raw = os.getenv("JAYA_PROCEDURE_MIN_HEALTH", "0.32")
        try:
            value = float(raw)
        except Exception:
            return 0.32
        return max(0.0, min(value, 1.0))

    @staticmethod
    def _resolve_clarify_threshold(override: Optional[float] = None) -> float:
        if override is not None:
            return max(0.35, min(float(override), 0.90))
        raw = os.getenv("JAYA_CLARIFY_THRESHOLD", "0.62")
        try:
            value = float(raw)
        except Exception:
            return 0.62
        return max(0.35, min(value, 0.90))

    @staticmethod
    def _resolve_policy_guard_window(override: Optional[int] = None) -> int:
        if override is not None:
            return max(3, min(int(override), 40))
        raw = os.getenv("JAYA_POLICY_GUARD_WINDOW", "8")
        try:
            value = int(raw)
        except Exception:
            return 8
        return max(3, min(value, 40))

    @staticmethod
    def _resolve_policy_guard_clarify_step(override: Optional[float] = None) -> float:
        if override is not None:
            return max(0.01, min(float(override), 0.20))
        raw = os.getenv("JAYA_POLICY_GUARD_CLARIFY_STEP", "0.05")
        try:
            value = float(raw)
        except Exception:
            return 0.05
        return max(0.01, min(value, 0.20))

    @staticmethod
    def _resolve_policy_guard_decay_step_hours(override: Optional[float] = None) -> float:
        if override is not None:
            return max(1.0, min(float(override), 120.0))
        raw = os.getenv("JAYA_POLICY_GUARD_DECAY_STEP_HOURS", "18")
        try:
            value = float(raw)
        except Exception:
            return 18.0
        return max(1.0, min(value, 120.0))

    @staticmethod
    def _resolve_policy_guard_cooldown_seconds(override: Optional[float] = None) -> float:
        if override is not None:
            return max(0.0, min(float(override), 3600.0))
        raw = os.getenv("JAYA_POLICY_GUARD_COOLDOWN_SECONDS", "45")
        try:
            value = float(raw)
        except Exception:
            return 45.0
        return max(0.0, min(value, 3600.0))

    def _append_policy_history(self, report: Dict[str, Any], source: str = "runtime") -> bool:
        """Persist adaptive-policy decisions for trend analysis across sessions."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO adaptive_policy_history
                    (
                        timestamp, source,
                        base_clarify_threshold, base_decay_hours,
                        recommended_clarify_threshold, recommended_decay_hours,
                        clarify_mode, decay_mode,
                        reasons_json, snapshot_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        time.time(),
                        source,
                        float(report.get("base_clarify_threshold", 0.62) or 0.62),
                        float(report.get("base_decay_hours", 120.0) or 120.0),
                        float(report.get("recommended_clarify_threshold", 0.62) or 0.62),
                        float(report.get("recommended_decay_hours", 120.0) or 120.0),
                        str(report.get("clarify_mode", "stable") or "stable"),
                        str(report.get("decay_mode", "stable") or "stable"),
                        json.dumps(report.get("reasons") or [], ensure_ascii=False),
                        json.dumps(report.get("snapshot") or {}, ensure_ascii=False),
                    ),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.warning("[Agentic RAG] Failed to persist policy history: %s", e)
            return False

    def log_policy_decision(self, report: Dict[str, Any], source: str = "runtime") -> bool:
        """Public wrapper for persisting a policy decision snapshot."""
        return self._append_policy_history(report, source=source)

    def get_policy_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return recent adaptive-policy history entries."""
        limit = max(1, min(int(limit), 100))
        rows: List[tuple[Any, ...]] = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT
                        id, timestamp, source,
                        base_clarify_threshold, base_decay_hours,
                        recommended_clarify_threshold, recommended_decay_hours,
                        clarify_mode, decay_mode, reasons_json, snapshot_json
                    FROM adaptive_policy_history
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        except Exception as e:
            logger.warning("[Agentic RAG] Failed loading policy history: %s", e)
            return []

        output: List[Dict[str, Any]] = []
        for (
            row_id,
            timestamp,
            source,
            base_clarify,
            base_decay,
            rec_clarify,
            rec_decay,
            clarify_mode,
            decay_mode,
            reasons_json,
            snapshot_json,
        ) in rows:
            try:
                reasons = json.loads(reasons_json) if reasons_json else []
            except Exception:
                reasons = []
            try:
                snapshot = json.loads(snapshot_json) if snapshot_json else {}
            except Exception:
                snapshot = {}

            output.append(
                {
                    "id": int(row_id),
                    "timestamp": float(timestamp or 0.0),
                    "source": str(source or "runtime"),
                    "base_clarify_threshold": float(base_clarify or 0.62),
                    "base_decay_hours": float(base_decay or 120.0),
                    "recommended_clarify_threshold": float(rec_clarify or 0.62),
                    "recommended_decay_hours": float(rec_decay or 120.0),
                    "clarify_mode": str(clarify_mode or "stable"),
                    "decay_mode": str(decay_mode or "stable"),
                    "reasons": reasons,
                    "snapshot": snapshot,
                }
            )
        return output

    def policy_history_summary(self, window: int = 20) -> Dict[str, Any]:
        """Provide compact trend summary for recent adaptive-policy history."""
        entries = self.get_policy_history(limit=max(1, min(int(window), 100)))
        if not entries:
            return {
                "count": 0,
                "avg_clarify_threshold": 0.0,
                "avg_decay_hours": 0.0,
                "last_clarify_threshold": None,
                "last_decay_hours": None,
                "clarify_trend": "stable",
                "decay_trend": "stable",
            }

        clarify_values = [float(item.get("recommended_clarify_threshold", 0.62) or 0.62) for item in entries]
        decay_values = [float(item.get("recommended_decay_hours", 120.0) or 120.0) for item in entries]
        newest = entries[0]
        oldest = entries[-1]

        clarify_delta = float(newest.get("recommended_clarify_threshold", 0.62) or 0.62) - float(oldest.get("recommended_clarify_threshold", 0.62) or 0.62)
        decay_delta = float(newest.get("recommended_decay_hours", 120.0) or 120.0) - float(oldest.get("recommended_decay_hours", 120.0) or 120.0)

        clarify_trend = "stable"
        if clarify_delta > 0.02:
            clarify_trend = "up"
        elif clarify_delta < -0.02:
            clarify_trend = "down"

        decay_trend = "stable"
        if decay_delta > 3.0:
            decay_trend = "up"
        elif decay_delta < -3.0:
            decay_trend = "down"

        return {
            "count": len(entries),
            "avg_clarify_threshold": sum(clarify_values) / len(clarify_values),
            "avg_decay_hours": sum(decay_values) / len(decay_values),
            "last_clarify_threshold": float(newest.get("recommended_clarify_threshold", 0.62) or 0.62),
            "last_decay_hours": float(newest.get("recommended_decay_hours", 120.0) or 120.0),
            "clarify_trend": clarify_trend,
            "decay_trend": decay_trend,
        }

    @staticmethod
    def _count_direction_flips(values: List[float], epsilon: float = 0.005) -> int:
        if len(values) < 3:
            return 0

        signs: List[int] = []
        for idx in range(1, len(values)):
            delta = float(values[idx]) - float(values[idx - 1])
            if abs(delta) <= epsilon:
                continue
            signs.append(1 if delta > 0 else -1)

        if len(signs) < 2:
            return 0

        flips = 0
        for idx in range(1, len(signs)):
            if signs[idx] != signs[idx - 1]:
                flips += 1
        return flips

    @staticmethod
    def _count_distinct_signals(values: List[Any]) -> int:
        seen: set[str] = set()
        for value in values:
            signal = str(value or "").strip().lower()
            if signal:
                seen.add(signal)
        return len(seen)

    def policy_guardrail_status(self, window: int = 10) -> Dict[str, Any]:
        """Return oscillation and drift risk indicators from policy history."""
        entries = self.get_policy_history(limit=self._resolve_policy_guard_window(window))
        if not entries:
            return {
                "count": 0,
                "clarify_sign_flips": 0,
                "decay_sign_flips": 0,
                "risk_level": "low",
                "last_clarify_threshold": None,
                "last_decay_hours": None,
            }

        chronological = list(reversed(entries))
        clarify_values = [float(item.get("recommended_clarify_threshold", 0.62) or 0.62) for item in chronological]
        decay_values = [float(item.get("recommended_decay_hours", 120.0) or 120.0) for item in chronological]

        clarify_flips = self._count_direction_flips(clarify_values, epsilon=0.005)
        decay_flips = self._count_direction_flips(decay_values, epsilon=0.5)
        max_flips = max(clarify_flips, decay_flips)

        risk_level = "low"
        if max_flips >= 4:
            risk_level = "high"
        elif max_flips >= 2:
            risk_level = "medium"

        latest = entries[0]
        return {
            "count": len(entries),
            "clarify_sign_flips": clarify_flips,
            "decay_sign_flips": decay_flips,
            "risk_level": risk_level,
            "last_clarify_threshold": float(latest.get("recommended_clarify_threshold", 0.62) or 0.62),
            "last_decay_hours": float(latest.get("recommended_decay_hours", 120.0) or 120.0),
        }

    def apply_policy_guardrails(
        self,
        report: Dict[str, Any],
        source: str = "runtime",
        window: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Stabilize policy updates to reduce oscillation under fast-changing feedback."""
        stabilized = dict(report)
        raw_clarify = self._safe_float(stabilized.get("recommended_clarify_threshold", 0.62), 0.62)
        raw_decay = self._safe_float(stabilized.get("recommended_decay_hours", 120.0), 120.0)
        guard_reasons: List[str] = []

        history_window = self._resolve_policy_guard_window(window)
        entries = self.get_policy_history(limit=history_window)
        if not entries:
            stabilized["raw_recommended_clarify_threshold"] = raw_clarify
            stabilized["raw_recommended_decay_hours"] = raw_decay
            stabilized["recommended_clarify_threshold"] = max(0.35, min(raw_clarify, 0.90))
            stabilized["recommended_decay_hours"] = max(24.0, min(raw_decay, 24.0 * 20.0))
            stabilized["guardrail_applied"] = False
            stabilized["guardrail_reasons"] = guard_reasons
            stabilized["guardrail_window"] = history_window
            stabilized["guardrail_source"] = source
            return stabilized

        last_entry = entries[0]
        last_ts = self._safe_float(last_entry.get("timestamp", 0.0), 0.0)
        last_clarify = self._safe_float(last_entry.get("recommended_clarify_threshold", raw_clarify), raw_clarify)
        last_decay = self._safe_float(last_entry.get("recommended_decay_hours", raw_decay), raw_decay)

        max_clarify_step = self._resolve_policy_guard_clarify_step(None)
        max_decay_step = self._resolve_policy_guard_decay_step_hours(None)
        cooldown_s = self._resolve_policy_guard_cooldown_seconds(None)

        bounded_clarify = max(last_clarify - max_clarify_step, min(raw_clarify, last_clarify + max_clarify_step))
        bounded_decay = max(last_decay - max_decay_step, min(raw_decay, last_decay + max_decay_step))
        if abs(bounded_clarify - raw_clarify) > 1e-6 or abs(bounded_decay - raw_decay) > 1e-6:
            guard_reasons.append("step_clamp")

        chrono = list(reversed(entries))
        clarify_values = [float(item.get("recommended_clarify_threshold", last_clarify) or last_clarify) for item in chrono]
        decay_values = [float(item.get("recommended_decay_hours", last_decay) or last_decay) for item in chrono]
        clarify_flips = self._count_direction_flips(clarify_values + [bounded_clarify], epsilon=0.005)
        decay_flips = self._count_direction_flips(decay_values + [bounded_decay], epsilon=0.5)
        if max(clarify_flips, decay_flips) >= 2:
            bounded_clarify = (0.70 * last_clarify) + (0.30 * bounded_clarify)
            bounded_decay = (0.70 * last_decay) + (0.30 * bounded_decay)
            guard_reasons.append("oscillation_dampening")

        now_ts = time.time()
        if cooldown_s > 0 and last_ts > 0 and (now_ts - last_ts) < cooldown_s:
            bounded_clarify = (0.85 * last_clarify) + (0.15 * bounded_clarify)
            bounded_decay = (0.85 * last_decay) + (0.15 * bounded_decay)
            guard_reasons.append("cooldown_blend")

        final_clarify = max(0.35, min(float(bounded_clarify), 0.90))
        final_decay = max(24.0, min(float(bounded_decay), 24.0 * 20.0))

        stabilized["raw_recommended_clarify_threshold"] = raw_clarify
        stabilized["raw_recommended_decay_hours"] = raw_decay
        stabilized["recommended_clarify_threshold"] = final_clarify
        stabilized["recommended_decay_hours"] = final_decay
        stabilized["guardrail_applied"] = len(guard_reasons) > 0
        stabilized["guardrail_reasons"] = guard_reasons
        stabilized["guardrail_window"] = history_window
        stabilized["guardrail_source"] = source
        stabilized["guardrail_last_timestamp"] = last_ts
        stabilized["guardrail_last_clarify_threshold"] = last_clarify
        stabilized["guardrail_last_decay_hours"] = last_decay
        return stabilized

    def _procedure_health_score(
        self,
        confidence: float,
        timestamp: float,
        usage_count: int,
        success_count: int,
        failure_count: int,
        last_used: float,
        now_ts: float,
    ) -> float:
        conf = self._clamp(float(confidence))

        anchor_ts = float(last_used or 0)
        if anchor_ts <= 0:
            anchor_ts = float(timestamp or 0)

        recency = self._decay_factor(now_ts - anchor_ts, self._decay_half_life_hours())

        usage_norm = min(max(int(usage_count), 0), 40) / 40.0
        attempts = max(0, int(success_count)) + max(0, int(failure_count))
        reliability = (max(0, int(success_count)) / attempts) if attempts > 0 else 0.5

        score = (
            0.35 * conf
            + 0.35 * recency
            + 0.15 * reliability
            + 0.15 * usage_norm
        )
        return self._clamp(score)

    def _procedure_rank_score(
        self,
        query_tokens: List[str],
        trigger: str,
        confidence: float,
        timestamp: float,
        usage_count: int,
        success_count: int,
        failure_count: int,
        last_used: float,
        now_ts: float,
    ) -> float:
        trigger_tokens = self._tokenize_terms(trigger)
        if not query_tokens or not trigger_tokens:
            return 0.0

        qset = set(query_tokens)
        tset = set(trigger_tokens)
        overlap = len(qset & tset)
        if overlap == 0:
            return 0.0

        coverage = overlap / max(1, len(qset))
        precision = overlap / max(1, len(tset))
        semantic = (0.65 * coverage) + (0.35 * precision)

        conf = self._clamp(float(confidence))

        half_life_h = self._decay_half_life_hours()
        recency = self._decay_factor(now_ts - float(timestamp or 0), half_life_h)

        usage_norm = min(max(int(usage_count), 0), 20) / 20.0
        if last_used and float(last_used) > 0:
            usage_recency = self._decay_factor(now_ts - float(last_used), half_life_h)
        else:
            usage_recency = 0.0

        attempts = max(0, int(success_count)) + max(0, int(failure_count))
        reliability = (max(0, int(success_count)) / attempts) if attempts > 0 else 0.5

        score = (
            0.45 * semantic
            + 0.20 * conf
            + 0.15 * recency
            + 0.10 * reliability
            + 0.10 * ((0.6 * usage_norm) + (0.4 * usage_recency))
        )

        if " ".join(query_tokens) in trigger.lower():
            score += 0.08

        return self._clamp(score)

    def memorize(self, topic: str, content: str, source: str = "auto_teacher", importance: int = 5) -> bool:
        """Menanamkan fakta/data baru ke dalam Agentic RAG."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO rag_memory (topic, content, source, timestamp, importance) VALUES (?, ?, ?, ?, ?)",
                    (topic, content, source, time.time(), importance)
                )
                conn.commit()
            logger.info(f"[Agentic RAG] Memorized new fact about: {topic}")
            return True
        except Exception as e:
            logger.error(f"[Agentic RAG] Failed to memorize: {e}")
            return False

    def recall(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Mengambil data dari ingatan menggunakan Full Text Search (FTS5)."""
        results = []
        try:
            safe_limit = int(limit)
        except Exception:
            safe_limit = 3
        if safe_limit <= 0:
            return results
        safe_limit = min(safe_limit, 50)

        try:
            with sqlite3.connect(self.db_path) as conn:
                # MATCH query syntax for FTS5
                # Sanitize query by removing non-alphanumeric chars for robust FTS5 matching
                clean_query = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(query))
                # Simple prefix search for every word
                fts_query = " OR ".join([f"{w}*" for w in clean_query.split() if len(w) > 2])

                if not fts_query:
                    return results

                cursor = conn.execute(
                    "SELECT topic, content, source, importance FROM rag_memory WHERE rag_memory MATCH ? ORDER BY rank, importance DESC LIMIT ?",
                    (fts_query, safe_limit)
                )
                for row in cursor.fetchall():
                    results.append({
                        "topic": row[0],
                        "content": row[1],
                        "source": row[2],
                        "importance": row[3]
                    })
        except Exception as e:
            logger.warning(f"[Agentic RAG] Recall failed for query '{query}': {e}")

        return results

    def recall_with_graph(self, query: str, limit: int = 3, graph_hop: int = 1) -> Dict[str, Any]:
        """Mengambil teks (FTS5) sekalian dengan Graph Traversal (Hop) otonom."""
        results = {"facts": self.recall(query, limit), "graph_context": []}

        # Ekstraksi kata penting dari query untuk graph search
        query_terms = [w.lower() for w in query.replace('"', '').replace("'", "").split() if len(w) > 2]
        if not query_terms:
            return results

        try:
            with sqlite3.connect(self.db_path) as conn:
                # 1. Cari Node Entry Pertama
                placeholders = " OR ".join(["source_node LIKE ? OR target_node LIKE ?"] * len(query_terms))
                params = []
                for term in query_terms:
                    params.extend([f"%{term}%", f"%{term}%"])

                cursor = conn.execute(f'''
                    SELECT source_node, relation, target_node
                    FROM semantic_graph
                    WHERE {placeholders}
                    LIMIT 20
                ''', params)

                edges = cursor.fetchall()
                for s, p, o in edges:
                    results["graph_context"].append(f"{s} --[{p}]--> {o}")

        except Exception as e:
            logger.warning(f"[Agentic RAG] Graph recall failed: {e}")

        return results

    def add_graph_edges(self, triples: List[List[str]]) -> int:
        """Menambahkan koneksi relasional [S, P, O] (Memori Asosiatif)."""
        added = 0
        try:
            with sqlite3.connect(self.db_path) as conn:
                for triple in triples:
                    if len(triple) == 3:
                        s, p, o = triple
                        conn.execute('''
                            INSERT OR IGNORE INTO semantic_graph (source_node, relation, target_node)
                            VALUES (?, ?, ?)
                        ''', (s.lower().strip(), p.lower().strip(), o.lower().strip()))
                        added += 1
                conn.commit()
            if added > 0:
                logger.info(f"[Agentic RAG] Tersambung {added} koneksi sinapsis memori baru.")
        except Exception as e:
            logger.error(f"[Agentic RAG] Graph injection failed: {e}")
        return added

    def check_topic_exists(self, topic: str) -> bool:
        """Pillar 2: Resource Aware. Mengecek apakah topik sudah dipelajari sebelumnya."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT 1 FROM rag_memory WHERE topic = ? LIMIT 1", (topic,))
                return cursor.fetchone() is not None
        except Exception:
            return False

    def memorize_procedure(
        self,
        trigger: str,
        steps: List[str],
        language: str = "id",
        source: str = "manual",
        confidence: float = 0.75,
        timestamp_override: Optional[float] = None,
        preserve_usage: bool = True,
        only_if_missing: bool = False,
    ) -> bool:
        """Store a compact procedural capsule for step-based problem solving."""
        clean_trigger = trigger.strip().lower()
        clean_steps = [s.strip() for s in steps if isinstance(s, str) and s.strip()]
        clean_language = (language or "id").strip().lower()
        clipped_conf = max(0.0, min(1.0, float(confidence)))

        if not clean_trigger or not clean_steps:
            return False

        try:
            with sqlite3.connect(self.db_path) as conn:
                existing = conn.execute(
                    """
                    SELECT usage_count, success_count, failure_count, last_used
                    FROM procedural_memory
                    WHERE trigger = ? AND language = ?
                    LIMIT 1
                    """,
                    (clean_trigger, clean_language),
                ).fetchone()

                if existing and only_if_missing:
                    return True

                usage_count = int(existing[0]) if (existing and preserve_usage) else 0
                success_count = int(existing[1]) if (existing and preserve_usage) else 0
                failure_count = int(existing[2]) if (existing and preserve_usage) else 0
                last_used = float(existing[3]) if (existing and preserve_usage) else 0.0

                # Keep latest capsule per trigger-language to stay compact.
                conn.execute(
                    "DELETE FROM procedural_memory WHERE trigger = ? AND language = ?",
                    (clean_trigger, clean_language),
                )
                conn.execute(
                    """
                    INSERT INTO procedural_memory
                    (
                        trigger, steps_json, language, source,
                        confidence, timestamp, usage_count, success_count,
                        failure_count, last_used
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean_trigger,
                        json.dumps(clean_steps, ensure_ascii=False),
                        clean_language,
                        source,
                        clipped_conf,
                        float(timestamp_override) if timestamp_override is not None else time.time(),
                        usage_count,
                        success_count,
                        failure_count,
                        last_used,
                    ),
                )
                conn.commit()
            logger.info("[Agentic RAG] Memorized procedure capsule: %s", clean_trigger)
            return True
        except Exception as e:
            logger.error("[Agentic RAG] Failed to memorize procedure: %s", e)
            return False

    def recall_procedure(
        self,
        query: str,
        language: Optional[str] = None,
        limit: int = 2,
    ) -> List[Dict[str, Any]]:
        """Retrieve procedural capsules ranked by semantic overlap + decay + usage success."""
        try:
            safe_limit = int(limit)
        except Exception:
            safe_limit = 2
        if safe_limit <= 0:
            return []
        safe_limit = min(safe_limit, 20)

        tokens = self._tokenize_terms(query)
        if not tokens:
            return []

        where_tokens = " OR ".join(["LOWER(trigger) LIKE ?" for _ in tokens])
        params: List[Any] = [f"%{tok}%" for tok in tokens]

        lang_clause = ""
        if language is not None:
            clean_language = str(language).strip().lower()
            if clean_language:
                lang_clause = " AND language = ?"
                params.append(clean_language)

        candidate_limit = max(safe_limit * 6, 8)
        params.append(candidate_limit)
        sql = (
            """
            SELECT
                id, trigger, steps_json, language, source,
                confidence, timestamp, usage_count, success_count,
                failure_count, last_used
            """
            "FROM procedural_memory "
            f"WHERE ({where_tokens}){lang_clause} "
            "ORDER BY confidence DESC, timestamp DESC LIMIT ?"
        )

        ranked: List[Dict[str, Any]] = []
        now_ts = time.time()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(sql, params)
                for (
                    row_id,
                    trigger,
                    steps_json,
                    lang,
                    source,
                    confidence,
                    timestamp,
                    usage_count,
                    success_count,
                    failure_count,
                    last_used,
                ) in cursor.fetchall():
                    try:
                        steps_data = json.loads(steps_json)
                    except Exception:
                        steps_data = []
                    steps = [str(s).strip() for s in steps_data if str(s).strip()]
                    if not steps:
                        continue
                    score = self._procedure_rank_score(
                        query_tokens=tokens,
                        trigger=str(trigger),
                        confidence=float(confidence),
                        timestamp=float(timestamp or 0),
                        usage_count=int(usage_count or 0),
                        success_count=int(success_count or 0),
                        failure_count=int(failure_count or 0),
                        last_used=float(last_used or 0),
                        now_ts=now_ts,
                    )
                    if score <= 0:
                        continue

                    reliability = self._clamp(
                        0.55 + (0.15 * min(int(success_count or 0), 5)) - (0.12 * min(int(failure_count or 0), 5))
                    )
                    recency_bonus = self._clamp(
                        self._decay_factor(now_ts - float(last_used or timestamp or 0), self._decay_half_life_hours())
                    )
                    score = self._clamp((0.82 * score) + (0.10 * reliability) + (0.08 * recency_bonus))

                    ranked.append(
                        {
                            "id": int(row_id),
                            "trigger": trigger,
                            "steps": steps,
                            "language": lang,
                            "source": source,
                            "confidence": float(confidence),
                            "score": float(score),
                            "usage_count": int(usage_count or 0),
                            "success_count": int(success_count or 0),
                            "failure_count": int(failure_count or 0),
                            "last_used": float(last_used or 0),
                        }
                    )
        except Exception as e:
            logger.warning("[Agentic RAG] Procedure recall failed for '%s': %s", query, e)

        ranked.sort(key=lambda item: (-item["score"], -item["confidence"]))
        return ranked[:safe_limit]

    def record_procedure_usage(self, procedure_id: int, success: bool = True) -> bool:
        """Record usage feedback so frequently successful procedures rank higher over time."""
        if procedure_id <= 0:
            return False
        now_ts = time.time()
        success_inc = 1 if success else 0
        failure_inc = 0 if success else 1
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    UPDATE procedural_memory
                    SET
                        usage_count = COALESCE(usage_count, 0) + 1,
                        success_count = COALESCE(success_count, 0) + ?,
                        failure_count = COALESCE(failure_count, 0) + ?,
                        last_used = ?
                    WHERE id = ?
                    """,
                    (success_inc, failure_inc, now_ts, procedure_id),
                )
                conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.warning("[Agentic RAG] Failed recording procedure usage id=%s: %s", procedure_id, e)
            return False

    def apply_procedure_feedback(
        self,
        query: str,
        success: bool = True,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply explicit user feedback to the best matching procedure for a query."""
        candidates = self.recall_procedure(query, language=language, limit=1)
        if not candidates:
            return {
                "ok": False,
                "message": "no_procedure_match",
                "query": query,
                "success": bool(success),
            }

        target = candidates[0]
        procedure_id = int(target.get("id", 0) or 0)
        if procedure_id <= 0:
            return {
                "ok": False,
                "message": "invalid_procedure_id",
                "query": query,
                "success": bool(success),
            }

        updated = self.record_procedure_usage(procedure_id, success=success)
        if not updated:
            return {
                "ok": False,
                "message": "usage_update_failed",
                "query": query,
                "success": bool(success),
                "procedure_id": procedure_id,
            }

        usage_count = int(target.get("usage_count", 0) or 0) + 1
        success_count = int(target.get("success_count", 0) or 0) + (1 if success else 0)
        failure_count = int(target.get("failure_count", 0) or 0) + (0 if success else 1)
        last_used = float(time.time())

        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    """
                    SELECT usage_count, success_count, failure_count, last_used
                    FROM procedural_memory
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (procedure_id,),
                ).fetchone()
            if row:
                usage_count = int(row[0] or usage_count)
                success_count = int(row[1] or success_count)
                failure_count = int(row[2] or failure_count)
                last_used = float(row[3] or last_used)
        except Exception:
            pass

        return {
            "ok": True,
            "message": "feedback_applied",
            "query": query,
            "success": bool(success),
            "procedure_id": procedure_id,
            "trigger": str(target.get("trigger") or ""),
            "usage_count": usage_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "last_used": last_used,
        }

    def procedural_stats_snapshot(self, top_n: int = 5) -> Dict[str, Any]:
        """Return a concise snapshot of procedural-memory health and usage."""
        top_n = max(1, min(int(top_n), 20))
        now_ts = time.time()
        stale_days = self._resolve_stale_days(None)
        min_health = self._resolve_min_health(None)

        rows: List[tuple[Any, ...]] = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT
                        id, trigger, language, confidence, timestamp,
                        usage_count, success_count, failure_count, last_used
                    FROM procedural_memory
                    """
                ).fetchall()
        except Exception as e:
            logger.warning("[Agentic RAG] Failed to build procedure stats snapshot: %s", e)
            return {
                "total_capsules": 0,
                "by_language": {},
                "avg_confidence": 0.0,
                "avg_usage": 0.0,
                "total_usage": 0,
                "success_rate": 0.0,
                "stale_candidates": 0,
                "top_capsules": [],
            }

        by_language: Dict[str, int] = {}
        total_conf = 0.0
        total_usage = 0
        total_success = 0
        total_failure = 0
        stale_candidates = 0
        scored: List[Dict[str, Any]] = []

        for (
            row_id,
            trigger,
            language,
            confidence,
            timestamp,
            usage_count,
            success_count,
            failure_count,
            last_used,
        ) in rows:
            lang = str(language or "unknown")
            by_language[lang] = by_language.get(lang, 0) + 1

            conf = float(confidence or 0.0)
            usage = int(usage_count or 0)
            succ = int(success_count or 0)
            fail = int(failure_count or 0)
            ts = float(timestamp or 0.0)
            last = float(last_used or 0.0)

            total_conf += conf
            total_usage += usage
            total_success += succ
            total_failure += fail

            health = self._procedure_health_score(
                confidence=conf,
                timestamp=ts,
                usage_count=usage,
                success_count=succ,
                failure_count=fail,
                last_used=last,
                now_ts=now_ts,
            )

            anchor_ts = last if last > 0 else ts
            age_days = max(0.0, (now_ts - anchor_ts) / 86400.0)
            if age_days > stale_days and (usage == 0 or health < min_health):
                stale_candidates += 1

            scored.append(
                {
                    "id": int(row_id),
                    "trigger": str(trigger),
                    "language": lang,
                    "usage_count": usage,
                    "confidence": conf,
                    "health": float(health),
                }
            )

        total = len(rows)
        attempts = total_success + total_failure
        success_rate = (total_success / attempts) if attempts > 0 else 0.0

        scored.sort(key=lambda item: (-item["usage_count"], -item["health"], -item["confidence"]))

        return {
            "total_capsules": total,
            "by_language": by_language,
            "avg_confidence": (total_conf / total) if total > 0 else 0.0,
            "avg_usage": (total_usage / total) if total > 0 else 0.0,
            "total_usage": total_usage,
            "success_rate": success_rate,
            "stale_candidates": stale_candidates,
            "top_capsules": scored[:top_n],
        }

    def suggest_adaptive_policy(
        self,
        clarify_threshold: Optional[float] = None,
        decay_hours: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Suggest lightweight adaptive tuning based on procedural-memory health."""
        base_clarify = self._resolve_clarify_threshold(clarify_threshold)
        if decay_hours is None:
            base_decay = self._decay_half_life_hours()
        else:
            base_decay = max(12.0, min(self._safe_float(decay_hours, self._decay_half_life_hours()), 24.0 * 30.0))

        snapshot = self.procedural_stats_snapshot(top_n=5)
        total = int(snapshot.get("total_capsules", 0) or 0)
        avg_conf = float(snapshot.get("avg_confidence", 0.0) or 0.0)
        avg_usage = float(snapshot.get("avg_usage", 0.0) or 0.0)
        success_rate = float(snapshot.get("success_rate", 0.0) or 0.0)
        stale_candidates = int(snapshot.get("stale_candidates", 0) or 0)
        stale_ratio = (stale_candidates / total) if total > 0 else 0.0

        tuned_clarify = base_clarify
        tuned_decay = base_decay
        reasons: List[str] = []

        # Sparse signals need stricter clarification to avoid brittle assumptions.
        if total < 6 or avg_usage < 0.40:
            tuned_clarify -= 0.08
            reasons.append("sparse_memory_signal")

        if stale_ratio >= 0.25:
            tuned_decay *= 0.75
            tuned_clarify -= 0.05
            reasons.append("stale_ratio_high")

        if success_rate <= 0.45 and total >= 4:
            tuned_clarify -= 0.07
            reasons.append("low_success_rate")

        if success_rate >= 0.80 and avg_conf >= 0.70 and avg_usage >= 1.0:
            tuned_clarify += 0.06
            tuned_decay *= 1.15
            reasons.append("reliable_procedures")

        distinct_capsules = self._count_distinct_signals(
            [item.get("trigger") for item in snapshot.get("top_capsules", [])]
        )
        if total >= 4 and distinct_capsules <= 2 and avg_usage < 0.80:
            tuned_clarify -= 0.04
            reasons.append("low_diversity_signal")

        tuned_clarify = max(0.35, min(tuned_clarify, 0.90))
        tuned_decay = max(24.0, min(tuned_decay, 24.0 * 20.0))

        clarify_mode = "stable"
        if tuned_clarify < (base_clarify - 0.01):
            clarify_mode = "more_clarification"
        elif tuned_clarify > (base_clarify + 0.01):
            clarify_mode = "less_clarification"

        decay_mode = "stable"
        if tuned_decay < (base_decay - 0.5):
            decay_mode = "faster_forgetting"
        elif tuned_decay > (base_decay + 0.5):
            decay_mode = "longer_retention"

        return {
            "base_clarify_threshold": float(base_clarify),
            "base_decay_hours": float(base_decay),
            "recommended_clarify_threshold": float(tuned_clarify),
            "recommended_decay_hours": float(tuned_decay),
            "clarify_mode": clarify_mode,
            "decay_mode": decay_mode,
            "reasons": reasons,
            "snapshot": {
                "total_capsules": total,
                "avg_confidence": avg_conf,
                "avg_usage": avg_usage,
                "success_rate": success_rate,
                "stale_candidates": stale_candidates,
                "stale_ratio": stale_ratio,
                "distinct_top_triggers": distinct_capsules,
            },
        }

    def apply_adaptive_policy(
        self,
        clarify_threshold: Optional[float] = None,
        decay_hours: Optional[float] = None,
        source: str = "runtime",
    ) -> Dict[str, Any]:
        """Apply adaptive policy suggestions to runtime environment variables."""
        report = self.suggest_adaptive_policy(
            clarify_threshold=clarify_threshold,
            decay_hours=decay_hours,
        )
        report = self.apply_policy_guardrails(report, source=source)

        previous_clarify = os.getenv("JAYA_CLARIFY_THRESHOLD")
        previous_decay = os.getenv("JAYA_PROCEDURE_DECAY_HOURS")

        safe_clarify = max(0.35, min(self._safe_float(report.get("recommended_clarify_threshold"), 0.62), 0.90))
        safe_decay = max(24.0, min(self._safe_float(report.get("recommended_decay_hours"), 120.0), 24.0 * 20.0))
        report["recommended_clarify_threshold"] = safe_clarify
        report["recommended_decay_hours"] = safe_decay

        os.environ["JAYA_CLARIFY_THRESHOLD"] = f"{safe_clarify:.2f}"
        os.environ["JAYA_PROCEDURE_DECAY_HOURS"] = f"{safe_decay:.1f}"

        history_written = self._append_policy_history(report, source=source)
        report["applied"] = True
        report["history_written"] = history_written
        report["previous_clarify_threshold"] = previous_clarify
        report["previous_decay_hours"] = previous_decay
        return report

    def prune_procedures(
        self,
        max_items: Optional[int] = None,
        stale_days: Optional[float] = None,
        min_health: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Prune stale and low-value procedural capsules to keep memory compact."""
        max_keep = self._resolve_procedure_max_items(max_items)
        stale_cut_days = self._resolve_stale_days(stale_days)
        min_keep_health = self._resolve_min_health(min_health)
        now_ts = time.time()

        rows: List[tuple[Any, ...]] = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT
                        id, trigger, confidence, timestamp,
                        usage_count, success_count, failure_count, last_used
                    FROM procedural_memory
                    """
                ).fetchall()
        except Exception as e:
            logger.warning("[Agentic RAG] Failed to load procedures for pruning: %s", e)
            return {
                "ok": False,
                "error": str(e),
                "max_items": max_keep,
                "stale_days": stale_cut_days,
                "min_health": min_keep_health,
            }

        if not rows:
            return {
                "ok": True,
                "before": 0,
                "after": 0,
                "removed_total": 0,
                "removed_stale": 0,
                "removed_overflow": 0,
                "max_items": max_keep,
                "stale_days": stale_cut_days,
                "min_health": min_keep_health,
            }

        enriched: List[Dict[str, Any]] = []
        for row_id, trigger, confidence, timestamp, usage_count, success_count, failure_count, last_used in rows:
            usage = int(usage_count or 0)
            health = self._procedure_health_score(
                confidence=float(confidence or 0.0),
                timestamp=float(timestamp or 0.0),
                usage_count=usage,
                success_count=int(success_count or 0),
                failure_count=int(failure_count or 0),
                last_used=float(last_used or 0.0),
                now_ts=now_ts,
            )
            anchor_ts = float(last_used or 0.0)
            if anchor_ts <= 0:
                anchor_ts = float(timestamp or 0.0)
            age_days = max(0.0, (now_ts - anchor_ts) / 86400.0)
            is_stale = age_days > stale_cut_days and (usage == 0 or health < min_keep_health)
            enriched.append(
                {
                    "id": int(row_id),
                    "trigger": str(trigger),
                    "health": health,
                    "usage": usage,
                    "anchor_ts": anchor_ts,
                    "is_stale": is_stale,
                }
            )

        stale_ids = [item["id"] for item in enriched if item["is_stale"]]
        stale_id_set = set(stale_ids)
        remaining = [item for item in enriched if item["id"] not in stale_id_set]

        overflow_ids: List[int] = []
        overflow = max(0, len(remaining) - max_keep)
        if overflow > 0:
            remaining_sorted = sorted(
                remaining,
                key=lambda item: (item["health"], item["usage"], item["anchor_ts"]),
            )
            overflow_ids = [item["id"] for item in remaining_sorted[:overflow]]

        remove_ids = stale_ids + overflow_ids
        if remove_ids:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    for chunk_start in range(0, len(remove_ids), 200):
                        chunk = remove_ids[chunk_start: chunk_start + 200]
                        placeholders = ",".join(["?"] * len(chunk))
                        conn.execute(
                            f"DELETE FROM procedural_memory WHERE id IN ({placeholders})",
                            chunk,
                        )
                    conn.commit()
            except Exception as e:
                logger.warning("[Agentic RAG] Failed pruning procedures: %s", e)
                return {
                    "ok": False,
                    "error": str(e),
                    "before": len(rows),
                    "after": len(rows),
                    "removed_total": 0,
                    "removed_stale": 0,
                    "removed_overflow": 0,
                    "max_items": max_keep,
                    "stale_days": stale_cut_days,
                    "min_health": min_keep_health,
                }

        after_count = len(rows) - len(remove_ids)
        return {
            "ok": True,
            "before": len(rows),
            "after": after_count,
            "removed_total": len(remove_ids),
            "removed_stale": len(stale_ids),
            "removed_overflow": len(overflow_ids),
            "max_items": max_keep,
            "stale_days": stale_cut_days,
            "min_health": min_keep_health,
            "remaining_total": after_count,
        }

    def tidy_up(self) -> Dict[str, Any]:
        """
        [Otonomi JAYA]
        JAYA memanggil ini sendiri saat CPU Idle untuk 'merapikan' ingatannya.
        Ini menghapus ingatan duplikat, dan meringkas (jika ada AI terhubung).
        Untuk versi ringan, ia melakukan defragmentasi SQLite dan menghapus data redundan / sampah.
        """
        logger.info("[Agentic RAG] Initiating Self-Tidy Up phase...")
        start_time = time.time()
        prune_report = self.prune_procedures()
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            # 1. Optimize FTS index
            conn.execute("INSERT INTO rag_memory(rag_memory) VALUES('optimize')")
            # 2. Vacuum to reclaim space (Lightweight OS principle)
            conn.execute("VACUUM")

            # (Di masa depan, JAYA bisa membaca isi RAG, merangkumnya lewat API, dan menuliskannya kembali)

        duration = time.time() - start_time
        logger.info(f"[Agentic RAG] Tidy up complete in {duration:.2f}s.")
        return {
            "status": "optimized",
            "duration_s": duration,
            "procedural_prune": prune_report,
            "procedural_stats": self.procedural_stats_snapshot(top_n=3),
        }
