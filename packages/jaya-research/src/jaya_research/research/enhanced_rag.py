"""Enhanced RAG chunking, embedding, retrieval, and web-fallback client."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import requests

from jaya_research.config import config
from jaya_research.provider_errors import (
    ProviderInvalidResponseError,
    ProviderPolicy,
    ensure_http_success,
    execute_with_retry,
)

try:
    from jaya_research.research.vector_store import VectorStore, normalize_vectors
except ImportError:
    from jaya_research.research.vector_store import VectorStore, normalize_vectors

try:
    from jaya_research.research.multimodal_pdf import (
        MultimodalPDFExtractor,
        PDFExtractionCode,
        PDFExtractionError,
    )
except ImportError:
    from jaya_research.research.multimodal_pdf import (
        MultimodalPDFExtractor,
        PDFExtractionCode,
        PDFExtractionError,
    )

try:
    from jaya_research.research.retrieval_evidence import AnswerStatus, build_grounded_response
except ImportError:
    from jaya_research.research.retrieval_evidence import (
        AnswerStatus,
        build_grounded_response,
    )

try:
    from jaya_research.research.web_search import WebSearchClient
except ImportError:
    try:
        from jaya_research.research.web_search import WebSearchClient
    except ImportError:
        WebSearchClient = None


logger = logging.getLogger(__name__)
_normalize_vectors = normalize_vectors

Chunk = Dict[str, Any]
SearchResult = Dict[str, Any]

_WORKSPACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ProviderExecutionMode(str, Enum):
    """How an embedding provider is actually executed."""

    REMOTE = "REMOTE"
    LOCAL_FALLBACK = "LOCAL_FALLBACK"
    INJECTED = "INJECTED"


class WebFallbackStatus(str, Enum):
    """Truthful outcome of the optional web-evidence fallback."""

    DISABLED = "DISABLED"
    NOT_NEEDED = "NOT_NEEDED"
    UNAVAILABLE = "UNAVAILABLE"
    EMPTY = "EMPTY"
    USED = "USED"


@dataclass(frozen=True)
class EmbeddingProviderIdentity:
    provider: str
    model: str
    version: str
    implementation_type: str
    execution_mode: ProviderExecutionMode
    is_fallback: bool
    fallback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "version": self.version,
            "implementation_type": self.implementation_type,
            "execution_mode": self.execution_mode.value,
            "is_fallback": self.is_fallback,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class WebFallbackIdentity:
    requested: bool
    status: WebFallbackStatus
    provider: Optional[str]
    result_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requested": self.requested,
            "status": self.status.value,
            "provider": self.provider,
            "result_count": self.result_count,
        }


def normalize_workspace_id(workspace_id: str) -> str:
    """Validate a workspace identifier before using it in paths or filters."""
    normalized = str(workspace_id).strip()
    if (
        normalized in {".", ".."}
        or not _WORKSPACE_ID_PATTERN.fullmatch(normalized)
    ):
        raise ValueError(
            "workspace_id must contain only letters, numbers, '.', '_', or '-'"
        )
    return normalized


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
    """Compatibility view over the canonical bounded PDF extractor.

    Typed extraction failures intentionally propagate. Callers that need an
    ingest response rather than an exception should use ``ingest_file``.
    """
    document = MultimodalPDFExtractor().extract(file_path)
    if document.status != PDFExtractionCode.COMPLETE.value:
        return []
    return [
        {
            "page_number": page.page_number,
            "text": page.text,
            "source": document.document_name,
            "extraction_method": page.extraction_method,
            "page_text_sha256": page.text_sha256,
        }
        for page in document.pages
        if page.text
    ]


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
        self.provider_identity = (
            EmbeddingProviderIdentity(
                provider="nvidia",
                model=self.model,
                version=os.getenv(
                    "NVIDIA_EMBEDDING_MODEL_VERSION",
                    "provider-managed",
                ),
                implementation_type="remote_dense_embedding",
                execution_mode=ProviderExecutionMode.REMOTE,
                is_fallback=False,
            )
            if self.api_key
            else EmbeddingProviderIdentity(
                provider="jaya_local",
                model="sha256-feature-hashing",
                version="1",
                implementation_type="deterministic_local_fallback",
                execution_mode=ProviderExecutionMode.LOCAL_FALLBACK,
                is_fallback=True,
                fallback_reason="NVIDIA_API_KEY_NOT_CONFIGURED",
            )
        )
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

    def get_provider_identity(self) -> Dict[str, Any]:
        """Return typed execution and fallback identity for this adapter."""
        return self.provider_identity.to_dict()

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


def _embedding_provider_identity(embedder: Any) -> Dict[str, Any]:
    getter = getattr(embedder, "get_provider_identity", None)
    if callable(getter):
        identity = getter()
        required = (
            "provider",
            "model",
            "version",
            "implementation_type",
            "execution_mode",
            "is_fallback",
            "fallback_reason",
        )
        if isinstance(identity, dict) and set(required) <= identity.keys():
            return {key: identity[key] for key in required}
    adapter_type = type(embedder).__name__
    return EmbeddingProviderIdentity(
        provider="injected_adapter",
        model=adapter_type,
        version="unknown",
        implementation_type="custom_embedding_adapter",
        execution_mode=ProviderExecutionMode.INJECTED,
        is_fallback=False,
    ).to_dict()


def _is_provider_error_result(result: Dict[str, Any]) -> bool:
    metadata = result.get("metadata")
    document = result.get("document")
    candidates = [result]
    if isinstance(metadata, dict):
        candidates.append(metadata)
    if isinstance(document, dict):
        candidates.append(document)
    return any(
        candidate.get("provider_error") is not None
        or candidate.get("error") is not None
        or str(candidate.get("status") or "").casefold()
        in {"error", "provider_error", "unavailable"}
        for candidate in candidates
    )


def _is_internal_knowledge_result(result: Dict[str, Any]) -> bool:
    metadata = result.get("metadata")
    document = result.get("document")
    candidates = [result]
    if isinstance(metadata, dict):
        candidates.append(metadata)
    if isinstance(document, dict):
        candidates.append(document)
    return any(
        str(
            candidate.get("knowledge_origin")
            or candidate.get("source_type")
            or ""
        ).strip().casefold()
        in {"internal", "internal_knowledge", "model_internal_knowledge"}
        for candidate in candidates
    )


def _is_rejected_evidence_result(result: Dict[str, Any]) -> bool:
    return _is_provider_error_result(result) or _is_internal_knowledge_result(result)


def _validate_ingest_metadata(metadata: Dict[str, Any]) -> None:
    if _is_provider_error_result(metadata):
        raise ValueError("Provider errors cannot be ingested as research evidence")
    if _is_internal_knowledge_result(metadata):
        raise ValueError("Internal model knowledge cannot be ingested as evidence")


def _source_key_for_ingest(text: str, metadata: Dict[str, Any]) -> str:
    for key in ("source_id", "source", "file_name", "source_uri"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return f"inline-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:20]}"


def _format_query_response(
    local_results: Sequence[Dict[str, Any]],
    web_results: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return extractive, cited evidence while preserving legacy response keys."""
    safe_local_results = [
        result for result in local_results if not _is_rejected_evidence_result(result)
    ]
    safe_web_results = [
        result for result in web_results if not _is_rejected_evidence_result(result)
    ]
    response = build_grounded_response(safe_local_results, safe_web_results)
    if response["status"] != AnswerStatus.ANSWERED.value:
        return response

    citations = response["citations"]
    local_citation_count = 0
    for result in safe_local_results:
        try:
            accepted = float(result.get("score", 0.0)) >= 0.55
        except (TypeError, ValueError):
            accepted = False
        local_citation_count += int(accepted)
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
        *,
        embedder: Any = None,
        pdf_extractor: Optional[MultimodalPDFExtractor] = None,
    ):
        self.workspace_id = normalize_workspace_id(workspace_id)
        self.use_embeddings = use_embeddings
        self.rerank_enabled = rerank_enabled
        self.store_dir = self._resolve_store_dir(
            vector_store_path,
            self.workspace_id,
        )
        self.embedder = embedder if embedder is not None else NVIDIAEmbeddings()
        self.pdf_extractor = pdf_extractor or MultimodalPDFExtractor()
        dimension = getattr(self.embedder, "dimension", config.RAG_EMBED_DIMENSION)
        if not isinstance(dimension, int):
            dimension = config.RAG_EMBED_DIMENSION

        self.vector_store = VectorStore(
            str(self.store_dir),
            workspace_id=self.workspace_id,
            dimension=dimension,
        )
        self.store = self.vector_store
        self.web_search = None
        if WebSearchClient is not None:
            try:
                self.web_search = WebSearchClient()
            except (ImportError, RuntimeError) as exc:
                logger.warning("Web search integration is unavailable: %s", exc)

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
        target_workspace = normalize_workspace_id(workspace_id or self.workspace_id)
        normalized_metadata = {
            **(metadata or {}),
            "workspace_id": target_workspace,
        }
        _validate_ingest_metadata(normalized_metadata)
        chunks = chunk_text(
            text,
            config.RAG_CHUNK_SIZE,
            config.RAG_CHUNK_OVERLAP,
            base_metadata=normalized_metadata,
        )
        if not chunks:
            return self._empty_ingest_response(target_workspace)
        source_key = _source_key_for_ingest(clean_text(text), normalized_metadata)
        normalized_metadata.setdefault("source_id", source_key)
        for chunk in chunks:
            chunk["metadata"].setdefault("source_id", source_key)
        return self._index_chunks(
            chunks,
            target_workspace,
            source_key,
        )

    def ingest_file(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_workspace = normalize_workspace_id(workspace_id or self.workspace_id)
        resolved_file = Path(file_path).expanduser().resolve()
        normalized_metadata = dict(metadata or {})
        normalized_metadata.setdefault("file_name", resolved_file.name)
        normalized_metadata.setdefault("source", normalized_metadata["file_name"])
        normalized_metadata.setdefault("source_uri", resolved_file.as_uri())
        normalized_metadata.setdefault("file_path", str(resolved_file))
        normalized_metadata["workspace_id"] = target_workspace
        _validate_ingest_metadata(normalized_metadata)
        source_key = _source_key_for_ingest("", normalized_metadata)
        normalized_metadata.setdefault("source_id", source_key)

        if resolved_file.suffix.lower() == ".pdf":
            try:
                document = self.pdf_extractor.extract(
                    resolved_file,
                    source_uri=str(normalized_metadata["source_uri"]),
                    license_id=str(normalized_metadata.get("license_id") or "UNKNOWN"),
                )
            except PDFExtractionError as exc:
                return {
                    "status": "error",
                    "error_code": exc.code.value,
                    "message": str(exc),
                    "chunks_added": 0,
                    "workspace_id": target_workspace,
                    "source_id": source_key,
                }
            if document.status == PDFExtractionCode.PARTIAL_OCR_REQUIRED.value:
                return {
                    "status": "requires_ocr",
                    "extraction_status": document.status,
                    "warnings": list(document.warnings),
                    "chunks_added": 0,
                    "workspace_id": target_workspace,
                    "source_id": source_key,
                }
            if document.status != PDFExtractionCode.COMPLETE.value:
                return {
                    "status": "empty",
                    "extraction_status": document.status,
                    "chunks_added": 0,
                    "workspace_id": target_workspace,
                    "source_id": source_key,
                }
            document_metadata = {
                **normalized_metadata,
                "source_sha256": document.metadata["source_sha256"],
                "accessed_at": document.metadata["extracted_at"],
                "pdf_parser": document.metadata["parser"],
                "pdf_extraction_status": document.status,
                "pdf_provenance_complete": document.metadata[
                    "provenance_complete"
                ],
            }
            chunks: List[Chunk] = []
            for page in document.pages:
                if not page.text:
                    continue
                chunks.extend(
                    chunk_text(
                        page.text,
                        config.RAG_CHUNK_SIZE,
                        config.RAG_CHUNK_OVERLAP,
                        page_number=page.page_number,
                        base_metadata={
                            **document_metadata,
                            "extraction_method": page.extraction_method,
                            "page_text_sha256": page.text_sha256,
                        },
                    )
                )
        else:
            if not resolved_file.is_file():
                return {
                    "status": "error",
                    "error_code": "FILE_NOT_FOUND",
                    "message": "Input file does not exist",
                    "chunks_added": 0,
                    "workspace_id": target_workspace,
                    "source_id": source_key,
                }
            try:
                file_text = _read_text_file(str(resolved_file))
            except OSError:
                return {
                    "status": "error",
                    "error_code": "FILE_READ_FAILED",
                    "message": "Input file could not be read",
                    "chunks_added": 0,
                    "workspace_id": target_workspace,
                    "source_id": source_key,
                }
            chunks = chunk_text(
                file_text,
                config.RAG_CHUNK_SIZE,
                config.RAG_CHUNK_OVERLAP,
                base_metadata=normalized_metadata,
            )

        if not chunks:
            return self._empty_ingest_response(target_workspace, source_key)
        result = self._index_chunks(chunks, target_workspace, source_key)
        result["file_path"] = str(resolved_file)
        return result

    def _index_chunks(
        self,
        chunks: Sequence[Chunk],
        workspace_id: str,
        source_key: str,
    ) -> Dict[str, Any]:
        if not chunks:
            return {
                "status": "empty",
                "chunks_added": 0,
                "workspace_id": workspace_id,
            }
        texts = [str(chunk["content"]) for chunk in chunks]
        embedding_provenance = _embedding_provenance(self.embedder)
        provider_identity = _embedding_provider_identity(self.embedder)
        metadatas = []
        for chunk in chunks:
            metadata = dict(chunk["metadata"])
            metadata["workspace_id"] = workspace_id
            metadata.setdefault("source_id", source_key)
            metadata["embedding"] = embedding_provenance
            metadata["embedding_provider"] = provider_identity
            metadatas.append(metadata)
        embeddings = self.embedder.embed_texts(texts)
        mutation = self.vector_store.replace_source(
            source_key,
            workspace_id,
            texts,
            embeddings,
            metadatas,
        )
        return {
            "status": "success",
            "chunks_added": mutation["added"],
            "chunks_replaced": mutation["removed"],
            "workspace_id": workspace_id,
            "source_id": source_key,
            "provider_identity": provider_identity,
        }

    @staticmethod
    def _empty_ingest_response(
        workspace_id: str,
        source_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "status": "empty",
            "chunks_added": 0,
            "chunks_replaced": 0,
            "workspace_id": workspace_id,
            "source_id": source_id,
        }

    def search(
        self,
        query: Any,
        top_k: int = 5,
        workspace_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        rerank: bool = False,
    ) -> List[SearchResult]:
        if rerank or self.rerank_enabled:
            raise RuntimeError("Reranking was requested but no reranker is configured")
        target_workspace = normalize_workspace_id(workspace_id or self.workspace_id)
        if isinstance(query, str) and not clean_text(query):
            return []
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
        response = build_grounded_response(self.search(query, top_k))
        if response["status"] != AnswerStatus.ANSWERED.value:
            return ""
        return "\n\n".join(
            str(claim["text"])
            for claim in response["claims"]
        )

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        web_fallback: bool = True,
    ) -> Dict[str, Any]:
        local_results = self.search(query_text, top_k)
        best_score = float(local_results[0].get("score", 0.0)) if local_results else 0.0
        needs_fallback = not local_results or best_score < 0.55
        web_results: List[Dict[str, Any]] = []
        if not web_fallback:
            fallback_status = WebFallbackStatus.DISABLED
        elif not needs_fallback:
            fallback_status = WebFallbackStatus.NOT_NEEDED
        elif self.web_search is None or not self.web_search.is_available():
            fallback_status = WebFallbackStatus.UNAVAILABLE
        else:
            raw_web_results = self.web_search.search(
                query_text,
                max_results=top_k,
            )
            if not isinstance(raw_web_results, list) or not all(
                isinstance(result, dict) for result in raw_web_results
            ):
                raise ProviderInvalidResponseError(
                    "web_search",
                    "Web provider returned an invalid result collection",
                )
            web_results = [
                result
                for result in raw_web_results
                if not _is_rejected_evidence_result(result)
            ]
            fallback_status = (
                WebFallbackStatus.USED
                if web_results
                else WebFallbackStatus.EMPTY
            )
        response = _format_query_response(local_results, web_results)
        response["provider_identity"] = {
            "embedding": _embedding_provider_identity(
                getattr(self, "embedder", None)
            ),
            "web_fallback": WebFallbackIdentity(
                requested=web_fallback,
                status=fallback_status,
                provider=(
                    type(self.web_search).__name__
                    if fallback_status in {
                        WebFallbackStatus.USED,
                        WebFallbackStatus.EMPTY,
                    }
                    else None
                ),
                result_count=len(web_results),
            ).to_dict(),
        }
        return response

    def list_documents(self) -> List[Dict[str, str]]:
        return [
            {"name": source, "type": "indexed_chunk_source", "path": source}
            for source in self.vector_store.stats(self.workspace_id).get("sources", [])
        ]

    def get_stats(self) -> Dict[str, Any]:
        return self.vector_store.stats(self.workspace_id)

    def delete_by_source(
        self,
        source_id: str,
        workspace_id: Optional[str] = None,
    ) -> int:
        target_workspace = normalize_workspace_id(workspace_id or self.workspace_id)
        return self.vector_store.delete_by_source(source_id, target_workspace)

    def reload(self) -> Dict[str, Any]:
        """Reload persisted evidence and report only this workspace's state."""
        self.vector_store.reload()
        return self.vector_store.stats(self.workspace_id)


RAGClient = EnhancedRAGClient
