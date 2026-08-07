"""
Native PyTorch implementation of the JAYA Librarian Core V0 Architecture.
This is the true Core, entirely separate from the BootstrapLibrarianModel.
"""

import math
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("JayaLibrarianNativeV0")

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

if HAS_TORCH:
    class RMSNorm(nn.Module):
        def __init__(self, d_model: int, eps: float = 1e-6):
            super().__init__()
            self.eps = eps
            self.weight = nn.Parameter(torch.ones(d_model))

        def forward(self, x):
            variance = x.pow(2).mean(-1, keepdim=True)
            x = x * torch.rsqrt(variance + self.eps)
            return self.weight * x

    class CausalSelfAttention(nn.Module):
        def __init__(self, d_model: int, n_heads: int):
            super().__init__()
            assert d_model % n_heads == 0
            self.n_heads = n_heads
            self.d_head = d_model // n_heads
            self.c_attn = nn.Linear(d_model, 3 * d_model, bias=False)
            self.c_proj = nn.Linear(d_model, d_model, bias=False)

        def forward(self, x):
            B, T, C = x.size()
            qkv = self.c_attn(x)
            q, k, v = qkv.split(C, dim=2)
            k = k.view(B, T, self.n_heads, self.d_head).transpose(1, 2)
            q = q.view(B, T, self.n_heads, self.d_head).transpose(1, 2)
            v = v.view(B, T, self.n_heads, self.d_head).transpose(1, 2)

            att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(self.d_head))
            mask = torch.tril(torch.ones(T, T, device=x.device)).view(1, 1, T, T)
            att = att.masked_fill(mask == 0, float('-inf'))
            att = F.softmax(att, dim=-1)
            y = att @ v
            y = y.transpose(1, 2).contiguous().view(B, T, C)
            return self.c_proj(y)

    class SwiGLU(nn.Module):
        def __init__(self, d_model: int, hidden_dim: int):
            super().__init__()
            self.w1 = nn.Linear(d_model, hidden_dim, bias=False)
            self.w2 = nn.Linear(hidden_dim, d_model, bias=False)
            self.w3 = nn.Linear(d_model, hidden_dim, bias=False)

        def forward(self, x):
            return self.w2(F.silu(self.w1(x)) * self.w3(x))

    class JayaLibrarianBlock(nn.Module):
        def __init__(self, d_model: int, n_heads: int):
            super().__init__()
            self.ln_1 = RMSNorm(d_model)
            self.attn = CausalSelfAttention(d_model, n_heads)
            self.ln_2 = RMSNorm(d_model)
            self.mlp = SwiGLU(d_model, 4 * d_model)

        def forward(self, x):
            x = x + self.attn(self.ln_1(x))
            x = x + self.mlp(self.ln_2(x))
            return x

    class JayaLibrarianNativeV0(nn.Module):
        """
        Native JAYA Librarian Core Architecture.
        Trained explicitly to output Librarian schema JSON.
        """
        def __init__(self, vocab_size: int = 32000, d_model: int = 128, n_layers: int = 4, n_heads: int = 4):
            super().__init__()
            self.config = {
                "architecture": "jaya_librarian_native_v0",
                "vocab_size": vocab_size,
                "d_model": d_model,
                "n_layers": n_layers,
                "n_heads": n_heads
            }
            self.token_emb = nn.Embedding(vocab_size, d_model)
            self.pos_emb = nn.Embedding(2048, d_model)
            
            self.blocks = nn.ModuleList([
                JayaLibrarianBlock(d_model, n_heads) for _ in range(n_layers)
            ])
            self.ln_f = RMSNorm(d_model)
            self.lm_head = nn.Linear(d_model, vocab_size, bias=False)
            self.token_emb.weight = self.lm_head.weight # Tie weights

        def forward(self, idx, targets=None):
            B, T = idx.size()
            pos = torch.arange(0, T, dtype=torch.long, device=idx.device)
            x = self.token_emb(idx) + self.pos_emb(pos)
            
            for block in self.blocks:
                x = block(x)
                
            x = self.ln_f(x)
            logits = self.lm_head(x)
            
            loss = None
            if targets is not None:
                loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1), ignore_index=-100)
                
            return logits, loss

        def generate(self, idx, max_new_tokens, temperature=0.1):
            """Minimal autoregressive generation loop."""
            for _ in range(max_new_tokens):
                idx_cond = idx if idx.size(1) <= 2048 else idx[:, -2048:]
                logits, _ = self(idx_cond)
                logits = logits[:, -1, :] / (temperature + 1e-5)
                probs = F.softmax(logits, dim=-1)
                idx_next = torch.multinomial(probs, num_samples=1)
                idx = torch.cat((idx, idx_next), dim=1)
            return idx
else:
    class JayaLibrarianNativeV0:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch is required to initialize JayaLibrarianNativeV0.")
