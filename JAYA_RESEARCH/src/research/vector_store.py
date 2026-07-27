"""Persistent vector storage with optional FAISS acceleration."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

try:
    from research.retrieval_evidence import enrich_chunk_metadata
except ImportError:
    from src.research.retrieval_evidence import enrich_chunk_metadata

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
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Failed to load vector store at {self.store_dir}: {exc}"
            ) from exc

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

        metadata_rows = list(metadatas or [{} for _ in texts])
        if len(metadata_rows) != len(texts):
            raise ValueError("metadatas length must match texts length")

        vectors = normalize_vectors(np.asarray(embeddings, dtype=np.float32))
        if vectors.shape[1] != self.dimension and not self._records:
            self.dimension = int(vectors.shape[1])
            self.dim = self.dimension
            self._vectors = np.zeros((0, self.dimension), dtype=np.float32)
            self._rebuild_index()

        expected_shape = (len(texts), self.dimension)
        if vectors.shape != expected_shape:
            raise ValueError(
                f"Embeddings have shape {vectors.shape}; expected {expected_shape}"
            )

        new_records: List[Dict[str, Any]] = []
        for text, metadata in zip(texts, metadata_rows):
            normalized_text = str(text)
            normalized_metadata = enrich_chunk_metadata(
                normalized_text,
                metadata,
            )
            normalized_metadata.setdefault("workspace_id", self.workspace_id)
            new_records.append(
                {
                    "content": normalized_text,
                    "metadata": normalized_metadata,
                }
            )

        self._records.extend(new_records)
        self._vectors = np.vstack([self._vectors, vectors])
        self._rebuild_index()
        self._persist()
        return len(new_records)

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
                from research.enhanced_rag import NVIDIAEmbeddings
            except ImportError:
                from src.research.enhanced_rag import NVIDIAEmbeddings

            resolved_embeddings = NVIDIAEmbeddings().embed_texts(list(texts))
        return self.add_chunks(texts, resolved_embeddings, metadatas)

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Search by cosine similarity and apply exact metadata filters."""
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
        target_workspace = workspace_id or self.workspace_id
        keep_indices: List[int] = []
        removed = 0

        for index, record in enumerate(self._records):
            metadata = record.get("metadata", {})
            record_workspace = metadata.get("workspace_id", self.workspace_id)
            record_source = metadata.get("source") or metadata.get("file_name")
            if record_workspace == target_workspace and record_source == source_id:
                removed += 1
            else:
                keep_indices.append(index)

        if not removed:
            return 0

        self._records = [self._records[index] for index in keep_indices]
        if keep_indices:
            self._vectors = self._vectors[np.asarray(keep_indices, dtype=np.int64)]
        else:
            self._vectors = np.zeros((0, self.dimension), dtype=np.float32)
        self._rebuild_index()
        self._persist()
        return removed

    def count(self, workspace_id: Optional[str] = None) -> int:
        """Return total records, or records scoped to a workspace."""
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
