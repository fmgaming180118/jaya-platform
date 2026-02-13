
import numpy as np
from typing import List, Dict, Any
from datetime import datetime

from .ternary import TernaryLinear
from .attention import DaVinciAttention
from ..format.schema import JayaHeader, JayaFlags

class JayaHybridModel:
    """
    Pillar 26: Lingua Logica (Symbolic Processing).
    Pillar 27: Ternary Precision (Iron Body).
    Pillar 33: Da Vinci Mode (Polymath Synthesis).
    
    This is the core Neural Network of V13.0.
    Supports full weight serialization for .jay format.
    """
    
    def __init__(self, 
                 d_model: int = 512, 
                 n_layers: int = 12, 
                 n_heads: int = 8,
                 vocab_size: int = 32000):
        
        self.d_model = d_model
        self.n_layers = n_layers
        self.n_heads = n_heads
        self.vocab_size = vocab_size
        
        # 1. Embeddings (Standard Float32, critical for input nuance)
        self.token_embeddings = np.random.randn(vocab_size, d_model).astype(np.float32)
        
        # 2. Layers (The Iron Body)
        self.layers = []
        for i in range(n_layers):
            layer = {}
            # Attention Mechanism (Pillar 33)
            layer['attn'] = DaVinciAttention(d_model, n_heads, domains=["logic", "physics", "code"])
            
            # Feed Forward Network (Pillar 27)
            # Ternary weights — massive expansion without memory cost
            layer['ffn_1'] = TernaryLinear(d_model, d_model * 4)
            layer['ffn_2'] = TernaryLinear(d_model * 4, d_model)
            
            self.layers.append(layer)
            
        # 3. Output Head
        self.output_head = TernaryLinear(d_model, vocab_size)

    def forward(self, token_ids: List[int]) -> np.ndarray:
        """
        Run inference (The Magnum Cycle).
        """
        # A. Embedding Lookup
        x = self.token_embeddings[token_ids]
        
        # B. Layer Stack
        for i, layer in enumerate(self.layers):
            # 1. Attention (Da Vinci)
            attn_out = layer['attn'].forward(x)
            x = x + attn_out  # Residual
            
            # 2. FFN (Ternary Iron Body)
            ffn_out = layer['ffn_1'].forward(x[-1])
            ffn_out = layer['ffn_2'].forward(ffn_out)
            x = x + ffn_out  # Residual (broadcasting)
            
        # C. Logits
        logits = self.output_head.forward(x[-1])
        return logits
    
    # ---- Configuration ----
    
    def get_config(self) -> dict:
        """Return model hyperparameters + metadata for MODEL_CONFIG section."""
        return {
            "d_model": self.d_model,
            "n_layers": self.n_layers,
            "n_heads": self.n_heads,
            "vocab_size": self.vocab_size,
            "kernel_version": "13.0",
            "creation_timestamp": datetime.now().isoformat(),
            "parent_dna_hash": b"GENESIS_ROOT"
        }
    
    # ---- Weight Serialization ----
    
    def get_state_dict(self) -> dict:
        """
        Export all model weights for .jay IRON_BODY section.
        Returns a dict of numpy arrays (serializable by JayaSerializer).
        """
        state = {
            "embeddings": self.token_embeddings,
            "layers": [],
            "output_head": self.output_head.get_weights()
        }
        
        for i, layer in enumerate(self.layers):
            layer_state = {
                "attn": layer['attn'].get_weights(),
                "ffn_1": layer['ffn_1'].get_weights(),
                "ffn_2": layer['ffn_2'].get_weights()
            }
            state["layers"].append(layer_state)
        
        return state
    
    def load_state_dict(self, state: dict):
        """
        Reconstruct model weights from loaded .jay IRON_BODY data.
        """
        # 1. Embeddings
        self.token_embeddings = state["embeddings"].astype(np.float32)
        
        # 2. Layers
        for i, layer_state in enumerate(state["layers"]):
            self.layers[i]['attn'].load_weights(layer_state["attn"])
            self.layers[i]['ffn_1'].load_weights(layer_state["ffn_1"])
            self.layers[i]['ffn_2'].load_weights(layer_state["ffn_2"])
        
        # 3. Output Head
        self.output_head.load_weights(state["output_head"])
        
        print(f"[MODEL] Weights restored: {self.n_layers} layers, d={self.d_model}")
    
    @classmethod
    def from_config(cls, config: dict) -> 'JayaHybridModel':
        """Create a model with correct dimensions from MODEL_CONFIG."""
        return cls(
            d_model=config["d_model"],
            n_layers=config["n_layers"],
            n_heads=config["n_heads"],
            vocab_size=config["vocab_size"]
        )
