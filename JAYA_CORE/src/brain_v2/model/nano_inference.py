# pyright: reportMissingTypeArgument=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownType=false, reportGeneralTypeIssues=false
# type: ignore

"""V18 — Pure-NumPy NANO Model Inference.

Replaces the Numba/Cython .pyd compiled model for Python 3.12+.
Zero external dependencies beyond NumPy.

Architecture: NANO config
    d_model   = 64
    n_layers  = 2
    n_heads   = 4
    vocab_size = 512
    topk_ratio = 0.10  (10% active neurons per forward pass)

STANDARD config (drop-in):
    d_model   = 128
    n_layers  = 4
    n_heads   = 4
    vocab_size = 1000

RAM profile
-----------
    NANO     weights: ~50 KB  (2-bit packed)
    STANDARD weights: ~250 KB (2-bit packed)
    Runtime overhead: ~5 MB NumPy + ~15 MB Python = ~20-22 MB total
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("NanoInference")

# ---------------------------------------------------------------------------
# Pre-defined model configs
# ---------------------------------------------------------------------------

NANO_CONFIG: dict[str, Any] = {
    "d_model": 64,
    "n_layers": 2,
    "n_heads": 4,
    "vocab_size": 512,
    "topk_ratio": 0.10,
    "model_profile": "NANO",
    "version": "V18.0",
}

STANDARD_CONFIG: dict[str, Any] = {
    "d_model": 128,
    "n_layers": 4,
    "n_heads": 4,
    "vocab_size": 1000,
    "topk_ratio": 0.10,
    "model_profile": "STANDARD",
    "version": "V18.0",
}


# ---------------------------------------------------------------------------
# Layer primitives (ternary, no Numba)
# ---------------------------------------------------------------------------

def _ternary_linear(x: np.ndarray, W: np.ndarray) -> np.ndarray:
    """Ternary matrix multiplication: x @ W  where W ∈ {-1, 0, +1}.

    Trick: split W into (pos_mask, neg_mask) uint8 arrays so the dot
    becomes two uint8 sums minus one — no float multiply.

    x shape: (..., in_features)
    W shape: (in_features, out_features)
    Returns: (..., out_features) float32
    """
    pos = (W == 1).astype(np.float32)
    neg = (W == -1).astype(np.float32)
    return np.dot(x.astype(np.float32), pos) - np.dot(x.astype(np.float32), neg)


def _topk_sparse(x: np.ndarray, topk_ratio: float) -> np.ndarray:
    """Keep only top-k activations (by absolute value), zero out rest."""
    k = max(1, int(x.shape[-1] * topk_ratio))
    result = np.zeros_like(x)
    if x.ndim == 1:
        idx = np.argpartition(np.abs(x), -k)[-k:]
        result[idx] = x[idx]
    else:
        for i in range(x.shape[0]):
            idx = np.argpartition(np.abs(x[i]), -k)[-k:]
            result[i, idx] = x[i, idx]
    return result


def _layer_norm(x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Simple layer normalization (no learned params — pure normalization)."""
    mean = x.mean(axis=-1, keepdims=True)
    std = x.std(axis=-1, keepdims=True)
    return (x - mean) / (std + eps)


def _attention(x: np.ndarray, Wq: np.ndarray, Wk: np.ndarray, Wv: np.ndarray,
               Wo: np.ndarray, n_heads: int, topk_ratio: float) -> np.ndarray:
    """Sparse ternary multi-head attention."""
    seq_len, d = x.shape
    head_dim = d // n_heads

    Q = _ternary_linear(x, Wq)  # (seq, d)
    K = _ternary_linear(x, Wk)
    V = _ternary_linear(x, Wv)

    # Split into heads
    Q = Q.reshape(seq_len, n_heads, head_dim).transpose(1, 0, 2)  # (h, s, hd)
    K = K.reshape(seq_len, n_heads, head_dim).transpose(1, 0, 2)
    V = V.reshape(seq_len, n_heads, head_dim).transpose(1, 0, 2)

    # Scaled dot-product attention
    scale = head_dim ** -0.5
    scores = np.matmul(Q, K.transpose(0, 2, 1)) * scale  # (h, s, s)
    # Softmax
    scores = scores - scores.max(axis=-1, keepdims=True)  # numerical stability
    attn = np.exp(scores)
    attn = attn / (attn.sum(axis=-1, keepdims=True) + 1e-9)

    out = np.matmul(attn, V)  # (h, s, hd)
    out = out.transpose(1, 0, 2).reshape(seq_len, d)  # (s, d)
    out = _ternary_linear(out, Wo)
    return _topk_sparse(out, topk_ratio)


def _ffn(x: np.ndarray, W1: np.ndarray, W2: np.ndarray, topk_ratio: float) -> np.ndarray:
    """Feed-forward: Ternary linear → ReLU → sparse → Ternary linear."""
    h = _ternary_linear(x, W1)
    h = np.maximum(h, 0)  # ReLU
    h = _topk_sparse(h, topk_ratio)
    return _ternary_linear(h, W2)


# ---------------------------------------------------------------------------
# NanoModel
# ---------------------------------------------------------------------------

class NanoModel:
    """Pure-NumPy ternary transformer (NANO or STANDARD config).

    Weights are int8 arrays stored on the instance; they are loaded
    from an unpacked state-dict.

    Parameters
    ----------
    config:
        Dict with keys: d_model, n_layers, n_heads, vocab_size, topk_ratio
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or NANO_CONFIG
        self.d_model: int    = cfg["d_model"]
        self.n_layers: int   = cfg["n_layers"]
        self.n_heads: int    = cfg["n_heads"]
        self.vocab_size: int = cfg["vocab_size"]
        self.topk_ratio: float = cfg.get("topk_ratio", 0.10)
        self.model_profile: str = cfg.get("model_profile", "NANO")
        self._weights: dict[str, Any] | None = None
        self._initialized = False

    # ------------------------------------------------------------------

    def random_init(self) -> None:
        """Initialise all weights randomly from {-1, 0, +1}."""
        rng = np.random.default_rng()  # unseeded — each call gives different weights
        d, v, _ = self.d_model, self.vocab_size, self.n_heads
        ffn_dim = d * 4

        def rand_ternary(*shape: int) -> np.ndarray:
            return rng.integers(-1, 2, size=shape, dtype=np.int8)

        layers = []
        for _ in range(self.n_layers):
            layers.append({
                "Wq": rand_ternary(d, d),
                "Wk": rand_ternary(d, d),
                "Wv": rand_ternary(d, d),
                "Wo": rand_ternary(d, d),
                "W1": rand_ternary(d, ffn_dim),
                "W2": rand_ternary(ffn_dim, d),
            })

        self._weights = {
            "embeddings": rand_ternary(v, d),
            "layers": layers,
            "output_head": rand_ternary(d, v),
        }
        self._initialized = True
        logger.debug("[NanoModel] random_init complete (%s, d=%d, L=%d)",
                     self.model_profile, self.d_model, self.n_layers)

    def load_state_dict(self, state_dict: dict[str, Any]) -> None:
        """Load weights from a pre-built state-dict (int8 arrays).

        Accepts the dict produced by :func:`~src.brain_v2.format.packer.
        unpack_state_dict`, which maps string keys to NumPy arrays.
        """
        self._weights = state_dict
        self._initialized = True

    def get_state_dict(self) -> dict:
        if not self._initialized:
            self.random_init()
        return self._weights  # type: ignore[return-value]

    def get_config(self) -> dict[str, Any]:
        return {
            "d_model": self.d_model,
            "n_layers": self.n_layers,
            "n_heads": self.n_heads,
            "vocab_size": self.vocab_size,
            "topk_ratio": self.topk_ratio,
            "model_profile": self.model_profile,
            "version": "V18.0",
        }

    # ------------------------------------------------------------------

    def forward(self, token_ids: list[int] | np.ndarray) -> np.ndarray:
        """Run a forward pass.

        Parameters
        ----------
        token_ids:
            1-D array/list of integer token IDs.

        Returns
        -------
        np.ndarray shape (seq_len, vocab_size) — logits (float32)
        """
        if not self._initialized:
            self.random_init()
        assert self._weights is not None

        w = self._weights
        ids = np.asarray(token_ids, dtype=np.int32)
        ids = np.clip(ids, 0, self.vocab_size - 1)

        # Embedding lookup
        x = w["embeddings"][ids].astype(np.float32)  # (seq, d)

        # Transformer layers
        for layer in w["layers"]:
            # Self-attention (residual)
            attn_out = _attention(
                x, layer["Wq"], layer["Wk"], layer["Wv"], layer["Wo"],
                self.n_heads, self.topk_ratio
            )
            x = _layer_norm(x + attn_out)

            # FFN (residual)
            ffn_out = _ffn(x, layer["W1"], layer["W2"], self.topk_ratio)
            x = _layer_norm(x + ffn_out)

        # Output projection
        logits = _ternary_linear(x, w["output_head"])  # (seq, vocab)
        return logits

    def predict_token(self, token_ids: list[int], temperature: float = 1.0) -> int:
        """Predict next token ID given a context."""
        logits = self.forward(token_ids)
        last_logits = logits[-1]  # only last position
        if temperature != 1.0:
            last_logits = last_logits / temperature
        probs = np.exp(last_logits - last_logits.max())
        probs /= probs.sum()
        return int(np.random.choice(len(probs), p=probs))

    # ------------------------------------------------------------------
    # Weight buffer access for LiveEvolver
    # ------------------------------------------------------------------

    def get_weight_buffers(self) -> list[tuple[str, np.ndarray]]:
        """Return a flat list of (key, weight_array) for all mutable weights."""
        if not self._initialized:
            self.random_init()
        assert self._weights is not None
        result: list[tuple[str, np.ndarray]] = []
        w = self._weights
        result.append(("embeddings", w["embeddings"]))
        for i, layer in enumerate(w["layers"]):
            for k, v in layer.items():
                result.append((f"layer_{i}.{k}", v))
        result.append(("output_head", w["output_head"]))
        return result

    def set_weight(self, key: str, new_val: np.ndarray) -> None:
        """Replace a single weight buffer (for LiveEvolver mutation)."""
        if not self._initialized:
            self.random_init()
        assert self._weights is not None
        if key == "embeddings":
            self._weights["embeddings"] = new_val
        elif key == "output_head":
            self._weights["output_head"] = new_val
        elif key.startswith("layer_"):
            parts = key.split(".", 1)
            layer_idx = int(parts[0].split("_")[1])
            w_name = parts[1]
            self._weights["layers"][layer_idx][w_name] = new_val
        else:
            raise KeyError(f"Unknown weight key: {key!r}")

    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        total = sum(arr.size for _, arr in self.get_weight_buffers())
        size_kb = total * 2 / 8 / 1024  # 2-bit per param
        return (f"NanoModel(profile={self.model_profile}, d={self.d_model}, "
                f"L={self.n_layers}, H={self.n_heads}, V={self.vocab_size}, "
                f"~{total:,} params, ~{size_kb:.0f} KB packed)")
