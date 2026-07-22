"""
Enhanced RAG — FAISS vector store + NVIDIA embeddings (Fase A.1).

Pipeline: clean text → page-aware chunking → embed → FAISS index per workspace.
"""
from __future__ import annotations

import functools
import gc
import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import psutil

from config import config

try:
    import faiss
except ImportError as exc:
    raise ImportError("faiss-cpu is required for Enhanced RAG") from exc

from research.web_search import WebSearchClient

# ---------------------------------------------------------------------------
# Utilities (preserved from original module)
# ---------------------------------------------------------------------------

def profile_memory(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / 1024 / 1024
        result = func(*args, **kwargs)
        mem_after = process.memory_info().rss / 1024 / 1024
        mem_used = mem_after - mem_before
        if mem_used > 50:
            print(f"⚠️ {func.__name__} used {mem_used:.1f}MB RAM")
        return result
    return wrapper


@contextmanager
def memory_guard(threshold_mb: float = 100.0):
    process = psutil.Process(os.getpid())
    try:
        yield
    finally:
        mem_mb = process.memory_info().rss / 1024 / 1024
        if mem_mb > threshold_mb:
            gc.collect()
            mem_after = process.memory_info().rss / 1024 / 1024
            print(f"🧹 GC triggered: {mem_mb:.1f}MB → {mem_after:.1f}MB")


# ---------------------------------------------------------------------------
# Text processing (v5 clean-embed + page-aware chunking)
# ---------------------------------------------------------------------------

_OCR_NOISE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NL = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Remove repeated headers/footers, normalize whitespace, strip OCR noise."""
    if not text:
        return ""

    text = _OCR_NOISE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    pages = re.split(r"\f+|\n-{3,}\s*Page\s+\d+\s*-{3,}\n", text, flags=re.IGNORECASE)
    if len(pages) <= 1:
        pages = text.split("\n\n")

    line_counts: Dict[str, int] = {}
    for page in pages:
        for line in page.split("\n"):
            key = line.strip()
            if len(key) >= 8:
                line_counts[key] = line_counts.get(key, 0) + 1

    threshold = max(2, int(len(pages) * 0.3))
    repeated = {line for line, count in line_counts.items() if count >= threshold}

    cleaned_pages: List[str] = []
    for page in pages if len(pages) > 1 else [text]:
        lines = []
        for line in page.split("\n"):
            if line.strip() in repeated:
                continue
            lines.append(line)
        page_text = "\n".join(lines)
        page_text = _MULTI_SPACE.sub(" ", page_text)
        page_text = _MULTI_NL.sub("\n\n", page_text)
        cleaned_pages.append(page_text.strip())

    return "\n\n".join(p for p in cleaned_pages if p).strip()


def chunk_text(
    text: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    page_number: Optional[int] = None,
    base_metadata: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Split text into overlapping chunks with page metadata."""
    chunk_size = chunk_size or int(os.getenv("RAG_CHUNK_SIZE", "512"))
    chunk_overlap = chunk_overlap or int(os.getenv("RAG_CHUNK_OVERLAP", "128"))
    base_metadata = dict(base_metadata or {})

    text = clean_text(text)
    if not text:
        return []

    chunks: List[Dict[str, Any]] = []
    start = 0
    length = len(text)
    idx = 0

    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            boundary = text.rfind(" ", start, end)
            if boundary > start + chunk_size // 2:
                end = boundary

        content = text[start:end].strip()
        if content:
            meta = {
                **base_metadata,
                "chunk_index": idx,
                "page_number": page_number if page_number is not None else base_metadata.get("page_number", 1),
            }
            chunks.append({"content": content, "metadata": meta})
            idx += 1

        if end >= length:
            break
        start = max(end - chunk_overlap, start + 1)

    return chunks


def chunk_pages(
    pages: List[Tuple[int, str]],
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    base_metadata: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Page-aware chunking — one FAISS entry preserves page boundary context."""
    all_chunks: List[Dict[str, Any]] = []
    for page_num, page_text in pages:
        all_chunks.extend(
            chunk_text(
                page_text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                page_number=page_num,
                base_metadata=base_metadata,
            )
        )
    return all_chunks


def _extract_pdf_pages(file_path: str) -> List[Tuple[int, str]]:
    """Extract per-page text from PDF (PyMuPDF → pdfplumber fallback)."""
    pages: List[Tuple[int, str]] = []

    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        for i, page in enumerate(doc, start=1):
            pages.append((i, page.get_text("text")))
        doc.close()
        if any(t.strip() for _, t in pages):
            return pages
    except Exception:
        pass

    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                pages.append((i, page.extract_text() or ""))
        if any(t.strip() for _, t in pages):
            return pages
    except Exception:
        pass

    return []


def _read_text_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


# ---------------------------------------------------------------------------
# NVIDIA Embeddings
# ---------------------------------------------------------------------------

class NVIDIAEmbeddings:
    """OpenAI-compatible NVIDIA embedding client with batching, cache, and retry."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        batch_size: Optional[int] = None,
        cache_dir: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY") or config.NVIDIA_API_KEY
        self.model = model or os.getenv("NVIDIA_EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5")
        self.batch_size = batch_size or int(os.getenv("RAG_EMBED_BATCH_SIZE", "32"))
        self.cache_dir = Path(cache_dir or (config.DATA_DIR / ".cache" / "embeddings"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._dimension: Optional[int] = None
        self._client = None

        if self.api_key:
            from openai import OpenAI
            base_url = os.getenv("NVIDIA_BASE_URL", config.NVIDIA_BASE_URL)
            self._client = OpenAI(base_url=base_url, api_key=self.api_key)

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = int(os.getenv("RAG_EMBED_DIMENSION", "1024"))
        return self._dimension

    def _cache_path(self, text: str) -> Path:
        key = hashlib.sha256(f"{self.model}:{text}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.json"

    def _load_cache(self, text: str) -> Optional[List[float]]:
        path = self._cache_path(text)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)["embedding"]
            except Exception:
                return None
        return None

    def _save_cache(self, text: str, embedding: List[float]) -> None:
        path = self._cache_path(text)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"embedding": embedding, "model": self.model}, f)

    def _embed_batch_api(self, texts: List[str]) -> np.ndarray:
        if not self._client:
            raise ValueError("NVIDIA_API_KEY required for embedding API calls")

        max_retries = 3
        backoff = 2
        last_err: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                response = self._client.embeddings.create(
                    input=texts,
                    model=self.model,
                    encoding_format="float",
                )
                vectors = [item.embedding for item in response.data]
                if vectors:
                    self._dimension = len(vectors[0])
                return np.array(vectors, dtype=np.float32)
            except Exception as exc:
                last_err = exc
                if attempt < max_retries - 1:
                    time.sleep(backoff ** attempt)

        raise RuntimeError(f"Embedding API failed after {max_retries} attempts: {last_err}")

    def _fallback_embed(self, texts: List[str]) -> np.ndarray:
        """Deterministic pseudo-embeddings for offline dev/tests without API key."""
        dim = self.dimension
        vectors = []
        for text in texts:
            seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**32)
            rng = np.random.RandomState(seed)
            vec = rng.randn(dim).astype(np.float32)
            vectors.append(vec)
        return np.vstack(vectors)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)

        vectors: List[List[float]] = []
        pending: List[str] = []
        pending_indices: List[int] = []

        for i, text in enumerate(texts):
            cached = self._load_cache(text)
            if cached is not None:
                vectors.append(cached)
            else:
                vectors.append([])
                pending.append(text)
                pending_indices.append(i)

        if pending:
            if self._client:
                for batch_start in range(0, len(pending), self.batch_size):
                    batch = pending[batch_start: batch_start + self.batch_size]
                    batch_vecs = self._embed_batch_api(batch)
                    for j, vec in enumerate(batch_vecs):
                        text = pending[batch_start + j]
                        emb = vec.tolist()
                        self._save_cache(text, emb)
                        vectors[pending_indices[batch_start + j]] = emb
            else:
                fallback = self._fallback_embed(pending)
                for j, vec in enumerate(fallback):
                    emb = vec.tolist()
                    self._save_cache(pending[j], emb)
                    vectors[pending_indices[j]] = emb

        arr = np.array(vectors, dtype=np.float32)
        return _normalize_vectors(arr)


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    if vectors.size == 0:
        return vectors
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


# ---------------------------------------------------------------------------
# FAISS Vector Store
# ---------------------------------------------------------------------------

class VectorStore:
    """Per-workspace FAISS index with JSON metadata sidecar."""

    def __init__(self, store_dir: str, workspace_id: str = "default", dimension: Optional[int] = None):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_id = workspace_id
        self.index_path = self.store_dir / "index.faiss"
        self.metadata_path = self.store_dir / "metadata.json"
        self.dimension = dimension or int(os.getenv("RAG_EMBED_DIMENSION", "1024"))
        self._records: List[Dict[str, Any]] = []
        self._index: Optional[faiss.Index] = None
        self._load()

    def _load(self) -> None:
        if self.metadata_path.exists():
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._records = data.get("chunks", [])
                self.dimension = data.get("dimension", self.dimension)

        if self.index_path.exists():
            self._index = faiss.read_index(str(self.index_path))
            if self._index.d != self.dimension:
                print(f"[VectorStore] Dimension mismatch — rebuilding index")
                self._index = faiss.IndexFlatIP(self.dimension)
        else:
            self._index = faiss.IndexFlatIP(self.dimension)

    def _save(self) -> None:
        faiss.write_index(self._index, str(self.index_path))
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "workspace_id": self.workspace_id,
                    "dimension": self.dimension,
                    "chunk_count": len(self._records),
                    "chunks": self._records,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def add_chunks(
        self,
        chunks: List[str],
        embeddings: np.ndarray,
        metadata_list: List[Dict[str, Any]],
    ) -> int:
        if not chunks:
            return 0

        if embeddings.shape[0] != len(chunks):
            raise ValueError("chunks and embeddings length mismatch")

        if self._index is None:
            self._index = faiss.IndexFlatIP(self.dimension)

        if self._index.ntotal == 0 and embeddings.shape[1] != self.dimension:
            self.dimension = embeddings.shape[1]
            self._index = faiss.IndexFlatIP(self.dimension)

        embeddings = _normalize_vectors(np.asarray(embeddings, dtype=np.float32))
        self._index.add(embeddings)

        for content, meta in zip(chunks, metadata_list):
            record = {
                "id": len(self._records),
                "content": content,
                "metadata": {**meta, "workspace_id": meta.get("workspace_id", self.workspace_id)},
            }
            self._records.append(record)

        self._save()
        return len(chunks)

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
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

    def delete_by_source(self, source_id: str) -> int:
        keep_records: List[Dict[str, Any]] = []
        keep_indices: List[int] = []

        for i, record in enumerate(self._records):
            meta = record.get("metadata", {})
            src = meta.get("source") or meta.get("file_name") or meta.get("source_id", "")
            if src != source_id:
                keep_records.append(record)
                keep_indices.append(i)

        removed = len(self._records) - len(keep_records)
        if removed == 0:
            return 0

        self._records = keep_records
        for i, rec in enumerate(self._records):
            rec["id"] = i

        if keep_indices and self.index_path.exists():
            old_index = faiss.read_index(str(self.index_path))
            reconstructor = faiss.downcast_index(old_index)
            if hasattr(reconstructor, "reconstruct"):
                vectors = np.vstack([reconstructor.reconstruct(i) for i in keep_indices]).astype(np.float32)
                self._index = faiss.IndexFlatIP(self.dimension)
                self._index.add(vectors)
            else:
                self._index = faiss.IndexFlatIP(self.dimension)
        else:
            self._index = faiss.IndexFlatIP(self.dimension)

        self._save()
        return removed

    def count(self) -> int:
        return len(self._records)

    def stats(self) -> Dict[str, Any]:
        sources = set()
        for r in self._records:
            m = r.get("metadata", {})
            sources.add(m.get("source") or m.get("file_name") or "unknown")
        return {
            "workspace_id": self.workspace_id,
            "chunk_count": len(self._records),
            "index_total": self._index.ntotal if self._index else 0,
            "dimension": self.dimension,
            "sources": sorted(sources),
        }


# ---------------------------------------------------------------------------
# Enhanced RAG Client
# ---------------------------------------------------------------------------

class EnhancedRAGClient:
    """FAISS + NVIDIA embeddings RAG client with optional web search fallback."""

    WEB_SCORE_THRESHOLD = 0.55

    def __init__(
        self,
        vector_store_path: Optional[str] = None,
        workspace_id: str = "default",
        use_embeddings: bool = True,
    ):
        self.workspace_id = workspace_id
        self.use_embeddings = use_embeddings

        store_dir = self._resolve_store_dir(vector_store_path)
        self.embedder = NVIDIAEmbeddings() if use_embeddings else None
        dim = self.embedder.dimension if self.embedder else int(os.getenv("RAG_EMBED_DIMENSION", "1024"))

        self.vector_store = VectorStore(store_dir, workspace_id=workspace_id, dimension=dim)
        self.web_search = WebSearchClient()

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

    @profile_memory
    def ingest_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata = dict(metadata or {})
        metadata.setdefault("workspace_id", self.workspace_id)
        source = metadata.get("source") or metadata.get("file_name")
        if source:
            self.vector_store.delete_by_source(source)

        chunks = chunk_text(text, base_metadata=metadata)
        if not chunks:
            return {"status": "empty", "chunks_added": 0}

        return self._index_chunks(chunks)

    @profile_memory
    def ingest_file(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata = dict(metadata or {})
        metadata.setdefault("file_name", os.path.basename(file_path))
        metadata.setdefault("source", metadata["file_name"])
        metadata.setdefault("workspace_id", self.workspace_id)

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
            return {"status": "empty", "chunks_added": 0}

        result = self._index_chunks(chunks)
        result["file_path"] = file_path
        return result

    def ingest_documents(self, file_paths: List[str]) -> Dict[str, Any]:
        """Compatibility wrapper used by API/CLI."""
        ingested = 0
        total_chunks = 0
        files: List[str] = []

        for path in file_paths:
            if not os.path.exists(path):
                continue
            result = self.ingest_file(path, metadata={"source": os.path.basename(path)})
            if result.get("chunks_added", 0) > 0:
                ingested += 1
                total_chunks += result["chunks_added"]
                files.append(path)

        return {
            "status": "success" if ingested else "empty",
            "ingested": ingested,
            "chunks": total_chunks,
            "chunks_added": total_chunks,
            "files": files,
        }

    def _index_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        texts = [c["content"] for c in chunks]
        metas = [c["metadata"] for c in chunks]

        with memory_guard():
            if not self.embedder:
                self.embedder = NVIDIAEmbeddings()
            embeddings = self.embedder.embed_texts(texts)
            added = self.vector_store.add_chunks(texts, embeddings, metas)

        return {"status": "success", "chunks_added": added, "workspace_id": self.workspace_id}

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not query.strip():
            return []

        if self.vector_store.count() == 0:
            return []

        if not self.embedder:
            self.embedder = NVIDIAEmbeddings()

        query_vec = self.embedder.embed_texts([query])
        results = self.vector_store.search(
            query_vec,
            top_k=top_k,
            filters={"workspace_id": self.workspace_id},
        )
        return results

    def get_context_for_query(self, query: str, top_k: int = 5) -> str:
        results = self.search(query, top_k=top_k)
        if not results:
            return ""
        parts = []
        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            src = meta.get("file_name") or meta.get("source", "doc")
            page = meta.get("page_number", "?")
            parts.append(f"[{i}] ({src}, p.{page})\n{r.get('content', r.get('snippet', ''))}")
        return "\n\n".join(parts)

    def query(self, query_text: str, top_k: int = 5, web_fallback: bool = True) -> Dict[str, Any]:
        """High-level query with optional web search fallback (voice agent / tests)."""
        local_results = self.search(query_text, top_k=top_k)
        best_score = local_results[0]["score"] if local_results else 0.0

        use_web = web_fallback and self.web_search.is_available() and (
            not local_results or best_score < self.WEB_SCORE_THRESHOLD
        )

        web_results: List[Dict[str, Any]] = []
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

    def list_documents(self) -> List[Dict[str, str]]:
        stats = self.vector_store.stats()
        return [
            {"name": src, "type": "indexed_chunk_source", "path": src}
            for src in stats.get("sources", [])
        ]

    def _ingest_pdf_multimodal(self, file_path: str) -> Dict[str, Any]:
        """CLI inspect helper — basic PDF ingest (multimodal tables/images in Fase D)."""
        result = self.ingest_file(file_path)
        pages = _extract_pdf_pages(file_path)
        return {
            "status": result.get("status"),
            "table_count": 0,
            "image_count": 0,
            "ocr_count": 0,
            "documents": [{"subtype": "text", "page_number": p, "order": i} for i, (p, _) in enumerate(pages[:10], 1)],
        }
