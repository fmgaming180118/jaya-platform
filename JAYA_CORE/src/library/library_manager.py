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

from JAYA_CORE.src.library.ast_parser import parse_python_file, CodeSymbol
from JAYA_CORE.src.rag.enhanced import get_rag_pipeline, Document

class LibraryManager:
    def __init__(self):
        self.catalog = get_rag_pipeline()
        self.sources: Dict[str, Dict[str, Any]] = {}
        
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
        
        if source_id not in self.sources:
            self.sources[source_id] = {
                "type": "document",
                "version": metadata.get("version", "v1"),
                "indexed_at": time.time(),
                "item_count": 0
            }
        self.sources[source_id]["item_count"] += 1
        
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
            
        if source_id not in self.sources:
            self.sources[source_id] = {
                "type": "code_repository",
                "version": version,
                "indexed_at": time.time(),
                "item_count": 0
            }
        self.sources[source_id]["item_count"] += len(symbols)
        
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
