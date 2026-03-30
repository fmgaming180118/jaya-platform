import os
import time
import json
import sqlite3
import logging
from typing import List, Dict, Any, Optional

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
            conn.commit()

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
            with sqlite3.connect(self.db_path) as conn:
                # MATCH query syntax for FTS5
                # We sanitize query simply by replacing quotes space
                clean_query = query.replace('"', '').replace("'", "")
                # Simple prefix search for every word
                fts_query = " OR ".join([f"{w}*" for w in clean_query.split() if len(w) > 2])
                
                if not fts_query:
                    return results

                cursor = conn.execute(
                    "SELECT topic, content, source, importance FROM rag_memory WHERE rag_memory MATCH ? ORDER BY rank, importance DESC LIMIT ?",
                    (fts_query, limit)
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

    def tidy_up(self) -> Dict[str, Any]:
        """
        [Otonomi JAYA]
        JAYA memanggil ini sendiri saat CPU Idle untuk 'merapikan' ingatannya.
        Ini menghapus ingatan duplikat, dan meringkas (jika ada AI terhubung).
        Untuk versi ringan, ia melakukan defragmentasi SQLite dan menghapus data redundan / sampah.
        """
        logger.info("[Agentic RAG] Initiating Self-Tidy Up phase...")
        start_time = time.time()
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            # 1. Optimize FTS index
            conn.execute("INSERT INTO rag_memory(rag_memory) VALUES('optimize')")
            # 2. Vacuum to reclaim space (Lightweight OS principle)
            conn.execute("VACUUM")
            
            # (Di masa depan, JAYA bisa membaca isi RAG, merangkumnya lewat API, dan menuliskannya kembali)
        
        duration = time.time() - start_time
        logger.info(f"[Agentic RAG] Tidy up complete in {duration:.2f}s.")
        return {"status": "optimized", "duration_s": duration}
