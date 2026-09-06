"""Backward-compatible wrapper for the canonical Phase A RAG contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from jaya_research.research.nvidia_rag_client import NVIDIARAGClient
except ImportError:
    from jaya_research.research.nvidia_rag_client import NVIDIARAGClient


class RAGClient:
    """Delegate legacy calls without maintaining a second RAG implementation."""

    def __init__(
        self,
        memory_path: Optional[str] = None,
        workspace_id: str = "default",
        *,
        vector_store_path: Optional[str] = None,
        client: Optional[NVIDIARAGClient] = None,
    ) -> None:
        if memory_path and vector_store_path:
            raise ValueError("Use memory_path or vector_store_path, not both")
        resolved_path = vector_store_path or memory_path
        self._client = client or NVIDIARAGClient(
            vector_store_path=resolved_path,
            workspace_id=workspace_id,
        )
        self.workspace_id = self._client.workspace_id

    def ingest_documents(self, file_paths: List[str]) -> Dict[str, Any]:
        """Ingest existing files and report every rejected input explicitly."""
        ingested = 0
        total_chunks = 0
        files: List[str] = []
        failures: List[Dict[str, str]] = []

        for raw_path in file_paths:
            path = Path(raw_path).expanduser()
            if not path.is_file():
                failures.append(
                    {"file": str(path), "error_code": "FILE_NOT_FOUND"}
                )
                continue
            result = self._client.ingest_file(
                str(path),
                metadata={"source": path.name},
                workspace_id=self.workspace_id,
            )
            chunks_added = int(result.get("chunks_added", 0))
            if result.get("status") == "success" and chunks_added > 0:
                ingested += 1
                total_chunks += chunks_added
                files.append(str(path))
            else:
                failures.append(
                    {
                        "file": str(path),
                        "error_code": str(
                            result.get("error_code")
                            or result.get("extraction_status")
                            or result.get("status")
                            or "INGEST_REJECTED"
                        ),
                    }
                )

        return {
            "status": (
                "success"
                if ingested and not failures
                else "partial"
                if ingested
                else "empty"
            ),
            "ingested": ingested,
            "chunks": total_chunks,
            "chunks_added": total_chunks,
            "files": files,
            "failures": failures,
            "workspace_id": self.workspace_id,
        }

    def ingest_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._client.ingest_text(
            text,
            metadata,
            workspace_id=self.workspace_id,
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        workspace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return self._client.search(
            query,
            top_k=top_k,
            workspace_id=workspace_id or self.workspace_id,
        )

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        web_fallback: bool = True,
    ) -> Dict[str, Any]:
        return self._client.query(
            query_text,
            top_k=top_k,
            web_fallback=web_fallback,
        )

    def list_documents(self) -> List[Dict[str, str]]:
        return self._client.list_documents()

    def get_stats(self) -> Dict[str, Any]:
        return self._client.get_stats()

    def delete_by_source(
        self,
        source_id: str,
        workspace_id: Optional[str] = None,
    ) -> int:
        return self._client.delete_by_source(
            source_id,
            workspace_id=workspace_id or self.workspace_id,
        )

    def reload(self) -> Dict[str, Any]:
        return self._client.reload()


__all__ = ["NVIDIARAGClient", "RAGClient"]
