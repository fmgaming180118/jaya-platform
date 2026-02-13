
import numpy as np

class TernaryLinear:
    """
    Pillar 27: Ternary Precision (BitNet 1.58b)
    
    Weights are restricted to {-1, 0, 1}.
    Computation is done via Addition/Subtraction only (No Float Mul).
    
    Supports:
    - 2-bit compact encoding (4 ternary values per byte)
    - Weight export/import for .jay serialization
    """
    
    def __init__(self, in_features: int, out_features: int):
        self.in_features = in_features
        self.out_features = out_features
        
        # Initialize randomly then quantize to {-1, 0, 1}
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
        Forward pass using pure Python/Numpy (Cython compiled).
        x: Input vector (float32 or int8)
        """
        return ternary_matmul(x, self.weights)
    
    # ---- Serialization ----
    
    def get_weights(self) -> np.ndarray:
        """Export int8 ternary weight matrix."""
        return self.weights
    
    def load_weights(self, w: np.ndarray):
        """Restore weights from loaded data."""
        assert w.shape == (self.out_features, self.in_features), \
            f"Shape mismatch: expected {(self.out_features, self.in_features)}, got {w.shape}"
        self.weights = w.astype(np.int8)
    
    # ---- 2-bit Compact Encoding ----
    # Encoding: 00=0, 01=+1, 10=-1, 11=reserved
    # 4 ternary values per byte → 75% compression vs int8
    
    @staticmethod
    def pack_ternary(arr: np.ndarray) -> bytes:
        """Pack int8 ternary array into 2-bit compact bytes."""
        flat = arr.flatten()
        # Pad to multiple of 4
        pad_len = (4 - len(flat) % 4) % 4
        if pad_len:
            flat = np.concatenate([flat, np.zeros(pad_len, dtype=np.int8)])
        
        packed = bytearray()
        for i in range(0, len(flat), 4):
            byte = 0
            for j in range(4):
                val = flat[i + j]
                if val == 1:
                    code = 0b01
                elif val == -1:
                    code = 0b10
                else:
                    code = 0b00
                byte |= (code << (j * 2))
            packed.append(byte)
        return bytes(packed)
    
    @staticmethod
    def unpack_ternary(data: bytes, shape: tuple) -> np.ndarray:
        """Unpack 2-bit compact bytes into int8 ternary array."""
        total = 1
        for s in shape:
            total *= s
            
        flat = np.zeros(total, dtype=np.int8)
        idx = 0
        for byte_val in data:
            for j in range(4):
                if idx >= total:
                    break
                code = (byte_val >> (j * 2)) & 0b11
                if code == 0b01:
                    flat[idx] = 1
                elif code == 0b10:
                    flat[idx] = -1
                else:
                    flat[idx] = 0
                idx += 1
        return flat.reshape(shape)


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
    
    for i in range(out_dim):
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
