"""Compatibility name for the canonical, evidence-grounded RAG client.

Historically this module carried a second implementation which diverged from
``EnhancedRAGClient``.  It now delegates every operation to the single Phase A
contract while retaining the import and constructor used by existing callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

try:
    from config import config
    from research.enhanced_rag import (
        EnhancedRAGClient,
        MultimodalPDFExtractor,
        NVIDIAEmbeddings,
    )
except ImportError:
    from src.config import config
    from src.research.enhanced_rag import (
        EnhancedRAGClient,
        MultimodalPDFExtractor,
        NVIDIAEmbeddings,
    )


class NVIDIARAGClient(EnhancedRAGClient):
    """Backward-compatible facade over the canonical Phase A RAG contract."""

    def __init__(
        self,
        vector_store_path: Optional[str] = None,
        workspace_id: str = "default",
        use_embeddings: bool = True,
        rerank_enabled: bool = False,
        *,
        embedder: Any = None,
        pdf_extractor: Optional[MultimodalPDFExtractor] = None,
    ) -> None:
        resolved_embedder = embedder if embedder is not None else NVIDIAEmbeddings()
        super().__init__(
            vector_store_path=vector_store_path,
            workspace_id=workspace_id,
            use_embeddings=use_embeddings,
            rerank_enabled=rerank_enabled,
            embedder=resolved_embedder,
            pdf_extractor=pdf_extractor,
        )

    @staticmethod
    def _resolve_store_dir(
        vector_store_path: Optional[str],
        workspace_id: str = "default",
    ) -> Path:
        if vector_store_path:
            path = Path(vector_store_path)
            return path.with_suffix("") if path.suffix == ".json" else path
        return Path(config.WORKSPACES_DIR) / workspace_id / "vector_store"


RAGClient = NVIDIARAGClient
