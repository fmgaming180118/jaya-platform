"""
JAYA Library Manager
Manages Non-Parametric Knowledge (books, source code) independently of the model.
Integrates with JayaCatalog (enhanced.py) and AST Parser for code semantification.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import hashlib
import time

import sqlite3

from JAYA_CORE.src.library.ast_parser import parse_python_file, CodeSymbol
from JAYA_CORE.src.rag.enhanced import get_rag_pipeline, Document

class LibraryManager:
    def __init__(self, db_path: str = "JAYA_CORE/data/library.db"):
        self.catalog = get_rag_pipeline()
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    type TEXT,
                    version TEXT,
                    indexed_at REAL,
                    item_count INTEGER
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    source_id TEXT,
                    content TEXT,
                    metadata_json TEXT
                )
            ''')
            
    def _update_source_count(self, source_id: str, type: str, version: str, count: int):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT item_count FROM sources WHERE source_id=?", (source_id,))
            row = cur.fetchone()
            if row:
                conn.execute("UPDATE sources SET item_count = item_count + ?, indexed_at = ? WHERE source_id = ?",
                             (count, time.time(), source_id))
            else:
                conn.execute("INSERT INTO sources (source_id, type, version, indexed_at, item_count) VALUES (?, ?, ?, ?, ?)",
                             (source_id, type, version, time.time(), count))
                             
    def _save_document(self, doc_id: str, source_id: str, content: str, metadata: dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO documents (doc_id, source_id, content, metadata_json) VALUES (?, ?, ?, ?)",
                         (doc_id, source_id, content, json.dumps(metadata)))
        
    def add_document(self, source_id: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Adds a standard document (book, manual) to the Library."""
        metadata = metadata or {}
        metadata["source_id"] = source_id
        
        doc = Document(
            id=f"{source_id}_{hashlib.md5(content.encode()).hexdigest()[:8]}",
            content=content,
            metadata=metadata
        )
        self.catalog.add_document(doc)
        
        self._save_document(doc.id, source_id, content, metadata)
        self._update_source_count(source_id, "document", metadata.get("version", "v1"), 1)
        
    def add_python_code(self, source_id: str, file_path: str, source_code: str, version: str = "v1"):
        """Adds source code, semantically parsed into the Library."""
        symbols = parse_python_file(source_id, file_path, source_code)
        
        for sym in symbols:
            doc = Document(
                id=f"{source_id}:{file_path}#{sym.symbol_name}",
                content=sym.to_document_text(),
                metadata={
                    "source_id": source_id,
                    "version": version,
                    "file_path": file_path,
                    "symbol_name": sym.symbol_name,
                    "symbol_type": sym.symbol_type,
                    "type": "code_symbol"
                }
            )
            self.catalog.add_document(doc)
            
            self._save_document(doc.id, source_id, doc.content, doc.metadata)
            
        self._update_source_count(source_id, "code_repository", version, len(symbols))
        
    def retrieve_evidence(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieves evidence from the catalog for a given query."""
        results = self.catalog.retrieve(query, top_k=top_k, use_expansion=False, use_rerank=False)
        evidence = []
        
        for res in results:
            doc = res.document
            evidence.append({
                "source_id": doc.metadata.get("source_id", "unknown"),
                "content": doc.content,
                "ref_id": doc.id,
                "score": res.score
            })
            
        return evidence
