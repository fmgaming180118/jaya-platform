"""
Enhanced RAG (Retrieval-Augmented Generation) for JAYA_CORE.

Provides:
- Hybrid search (BM25 + semantic vector search)
- Multiple embedding model support
- Query expansion and reranking
- Context-aware retrieval
- Incremental indexing
"""

from __future__ import annotations

import logging
import math
import re
import time
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from JAYA_CORE.src.observability import get_structured_logger, record_error
from JAYA_CORE.src.security import get_audit_logger

logger = get_structured_logger(__name__, component="rag_enhanced")
audit_logger = get_audit_logger()


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Document:
    """Document for RAG indexing."""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class SearchResult:
    """Search result with score and metadata."""
    document: Document
    score: float
    search_type: str  # "bm25", "vector", "hybrid"
    rank: int = 0
    highlights: List[str] = field(default_factory=list)


@dataclass
class RAGConfig:
    """Configuration for RAG system."""
    # Embedding
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    embedding_batch_size: int = 32
    
    # Search
    bm25_weight: float = 0.4
    vector_weight: float = 0.6
    top_k: int = 10
    rerank_top_k: int = 5
    
    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 50
    min_chunk_size: int = 100
    
    # Query processing
    expand_query: bool = True
    max_query_expansions: int = 3
    
    # Filtering
    similarity_threshold: float = 0.3
    bm25_threshold: float = 0.1


# ============================================================================
# Embedding Providers
# ============================================================================

class EmbeddingProvider(ABC):
    """Abstract embedding provider."""
    
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        pass
    
    @abstractmethod
    def embed_single(self, text: str) -> List[float]:
        """Generate embedding for single text."""
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding dimension."""
        pass


class SentenceTransformerProvider(EmbeddingProvider):
    """Sentence Transformers embedding provider."""
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._load_model()
    
    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            logger.info("Loaded embedding model", model=self.model_name)
        except ImportError:
            logger.error("sentence-transformers not installed")
            raise
        except Exception as e:
            logger.error("Failed to load embedding model", error=str(e))
            raise
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self._model:
            self._load_model()
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    def embed_single(self, text: str) -> List[float]:
        return self.embed([text])[0]
    
    @property
    def dimension(self) -> int:
        if self._model:
            return self._model.get_sentence_embedding_dimension()
        return 384


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama embedding provider."""
    
    def __init__(self, model_name: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        import requests
        embeddings = []
        for text in texts:
            embeddings.append(self.embed_single(text))
        return embeddings
    
    def embed_single(self, text: str) -> List[float]:
        import requests
        response = requests.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model_name, "prompt": text},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["embedding"]
    
    @property
    def dimension(self) -> int:
        # nomic-embed-text is 768 dimensions
        return 768


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embedding provider."""
    
    def __init__(self, model_name: str = "text-embedding-3-small", api_key: str = None):
        self.model_name = model_name
        self.api_key = api_key
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        response = client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        return [d.embedding for d in response.data]
    
    def embed_single(self, text: str) -> List[float]:
        return self.embed([text])[0]
    
    @property
    def dimension(self) -> int:
        if "large" in self.model_name:
            return 3072
        return 1536


# ============================================================================
# BM25 Implementation
# ============================================================================

class BM25Index:
    """BM25 full-text search index."""
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: Dict[str, Document] = {}
        self.doc_freqs: Dict[str, Dict[str, int]] = {}  # doc_id -> term -> freq
        self.term_doc_freq: Dict[str, int] = {}  # term -> doc count
        self.doc_lengths: Dict[str, int] = {}
        self.avgdl: float = 0
        self.N: int = 0
    
    def add_document(self, doc: Document):
        """Add document to index."""
        self.documents[doc.id] = doc
        
        # Tokenize
        terms = self._tokenize(doc.content)
        self.doc_lengths[doc.id] = len(terms)
        
        # Count term frequencies
        term_freq = Counter(terms)
        self.doc_freqs[doc.id] = dict(term_freq)
        
        # Update document frequency
        for term in term_freq:
            self.term_doc_freq[term] = self.term_doc_freq.get(term, 0) + 1
        
        self.N += 1
        self._update_avgdl()
    
    def remove_document(self, doc_id: str):
        """Remove document from index."""
        if doc_id not in self.documents:
            return
        
        # Update term document frequencies
        for term in self.doc_freqs[doc_id]:
            self.term_doc_freq[term] -= 1
            if self.term_doc_freq[term] <= 0:
                del self.term_doc_freq[term]
        
        del self.documents[doc_id]
        del self.doc_freqs[doc_id]
        del self.doc_lengths[doc_id]
        self.N -= 1
        self._update_avgdl()
    
    def _update_avgdl(self):
        """Update average document length."""
        if self.doc_lengths:
            self.avgdl = sum(self.doc_lengths.values()) / len(self.doc_lengths)
        else:
            self.avgdl = 0
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        # Lowercase and split on non-alphanumeric
        text = text.lower()
        # Keep alphanumeric and some special chars
        tokens = re.findall(r'[a-zA-Z0-9_]+', text)
        return tokens
    
    def _idf(self, term: str) -> float:
        """Calculate IDF for term."""
        df = self.term_doc_freq.get(term, 0)
        if df == 0:
            return 0
        return math.log((self.N - df + 0.5) / (df + 0.5) + 1)
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Search using BM25."""
        query_terms = self._tokenize(query)
        if not query_terms:
            return []
        
        scores = {}
        
        for doc_id, doc in self.documents.items():
            score = 0.0
            doc_len = self.doc_lengths.get(doc_id, 0)
            term_freqs = self.doc_freqs.get(doc_id, {})
            
            for term in query_terms:
                tf = term_freqs.get(term, 0)
                if tf == 0:
                    continue
                
                idf = self._idf(term)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                score += idf * numerator / denominator
            
            if score > 0:
                scores[doc_id] = score
        
        # Sort by score
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]


# ============================================================================
# Vector Index
# ============================================================================

class VectorIndex:
    """Vector similarity index using numpy."""
    
    def __init__(self, dimension: int):
        self.dimension = dimension
        self.vectors: Dict[str, np.ndarray] = {}
        self.documents: Dict[str, Document] = {}
    
    def add_document(self, doc: Document):
        """Add document with embedding."""
        if doc.embedding is None:
            raise ValueError("Document must have embedding")
        
        vec = np.array(doc.embedding, dtype=np.float32)
        if vec.shape[0] != self.dimension:
            raise ValueError(f"Embedding dimension mismatch: {vec.shape[0]} != {self.dimension}")
        
        # Normalize for cosine similarity
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        
        self.vectors[doc.id] = vec
        self.documents[doc.id] = doc
    
    def remove_document(self, doc_id: str):
        """Remove document."""
        self.vectors.pop(doc_id, None)
        self.documents.pop(doc_id, None)
    
    def search(self, query_embedding: List[float], top_k: int = 10, threshold: float = 0.0) -> List[Tuple[str, float]]:
        """Search by cosine similarity."""
        if not self.vectors:
            return []
        
        query_vec = np.array(query_embedding, dtype=np.float32)
        norm = np.linalg.norm(query_vec)
        if norm > 0:
            query_vec = query_vec / norm
        
        # Compute cosine similarities
        scores = {}
        for doc_id, vec in self.vectors.items():
            similarity = float(np.dot(query_vec, vec))
            if similarity >= threshold:
                scores[doc_id] = similarity
        
        # Sort by score
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]


# ============================================================================
# Hybrid Search Engine
# ============================================================================

class HybridSearchEngine:
    """Hybrid search combining BM25 and vector search."""
    
    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self.bm25_index = BM25Index()
        self.vector_index: Optional[VectorIndex] = None
        self.embedding_provider: Optional[EmbeddingProvider] = None
        self._initialized = False
    
    def initialize(self, embedding_provider: EmbeddingProvider = None):
        """Initialize the search engine."""
        if embedding_provider:
            self.embedding_provider = embedding_provider
        elif not self.embedding_provider:
            # Default to sentence transformers
            self.embedding_provider = SentenceTransformerProvider(self.config.embedding_model)
        
        self.vector_index = VectorIndex(self.embedding_provider.dimension)
        self._initialized = True
        logger.info("Hybrid search engine initialized", 
                   embedding_model=self.embedding_provider.model_name,
                   dimension=self.embedding_provider.dimension)
    
    def add_document(self, doc: Document):
        """Add document to both indexes."""
        if not self._initialized:
            self.initialize()
        
        # Generate embedding if not present
        if doc.embedding is None and self.embedding_provider:
            doc.embedding = self.embedding_provider.embed_single(doc.content)
        
        # Add to BM25
        self.bm25_index.add_document(doc)
        
        # Add to vector index
        if doc.embedding:
            self.vector_index.add_document(doc)
        
        logger.debug("Document added to hybrid index", doc_id=doc.id)
    
    def add_documents(self, docs: List[Document]):
        """Add multiple documents efficiently."""
        if not self._initialized:
            self.initialize()
        
        # Generate embeddings in batch
        texts = [doc.content for doc in docs if doc.embedding is None]
        if texts and self.embedding_provider:
            embeddings = self.embedding_provider.embed(texts)
            idx = 0
            for doc in docs:
                if doc.embedding is None:
                    doc.embedding = embeddings[idx]
                    idx += 1
        
        # Add to indexes
        for doc in docs:
            self.bm25_index.add_document(doc)
            if doc.embedding:
                self.vector_index.add_document(doc)
        
        logger.info("Documents added to hybrid index", count=len(docs))
    
    def remove_document(self, doc_id: str):
        """Remove document from both indexes."""
        self.bm25_index.remove_document(doc_id)
        if self.vector_index:
            self.vector_index.remove_document(doc_id)
    
    def search(
        self,
        query: str,
        top_k: int = None,
        bm25_weight: float = None,
        vector_weight: float = None,
        filter_fn: Callable[[Document], bool] = None,
    ) -> List[SearchResult]:
        """Hybrid search combining BM25 and vector similarity."""
        if not self._initialized:
            self.initialize()
        
        top_k = top_k or self.config.top_k
        bm25_weight = bm25_weight if bm25_weight is not None else self.config.bm25_weight
        vector_weight = vector_weight if vector_weight is not None else self.config.vector_weight
        
        # Normalize weights
        total_weight = bm25_weight + vector_weight
        if total_weight > 0:
            bm25_weight /= total_weight
            vector_weight /= total_weight
        
        # BM25 search
        bm25_results = self.bm25_index.search(query, top_k * 2)
        bm25_scores = {doc_id: score for doc_id, score in bm25_results}
        
        # Vector search
        vector_scores = {}
        if self.embedding_provider and self.vector_index:
            query_embedding = self.embedding_provider.embed_single(query)
            vector_results = self.vector_index.search(
                query_embedding, 
                top_k * 2, 
                threshold=self.config.similarity_threshold
            )
            vector_scores = {doc_id: score for doc_id, score in vector_results}
        
        # Combine scores
        all_doc_ids = set(bm25_scores.keys()) | set(vector_scores.keys())
        combined_results = []
        
        for doc_id in all_doc_ids:
            bm25_score = bm25_scores.get(doc_id, 0)
            vector_score = vector_scores.get(doc_id, 0)
            
            # Normalize BM25 score (rough normalization)
            norm_bm25 = min(bm25_score / 10.0, 1.0) if bm25_score > 0 else 0
            
            combined_score = bm25_weight * norm_bm25 + vector_weight * vector_score
            
            if combined_score > 0:
                doc = self.bm25_index.documents.get(doc_id) or self.vector_index.documents.get(doc_id)
                if doc and (filter_fn is None or filter_fn(doc)):
                    combined_results.append(SearchResult(
                        document=doc,
                        score=combined_score,
                        search_type="hybrid",
                    ))
        
        # Sort and rank
        combined_results.sort(key=lambda x: x.score, reverse=True)
        for i, result in enumerate(combined_results[:top_k]):
            result.rank = i + 1
        
        return combined_results[:top_k]
    
    def search_bm25_only(self, query: str, top_k: int = None) -> List[SearchResult]:
        """Search using only BM25."""
        top_k = top_k or self.config.top_k
        results = self.bm25_index.search(query, top_k)
        return [
            SearchResult(
                document=self.bm25_index.documents[doc_id],
                score=score,
                search_type="bm25",
                rank=i + 1,
            )
            for i, (doc_id, score) in enumerate(results)
        ]
    
    def search_vector_only(self, query: str, top_k: int = None) -> List[SearchResult]:
        """Search using only vector similarity."""
        if not self.embedding_provider or not self.vector_index:
            return []
        
        top_k = top_k or self.config.top_k
        query_embedding = self.embedding_provider.embed_single(query)
        results = self.vector_index.search(query_embedding, top_k, self.config.similarity_threshold)
        return [
            SearchResult(
                document=self.vector_index.documents[doc_id],
                score=score,
                search_type="vector",
                rank=i + 1,
            )
            for i, (doc_id, score) in enumerate(results)
        ]


# ============================================================================
# Query Expansion
# ============================================================================

class QueryExpander:
    """Expand queries for better retrieval."""
    
    def __init__(self, embedding_provider: EmbeddingProvider = None):
        self.embedding_provider = embedding_provider
        self._synonym_cache: Dict[str, List[str]] = {}
    
    def expand(self, query: str, max_expansions: int = 3) -> List[str]:
        """Generate expanded queries."""
        expanded = [query]
        
        # Simple synonym expansion (would use WordNet or similar in production)
        synonyms = self._get_synonyms(query)
        for syn in synonyms[:max_expansions]:
            expanded.append(syn)
        
        # Query decomposition for complex queries
        if len(query.split()) > 5:
            sub_queries = self._decompose_query(query)
            expanded.extend(sub_queries[:max_expansions])
        
        return expanded[:max_expansions + 1]
    
    def _get_synonyms(self, query: str) -> List[str]:
        """Get synonyms for query terms."""
        # Placeholder - would integrate with WordNet or similar
        return []
    
    def _decompose_query(self, query: str) -> List[str]:
        """Decompose complex query into sub-queries."""
        # Split by conjunctions
        parts = re.split(r'\b(?:and|or|but)\b', query, flags=re.IGNORECASE)
        return [p.strip() for p in parts if len(p.strip()) > 10]


# ============================================================================
# Reranker
# ============================================================================

class Reranker:
    """Rerank search results for better relevance."""
    
    def __init__(self, embedding_provider: EmbeddingProvider = None):
        self.embedding_provider = embedding_provider
    
    def rerank(
        self,
        query: str,
        results: List[SearchResult],
        top_k: int = 5,
    ) -> List[SearchResult]:
        """Rerank results using cross-encoder or semantic similarity."""
        if not results or not self.embedding_provider:
            return results[:top_k]
        
        query_embedding = self.embedding_provider.embed_single(query)
        
        # Re-score using embedding similarity
        for result in results:
            if result.document.embedding:
                doc_embedding = np.array(result.document.embedding)
                query_vec = np.array(query_embedding)
                
                # Cosine similarity
                sim = float(np.dot(query_vec, doc_embedding) / 
                           (np.linalg.norm(query_vec) * np.linalg.norm(doc_embedding)))
                
                # Combine with original score
                result.score = 0.7 * result.score + 0.3 * sim
        
        # Re-sort
        results.sort(key=lambda x: x.score, reverse=True)
        for i, result in enumerate(results[:top_k]):
            result.rank = i + 1
        
        return results[:top_k]


# ============================================================================
# Enhanced RAG Pipeline
# ============================================================================

class EnhancedRAGPipeline:
    """Complete RAG pipeline with hybrid search, expansion, and reranking."""
    
    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self.search_engine = HybridSearchEngine(config)
        self.query_expander = QueryExpander()
        self.reranker = Reranker()
        self._initialized = False
    
    def initialize(self, embedding_provider: EmbeddingProvider = None):
        """Initialize the pipeline."""
        self.search_engine.initialize(embedding_provider)
        self.query_expander.embedding_provider = self.search_engine.embedding_provider
        self.reranker.embedding_provider = self.search_engine.embedding_provider
        self._initialized = True
        logger.info("Enhanced RAG pipeline initialized")
    
    def add_documents(self, docs: List[Document]):
        """Add documents to the pipeline."""
        if not self._initialized:
            self.initialize()
        self.search_engine.add_documents(docs)
    
    def add_document(self, doc: Document):
        """Add single document."""
        if not self._initialized:
            self.initialize()
        self.search_engine.add_document(doc)
    
    def retrieve(
        self,
        query: str,
        top_k: int = None,
        use_expansion: bool = None,
        use_rerank: bool = None,
        filter_fn: Callable[[Document], bool] = None,
    ) -> List[SearchResult]:
        """Retrieve relevant documents for query."""
        if not self._initialized:
            self.initialize()
        
        top_k = top_k or self.config.top_k
        use_expansion = use_expansion if use_expansion is not None else self.config.expand_query
        use_rerank = use_rerank if use_rerank is not None else (self.config.rerank_top_k > 0)
        
        # Expand query
        queries = [query]
        if use_expansion:
            queries = self.query_expander.expand(query, self.config.max_query_expansions)
        
        # Search for each expanded query
        all_results = []
        for q in queries:
            results = self.search_engine.search(q, top_k * 2, filter_fn=filter_fn)
            all_results.extend(results)
        
        # Deduplicate by document ID
        seen = set()
        unique_results = []
        for result in all_results:
            if result.document.id not in seen:
                seen.add(result.document.id)
                unique_results.append(result)
        
        # Rerank
        if use_rerank and unique_results:
            unique_results = self.reranker.rerank(query, unique_results, self.config.rerank_top_k)
        else:
            unique_results.sort(key=lambda x: x.score, reverse=True)
            for i, result in enumerate(unique_results[:top_k]):
                result.rank = i + 1
        
        return unique_results[:top_k]
    
    def generate_context(
        self,
        query: str,
        max_tokens: int = 2000,
        top_k: int = None,
    ) -> str:
        """Generate context string for LLM prompt."""
        results = self.retrieve(query, top_k)
        
        context_parts = []
        total_tokens = 0
        
        for result in results:
            # Estimate tokens (rough: 1 token ≈ 4 chars)
            content = result.document.content
            est_tokens = len(content) // 4
            
            if total_tokens + est_tokens > max_tokens:
                # Truncate
                remaining = max_tokens - total_tokens
                if remaining > 100:
                    content = content[:remaining * 4] + "..."
                    context_parts.append(f"[Source: {result.document.id}] {content}")
                break
            
            context_parts.append(f"[Source: {result.document.id}] {content}")
            total_tokens += est_tokens
        
        return "\n\n".join(context_parts)


# ============================================================================
# Factory Functions
# ============================================================================

def create_rag_pipeline(
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    config: RAGConfig = None,
) -> EnhancedRAGPipeline:
    """Create RAG pipeline with specified embedding model."""
    pipeline = EnhancedRAGPipeline(config)
    
    if "sentence-transformers" in embedding_model:
        provider = SentenceTransformerProvider(embedding_model)
    elif "ollama" in embedding_model.lower() or "/" not in embedding_model:
        provider = OllamaEmbeddingProvider(embedding_model)
    elif "openai" in embedding_model.lower() or "text-embedding" in embedding_model:
        provider = OpenAIEmbeddingProvider(embedding_model)
    else:
        provider = SentenceTransformerProvider(embedding_model)
    
    pipeline.initialize(provider)
    return pipeline


# ============================================================================
# Default Instance
# ============================================================================

_rag_pipeline: Optional[EnhancedRAGPipeline] = None


def get_rag_pipeline() -> EnhancedRAGPipeline:
    """Get global RAG pipeline instance."""
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = create_rag_pipeline()
    return _rag_pipeline