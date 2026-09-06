"""Persistent vector storage with optional FAISS acceleration."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

try:
    from jaya_research.research.retrieval_evidence import enrich_chunk_metadata
except ImportError:
    from jaya_research.research.retrieval_evidence import enrich_chunk_metadata

try:
    import faiss
except ImportError:
    faiss = None


logger = logging.getLogger(__name__)

SearchResult = Dict[str, Any]


def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize one vector or a matrix of vectors."""
    array = np.asarray(vectors, dtype=np.float32)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if array.ndim != 2:
        raise ValueError("Embedding vectors must be a one- or two-dimensional array")

    norms = np.linalg.norm(array, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (array / norms).astype(np.float32)


def _validate_evidence_metadata(metadata: Dict[str, Any]) -> None:
    """Reject operational failures and uncited model memory at storage boundary."""
    if metadata.get("provider_error") is not None:
        raise ValueError("Provider errors cannot be stored as research evidence")
    origin = str(
        metadata.get("knowledge_origin")
        or metadata.get("source_type")
        or ""
    ).strip().casefold()
    if origin in {"internal", "internal_knowledge", "model_internal_knowledge"}:
        raise ValueError("Internal model knowledge cannot be stored as evidence")


class VectorStore:
    """Persistent vector store with workspace-scoped retrieval and deletion."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        store_dir: Optional[Any] = None,
        workspace_id: str = "default",
        dimension: int = 1024,
        *,
        dim: Optional[int] = None,
    ):
        if isinstance(store_dir, int):
            if dim is not None:
                raise ValueError("dimension was provided more than once")
            dim = store_dir
            store_dir = None

        resolved_dimension = dim if dim is not None else dimension
        if resolved_dimension <= 0:
            raise ValueError("dimension must be greater than zero")

        self.dimension = int(resolved_dimension)
        self.dim = self.dimension
        self.workspace_id = workspace_id
        self.store_dir = Path(store_dir) if store_dir else None
        self._records: List[Dict[str, Any]] = []
        self._vectors = np.zeros((0, self.dimension), dtype=np.float32)
        self._index = None
        self._loaded_signature: tuple[Any, ...] | None = None

        if self.store_dir:
            self.store_dir.mkdir(parents=True, exist_ok=True)
            self._records_path = self.store_dir / "records.json"
            self._vectors_path = self.store_dir / "vectors.npy"
            self._load()
        else:
            self._records_path = None
            self._vectors_path = None

        self._rebuild_index()

    def _load(self) -> None:
        records_exist = bool(self._records_path and self._records_path.exists())
        vectors_exist = bool(self._vectors_path and self._vectors_path.exists())
        if not records_exist and not vectors_exist:
            self._records = []
            self._vectors = np.zeros((0, self.dimension), dtype=np.float32)
            self._loaded_signature = self._storage_signature()
            return
        if records_exist != vectors_exist:
            raise ValueError(f"Incomplete vector store at {self.store_dir}")

        try:
            with open(self._records_path, "r", encoding="utf-8") as file_handle:
                payload = json.load(file_handle)
            stored_dimension = int(payload.get("dimension", self.dimension))
            if stored_dimension != self.dimension:
                raise ValueError(
                    f"Stored dimension {stored_dimension} does not match "
                    f"requested dimension {self.dimension}"
                )

            records = payload.get("records", [])
            if not isinstance(records, list) or not all(
                isinstance(record, dict) for record in records
            ):
                raise ValueError("Stored records must be a list of objects")
            vectors = np.asarray(
                np.load(self._vectors_path, allow_pickle=False),
                dtype=np.float32,
            )
            expected_shape = (len(records), self.dimension)
            if vectors.shape != expected_shape:
                raise ValueError(
                    f"Stored vectors have shape {vectors.shape}; "
                    f"expected {expected_shape}"
                )

            self._records = records
            self._vectors = normalize_vectors(vectors) if len(vectors) else vectors
            self._loaded_signature = self._storage_signature()
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Failed to load vector store at {self.store_dir}: {exc}"
            ) from exc

    def _storage_signature(self) -> tuple[Any, ...]:
        """Return a cheap signature used to notice changes by another client."""
        signature: list[Any] = []
        for path in (self._records_path, self._vectors_path):
            if path is None or not path.exists():
                signature.extend((None, None))
                continue
            stat = path.stat()
            signature.extend((stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    def _refresh_if_changed(self) -> None:
        if self.store_dir and self._storage_signature() != self._loaded_signature:
            self._load()
            self._rebuild_index()

    def reload(self) -> int:
        """Reload persisted state, failing closed on incomplete/corrupt storage."""
        if not self.store_dir:
            return len(self._records)
        self._load()
        self._rebuild_index()
        return len(self._records)

    def _rebuild_index(self) -> None:
        if faiss is None:
            self._index = None
            return

        self._index = faiss.IndexFlatIP(self.dimension)
        if len(self._vectors):
            self._index.add(np.ascontiguousarray(self._vectors, dtype=np.float32))

    def _persist(self) -> None:
        if not self.store_dir or not self._records_path or not self._vectors_path:
            return

        vector_temp = self._temporary_path(self._vectors_path)
        records_temp = self._temporary_path(self._records_path)
        try:
            with open(vector_temp, "wb") as file_handle:
                np.save(file_handle, self._vectors, allow_pickle=False)

            payload = {
                "schema_version": self.SCHEMA_VERSION,
                "dimension": self.dimension,
                "records": self._records,
            }
            with open(records_temp, "w", encoding="utf-8") as file_handle:
                json.dump(
                    payload,
                    file_handle,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )

            os.replace(vector_temp, self._vectors_path)
            os.replace(records_temp, self._records_path)
            self._loaded_signature = self._storage_signature()
        except Exception:
            for temporary_path in (vector_temp, records_temp):
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Could not remove temporary file %s",
                        temporary_path,
                    )
            raise

    def _temporary_path(self, target: Path) -> Path:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(self.store_dir),
        )
        os.close(descriptor)
        return Path(name)

    def add_chunks(
        self,
        texts: Sequence[str],
        embeddings: np.ndarray,
        metadatas: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> int:
        """Add text chunks and aligned embeddings, then persist them."""
        if not texts:
            return 0
        self._refresh_if_changed()
        snapshot = self._snapshot()
        try:
            new_records, vectors = self._prepare_chunks(
                texts,
                embeddings,
                metadatas,
            )
            self._records.extend(new_records)
            self._vectors = np.vstack([self._vectors, vectors])
            self._rebuild_index()
            self._persist()
        except Exception:
            self._restore(snapshot)
            raise
        return len(new_records)

    def replace_source(
        self,
        source_id: str,
        workspace_id: str,
        texts: Sequence[str],
        embeddings: np.ndarray,
        metadatas: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, int]:
        """Atomically replace one source inside one workspace in this process."""
        if not source_id.strip():
            raise ValueError("source_id must not be empty")
        if not texts:
            raise ValueError("replacement must contain at least one chunk")
        self._refresh_if_changed()
        snapshot = self._snapshot()
        try:
            new_records, vectors = self._prepare_chunks(
                texts,
                embeddings,
                metadatas,
            )
            keep_indices = [
                index
                for index, record in enumerate(self._records)
                if not self._matches_source(record, source_id, workspace_id)
            ]
            removed = len(self._records) - len(keep_indices)
            kept_vectors = (
                self._vectors[np.asarray(keep_indices, dtype=np.int64)]
                if keep_indices
                else np.zeros((0, self.dimension), dtype=np.float32)
            )
            self._records = [self._records[index] for index in keep_indices]
            self._records.extend(new_records)
            self._vectors = np.vstack([kept_vectors, vectors])
            self._rebuild_index()
            self._persist()
        except Exception:
            self._restore(snapshot)
            raise
        return {"removed": removed, "added": len(new_records)}

    def _prepare_chunks(
        self,
        texts: Sequence[str],
        embeddings: np.ndarray,
        metadatas: Optional[Sequence[Dict[str, Any]]],
    ) -> tuple[List[Dict[str, Any]], np.ndarray]:
        metadata_rows = list(metadatas or [{} for _ in texts])
        if len(metadata_rows) != len(texts):
            raise ValueError("metadatas length must match texts length")

        vectors = normalize_vectors(np.asarray(embeddings, dtype=np.float32))
        if vectors.shape[1] != self.dimension and not self._records:
            self.dimension = int(vectors.shape[1])
            self.dim = self.dimension
            self._vectors = np.zeros((0, self.dimension), dtype=np.float32)
        expected_shape = (len(texts), self.dimension)
        if vectors.shape != expected_shape:
            raise ValueError(
                f"Embeddings have shape {vectors.shape}; expected {expected_shape}"
            )

        new_records: List[Dict[str, Any]] = []
        for text, metadata in zip(texts, metadata_rows):
            normalized_text = str(text).strip()
            if not normalized_text:
                raise ValueError("Stored chunks must not be empty")
            _validate_evidence_metadata(metadata)
            normalized_metadata = enrich_chunk_metadata(
                normalized_text,
                metadata,
            )
            normalized_metadata.setdefault("workspace_id", self.workspace_id)
            new_records.append(
                {"content": normalized_text, "metadata": normalized_metadata}
            )
        return new_records, vectors

    def _snapshot(self) -> tuple[List[Dict[str, Any]], np.ndarray, int]:
        return (list(self._records), self._vectors.copy(), self.dimension)

    def _restore(
        self,
        snapshot: tuple[List[Dict[str, Any]], np.ndarray, int],
    ) -> None:
        self._records, self._vectors, self.dimension = snapshot
        self.dim = self.dimension
        self._rebuild_index()

    def _matches_source(
        self,
        record: Dict[str, Any],
        source_id: str,
        workspace_id: str,
    ) -> bool:
        metadata = record.get("metadata", {})
        record_workspace = metadata.get("workspace_id", self.workspace_id)
        identifiers = {
            str(value)
            for key in ("source_id", "source", "file_name", "source_uri")
            if (value := metadata.get(key)) is not None
        }
        return record_workspace == workspace_id and source_id in identifiers

    def add_texts(
        self,
        texts: Sequence[str],
        metadatas: Optional[Sequence[Dict[str, Any]]] = None,
        embeddings: Optional[np.ndarray] = None,
    ) -> int:
        """Compatibility helper that embeds text when vectors are omitted."""
        resolved_embeddings = embeddings
        if resolved_embeddings is None:
            try:
                from jaya_research.research.enhanced_rag import NVIDIAEmbeddings
            except ImportError:
                from jaya_research.research.enhanced_rag import NVIDIAEmbeddings

            resolved_embeddings = NVIDIAEmbeddings().embed_texts(list(texts))
        return self.add_chunks(texts, resolved_embeddings, metadatas)

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Search by cosine similarity and apply exact metadata filters."""
        self._refresh_if_changed()
        if top_k <= 0 or not self._records:
            return []

        query = normalize_vectors(np.asarray(query_embedding, dtype=np.float32))
        expected_shape = (1, self.dimension)
        if query.shape != expected_shape:
            raise ValueError(
                f"Query embedding has shape {query.shape}; expected {expected_shape}"
            )

        if self._index is not None:
            scores, indices = self._index.search(query, len(self._records))
            candidates = zip(scores[0].tolist(), indices[0].tolist())
        else:
            scores = self._vectors @ query[0]
            ordered_indices = np.argsort(scores)[::-1]
            candidates = (
                (float(scores[index]), int(index))
                for index in ordered_indices
            )

        required_filters = dict(filters or {})
        results: List[SearchResult] = []
        retrieved_at = datetime.now(timezone.utc).isoformat()
        for score, index in candidates:
            if index < 0 or index >= len(self._records):
                continue

            record = self._records[index]
            metadata = dict(record.get("metadata", {}))
            if any(
                metadata.get(key) != value
                for key, value in required_filters.items()
            ):
                continue

            content = str(record.get("content", ""))
            results.append(
                {
                    "content": content,
                    "score": float(score),
                    "score_kind": "COSINE_SIMILARITY",
                    "retrieved_at": retrieved_at,
                    "metadata": metadata,
                    "document": metadata,
                    "snippet": (
                        content[:400] + ("..." if len(content) > 400 else "")
                    ),
                }
            )
            if len(results) >= top_k:
                break

        return results

    def delete_by_source(
        self,
        source_id: str,
        workspace_id: Optional[str] = None,
    ) -> int:
        """Delete matching source chunks inside one workspace."""
        self._refresh_if_changed()
        target_workspace = workspace_id or self.workspace_id
        keep_indices: List[int] = []
        removed = 0

        for index, record in enumerate(self._records):
            if self._matches_source(record, source_id, target_workspace):
                removed += 1
            else:
                keep_indices.append(index)

        if not removed:
            return 0

        snapshot = self._snapshot()
        try:
            self._records = [self._records[index] for index in keep_indices]
            if keep_indices:
                self._vectors = self._vectors[
                    np.asarray(keep_indices, dtype=np.int64)
                ]
            else:
                self._vectors = np.zeros((0, self.dimension), dtype=np.float32)
            self._rebuild_index()
            self._persist()
        except Exception:
            self._restore(snapshot)
            raise
        return removed

    def count(self, workspace_id: Optional[str] = None) -> int:
        """Return total records, or records scoped to a workspace."""
        self._refresh_if_changed()
        if workspace_id is None:
            return len(self._records)
        return sum(
            1
            for record in self._records
            if record.get("metadata", {}).get(
                "workspace_id",
                self.workspace_id,
            )
            == workspace_id
        )

    def stats(self, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Return source and storage statistics for a workspace."""
        self._refresh_if_changed()
        target_workspace = workspace_id or self.workspace_id
        selected_records = [
            record
            for record in self._records
            if record.get("metadata", {}).get(
                "workspace_id",
                self.workspace_id,
            )
            == target_workspace
        ]
        sources = sorted(
            {
                str(source)
                for record in selected_records
                if (
                    source := (
                        record.get("metadata", {}).get("source")
                        or record.get("metadata", {}).get("file_name")
                        or record.get("metadata", {}).get("source_id")
                    )
                )
            }
        )
        return {
            "count": len(selected_records),
            "total_count": len(self._records),
            "workspace_id": target_workspace,
            "dimension": self.dimension,
            "sources": sources,
            "store_dir": str(self.store_dir) if self.store_dir else None,
        }
