
import numpy as np
from numba import njit, prange

class TernaryLinear:
    """
    Pillar 27: Ternary Precision (BitNet 1.58b)
    
    Weights are restricted to {-1, 0, 1}.
    Computation is done via Addition/Subtraction only (No Float Mul).
    """
    
    def __init__(self, in_features: int, out_features: int):
        self.in_features = in_features
        self.out_features = out_features
        
        # Initialize randomly then quantize to {-1, 0, 1}
        # In a real training scenario, we'd keep a latent float weight
        # But for the Kernel inference, we only need the quantized integer weights.
        raw_weights = np.random.randn(out_features, in_features)
        self.weights = self.quantize_weights(raw_weights)
        
    def quantize_weights(self, w: np.ndarray) -> np.ndarray:
        """
        BitNet 1.58b Quantization logic: E(W) -> {-1, 0, 1}
        """
        scale = np.mean(np.abs(w))
        w_scaled = w / (scale + 1e-6)
        return np.round(np.clip(w_scaled, -1, 1)).astype(np.int8)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """
        Forward pass using Numba-optimized kernel.
        x: Input vector (float32 or int8)
        """
        return ternary_matmul(x, self.weights)

@njit(fastmath=True, parallel=True)
def ternary_matmul(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """
    Custom Matrix Multiplication for Ternary Weights.
    y = W @ x
    
    Optimized to use Addition/Subtraction logic.
    w is shape (out, in)
    x is shape (in,)
    """
    out_dim = w.shape[0]
    in_dim = w.shape[1]
    output = np.zeros(out_dim, dtype=np.float32)
    
    for i in prange(out_dim):
        acc = 0.0
        for j in range(in_dim):
            weight_val = w[i, j]
            if weight_val == 1:
                acc += x[j]
            elif weight_val == -1:
                acc -= x[j]
            # if 0, do nothing (Cognitive Silence at synapse level)
        output[i] = acc
        
    return output

