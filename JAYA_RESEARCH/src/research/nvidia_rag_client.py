"""
NVIDIARAGClient — Production RAG client using NVIDIA embeddings + FAISS.
Implements the interface expected by the research API and thesis analyzer.
"""
from __future__ import annotations

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

from config import config
from research.enhanced_rag import (
    NVIDIAEmbeddings,
    VectorStore,
    clean_text,
    chunk_text,
    chunk_pages,
    _extract_pdf_pages,
    _read_text_file,
    _normalize_vectors,
)


class NVIDIARAGClient:
    """
    High-level RAG client that provides:
    - embed(texts) -> List[List[float]]
    - ingest_text(text, metadata, workspace_id) -> Dict
    - search(query, top_k, workspace_id, rerank) -> List[Dict]
    - query(query_text, top_k, web_fallback) -> Dict (for voice agent compatibility)
    """

    def __init__(
        self,
        vector_store_path: Optional[str] = None,
        workspace_id: str = "default",
        use_embeddings: bool = True,
        rerank_enabled: bool = False,
    ):
        self.workspace_id = workspace_id
        self.use_embeddings = use_embeddings
        self.rerank_enabled = rerank_enabled

        # Resolve store directory
        store_dir = self._resolve_store_dir(vector_store_path)
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

        # Initialize embedder
        self.embedder = NVIDIAEmbeddings() if use_embeddings else None
        dim = self.embedder.dimension if self.embedder else int(os.getenv("RAG_EMBED_DIMENSION", "1024"))

        # Initialize vector store (single global index + workspace filter)
        self.vector_store = VectorStore(
            store_dir=str(self.store_dir),
            workspace_id=workspace_id,
            dimension=dim,
        )

        # Web search fallback (optional)
        self.web_search = None
        try:
            from research.web_search import WebSearchClient
            self.web_search = WebSearchClient()
        except Exception:
            pass

    @staticmethod
    def _resolve_store_dir(vector_store_path: Optional[str]) -> str:
        if not vector_store_path:
            base = Path(config.WORKSPACES_DIR) / "default" / "vector_store"
            base.mkdir(parents=True, exist_ok=True)
            return str(base)
        path = Path(vector_store_path)
        if path.suffix == ".json":
            return str(path.with_suffix(""))
        return str(path)

    # ---------------------------------------------------------------------
    # Embedding API
    # ---------------------------------------------------------------------
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts using NVIDIA embeddings (with cache + fallback)."""
        if not texts:
            return []
        if not self.embedder:
            self.embedder = NVIDIAEmbeddings()
        arr = self.embedder.embed_texts(texts)
        return arr.tolist()

    # ---------------------------------------------------------------------
    # Ingestion API
    # ---------------------------------------------------------------------
    def ingest_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingest raw text into the vector store.
        Returns dict with status, chunks_added, workspace_id.
        """
        ws_id = workspace_id or self.workspace_id
        metadata = dict(metadata or {})
        metadata.setdefault("workspace_id", ws_id)

        # Delete existing chunks from same source (idempotent)
        source = metadata.get("source") or metadata.get("file_name")
        if source:
            self.vector_store.delete_by_source(source)

        # Chunk
        chunks = chunk_text(text, base_metadata=metadata)
        if not chunks:
            return {"status": "empty", "chunks_added": 0, "workspace_id": ws_id}

        return self._index_chunks(chunks, ws_id)

    def ingest_file(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ingest a file (PDF or text) into the vector store."""
        ws_id = workspace_id or self.workspace_id
        metadata = dict(metadata or {})
        metadata.setdefault("file_name", os.path.basename(file_path))
        metadata.setdefault("source", metadata["file_name"])
        metadata.setdefault("workspace_id", ws_id)

        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            pages = _extract_pdf_pages(file_path)
            if not pages:
                return {"status": "error", "message": f"Could not extract PDF: {file_path}", "chunks_added": 0}
            chunks = chunk_pages(pages, base_metadata=metadata)
        else:
            text = _read_text_file(file_path)
            chunks = chunk_text(text, base_metadata=metadata)

        if not chunks:
            return {"status": "empty", "chunks_added": 0, "workspace_id": ws_id}

        result = self._index_chunks(chunks, ws_id)
        result["file_path"] = file_path
        return result

    def _index_chunks(self, chunks: List[Dict[str, Any]], workspace_id: str) -> Dict[str, Any]:
        texts = [c["content"] for c in chunks]
        metas = [c["metadata"] for c in chunks]

        if not self.embedder:
            self.embedder = NVIDIAEmbeddings()

        embeddings = self.embedder.embed_texts(texts)
        added = self.vector_store.add_chunks(texts, embeddings, metas)

        return {"status": "success", "chunks_added": added, "workspace_id": workspace_id}

    # ---------------------------------------------------------------------
    # Search API
    # ---------------------------------------------------------------------
    def search(
        self,
        query: str,
        top_k: int = 5,
        workspace_id: Optional[str] = None,
        rerank: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search with optional reranking.
        Returns list of dicts with: content, score, metadata, snippet, document.
        """
        ws_id = workspace_id or self.workspace_id

        if self.vector_store.count() == 0:
            return []

        if not self.embedder:
            self.embedder = NVIDIAEmbeddings()

        query_vec = self.embedder.embed_texts([query])
        results = self.vector_store.search(
            query_vec,
            top_k=top_k,
            filters={"workspace_id": ws_id},
        )

        # Optional rerank (placeholder for Nemotron reranker integration)
        if rerank and results:
            results = self._rerank_results(query, results, top_k)

        return results[:top_k]

    def _rerank_results(self, query: str, results: List[Dict], top_k: int) -> List[Dict]:
        """Placeholder for Nemotron reranker integration."""
        # TODO: Integrate NVIDIA Nemotron reranker API
        # For now, return as-is (already sorted by FAISS score)
        return results

    # ---------------------------------------------------------------------
    # High-level Query API (compatible with voice agent / tests)
    # ---------------------------------------------------------------------
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        web_fallback: bool = True,
    ) -> Dict[str, Any]:
        """
        High-level query with optional web search fallback.
        Returns dict with 'answer' and 'sources'.
        """
        local_results = self.search(query_text, top_k=top_k)
        best_score = local_results[0]["score"] if local_results else 0.0

        use_web = (
            web_fallback
            and self.web_search
            and self.web_search.is_available()
            and (not local_results or best_score < 0.55)
        )

        web_results: List[Dict] = []
        if use_web:
            web_results = self.web_search.search(query_text, max_results=top_k)

        parts: List[str] = []
        sources: List[str] = []

        if local_results:
            parts.append("**Local Research Data:**")
            for r in local_results:
                doc = r.get("document", {})
                name = doc.get("file_name") or doc.get("source", "document")
                parts.append(f"- [{name}] {r.get('snippet', '')}")
                sources.append(name)

        if web_results:
            parts.append("**Web Search Results:**")
            for r in web_results:
                doc = r.get("document", {})
                title = doc.get("title", "Web")
                parts.append(f"- [{title}] {r.get('snippet', '')}")
                sources.append(doc.get("url", title))

        if not parts:
            return {"answer": "No relevant context found.", "sources": []}

        return {"answer": "\n".join(parts), "sources": sources}

    # ---------------------------------------------------------------------
    # Utility
    # ---------------------------------------------------------------------
    def list_documents(self) -> List[Dict[str, str]]:
        stats = self.vector_store.stats()
        return [
            {"name": src, "type": "indexed_chunk_source", "path": src}
            for src in stats.get("sources", [])
        ]

    def get_stats(self) -> Dict[str, Any]:
        return self.vector_store.stats()

    def delete_by_source(self, source_id: str) -> int:
        return self.vector_store.delete_by_source(source_id)


# Backward compatibility alias
RAGClient = NVIDIARAGClient