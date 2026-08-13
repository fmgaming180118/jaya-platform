"""
symbolic_interface.py — Interface between Neural Net and Symbolic Reasoner.

Provides the bridge between TinyNeuralNet and SymbolicReasoner for
neural-symbolic hybrid reasoning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import torch

from JAYA_CORE.src.neural.tiny_net import TinyNeuralNet, TinyNetConfig
from JAYA_CORE.src.reasoning import SymbolicReasoner
from JAYA_CORE.src.cognitive.contracts import Intent, IntentType

logger = logging.getLogger(__name__)


@dataclass
class TokenizerConfig:
    """Configuration for tokenizer."""
    vocab_size: int = 30000
    max_seq_len: int = 512
    pad_token: str = "[PAD]"
    unk_token: str = "[UNK]"
    cls_token: str = "[CLS]"
    sep_token: str = "[SEP]"


class SimpleTokenizer:
    """
    Simple tokenizer for TinyNeuralNet.
    
    In production, this would be replaced with a proper tokenizer (BPE, WordPiece, etc.)
    For now, implements a simple word-level tokenizer with vocab.
    """
    
    def __init__(self, config: TokenizerConfig = None):
        self.config = config or TokenizerConfig()
        self.vocab: Dict[str, int] = {}
        self.id_to_token: Dict[int, str] = {}
        self._build_vocab()
    
    def _build_vocab(self):
        """Build basic vocabulary."""
        # Special tokens
        special_tokens = [
            self.config.pad_token,
            self.config.unk_token,
            self.config.cls_token,
            self.config.sep_token,
        ]
        
        for i, token in enumerate(special_tokens):
            self.vocab[token] = i
            self.id_to_token[i] = token
        
        # Add common words (in production, load from vocab file)
        common_words = [
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
            "buat", "rencana", "python", "belajar", "machine", "learning", "kode", "program",
            "cari", "tahu", "tentang", "eksekusi", "kode", "print", "hello", "world",
            "buatkan", "rencanakan", "cari", "tahu", "jelaskan", "apa", "siapa", "bagaimana",
        ]
        
        for word in common_words:
            if word not in self.vocab:
                idx = len(self.vocab)
                self.vocab[word] = idx
                self.id_to_token[idx] = word
        
        # Fill remaining vocab with placeholder tokens
        while len(self.vocab) < 30000:
            idx = len(self.vocab)
            token = f"[UNUSED_{idx}]"
            self.vocab[token] = idx
            self.id_to_token[idx] = token
    
    def encode(self, text: str, max_length: int = None, padding: bool = True, truncation: bool = True) -> Dict[str, List[int]]:
        """Encode text to token IDs."""
        max_length = max_length or self.config.max_seq_len
        
        # Simple word-level tokenization
        words = text.lower().split()
        token_ids = [self.vocab.get(self.config.cls_token, 2)]  # CLS token
        
        for word in words:
            if len(token_ids) >= self.config.max_seq_len - 1:
                break
            token_ids.append(self.vocab.get(word, self.vocab.get(self.config.unk_token, 1)))
        
        token_ids.append(self.vocab.get(self.config.sep_token, 3))  # SEP token
        
        # Truncation
        if truncation and len(token_ids) > max_length:
            token_ids = token_ids[:max_length-1] + [self.vocab.get(self.config.sep_token, 3)]
        
        # Padding
        attention_mask = [1] * len(token_ids)
        if padding and len(token_ids) < max_length:
            pad_len = max_length - len(token_ids)
            pad_id = self.vocab.get(self.config.pad_token, 0)
            token_ids.extend([pad_id] * pad_len)
            attention_mask.extend([0] * pad_len)
        
        return {
            "input_ids": token_ids,
            "attention_mask": attention_mask,
        }
    
    def batch_encode(self, texts: List[str], max_length: int = None, padding: bool = True, truncation: bool = True) -> Dict[str, torch.Tensor]:
        """Encode batch of texts."""
        encoded = [self.encode(t, max_length, padding, truncation) for t in texts]
        
        input_ids = torch.tensor([e["input_ids"] for e in encoded], dtype=torch.long)
        attention_mask = torch.tensor([e["attention_mask"] for e in encoded], dtype=torch.long)
        
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
    
    def decode(self, token_ids: List[int]) -> str:
        """Decode token IDs back to text."""
        tokens = [self.id_to_token.get(tid, self.config.unk_token) for tid in token_ids]
        # Remove special tokens
        tokens = [t for t in tokens if t not in [self.config.pad_token, self.config.cls_token, self.config.sep_token]]
        return " ".join(tokens)


@dataclass
class NeuralSymbolicConfig:
    """Configuration for NeuralSymbolicInterface."""
    tiny_net_config: TinyNetConfig = None
    tokenizer_config: TokenizerConfig = None
    device: str = "cpu"


class NeuralSymbolicInterface:
    """
    Interface between Neural Net and Symbolic Reasoner.
    
    Provides neural capabilities (embedding, classification, reranking)
    that complement the symbolic reasoner.
    """
    
    def __init__(
        self,
        neural_net: TinyNeuralNet,
        symbolic_reasoner: Any,
        tokenizer: SimpleTokenizer = None,
        config: NeuralSymbolicConfig = None,
    ):
        self.net = neural_net
        self.reasoner = symbolic_reasoner
        self.tokenizer = tokenizer or SimpleTokenizer()
        self.config = config or NeuralSymbolicConfig()
        self.device = self.config.device
        
        # Move model to device
        self.net.to(self.device)
        self.net.eval()
        
        logger.info("NeuralSymbolicInterface initialized on device: %s", self.device)
    
    def neural_embed(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for semantic search.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            Embeddings array of shape [batch, embed_dim]
        """
        if not texts:
            return np.array([])
        
        # Tokenize
        encoded = self.tokenizer.batch_encode(texts, max_length=self.net.config.max_seq_len)
        input_ids = encoded["input_ids"].to(self.device)
        attention_mask = encoded["attention_mask"].to(self.device)
        
        # Generate embeddings
        with torch.no_grad():
            embeddings = self.net(input_ids, attention_mask, task="embed")
        
        return embeddings.cpu().numpy()
    
    def neural_classify(self, text: str, labels: List[str]) -> Dict[str, float]:
        """
        Classify text into given labels.
        
        Args:
            text: Input text
            labels: List of possible labels
            
        Returns:
            Dict mapping label to probability
        """
        # Format input for classification
        prompt = f"Classify: {text} | labels: {', '.join(labels)}"
        
        encoded = self.tokenizer.encode(prompt, max_length=self.net.config.max_seq_len)
        input_ids = torch.tensor([encoded["input_ids"]], dtype=torch.long).to(self.device)
        attention_mask = torch.tensor([encoded["attention_mask"]], dtype=torch.long).to(self.device)
        
        with torch.no_grad():
            logits = self.net(input_ids, attention_mask, task="classify")
            probs = torch.softmax(logits, dim=-1)
        
        # Map to labels (assuming labels match class indices)
        probs = probs[0].cpu().numpy()
        return {label: float(prob) for label, prob in zip(labels, probs[:len(labels)])}
    
    def neural_rerank(self, query: str, candidates: List[str]) -> List[float]:
        """
        Rerank candidates for a query using neural reranker.
        
        Args:
            query: Query string
            candidates: List of candidate strings
            
        Returns:
            List of relevance scores
        """
        if not candidates:
            return []
        
        # Encode query and candidates
        query_encoded = self.tokenizer.encode(query, max_length=self.net.config.max_seq_len // 2)
        candidate_encoded = [self.tokenizer.encode(c, max_length=self.net.config.max_seq_len // 2) for c in candidates]
        
        # Prepare batch input for reranker
        batch_size = len(candidates)
        query_ids = torch.tensor([query_encoded["input_ids"]] * len(candidates), dtype=torch.long).to(self.device)
        candidate_ids = torch.tensor([c["input_ids"] for c in candidate_encoded], dtype=torch.long).to(self.device)
        
        query_mask = torch.tensor([query_encoded["attention_mask"]] * len(candidates), dtype=torch.long).to(self.device)
        candidate_masks = torch.tensor([c["attention_mask"] for c in candidate_encoded], dtype=torch.long).to(self.device)
        
        # Stack for reranker: [batch, 2, seq_len]
        input_ids = torch.stack([query_ids, candidate_ids], dim=1)
        attention_mask = torch.stack([query_mask, candidate_masks], dim=1)
        
        with torch.no_grad():
            scores = self.net(input_ids, attention_mask, task="rerank")
        
        return scores.squeeze(-1).cpu().numpy().tolist()
    
    def semantic_search(self, query: str, documents: List[str], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Perform semantic search using neural embeddings.
        
        Args:
            query: Search query
            documents: List of document strings
            top_k: Number of top results to return
            
        Returns:
            List of dicts with document, score, and index
        """
        if not documents:
            return []
        
        # Embed query and documents
        query_emb = self.neural_embed([query])[0]  # [embed_dim]
        doc_embs = self.neural_embed(documents)  # [n_docs, embed_dim]
        
        # Compute cosine similarity
        query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-8)
        doc_norms = doc_embs / (np.linalg.norm(doc_embs, axis=1, keepdims=True) + 1e-8)
        
        scores = np.dot(doc_norms, query_norm)
        
        # Get top-k
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            results.append({
                "document": documents[idx],
                "score": float(scores[idx]),
                "index": int(idx),
            })
        
        return results
    
    def extract_entities(self, text: str, entity_types: List[str] = None) -> Dict[str, List[str]]:
        """
        Extract entities from text using neural classification.
        
        Args:
            text: Input text
            entity_types: List of entity types to extract (e.g., ["PERSON", "ORG", "LOC"])
            
        Returns:
            Dict mapping entity type to list of extracted entities
        """
        # This is a simplified implementation
        # In production, would use a proper NER model
        entity_types = entity_types or ["PERSON", "ORG", "LOC", "DATE", "TECH"]
        
        # For now, return empty - real implementation would use sequence labeling
        return {etype: [] for etype in entity_types}
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the neural model."""
        return {
            "model_type": "TinyNeuralNet",
            "total_params": self.net.get_num_params(),
            "trainable_params": self.net.get_trainable_params(),
            "config": {
                "vocab_size": self.net.config.vocab_size,
                "d_model": self.net.config.d_model,
                "n_layers": self.net.config.n_layers,
                "n_heads": self.net.config.n_heads,
                "embed_dim": self.net.config.embed_dim,
                "n_classes": self.net.config.n_classes,
            },
            "device": self.device,
        }


def create_neural_symbolic_interface(
    model_path: str = None,
    config: NeuralSymbolicConfig = None,
    symbolic_reasoner: Any = None,
) -> NeuralSymbolicInterface:
    """Factory function to create NeuralSymbolicInterface."""
    config = config or NeuralSymbolicConfig()
    
    # Create neural net
    net_config = config.tiny_net_config or TinyNetConfig()
    neural_net = TinyNeuralNet(net_config)
    
    # Load weights if path provided
    if model_path:
        neural_net = TinyNeuralNet.from_pretrained(model_path)
    
    # Create tokenizer
    tokenizer = SimpleTokenizer(config.tokenizer_config or TokenizerConfig())
    
    # Create symbolic reasoner if not provided
    if symbolic_reasoner is None:
        from JAYA_CORE.src.reasoning import create_symbolic_reasoner
        symbolic_reasoner = create_symbolic_reasoner()
    
    return NeuralSymbolicInterface(
        neural_net=neural_net,
        symbolic_reasoner=symbolic_reasoner,
        tokenizer=tokenizer,
        config=config,
    )