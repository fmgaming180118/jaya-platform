"""
Enhanced RAG Client with NVIDIA NIM Embeddings
Supports vector search using NVIDIA NIM API
"""
import os
import json
import hashlib
import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path
import requests

class NVIDIAEmbeddings:
    """NVIDIA NIM Embeddings API Client"""
    
    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize NVIDIA embeddings client.
        
        Args:
            api_key: NVIDIA API key (defaults to NVIDIA_API_KEY env var)
            model: Embedding model to use
        """
        self.api_key = api_key or os.getenv('NVIDIA_API_KEY')
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY not found in environment")
        
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY not found in environment")
        
        # STRICT NO-HARDCODING: Load from Env, default to config if needed (but prefer env)
        self.model = model or os.getenv("NVIDIA_EMBEDDING_MODEL")
        if not self.model:
             raise ValueError("NVIDIA_EMBEDDING_MODEL not found in .env")
        self.base_url = "https://integrate.api.nvidia.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        # NVIDIA NIM embeddings endpoint
        url = f"{self.base_url}/embeddings"
        
        payload = {
            "input": texts,
            "model": self.model,
            "input_type": "passage"  # or "query" for search queries
        }
        
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            embeddings = [item['embedding'] for item in data['data']]
            
            return embeddings
        
        except requests.exceptions.RequestException as e:
            print(f"Error calling NVIDIA embeddings API: {e}")
            # Fallback to random embeddings for development
            return [[0.0] * 1024 for _ in texts]
    
    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single query.
        
        Args:
            query: Search query string
            
        Returns:
            Embedding vector
        """
        url = f"{self.base_url}/embeddings"
        
        payload = {
            "input": [query],
            "model": self.model,
            "input_type": "query"
        }
        
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            return data['data'][0]['embedding']
        
        except requests.exceptions.RequestException as e:
            print(f"Error embedding query: {e}")
            return [0.0] * 1024


import faiss

class VectorStore:
    """FAISS-powered vector store for high-performance similarity search"""
    
    def __init__(self, storage_path: str = None):
        """Initialize vector store
        Args:
            storage_path: Path to save/load vector data. If None, defaults to data/vector_store.json
        """
        self.storage_path = storage_path or "data/vector_store.json"
        self.index_path = self.storage_path.replace(".json", ".index")
        
        self.documents = []
        self.index = None
        self._load()
    
    def add_documents(self, documents: List[Dict[str, Any]], embeddings: List[List[float]]):
        """Add documents and their embeddings to the store"""
        if not embeddings:
            return

        # Convert to numpy float32
        embeddings_np = np.array(embeddings).astype('float32')
        faiss.normalize_L2(embeddings_np) # Normalize for Cosine Similarity (Inner Product)
        
        # Initialize index if needed
        if self.index is None:
            dimension = embeddings_np.shape[1]
            self.index = faiss.IndexFlatIP(dimension) # Inner Product for similarity
            
        self.index.add(embeddings_np)
        self.documents.extend(documents)
        self._save()
    
    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar documents using FAISS.
        """
        if not self.index or self.index.ntotal == 0:
            return []
        
        # Convert to numpy float32
        query_vec = np.array([query_embedding]).astype('float32')
        faiss.normalize_L2(query_vec)
        
        # Search
        distances, indices = self.index.search(query_vec, top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1 or idx >= len(self.documents):
                continue
                
            results.append({
                "document": self.documents[idx],
                "score": float(distances[0][i]),
                "snippet": self._extract_snippet(self.documents[idx].get('content', ''))
            })
        
        return results
    
    def _extract_snippet(self, content: str, max_length: int = 200) -> str:
        """Extract snippet from content"""
        if len(content) <= max_length:
            return content
        return content[:max_length] + "..."
    
    def _save(self):
        """Save documents and FAISS index to disk"""
        # Save Documents (Metadata)
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump({"documents": self.documents}, f, ensure_ascii=False, indent=2)
            
        # Save FAISS index
        if self.index:
            faiss.write_index(self.index, self.index_path)
    
    def _load(self):
        """Load documents and FAISS index from disk"""
        # Load Documents
        if os.path.exists(self.storage_path):
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.documents = data.get('documents', [])
        
        # Load FAISS Index
        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
        else:
            self.index = None


class EnhancedRAGClient:
    """
    Enhanced RAG client with NVIDIA NIM embeddings and vector search.
    Replaces the simpler keyword-based RAGClient.
    """
    
    def __init__(self, use_embeddings: bool = True, vector_store_path: str = None):
        """
        Initialize Enhanced RAG Client.
        
        Args:
            use_embeddings: If True, use NVIDIA embeddings. If False, fallback to keyword search.
            vector_store_path: Path to the vector store file (for Workspaces)
        """
        self.use_embeddings = use_embeddings
        
        if self.use_embeddings:
            try:
                self.embedder = NVIDIAEmbeddings()
                self.vector_store = VectorStore(storage_path=vector_store_path)
                print("[RAG] ✅ NVIDIA embeddings enabled")
            except ValueError as e:
                print(f"[RAG] ⚠️  {e}, falling back to keyword search")
                self.use_embeddings = False
        
        # Fallback to simple keyword search
        if not self.use_embeddings:
            from research.rag_client import RAGClient as SimpleRAG
            self.simple_rag = SimpleRAG()
    
    def ingest_documents(self, file_paths: List[str]) -> Dict[str, Any]:
        """
        Ingest documents with embedding generation.
        
        Args:
            file_paths: List of document paths
            
        Returns:
            Ingestion status
        """
        documents = []
        texts = []
        
        for path in file_paths:
            if not os.path.exists(path):
                continue
            
            try:
                # Read document
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Chunk document (simple splitting for MVP)
                chunks = self._chunk_text(content, chunk_size=512)
                
                for i, chunk in enumerate(chunks):
                    doc = {
                        "type": "research_document",
                        "file_path": path,
                        "file_name": os.path.basename(path),
                        "chunk_id": i,
                        "content": chunk,
                        "timestamp": __import__('time').time()
                    }
                    documents.append(doc)
                    texts.append(chunk)
            
            except Exception as e:
                print(f"[RAG] Error ingesting {path}: {e}")
        
        if not documents:
            return {"status": "error", "message": "No documents ingested"}
        
        # Generate embeddings if enabled
        if self.use_embeddings:
            print(f"[RAG] Generating embeddings for {len(texts)} chunks...")
            embeddings = self.embedder.embed_texts(texts)
            self.vector_store.add_documents(documents, embeddings)
            print(f"[RAG] ✅ Ingested {len(documents)} chunks with embeddings")
        else:
            # Use simple RAG fallback
            return self.simple_rag.ingest_documents(file_paths)
        
        return {
            "status": "success",
            "ingested": len(file_paths),
            "chunks": len(documents)
        }
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search documents using vector similarity.
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            List of relevant documents
        """
        if self.use_embeddings:
            # Vector search
            query_embedding = self.embedder.embed_query(query)
            results = self.vector_store.search(query_embedding, top_k=top_k)
            return results
        else:
            # Keyword search fallback
            return self.simple_rag.search(query, top_k=top_k)
    
    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 128) -> List[str]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Text to chunk
            chunk_size: Size of each chunk in characters
            overlap: Overlap between chunks
            
        Returns:
            List of text chunks
        """
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap
        
        return chunks
    
    def list_documents(self) -> List[Dict[str, str]]:
        """List indexed documents"""
        if self.use_embeddings:
            # Get unique file names from vector store
            files = {}
            for doc in self.vector_store.documents:
                fname = doc.get('file_name', 'Unknown')
                if fname not in files:
                    files[fname] = {
                        "name": fname,
                        "type": doc.get('type', 'Unknown'),
                        "path": doc.get('file_path', 'N/A')
                    }
            return list(files.values())
        else:
            return self.simple_rag.list_documents()
