"""
Compressed Knowledge Index for Jaya AI
A simple in-memory index for demonstration. In production, replace with FAISS-IVFPQ or Annoy with PQ.
"""

import logging
import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class CompressedIndex:
    def __init__(self):
        """
        Initialize an empty index.
        We'll store documents and a simple term-frequency inverse document frequency (TF-IDF) index.
        """
        self.docs: List[Dict[str, Any]] = []  # each doc: {'id': str, 'text': str, 'metadata': dict}
        self.term_doc_freq: Dict[str, int] = defaultdict(int)
        self.doc_vectors: List[Dict[str, float]] = []  # sparse tf-idf vectors per doc
        self._is_dirty = True

    def add_document(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Add a document to the index.
        :param doc_id: Unique identifier.
        :param text: Document text.
        :param metadata: Optional metadata.
        """
        self.docs.append({'id': doc_id, 'text': text, 'metadata': metadata or {}})
        self._is_dirty = True
        logger.debug(f"Added document {doc_id}")

    def remove_document(self, doc_id: str):
        """
        Remove a document by id.
        """
        for i, doc in enumerate(self.docs):
            if doc['id'] == doc_id:
                del self.docs[i]
                self._is_dirty = True
                logger.debug(f"Removed document {doc_id}")
                return
        logger.warning(f"Document {doc_id} not found for removal.")

    def _compute_tfidf(self):
        """Compute TF-IDF vectors for all documents."""
        # Term frequency per document
        tf_list: List[Dict[str, float]] = []
        for doc in self.docs:
            words = doc['text'].lower().split()
            tf: Dict[str, float] = defaultdict(int)
            for w in words:
                tf[w] += 1
            # normalize by max freq
            if tf:
                max_freq = max(tf.values())
                for w in tf:
                    tf[w] = tf[w] / max_freq
            tf_list.append(tf)
            # update document frequency
            for w in set(tf.keys()):
                self.term_doc_freq[w] += 1
        # Compute TF-IDF
        N = len(self.docs)
        self.doc_vectors = []
        for tf in tf_list:
            vec: Dict[str, float] = {}
            for term, tf_val in tf.items():
                df = self.term_doc_freq.get(term, 0)
                if df > 0:
                    idf = math.log((N + 1) / (df + 1)) + 1  # smoothed
                    vec[term] = tf_val * idf
            self.doc_vectors.append(vec)
        self._is_dirty = False

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Search for top_k documents similar to query.
        :param query: Query string.
        :param top_k: Number of results to return.
        :return: List of (doc_id, score) sorted descending.
        """
        if self._is_dirty:
            self._compute_tfidf()
        # Compute query vector
        q_words = query.lower().split()
        q_tf: Dict[str, float] = defaultdict(int)
        for w in q_words:
            q_tf[w] += 1
        if q_tf:
            max_q = max(q_tf.values())
            for w in q_tf:
                q_tf[w] = q_tf[w] / max_q
        # TF-IDF for query (using same idf as docs)
        N = len(self.docs)
        q_vec: Dict[str, float] = {}
        for term, tf_val in q_tf.items():
            df = self.term_doc_freq.get(term, 0)
            if df > 0:
                idf = math.log((N + 1) / (df + 1)) + 1
                q_vec[term] = tf_val * idf
        # Compute cosine similarity
        scores: List[Tuple[int, float]] = []
        for i, doc_vec in enumerate(self.doc_vectors):
            dot = sum(q_vec.get(t, 0) * dv for t, dv in doc_vec.items())
            norm_q = math.sqrt(sum(v*v for v in q_vec.values()))
            norm_d = math.sqrt(sum(v*v for v in doc_vec.values()))
            if norm_q == 0 or norm_d == 0:
                sim = 0.0
            else:
                sim = dot / (norm_q * norm_d)
            scores.append((i, sim))
        # Sort descending
        scores.sort(key=lambda x: x[1], reverse=True)
        # Return top_k doc ids and scores
        results = []
        for idx, score in scores[:top_k]:
            doc_id = self.docs[idx]['id']
            results.append((doc_id, score))
        return results

    def get_document_text(self, doc_id: str) -> Optional[str]:
        """Retrieve the full text of a document by id."""
        for doc in self.docs:
            if doc['id'] == doc_id:
                return doc['text']
        return None

    def clear(self):
        """Clear the index."""
        self.docs.clear()
        self.term_doc_freq.clear()
        self.doc_vectors.clear()
        self._is_dirty = True
