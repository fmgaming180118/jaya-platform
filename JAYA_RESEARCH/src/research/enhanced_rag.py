"""Enhanced RAG chunking, embedding, retrieval, and web-fallback client."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import requests

try:
    from config import config
    from provider_errors import (
        ProviderInvalidResponseError,
        ProviderPolicy,
        ensure_http_success,
        execute_with_retry,
    )
except ImportError:
    from src.config import config
    from src.provider_errors import (
        ProviderInvalidResponseError,
        ProviderPolicy,
        ensure_http_success,
        execute_with_retry,
    )

try:
    from research.vector_store import VectorStore, normalize_vectors
except ImportError:
    from src.research.vector_store import VectorStore, normalize_vectors

try:
    from research.retrieval_evidence import AnswerStatus, build_grounded_response
except ImportError:
    from src.research.retrieval_evidence import (
        AnswerStatus,
        build_grounded_response,
    )

try:
    from research.web_search import WebSearchClient
except ImportError:
    try:
        from src.research.web_search import WebSearchClient
    except ImportError:
        WebSearchClient = None


logger = logging.getLogger(__name__)
_normalize_vectors = normalize_vectors

Chunk = Dict[str, Any]
SearchResult = Dict[str, Any]


def clean_text(text: str) -> str:
    """Normalize text and remove obvious headers repeated across PDF pages."""
    if not text:
        return ""

    normalized = re.sub(r"\r\n|\r", "\n", text.replace("\x00", ""))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]
    counts: Dict[str, int] = {}
    for line in lines:
        if line:
            counts[line] = counts.get(line, 0) + 1

    repeated_headers = {
        line
        for line, count in counts.items()
        if count >= 3 and len(line) <= 200
    }
    normalized = "\n".join(line for line in lines if line not in repeated_headers)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _resolve_overlap(overlap: Optional[int], chunk_overlap: Optional[int]) -> int:
    if overlap is not None and chunk_overlap is not None and overlap != chunk_overlap:
        raise ValueError("Use either overlap or chunk_overlap, not conflicting values")
    return (
        chunk_overlap
        if chunk_overlap is not None
        else (overlap if overlap is not None else 50)
    )


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: Optional[int] = None,
    *,
    chunk_overlap: Optional[int] = None,
    page_number: Optional[int] = None,
    base_metadata: Optional[Dict[str, Any]] = None,
) -> List[Chunk]:
    """Split text into a canonical content/metadata chunk representation."""
    resolved_overlap = _resolve_overlap(overlap, chunk_overlap)
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if resolved_overlap < 0 or resolved_overlap >= chunk_size:
        raise ValueError("chunk overlap must satisfy 0 <= overlap < chunk_size")

    words = clean_text(text).split()
    if not words:
        return []

    step = chunk_size - resolved_overlap
    metadata_seed = dict(base_metadata or {})
    if page_number is not None:
        metadata_seed["page_number"] = page_number

    chunks: List[Chunk] = []
    for chunk_index, start in enumerate(range(0, len(words), step)):
        chunk_words = words[start : start + chunk_size]
        metadata = {
            **metadata_seed,
            "chunk_index": chunk_index,
            "word_start": start,
            "word_end": start + len(chunk_words),
        }
        chunks.append({"content": " ".join(chunk_words), "metadata": metadata})
        if start + chunk_size >= len(words):
            break
    return chunks


def chunk_pages(
    pages: Sequence[Any],
    chunk_size: int = 500,
    overlap: Optional[int] = None,
    *,
    chunk_overlap: Optional[int] = None,
    base_metadata: Optional[Dict[str, Any]] = None,
) -> List[Chunk]:
    """Chunk mappings or ``(page_number, text)`` tuples with page provenance."""
    resolved_overlap = _resolve_overlap(overlap, chunk_overlap)
    chunks: List[Chunk] = []
    for page in pages:
        page_metadata = dict(base_metadata or {})
        if isinstance(page, dict):
            page_number = int(page.get("page_number", page.get("page_num", 1)))
            page_text = str(page.get("text", ""))
            if page.get("source"):
                page_metadata.setdefault("source", page["source"])
        elif isinstance(page, (tuple, list)) and len(page) >= 2:
            page_number, page_text = int(page[0]), str(page[1])
        else:
            raise TypeError("Each page must be a mapping or (page_number, text) tuple")

        chunks.extend(
            chunk_text(
                page_text,
                chunk_size,
                resolved_overlap,
                page_number=page_number,
                base_metadata=page_metadata,
            )
        )
    return chunks


def _extract_pdf_pages(file_path: str) -> List[Dict[str, Any]]:
    """Extract PDF text page by page using an installed PDF reader."""
    pages: List[Dict[str, Any]] = []
    try:
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader

        with open(file_path, "rb") as file_handle:
            for page_number, page in enumerate(PdfReader(file_handle).pages, start=1):
                pages.append(
                    {
                        "page_number": page_number,
                        "text": page.extract_text() or "",
                        "source": os.path.basename(file_path),
                    }
                )
    except Exception as exc:
        logger.error("Failed to extract PDF %s: %s", file_path, exc)
    return pages


def _read_text_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as file_handle:
        return file_handle.read()


class NVIDIAEmbeddings:
    """NVIDIA NIM adapter with explicit, deterministic offline mode."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.base_url = base_url or os.getenv(
            "NVIDIA_BASE_URL",
            "https://integrate.api.nvidia.com/v1",
        )
        self.model = os.getenv("NVIDIA_EMBEDDING_MODEL", config.NVIDIA_EMBEDDING_MODEL)
        self.dimension = int(
            os.getenv("RAG_EMBED_DIMENSION", str(config.RAG_EMBED_DIMENSION))
        )
        self.batch_size = max(
            1,
            int(os.getenv("RAG_EMBED_BATCH_SIZE", str(config.RAG_EMBED_BATCH_SIZE))),
        )
        self.timeout_seconds = max(
            1.0,
            float(os.getenv("RAG_EMBED_TIMEOUT_SECONDS", "30")),
        )
        self.provider_policy = ProviderPolicy.from_env("NVIDIA_EMBEDDING_PROVIDER")
        self.mode = "remote" if self.api_key else "local_offline"
        self.provenance = (
            {
                "provider": "nvidia",
                "model": self.model,
                "version": os.getenv(
                    "NVIDIA_EMBEDDING_MODEL_VERSION",
                    "provider-managed",
                ),
                "type": "remote_dense_embedding",
            }
            if self.api_key
            else {
                "provider": "jaya_local",
                "model": "sha256-feature-hashing",
                "version": "1",
                "type": "deterministic_local_fallback",
            }
        )

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)

        cleaned = [clean_text(str(text))[:8000] for text in texts]
        if self.api_key:
            return self._embed_remote(cleaned)
        return self._embed_local(cleaned)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Compatibility alias used by all RAG clients."""
        return self.embed_documents(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]

    def get_provenance(self) -> Dict[str, str]:
        """Describe the actual embedding implementation used for evidence."""
        return dict(self.provenance)

    def _embed_remote(self, texts: List[str]) -> np.ndarray:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        embeddings: List[List[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]

            def request_batch() -> List[Dict[str, Any]]:
                response = requests.post(
                    f"{self.base_url.rstrip('/')}/embeddings",
                    headers=headers,
                    json={"input": batch, "model": self.model},
                    timeout=(
                        self.provider_policy.connect_timeout_seconds,
                        min(
                            self.timeout_seconds,
                            self.provider_policy.read_timeout_seconds,
                        ),
                    ),
                )
                ensure_http_success("nvidia_embeddings", response)
                try:
                    payload = response.json()
                except (TypeError, ValueError) as exc:
                    raise ProviderInvalidResponseError(
                        "nvidia_embeddings",
                        "Provider returned malformed JSON",
                        cause_type=type(exc).__name__,
                    ) from exc
                if not isinstance(payload, dict):
                    raise ProviderInvalidResponseError(
                        "nvidia_embeddings",
                        "Provider response must be a JSON object",
                    )
                rows = payload.get("data")
                if not isinstance(rows, list) or len(rows) != len(batch):
                    raise ProviderInvalidResponseError(
                        "nvidia_embeddings",
                        "Provider returned an invalid embedding batch",
                    )
                return rows

            rows = execute_with_retry(
                "nvidia_embeddings",
                request_batch,
                self.provider_policy,
            )
            if not isinstance(rows, list) or len(rows) != len(batch):
                raise ProviderInvalidResponseError(
                    "nvidia_embeddings",
                    "Provider returned an invalid embedding batch",
                )
            try:
                ordered_rows = sorted(
                    rows,
                    key=lambda row: int(row.get("index", 0)),
                )
                embeddings.extend(row["embedding"] for row in ordered_rows)
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderInvalidResponseError(
                    "nvidia_embeddings",
                    "Provider returned malformed embedding rows",
                    cause_type=type(exc).__name__,
                ) from exc

        try:
            vectors = np.asarray(embeddings, dtype=np.float32)
        except (TypeError, ValueError) as exc:
            raise ProviderInvalidResponseError(
                "nvidia_embeddings",
                "Provider returned non-numeric embeddings",
                cause_type=type(exc).__name__,
            ) from exc
        expected_shape = (len(texts), self.dimension)
        if vectors.shape != expected_shape or not np.isfinite(vectors).all():
            raise ProviderInvalidResponseError(
                "nvidia_embeddings",
                "Provider returned invalid embedding dimensions or values",
            )
        return _normalize_vectors(vectors)

    def _embed_local(self, texts: List[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row_index, text in enumerate(texts):
            tokens = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                column = int.from_bytes(digest[:8], "big") % self.dimension
                vectors[row_index, column] += 1.0 if digest[8] & 1 else -1.0
            if not tokens:
                digest = hashlib.sha256(text.encode("utf-8")).digest()
                column = int.from_bytes(digest[:8], "big") % self.dimension
                vectors[row_index, column] = 1.0
        return _normalize_vectors(vectors)


def _result_document(result: Dict[str, Any]) -> Dict[str, Any]:
    document = result.get("document")
    if isinstance(document, dict):
        return document
    return {
        "title": result.get("title", ""),
        "url": result.get("url", ""),
        "source": result.get("source", ""),
    }


def _embedding_provenance(embedder: Any) -> Dict[str, str]:
    getter = getattr(embedder, "get_provenance", None)
    if callable(getter):
        provenance = getter()
        if isinstance(provenance, dict) and all(
            isinstance(provenance.get(key), str)
            for key in ("provider", "model", "version", "type")
        ):
            return dict(provenance)
    adapter_type = type(embedder).__name__
    return {
        "provider": "injected_adapter",
        "model": adapter_type,
        "version": "unknown",
        "type": "custom_embedding_adapter",
    }


def _format_query_response(
    local_results: Sequence[Dict[str, Any]],
    web_results: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return extractive, cited evidence while preserving legacy response keys."""
    response = build_grounded_response(local_results, web_results)
    if response["status"] != AnswerStatus.ANSWERED.value:
        return response

    citations = response["citations"]
    local_citation_count = max(0, len(citations) - len(web_results))
    parts: List[str] = []
    if local_citation_count:
        parts.append("**Local Research Data:**")
        parts.extend(
            f"- [{citation['citation_id']}] {citation['snippet']}"
            for citation in citations[:local_citation_count]
        )
    if len(citations) > local_citation_count:
        parts.append("**Web Search Results:**")
        parts.extend(
            f"- [{citation['citation_id']}] {citation['snippet']}"
            for citation in citations[local_citation_count:]
        )

    response["answer"] = "\n".join(parts)
    return response


class EnhancedRAGClient:
    """High-level RAG interface shared by research, voice, CLI, and API."""

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
        self.store_dir = self._resolve_store_dir(vector_store_path, workspace_id)
        self.embedder = NVIDIAEmbeddings()
        dimension = getattr(self.embedder, "dimension", config.RAG_EMBED_DIMENSION)
        if not isinstance(dimension, int):
            dimension = config.RAG_EMBED_DIMENSION

        self.vector_store = VectorStore(
            str(self.store_dir),
            workspace_id=workspace_id,
            dimension=dimension,
        )
        self.store = self.vector_store
        self.web_search = WebSearchClient() if WebSearchClient is not None else None

    @staticmethod
    def _resolve_store_dir(path: Optional[str], workspace_id: str) -> Path:
        if path:
            resolved = Path(path)
            return resolved.with_suffix("") if resolved.suffix == ".json" else resolved
        return Path(config.WORKSPACES_DIR) / workspace_id / "vector_store"

    def embed(self, texts: List[str]) -> List[List[float]]:
        return self.embedder.embed_texts(texts).tolist()

    def ingest_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_workspace = workspace_id or self.workspace_id
        normalized_metadata = {
            **(metadata or {}),
            "workspace_id": target_workspace,
        }
        source = normalized_metadata.get("source") or normalized_metadata.get(
            "file_name"
        )
        if source:
            self.vector_store.delete_by_source(str(source), target_workspace)
        return self._index_chunks(
            chunk_text(
                text,
                config.RAG_CHUNK_SIZE,
                config.RAG_CHUNK_OVERLAP,
                base_metadata=normalized_metadata,
            ),
            target_workspace,
        )

    def ingest_file(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_workspace = workspace_id or self.workspace_id
        normalized_metadata = dict(metadata or {})
        normalized_metadata.setdefault("file_name", os.path.basename(file_path))
        normalized_metadata.setdefault("source", normalized_metadata["file_name"])
        normalized_metadata["workspace_id"] = target_workspace

        if Path(file_path).suffix.lower() == ".pdf":
            pages = _extract_pdf_pages(file_path)
            if not pages:
                return {
                    "status": "error",
                    "message": f"Could not extract PDF: {file_path}",
                    "chunks_added": 0,
                    "workspace_id": target_workspace,
                }
            chunks = chunk_pages(
                pages,
                config.RAG_CHUNK_SIZE,
                config.RAG_CHUNK_OVERLAP,
                base_metadata=normalized_metadata,
            )
        else:
            chunks = chunk_text(
                _read_text_file(file_path),
                config.RAG_CHUNK_SIZE,
                config.RAG_CHUNK_OVERLAP,
                base_metadata=normalized_metadata,
            )

        self.vector_store.delete_by_source(
            str(normalized_metadata["source"]),
            target_workspace,
        )
        result = self._index_chunks(chunks, target_workspace)
        result["file_path"] = file_path
        return result

    def _index_chunks(
        self,
        chunks: Sequence[Chunk],
        workspace_id: str,
    ) -> Dict[str, Any]:
        if not chunks:
            return {
                "status": "empty",
                "chunks_added": 0,
                "workspace_id": workspace_id,
            }
        texts = [str(chunk["content"]) for chunk in chunks]
        embedding_provenance = _embedding_provenance(self.embedder)
        metadatas = []
        for chunk in chunks:
            metadata = dict(chunk["metadata"])
            metadata["embedding"] = embedding_provenance
            metadatas.append(metadata)
        added = self.vector_store.add_chunks(
            texts,
            self.embedder.embed_texts(texts),
            metadatas,
        )
        return {
            "status": "success",
            "chunks_added": added,
            "workspace_id": workspace_id,
        }

    def search(
        self,
        query: Any,
        top_k: int = 5,
        workspace_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        rerank: bool = False,
    ) -> List[SearchResult]:
        del rerank
        target_workspace = workspace_id or self.workspace_id
        query_embedding = (
            self.embedder.embed_texts([query])[0]
            if isinstance(query, str)
            else np.asarray(query, dtype=np.float32)
        )
        resolved_filters = {
            **(filters or {}),
            "workspace_id": target_workspace,
        }
        return self.vector_store.search(query_embedding, top_k, resolved_filters)

    def get_context_for_query(self, query: str, top_k: int = 5) -> str:
        return "\n\n".join(
            result.get("content") or result.get("snippet", "")
            for result in self.search(query, top_k)
        )

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        web_fallback: bool = True,
    ) -> Dict[str, Any]:
        local_results = self.search(query_text, top_k)
        best_score = float(local_results[0].get("score", 0.0)) if local_results else 0.0
        use_web = bool(
            web_fallback
            and self.web_search
            and self.web_search.is_available()
            and (not local_results or best_score < 0.55)
        )
        web_results = (
            self.web_search.search(query_text, max_results=top_k)
            if use_web
            else []
        )
        return _format_query_response(local_results, web_results)

    def list_documents(self) -> List[Dict[str, str]]:
        return [
            {"name": source, "type": "indexed_chunk_source", "path": source}
            for source in self.vector_store.stats(self.workspace_id).get("sources", [])
        ]

    def get_stats(self) -> Dict[str, Any]:
        return self.vector_store.stats(self.workspace_id)

    def delete_by_source(self, source_id: str) -> int:
        return self.vector_store.delete_by_source(source_id, self.workspace_id)


RAGClient = EnhancedRAGClient
