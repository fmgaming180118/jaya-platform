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

from jaya_core.library.ast_parser import parse_python_file, parse_python_repo, CodeSymbol
from jaya_core.paths import core_data_dir
from jaya_core.rag.enhanced import get_rag_pipeline, Document

class LibraryManager:
    def __init__(self, db_path: str | Path | None = None):
        self.catalog = get_rag_pipeline()
        self.db_path = str(
            Path(db_path) if db_path is not None else core_data_dir() / "library.db"
        )
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._load_from_db()
        
    def _load_from_db(self):
        """Loads existing documents from SQLite into the BM25 catalog to ensure persistence across restarts."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            try:
                cur.execute("SELECT doc_id, content, metadata_json FROM documents")
                rows = cur.fetchall()
                for row in rows:
                    doc_id, content, metadata_json = row
                    metadata = json.loads(metadata_json) if metadata_json else {}
                    
                    # Check if already in catalog to avoid duplicates
                    if doc_id not in self.catalog.search_engine.bm25_index.documents:
                        doc = Document(id=doc_id, content=content, metadata=metadata)
                        self.catalog.add_document(doc)
            except sqlite3.OperationalError:
                pass # Tables might not exist yet
        
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
            conn.execute('''
                CREATE TABLE IF NOT EXISTS code_symbols (
                    symbol_id TEXT PRIMARY KEY,
                    source_id TEXT,
                    file_path TEXT,
                    symbol_name TEXT,
                    symbol_type TEXT,
                    content TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS code_edges (
                    edge_id TEXT PRIMARY KEY,
                    source_symbol_id TEXT,
                    target_symbol_id TEXT,
                    relation_type TEXT
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
        symbols = parse_python_file(source_id, file_path, source_code, version)
        self._store_symbols(source_id, version, symbols)

    def add_python_repo(self, source_id: str, repo_path: str, version: str = "v1"):
        """Adds a whole repository with cross-file graph resolution."""
        symbols = parse_python_repo(source_id, repo_path, version)
        self._store_symbols(source_id, version, symbols)
        
    def _store_symbols(self, source_id: str, version: str, symbols: List[CodeSymbol]):
        with sqlite3.connect(self.db_path) as conn:
            for sym in symbols:
                doc = Document(
                    id=sym.canonical_id,
                    content=sym.to_document_text(),
                    metadata={
                        "source_id": source_id,
                        "version": version,
                        "file_path": sym.file_path,
                        "symbol_name": sym.symbol_name,
                        "symbol_type": sym.symbol_type,
                        "type": "code_symbol"
                    }
                )
                self.catalog.add_document(doc)
                
                # documents table
                conn.execute("INSERT OR REPLACE INTO documents (doc_id, source_id, content, metadata_json) VALUES (?, ?, ?, ?)",
                             (doc.id, source_id, doc.content, json.dumps(doc.metadata)))
                             
                # code_symbols table
                conn.execute("INSERT OR REPLACE INTO code_symbols (symbol_id, source_id, file_path, symbol_name, symbol_type, content) VALUES (?, ?, ?, ?, ?, ?)",
                             (sym.canonical_id, source_id, sym.file_path, sym.symbol_name, sym.symbol_type, sym.to_document_text()))
                             
                # code_edges table
                for target_id in sym.calls:
                    edge_id = f"{sym.canonical_id}->{target_id}:CALLS"
                    conn.execute("INSERT OR REPLACE INTO code_edges (edge_id, source_symbol_id, target_symbol_id, relation_type) VALUES (?, ?, ?, ?)",
                                 (edge_id, sym.canonical_id, target_id, "CALLS"))
                                 
                for test_id in sym.tests:
                    edge_id = f"{test_id}->{sym.canonical_id}:TESTS"
                    conn.execute("INSERT OR REPLACE INTO code_edges (edge_id, source_symbol_id, target_symbol_id, relation_type) VALUES (?, ?, ?, ?)",
                                 (edge_id, test_id, sym.canonical_id, "TESTS"))
            
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
