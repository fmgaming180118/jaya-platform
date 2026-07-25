"""
RAG Vault & Episodic Memory Engine for JAYA_AGENT.
Queries synchronized SQLite agentic_jarvis.db patches and retrieves top relevant knowledge items.
"""

import sys
import os
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional


class RAGMemoryEngine:
    """
    Episodic memory & RAG retriever querying synchronized SQLite patches.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            root_dir = Path(__file__).resolve().parent.parent.parent.parent
            core_db = root_dir / "JAYA_CORE" / "data" / "agentic_jarvis.db"
            research_db = root_dir / "JAYA_RESEARCH" / "data" / "agentic_jarvis.db"
            self.db_path = core_db if core_db.exists() else research_db

        print(f"[RAG MEMORY] Engine bound to SQLite DB: {self.db_path}")

    def query_relevant_patches(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieves top relevant knowledge patches matching user query keywords.
        """
        if not self.db_path.exists():
            return []

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Search keywords
            keywords = [w.lower() for w in query.split() if len(w) > 3]
            if not keywords:
                rows = cursor.execute(
                    "SELECT patch_id, topic, statement, bayes_confidence FROM jarvis_patches "
                    "ORDER BY bayes_confidence DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                where_clause = " OR ".join(["topic LIKE ?" for _ in keywords] + ["statement LIKE ?" for _ in keywords])
                params = [f"%{k}%" for k in keywords] * 2 + [limit]
                sql = (
                    f"SELECT patch_id, topic, statement, bayes_confidence FROM jarvis_patches "
                    f"WHERE {where_clause} ORDER BY bayes_confidence DESC LIMIT ?"
                )
                rows = cursor.execute(sql, params).fetchall()

            results = []
            for r in rows:
                results.append({
                    "patch_id": r["patch_id"],
                    "topic": r["topic"],
                    "statement": r["statement"],
                    "confidence": round(r["bayes_confidence"] * 100, 1)
                })
            conn.close()
            return results
        except Exception as e:
            print(f"[RAG MEMORY] Database query notice: {e}")
            return []
