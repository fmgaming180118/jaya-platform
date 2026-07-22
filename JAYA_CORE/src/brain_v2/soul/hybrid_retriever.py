"""
Fase 2 — HybridRetriever: Micro-GraphRAG + Hybrid BM25 + Dense Vector Retrieval
=================================================================================

Modul pengetahuan utama JAYA_CORE untuk Fase 2 Ultra-Intelligence.

Architecture
------------
  BM25SparseIndex     — SQLite FTS5 full-text sparse keyword search.
  DenseVectorIndex    — all-MiniLM-L6-v2 (23 MB) sentence-transformer embeddings
                        stored as float32 blobs in SQLite.
  HybridRetriever     — Reciprocal Rank Fusion (RRF) gabungan BM25 + Dense.
  MicroGraphRAG       — SQLite entity-relation knowledge graph dengan multi-hop traversal.
  
Hard Constraint: embedding model < 25 MB, total db < 30 MB.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("HybridRetriever")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = str(Path(__file__).resolve().parents[4] / "data" / "hybrid_rag.db")
EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"  # ~23 MB
EMBEDDING_DIM = 384
RRF_K = 60  # RRF constant (standard = 60)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _blob_to_vec(blob: bytes) -> List[float]:
    """Deserialize float32 blob → Python list[float]."""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _vec_to_blob(vec: List[float]) -> bytes:
    """Serialize list[float] → float32 blob."""
    return struct.pack(f"{len(vec)}f", *vec)


def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


def _tokenize_bm25(text: str) -> List[str]:
    """Simple tokenizer untuk BM25 index."""
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return [w for w in text.split() if len(w) > 1]


# ---------------------------------------------------------------------------
# BM25 Sparse Index (SQLite FTS5)
# ---------------------------------------------------------------------------

class BM25SparseIndex:
    """
    BM25-style full-text search using SQLite FTS5.
    Zero external dependencies, berjalan sepenuhnya di dalam SQLite.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS bm25_chunks USING fts5(
                chunk_id UNINDEXED,
                title,
                body,
                source UNINDEXED,
                tokenize='porter unicode61'
            )
        """)
        self._conn.commit()

    def add(self, chunk_id: str, title: str, body: str, source: str = "") -> None:
        """Index one chunk."""
        self._conn.execute(
            "INSERT INTO bm25_chunks(chunk_id, title, body, source) VALUES (?, ?, ?, ?)",
            (chunk_id, title, body, source),
        )
        self._conn.commit()

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """BM25 ranked search; returns list of {chunk_id, title, body, score}."""
        if not query.strip():
            return []
        # FTS5 MATCH returns results ordered by BM25 by default
        fts_query = " OR ".join(_tokenize_bm25(query)) or query
        try:
            rows = self._conn.execute(
                """
                SELECT chunk_id, title, body, source,
                       bm25(bm25_chunks) AS score
                FROM bm25_chunks
                WHERE bm25_chunks MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        return [
            {"chunk_id": r[0], "title": r[1], "body": r[2], "source": r[3], "bm25_score": float(r[4])}
            for r in rows
        ]

    def count(self) -> int:
        try:
            return self._conn.execute("SELECT COUNT(*) FROM bm25_chunks").fetchone()[0]
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Dense Vector Index (all-MiniLM-L6-v2, stored in SQLite)
# ---------------------------------------------------------------------------

class DenseVectorIndex:
    """
    Dense vector index using all-MiniLM-L6-v2 (23 MB).
    Embeddings stored as float32 blobs in SQLite — no external vector DB needed.
    
    Cosine similarity computed in pure Python (suitable for < 10K chunks).
    For larger corpora, can be swapped to faiss-cpu without interface changes.
    """

    def __init__(self, conn: sqlite3.Connection, cache_dir: Optional[str] = None) -> None:
        self._conn = conn
        self._cache_dir = cache_dir or str(Path.home() / ".cache" / "jaya_models")
        self._model = None
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS dense_chunks (
                chunk_id TEXT PRIMARY KEY,
                title    TEXT,
                body     TEXT,
                source   TEXT,
                embedding BLOB NOT NULL
            )
        """)
        self._conn.commit()

    def _load_model(self) -> bool:
        """Lazy-load all-MiniLM-L6-v2."""
        if self._model is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("[DenseVectorIndex] Loading all-MiniLM-L6-v2 (~23 MB)...")
            self._model = SentenceTransformer(
                EMBEDDING_MODEL_ID,
                cache_folder=self._cache_dir,
            )
            logger.info("[DenseVectorIndex] Embedding model ready.")
            return True
        except ImportError:
            logger.warning("[DenseVectorIndex] sentence-transformers not installed. Falling back to TF-IDF sim.")
            return False
        except Exception as e:
            logger.error("[DenseVectorIndex] Load failed: %s", e)
            return False

    def _embed(self, text: str) -> Optional[List[float]]:
        if not self._load_model():
            return None
        try:
            vec = self._model.encode(text, normalize_embeddings=True)
            return vec.tolist()
        except Exception as e:
            logger.error("[DenseVectorIndex] Embed error: %s", e)
            return None

    def add(self, chunk_id: str, title: str, body: str, source: str = "") -> bool:
        """Embed and store one chunk."""
        text = f"{title}. {body}" if title else body
        vec = self._embed(text)
        if vec is None:
            return False
        self._conn.execute(
            """INSERT OR REPLACE INTO dense_chunks(chunk_id, title, body, source, embedding)
               VALUES (?, ?, ?, ?, ?)""",
            (chunk_id, title, body, source, _vec_to_blob(vec)),
        )
        self._conn.commit()
        return True

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Cosine similarity search against all stored chunks."""
        q_vec = self._embed(query)
        if q_vec is None:
            return []

        rows = self._conn.execute(
            "SELECT chunk_id, title, body, source, embedding FROM dense_chunks"
        ).fetchall()

        scored = []
        for chunk_id, title, body, source, blob in rows:
            if blob:
                d_vec = _blob_to_vec(blob)
                score = _cosine(q_vec, d_vec)
                scored.append({
                    "chunk_id": chunk_id,
                    "title": title,
                    "body": body,
                    "source": source,
                    "dense_score": score,
                })

        scored.sort(key=lambda x: x["dense_score"], reverse=True)
        return scored[:limit]

    def count(self) -> int:
        try:
            return self._conn.execute("SELECT COUNT(*) FROM dense_chunks").fetchone()[0]
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Micro-GraphRAG (SQLite Entity-Relation Knowledge Graph)
# ---------------------------------------------------------------------------

class MicroGraphRAG:
    """
    SQLite Micro-GraphRAG — Entity-Relation knowledge graph dengan multi-hop traversal.
    
    Digunakan untuk menjawab pertanyaan seperti:
      "Siapa yang menulis paper tentang federated learning yang direferensi BAB II?"
    
    100% SQLite, zero external dependencies.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS kg_nodes (
                node_id   TEXT PRIMARY KEY,
                label     TEXT NOT NULL,
                node_type TEXT DEFAULT 'concept',
                metadata  TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS kg_edges (
                edge_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                src        TEXT NOT NULL,
                relation   TEXT NOT NULL,
                dst        TEXT NOT NULL,
                weight     REAL DEFAULT 1.0,
                source_doc TEXT DEFAULT '',
                UNIQUE(src, relation, dst)
            );
            CREATE INDEX IF NOT EXISTS idx_kg_edges_src ON kg_edges(src);
            CREATE INDEX IF NOT EXISTS idx_kg_edges_dst ON kg_edges(dst);
        """)
        self._conn.commit()

    def add_node(self, node_id: str, label: str, node_type: str = "concept", metadata: Optional[Dict] = None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO kg_nodes(node_id, label, node_type, metadata) VALUES (?, ?, ?, ?)",
            (node_id, label, node_type, json.dumps(metadata or {})),
        )
        self._conn.commit()

    def add_edge(self, src: str, relation: str, dst: str, weight: float = 1.0, source_doc: str = "") -> None:
        """Add a directed relation edge. Auto-creates nodes if missing."""
        for nid in (src, dst):
            self._conn.execute(
                "INSERT OR IGNORE INTO kg_nodes(node_id, label) VALUES (?, ?)", (nid, nid)
            )
        self._conn.execute(
            """INSERT OR REPLACE INTO kg_edges(src, relation, dst, weight, source_doc)
               VALUES (?, ?, ?, ?, ?)""",
            (src, relation, dst, weight, source_doc),
        )
        self._conn.commit()

    def neighbors(self, node_id: str, max_hops: int = 2, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Multi-hop BFS traversal from node_id up to max_hops.
        Returns list of {node, relation, hop, weight}.
        """
        visited = {node_id}
        frontier = [(node_id, 0)]
        results = []

        while frontier:
            current, hop = frontier.pop(0)
            if hop >= max_hops:
                continue
            edges = self._conn.execute(
                "SELECT dst, relation, weight FROM kg_edges WHERE src = ? LIMIT 50",
                (current,),
            ).fetchall()
            for dst, relation, weight in edges:
                if dst not in visited:
                    visited.add(dst)
                    results.append({
                        "node": dst,
                        "relation": relation,
                        "from": current,
                        "hop": hop + 1,
                        "weight": weight,
                    })
                    frontier.append((dst, hop + 1))
                    if len(results) >= limit:
                        return results
        return results

    def query_path(self, src: str, dst: str, max_hops: int = 3) -> Optional[List[str]]:
        """Find shortest relation path from src to dst (BFS)."""
        if src == dst:
            return [src]
        frontier = [(src, [src])]
        visited = {src}
        for _ in range(max_hops * 50):
            if not frontier:
                break
            current, path = frontier.pop(0)
            edges = self._conn.execute(
                "SELECT dst FROM kg_edges WHERE src = ? LIMIT 20", (current,)
            ).fetchall()
            for (neighbor,) in edges:
                if neighbor not in visited:
                    new_path = path + [neighbor]
                    if neighbor == dst:
                        return new_path
                    visited.add(neighbor)
                    frontier.append((neighbor, new_path))
        return None

    def extract_entities_from_text(self, text: str, source_doc: str = "") -> int:
        """
        Heuristic entity extraction dari teks bebas.
        Deteksi pola: "X adalah Y", "X merupakan Y", "X oleh Y", "X berkaitan dengan Y"
        Return: jumlah entitas yang diekstrak.
        """
        patterns = [
            (r"(\w[\w\s]{2,30})\s+adalah\s+([\w\s]{2,40})", "adalah"),
            (r"(\w[\w\s]{2,30})\s+merupakan\s+([\w\s]{2,40})", "merupakan"),
            (r"(\w[\w\s]{2,30})\s+oleh\s+([\w\s]{2,40})", "oleh"),
            (r"(\w[\w\s]{2,30})\s+berkaitan\s+dengan\s+([\w\s]{2,40})", "berkaitan_dengan"),
            (r"(\w[\w\s]{2,30})\s+menggunakan\s+([\w\s]{2,40})", "menggunakan"),
            (r"(\w[\w\s]{2,30})\s+terdiri\s+dari\s+([\w\s]{2,40})", "terdiri_dari"),
        ]
        count = 0
        for pattern, relation in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                src = match.group(1).strip().lower()[:60]
                dst = match.group(2).strip().lower()[:60]
                if len(src) > 2 and len(dst) > 2:
                    self.add_edge(src, relation, dst, source_doc=source_doc)
                    count += 1
        return count

    def stats(self) -> Dict[str, int]:
        return {
            "nodes": self._conn.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0],
            "edges": self._conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0],
        }


# ---------------------------------------------------------------------------
# HybridRetriever — RRF Fusion of BM25 + Dense + GraphRAG
# ---------------------------------------------------------------------------

class HybridRetriever:
    """
    Fase 2 — Hybrid Retrieval-Augmented Generation Engine.

    Menggabungkan:
      1. BM25 sparse keyword search (SQLite FTS5)
      2. Dense semantic vector search (all-MiniLM-L6-v2, 23 MB)
      3. MicroGraphRAG entity-relation traversal
      via Reciprocal Rank Fusion (RRF, k=60).

    Hard constraint: < 30 MB total (embedding model 23 MB + SQLite DB < 7 MB).
    """

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        cache_dir: Optional[str] = None,
    ) -> None:
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")

        self._bm25 = BM25SparseIndex(self._conn)
        self._dense = DenseVectorIndex(self._conn, cache_dir=cache_dir)
        self._graph = MicroGraphRAG(self._conn)

        logger.info("[HybridRetriever] Initialized | db=%s", db_path)

    def add_document(
        self,
        doc_id: str,
        title: str,
        body: str,
        source: str = "",
        extract_graph: bool = True,
    ) -> Dict[str, Any]:
        """
        Tambah satu dokumen ke semua indeks sekaligus.
        Otomatis extract entity untuk knowledge graph.
        """
        # BM25 index (always available)
        self._bm25.add(doc_id, title, body, source)

        # Dense vector index (requires sentence-transformers)
        dense_ok = self._dense.add(doc_id, title, body, source)

        # Graph entity extraction
        entity_count = 0
        if extract_graph:
            entity_count = self._graph.extract_entities_from_text(body, source_doc=doc_id)

        return {
            "doc_id": doc_id,
            "bm25_indexed": True,
            "dense_indexed": dense_ok,
            "entities_extracted": entity_count,
        }

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        bm25_weight: float = 0.5,
        dense_weight: float = 0.5,
        graph_hops: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid RRF retrieval: BM25 + Dense + optional GraphRAG context.

        Returns top-`limit` results sorted by RRF fusion score, each with:
          {chunk_id, title, body, source, rrf_score, bm25_rank, dense_rank, graph_context}
        """
        # 1. BM25 results
        bm25_results = self._bm25.search(query, limit=limit * 3)
        bm25_rank = {r["chunk_id"]: i + 1 for i, r in enumerate(bm25_results)}

        # 2. Dense results
        dense_results = self._dense.search(query, limit=limit * 3)
        dense_rank = {r["chunk_id"]: i + 1 for i, r in enumerate(dense_results)}

        # 3. RRF fusion
        all_ids = set(bm25_rank.keys()) | set(dense_rank.keys())
        scored = {}
        for cid in all_ids:
            b_rank = bm25_rank.get(cid, 9999)
            d_rank = dense_rank.get(cid, 9999)
            rrf = (bm25_weight / (RRF_K + b_rank)) + (dense_weight / (RRF_K + d_rank))
            scored[cid] = rrf

        # 4. Reconstruct results with metadata
        meta: Dict[str, Dict[str, Any]] = {}
        for r in bm25_results:
            meta[r["chunk_id"]] = r
        for r in dense_results:
            if r["chunk_id"] not in meta:
                meta[r["chunk_id"]] = r

        top = sorted(scored.items(), key=lambda x: x[1], reverse=True)[:limit]

        results = []
        for cid, rrf_score in top:
            m = meta.get(cid, {})
            entry: Dict[str, Any] = {
                "chunk_id": cid,
                "title": m.get("title", ""),
                "body": m.get("body", ""),
                "source": m.get("source", ""),
                "rrf_score": round(rrf_score, 6),
                "bm25_rank": bm25_rank.get(cid, None),
                "dense_rank": dense_rank.get(cid, None),
                "graph_context": [],
            }

            # 5. Optional GraphRAG context enrichment
            if graph_hops > 0:
                entity_query = query.lower().strip()[:60]
                neighbors = self._graph.neighbors(entity_query, max_hops=graph_hops, limit=3)
                entry["graph_context"] = [
                    f"{n['from']} --[{n['relation']}]--> {n['node']}" for n in neighbors
                ]

            results.append(entry)

        logger.debug("[HybridRetriever] Retrieved %d results for query: '%s'", len(results), query[:50])
        return results

    def retrieve_facts(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Convenience wrapper compatible with AgenticRAG.retrieve_facts() call signature.
        Returns list of {'content': str, 'source': str, 'score': float}.
        """
        results = self.retrieve(query, limit=limit)
        return [
            {
                "content": f"{r['title']}. {r['body']}".strip(". ") if r['title'] else r['body'],
                "source": r["source"],
                "score": r["rrf_score"],
                "graph_context": r["graph_context"],
            }
            for r in results
        ]

    def add_knowledge(self, topic: str, content: str, source: str = "manual") -> Dict[str, Any]:
        """Add a knowledge fact (compatibility with AgenticRAG.add_knowledge interface)."""
        doc_id = f"know_{hash(topic + content) & 0xFFFFFF:06x}"
        return self.add_document(doc_id, title=topic, body=content, source=source)

    def status(self) -> Dict[str, Any]:
        return {
            "db_path": self._db_path,
            "bm25_chunks": self._bm25.count(),
            "dense_chunks": self._dense.count(),
            "graph": self._graph.stats(),
            "embedding_model": EMBEDDING_MODEL_ID,
        }

    def __del__(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
