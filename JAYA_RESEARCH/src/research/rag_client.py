import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import config
"""
RAG Client for JAYA Research Assistant
Wrapper around NVIDIARAGClient for backward compatibility.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path

# Import the new production RAG client
from research.nvidia_rag_client import NVIDIARAGClient


class RAGClient:
    """
    Backward-compatible wrapper around NVIDIARAGClient.
    Delegates all operations to the production implementation.
    """
    
    def __init__(self, memory_path: str = config.EVOLUTION_MEMORY_PATH, workspace_id: str = "default"):
        """Initialize RAG client with NVIDIARAGClient backend"""
        # memory_path is kept for backward compatibility but not used
        # The new client uses FAISS + SQLite via VectorStore
        self._client = NVIDIARAGClient(workspace_id=workspace_id)
        self.workspace_id = workspace_id
    
    def ingest_documents(self, file_paths: List[str]) -> Dict[str, Any]:
        """
        Ingest new documents into RAG system.
        Delegates to NVIDIARAGClient.ingest_file for each path.
        """
        ingested = 0
        total_chunks = 0
        files = []
        
        for path in file_paths:
            if not os.path.exists(path):
                continue
            result = self._client.ingest_file(path, metadata={"source": os.path.basename(path)})
            if result.get("chunks_added", 0) > 0:
                ingested += 1
                total_chunks += result.get("chunks_added", 0)
                files.append(path)
        
        return {
            "status": "success" if ingested else "empty",
            "ingested": ingested,
            "chunks": total_chunks,
            "chunks_added": total_chunks,
            "files": files
        }
    
    def ingest_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ingest raw text - delegates to NVIDIARAGClient.ingest_text"""
        return self._client.ingest_text(text, metadata, self.workspace_id)
    
    def search(self, query: str, top_k: int = 5, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for relevant documents.
        Delegates to NVIDIARAGClient.search with workspace filter.
        """
        ws_id = workspace_id or self.workspace_id
        return self._client.search(query, top_k=top_k, workspace_id=ws_id)
    
    def query(self, query_text: str, top_k: int = 5, web_fallback: bool = True) -> Dict[str, Any]:
        """High-level query with web fallback - delegates to NVIDIARAGClient.query"""
        return self._client.query(query_text, top_k=top_k, web_fallback=web_fallback)
    
    def list_documents(self) -> List[Dict[str, str]]:
        """List all indexed documents - delegates to NVIDIARAGClient.list_documents"""
        return self._client.list_documents()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics"""
        return self._client.get_stats()
    
    def delete_by_source(self, source_id: str) -> int:
        """Delete documents by source"""
        return self._client.delete_by_source(source_id)


# For future: Full NVIDIA RAG integration
class NVIDIARAGClient:
    """
    Full RAG client using NVIDIA NIM services.
    This would replace RAGClient when deploying with multimodal capabilities.
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('NVIDIA_API_KEY')
        # Initialize NVIDIA NIM clients for:
        # - nv-ingest (document ingestion)
        # - nv-embedqa (embeddings)
        # - nv-rerankqa (reranking)
        pass
    
    def ingest_multimodal(self, file_paths: List[str]):
        """Ingest PDFs with images, tables, charts"""
        # Use NVIDIA NIM nv-ingest service
        pass
    
    def search_multimodal(self, query: str, top_k: int = 5):
        """Search with embeddings and reranking"""
        # Use NVIDIA NIM embeddings + reranker
        pass
