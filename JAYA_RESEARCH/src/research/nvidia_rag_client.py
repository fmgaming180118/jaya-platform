"""
NVIDIARAGClient — Production RAG client using NVIDIA embeddings + FAISS.
Implements the interface expected by the research API and thesis analyzer.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import config
from research.enhanced_rag import (
    NVIDIAEmbeddings,
    VectorStore,
    _embedding_provenance,
    _extract_pdf_pages,
    _format_query_response,
    _read_text_file,
    chunk_pages,
    chunk_text,
)

logger = logging.getLogger(__name__)


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
        dim = (
            self.embedder.dimension
            if self.embedder
            else int(os.getenv("RAG_EMBED_DIMENSION", "1024"))
        )

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
        except (ImportError, RuntimeError) as exc:
            logger.warning("Web search integration is unavailable: %s", exc)

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
        """Embed texts using the configured remote or explicitly local adapter."""
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
            self.vector_store.delete_by_source(str(source), ws_id)

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
                return {
                    "status": "error",
                    "message": f"Could not extract PDF: {file_path}",
                    "chunks_added": 0,
                    "workspace_id": ws_id,
                }
            chunks = chunk_pages(pages, base_metadata=metadata)
        else:
            text = _read_text_file(file_path)
            chunks = chunk_text(text, base_metadata=metadata)

        if not chunks:
            return {"status": "empty", "chunks_added": 0, "workspace_id": ws_id}

        result = self._index_chunks(chunks, ws_id)
        result["file_path"] = file_path
        return result

    def _index_chunks(
        self, chunks: List[Dict[str, Any]], workspace_id: str
    ) -> Dict[str, Any]:
        texts = [c["content"] for c in chunks]

        if not self.embedder:
            self.embedder = NVIDIAEmbeddings()

        provenance = _embedding_provenance(self.embedder)
        metas = []
        for chunk in chunks:
            metadata = dict(chunk["metadata"])
            metadata["embedding"] = provenance
            metas.append(metadata)

        embeddings = self.embedder.embed_texts(texts)
        added = self.vector_store.add_chunks(texts, embeddings, metas)

        return {
            "status": "success",
            "chunks_added": added,
            "workspace_id": workspace_id,
        }

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

        if self.vector_store.count(ws_id) == 0:
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
        if (rerank or self.rerank_enabled) and results:
            results = self._rerank_results(query, results, top_k)

        return results[:top_k]

    def _rerank_results(
        self, query: str, results: List[Dict], top_k: int
    ) -> List[Dict]:
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

        return _format_query_response(local_results, web_results)

    # ---------------------------------------------------------------------
    # Utility
    # ---------------------------------------------------------------------
    def list_documents(self) -> List[Dict[str, str]]:
        stats = self.vector_store.stats(self.workspace_id)
        return [
            {"name": src, "type": "indexed_chunk_source", "path": src}
            for src in stats.get("sources", [])
        ]

    def get_stats(self) -> Dict[str, Any]:
        return self.vector_store.stats(self.workspace_id)

    def delete_by_source(self, source_id: str) -> int:
        return self.vector_store.delete_by_source(source_id, self.workspace_id)


# Backward compatibility alias
RAGClient = NVIDIARAGClient
