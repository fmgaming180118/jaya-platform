"""
Enhanced RAG Client with NVIDIA Embeddings, FAISS VectorStore, and PDF Chunking.
"""
from __future__ import annotations

import os
import re
import json
import time
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

from config import config


def clean_text(text: str) -> str:
    """Normalize whitespace and remove null characters."""
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Splits text into overlapping chunks by word boundaries."""
    text = clean_text(text)
    if not text:
        return []
    words = text.split(" ")
    if len(words) <= chunk_size:
        return [text]
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i:i + chunk_size]
        chunks.append(" ".join(chunk_words))
        i += chunk_size - overlap
    return chunks


def chunk_pages(pages: List[Dict[str, Any]], chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, Any]]:
    """Chunks list of page dictionaries preserving page metadata."""
    chunked = []
    for p in pages:
        page_num = p.get("page_num", 1)
        text = p.get("text", "")
        for idx, chunk_str in enumerate(chunk_text(text, chunk_size, overlap)):
            chunked.append({
                "content": chunk_str,
                "metadata": {
                    "page_num": page_num,
                    "chunk_index": idx,
                    "source": p.get("source", "unknown")
                }
            })
    return chunked


def _extract_pdf_pages(file_path: str) -> List[Dict[str, Any]]:
    """Extract text page by page from PDF using PyPDF2 or pypdf fallback."""
    pages = []
    try:
        import PyPDF2
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                pages.append({"page_num": idx + 1, "text": text, "source": os.path.basename(file_path)})
    except Exception:
        # Fallback raw text read
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                pages.append({"page_num": 1, "text": f.read(), "source": os.path.basename(file_path)})
        except Exception:
            pass
    return pages


def _read_text_file(file_path: str) -> str:
    """Reads plain text file."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _normalize_vectors(v: np.ndarray) -> np.ndarray:
    """L2 normalize vectors for cosine similarity in FAISS."""
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (v / norms).astype(np.float32)


class NVIDIAEmbeddings:
    """NVIDIA NIM API Embeddings client with local fallback."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.base_url = base_url or os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self.model = os.getenv("NVIDIA_EMBEDDING_MODEL", "nvidia/nv-embed-v1")
        self.dimension = 1024

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        """Embed list of document texts."""
        if not texts:
            return np.zeros((0, 1024), dtype=np.float32)

        # Truncate texts for safety
        cleaned = [clean_text(t)[:1000] for t in texts]
        
        if self.api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                url = f"{self.base_url.rstrip('/')}/embeddings"
                payload = {"input": cleaned[:16], "model": self.model}
                resp = requests.post(url, headers=headers, json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    embeds = [d["embedding"] for d in data["data"]]
                    vecs = np.array(embeds, dtype=np.float32)
                    return _normalize_vectors(vecs)
            except Exception as e:
                print(f"[NVIDIAEmbeddings] NIM API fallback: {e}")

        # Deterministic lightweight fallback embedding
        dim = 1024
        vecs = []
        for text in cleaned:
            seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**32)
            rng = np.random.RandomState(seed)
            vec = rng.randn(dim).astype(np.float32)
            vecs.append(vec)
        return _normalize_vectors(np.array(vecs))

    def embed_query(self, text: str) -> np.ndarray:
        """Embed single query string."""
        return self.embed_documents([text])[0]


class VectorStore:
    """FAISS-backed vector store for document records."""

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self._records: List[Dict[str, Any]] = []
        if faiss is not None:
            self._index = faiss.IndexFlatIP(dim)
        else:
            self._index = None

    def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None, embeddings: Optional[np.ndarray] = None):
        if not texts:
            return
        metadatas = metadatas or [{} for _ in texts]
        if embeddings is None:
            embedder = NVIDIAEmbeddings()
            embeddings = embedder.embed_documents(texts)

        if self._index is not None and len(embeddings) > 0:
            self._index.add(_normalize_vectors(embeddings))

        for text, meta in zip(texts, metadatas):
            self._records.append({"content": text, "metadata": meta})


class EnhancedRAGClient:
    """
    Enhanced RAG Client for JAYA Research ecosystem.
    Integrates FAISS VectorStore, NVIDIA Embeddings, and metadata search filters.
    """

    def __init__(self, vector_store_path: Optional[str] = None, workspace_id: str = "default"):
        self.workspace_id = workspace_id
        self.vector_store_path = vector_store_path
        self.store = VectorStore(dim=1024)
        self.embedder = NVIDIAEmbeddings()
        self._records = self.store._records
        self._index = self.store._index

    def search(
        self, query_embedding: np.ndarray, top_k: int = 5, filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if self._index is None or self._index.ntotal == 0:
            return []
        filters = filters or {}
        required_workspace = filters.get("workspace_id", self.workspace_id)
        q = _normalize_vectors(np.asarray(query_embedding, dtype=np.float32).reshape(1, -1))
        fetch_k = min(max(top_k * 4, top_k), self._index.ntotal)
        scores, indices = self._index.search(q, fetch_k)
        results: List[Dict[str, Any]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._records):
                continue
            record = self._records[idx]
            meta = record.get("metadata", {})
            if meta.get("workspace_id", self.workspace_id) != required_workspace:
                continue
            content = record.get("content", "")
            results.append({
                "content": content,
                "score": float(score),
                "metadata": meta,
                "document": meta,
                "snippet": content[:400] + ("..." if len(content) > 400 else ""),
            })
            if len(results) >= top_k:
                break
        return results