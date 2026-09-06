"""
tiny_net.py — Tiny Neural Network (<10M params) for JAYA Core.

Provides a small neural network for specific tasks:
- Embedding generation for semantic search
- Classification for intent/entity recognition
- Reranking for RAG

Real implementation using PyTorch - no mocks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


@dataclass
class TinyNetConfig:
    """Configuration for TinyNeuralNet."""
    vocab_size: int = 30000
    d_model: int = 256
    n_layers: int = 4
    n_heads: int = 8
    d_ff: int = 1024
    embed_dim: int = 128
    n_classes: int = 10
    max_seq_len: int = 512
    dropout: float = 0.1
    pad_token_id: int = 0


class TinyNeuralNet(nn.Module):
    """
    Tiny Neural Network (<10M params) for specific tasks.
    
    Architecture:
    - Shared embedding layer
    - Transformer encoder (2-4 layers)
    - Task-specific heads:
      - Embedding head (for semantic search)
      - Classification head (for intent/entity)
      - Reranker head (for RAG reranking)
    
    Total params: ~5-8M depending on config
    """
    
    def __init__(self, config: TinyNetConfig):
        super().__init__()
        self.config = config
        
        # Shared embedding layer
        self.embedding = nn.Embedding(
            config.vocab_size, 
            config.d_model,
            padding_idx=config.pad_token_id
        )
        
        # Positional encoding
        self.pos_encoding = nn.Parameter(
            torch.zeros(1, config.max_seq_len, config.d_model)
        )
        nn.init.normal_(self.pos_encoding, std=0.02)
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=config.d_model,
            nhead=config.n_heads,
            dim_feedforward=config.d_ff,
            dropout=config.dropout,
            batch_first=True,
            norm_first=True,  # Pre-norm for better training stability
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, config.n_layers)
        
        # Layer norm after encoder
        self.ln_final = nn.LayerNorm(config.d_model)
        
        # Task-specific heads
        self.embedding_head = nn.Linear(config.d_model, config.embed_dim)
        self.classifier_head = nn.Linear(config.d_model, config.n_classes)
        self.reranker_head = nn.Linear(config.d_model * 2, 1)
        
        # Dropout
        self.dropout = nn.Dropout(config.dropout)
        
        # Initialize weights
        self._init_weights()
        
        # Log parameter count
        total_params = sum(p.numel() for p in self.parameters())
        trainable_params = sum(p.numel() for p in self.parameters() if p.requires_grad)
        logger.info(f"TinyNeuralNet initialized: {total_params:,} total params, {trainable_params:,} trainable")
    
    def _init_weights(self):
        """Initialize weights with proper scaling."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
            elif isinstance(module, nn.LayerNorm):
                nn.init.ones_(module.weight)
                nn.init.zeros_(module.bias)
    
    def forward(
        self, 
        input_ids: torch.Tensor, 
        attention_mask: Optional[torch.Tensor] = None,
        task: str = "embed"
    ) -> torch.Tensor:
        """
        Forward pass.
        
        Args:
            input_ids: [batch_size, seq_len] token IDs (or [batch, 2, seq_len] for rerank)
            attention_mask: [batch_size, seq_len] attention mask (1 = attend, 0 = pad)
            task: One of "embed", "classify", "rerank"
            
        Returns:
            Task-specific output tensor
        """
        # Handle 3D input for rerank task first
        if task == "rerank" and input_ids.dim() == 3:
            return self._forward_rerank(input_ids, attention_mask)
        
        batch_size, seq_len = input_ids.shape
        
        # Embedding + positional encoding
        x = self.embedding(input_ids)  # [batch, seq_len, d_model]
        x = x + self.pos_encoding[:, :seq_len, :]
        x = self.dropout(x)
        
        # Prepare attention mask for transformer
        # Transformer expects True for positions to MASK (not attend)
        if attention_mask is not None:
            # Convert: 1=attend -> 0=don't mask, 0=pad -> 1=mask
            src_key_padding_mask = (attention_mask == 0)
        else:
            src_key_padding_mask = None
        
        # Transformer encoder
        x = self.encoder(x, src_key_padding_mask=src_key_padding_mask)
        x = self.ln_final(x)
        
        # Task-specific heads
        if task == "embed":
            # Use CLS token (first token) for sentence embedding
            cls_token = x[:, 0, :]  # [batch, d_model]
            return self.embedding_head(cls_token)  # [batch, embed_dim]
            
        elif task == "classify":
            # Use CLS token for classification
            cls_token = x[:, 0, :]  # [batch, d_model]
            return self.classifier_head(cls_token)  # [batch, n_classes]
        
        else:
            raise ValueError(f"Unknown task: {task}. Must be 'embed', 'classify', or 'rerank'")
    
    def _forward_rerank(self, input_ids: torch.Tensor, attention_mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        """Forward pass for rerank task with 3D input [batch, 2, seq_len]."""
        batch, pair, seq = input_ids.shape
        input_ids = input_ids.view(batch * 2, seq)
        if attention_mask is not None:
            attention_mask = attention_mask.view(batch * 2, seq)
        
        # Re-run forward for paired input
        x = self.embedding(input_ids)
        x = x + self.pos_encoding[:, :input_ids.size(1), :]
        x = self.dropout(x)
        
        if attention_mask is not None:
            src_key_padding_mask = (attention_mask == 0)
        else:
            src_key_padding_mask = None
        
        x = self.encoder(x, src_key_padding_mask=src_key_padding_mask)
        x = self.ln_final(x)
        
        # Use CLS tokens
        cls_tokens = x[:, 0, :].view(-1, 2, x.size(-1))  # [batch, 2, d_model]
        # Concatenate query and candidate representations
        combined = torch.cat([cls_tokens[:, 0], cls_tokens[:, 1]], dim=-1)  # [batch, 2*d_model]
        return self.reranker_head(combined)  # [batch, 1]
    
    def get_embedding(self, input_ids: torch.Tensor, attention_mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        """Get sentence embeddings (alias for forward with task='embed')."""
        return self.forward(input_ids, attention_mask, task="embed")
    
    def classify(self, input_ids: torch.Tensor, attention_mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        """Classify input (alias for forward with task='classify')."""
        return self.forward(input_ids, attention_mask, task="classify")
    
    def rerank(self, query_input_ids: torch.Tensor, candidate_input_ids: torch.Tensor,
               query_mask: Optional[torch.Tensor] = None, candidate_mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        Rerank candidates for a query.
        
        Args:
            query_input_ids: [batch, seq_len]
            candidate_input_ids: [batch, num_candidates, seq_len]
            query_mask: [batch, seq_len]
            candidate_mask: [batch, num_candidates, seq_len]
            
        Returns:
            scores: [batch, num_candidates]
        """
        batch, num_cand, seq_len = candidate_input_ids.shape
        
        # Repeat query for each candidate
        query_input_ids = query_input_ids.unsqueeze(1).expand(-1, num_cand, -1).reshape(-1, candidate_input_ids.size(-1))
        candidate_input_ids = candidate_input_ids.reshape(-1, candidate_input_ids.size(-1))
        
        if query_mask is not None:
            query_mask = query_mask.unsqueeze(1).expand(-1, num_cand, -1).reshape(-1, query_mask.size(-1))
        if candidate_mask is not None:
            candidate_mask = candidate_mask.reshape(-1, candidate_mask.size(-1))
        
        # Combine query and candidate
        input_ids = torch.stack([query_input_ids, candidate_input_ids], dim=1)  # [batch*num_cand, 2, seq_len]
        attention_mask = None
        if query_mask is not None and candidate_mask is not None:
            attention_mask = torch.stack([query_mask, candidate_mask], dim=1)
        
        scores = self.forward(input_ids, attention_mask, task="rerank")
        return scores.view(-1, num_cand)  # [batch, num_candidates]
    
    def save_pretrained(self, path: str):
        """Save model weights and config."""
        import json
        from pathlib import Path
        
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        # Save model weights
        torch.save(self.state_dict(), path / "pytorch_model.bin")
        
        # Save config
        config_dict = {
            "vocab_size": self.config.vocab_size,
            "d_model": self.config.d_model,
            "n_layers": self.config.n_layers,
            "n_heads": self.config.n_heads,
            "d_ff": self.config.d_ff,
            "embed_dim": self.config.embed_dim,
            "n_classes": self.config.n_classes,
            "max_seq_len": self.config.max_seq_len,
            "dropout": self.config.dropout,
            "pad_token_id": self.config.pad_token_id,
        }
        with open(path / "config.json", "w") as f:
            json.dump(config_dict, f, indent=2)
        
        logger.info(f"Model saved to {path}")
    
    @classmethod
    def from_pretrained(cls, path: str, device: str = "cpu") -> "TinyNeuralNet":
        """Load model from pretrained path."""
        from pathlib import Path
        import json
        
        path = Path(path)
        
        # Load config
        with open(path / "config.json", "r") as f:
            config_dict = json.load(f)
        config = TinyNetConfig(**config_dict)
        
        # Create model and load weights
        model = cls(config)
        state_dict = torch.load(path / "pytorch_model.bin", map_location=device)
        model.load_state_dict(state_dict)
        model.to(device)
        model.eval()
        
        logger.info(f"Model loaded from {path}")
        return model
    
    def get_num_params(self) -> int:
        """Get total number of parameters."""
        return sum(p.numel() for p in self.parameters())
    
    def get_trainable_params(self) -> int:
        """Get number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)