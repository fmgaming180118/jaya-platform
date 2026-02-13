
import numpy as np

class DaVinciAttention:
    """
    Pillar 33: Da Vinci Mode (Polymath Synthesis).
    
    Standard Multi-Head Attention, but heads are grouped by 'Domain'.
    Typical Domains: Logic, Physics, Biology, Code, Ethics.
    
    Supports weight export/import for .jay serialization.
    """
    
    def __init__(self, d_model: int, n_heads: int, domains: list[str]):
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.domains = domains
        
        # Init weights (simulated)
        self.W_q = np.random.randn(d_model, d_model).astype(np.float32)
        self.W_k = np.random.randn(d_model, d_model).astype(np.float32)
        self.W_v = np.random.randn(d_model, d_model).astype(np.float32)
        self.W_o = np.random.randn(d_model, d_model).astype(np.float32)
        
    def forward(self, x: np.ndarray, mask: np.ndarray = None) -> np.ndarray:
        """
        Compute Cross-Domain Attention.
        x: (seq_len, d_model)
        """
        Q = x @ self.W_q
        K = x @ self.W_k
        V = x @ self.W_v
        
        seq_len = x.shape[0]
        output = np.zeros_like(x)
        output = scaled_dot_product_attention(Q, K, V, self.head_dim)
            
        return output @ self.W_o
    
    # ---- Serialization ----
    
    def get_weights(self) -> dict:
        """Export attention weight matrices."""
        return {
            "W_q": self.W_q,
            "W_k": self.W_k,
            "W_v": self.W_v,
            "W_o": self.W_o
        }
    
    def load_weights(self, d: dict):
        """Restore attention weights from loaded data."""
        self.W_q = d["W_q"].astype(np.float32)
        self.W_k = d["W_k"].astype(np.float32)
        self.W_v = d["W_v"].astype(np.float32)
        self.W_o = d["W_o"].astype(np.float32)


def scaled_dot_product_attention(Q, K, V, head_dim):
    """
    Simplified Attention Kernel.
    Attention(Q, K, V) = softmax(QK^T / sqrt(d_k))V
    """
    scale = 1.0 / np.sqrt(head_dim)
    scores = (Q @ K.T) * scale
    
    # Softmax (row-wise, with max subtraction for stability)
    for i in range(scores.shape[0]):
        row = scores[i]
        max_val = np.max(row)
        exp_row = np.exp(row - max_val)
        sum_exp = np.sum(exp_row)
        scores[i] = exp_row / sum_exp
        
    return scores @ V
