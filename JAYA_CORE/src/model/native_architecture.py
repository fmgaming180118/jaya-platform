"""
Native PyTorch implementation of the JAYA Librarian Core V0 Architecture.
This is the true Core, entirely separate from the BootstrapLibrarianModel.
"""

import math
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("JayaLibrarianNativeV0")

import json
import hashlib
from pathlib import Path

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
            
            # Auxiliary heads for Librarian behaviors
            # 4 classes: 0: DIRECT_ANSWER, 1: NEED_RETRIEVAL, 2: INSUFFICIENT_EVIDENCE, 3: RETRIEVE_MORE
            self.retrieval_decision_head = nn.Linear(d_model, 4)
            # 2 classes: 0: INSUFFICIENT, 1: SUFFICIENT
            self.evidence_sufficiency_head = nn.Linear(d_model, 2)

        def forward(self, idx, targets=None, retrieval_targets=None, evidence_targets=None):
            B, T = idx.size()
            pos = torch.arange(0, T, dtype=torch.long, device=idx.device)
            x = self.token_emb(idx) + self.pos_emb(pos)
            
            for block in self.blocks:
                x = block(x)
                
            x = self.ln_f(x)
            logits = self.lm_head(x)
            
            retrieval_logits = self.retrieval_decision_head(x)
            evidence_logits = self.evidence_sufficiency_head(x)
            
            loss = None
            if targets is not None:
                lm_loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1), ignore_index=-100)
                loss = lm_loss
                
                # Multi-task training
                if retrieval_targets is not None:
                    retrieval_loss = F.cross_entropy(retrieval_logits.view(-1, 4), retrieval_targets.view(-1), ignore_index=-100)
                    loss = loss + 0.5 * retrieval_loss
                
                if evidence_targets is not None:
                    evidence_loss = F.cross_entropy(evidence_logits.view(-1, 2), evidence_targets.view(-1), ignore_index=-100)
                    loss = loss + 0.5 * evidence_loss
                
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

    class NativeJayaLibrarianRuntime:
        """
        Native Runtime Adapter for JayaLibrarianNativeV0.
        Loads tokenizer, model configuration, and safe weights.
        Validates artifact SHA-256 against the manifest.
        """
        def __init__(self, model_dir: str):
            self.model_dir = Path(model_dir)
            self._is_loaded = False
            self.model = None
            self.tokenizer = None
            
        def load(self):
            manifest_path = self.model_dir / "training_manifest.json"
            config_path = self.model_dir / "model_config.json"
            weights_path = self.model_dir / "model.safetensors"
            
            if not manifest_path.exists() or not config_path.exists() or not weights_path.exists():
                raise FileNotFoundError("Missing native checkpoint artifacts.")
                
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
                
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                
            # Verify artifact hash
            expected_sha = manifest.get("artifact_sha256")
            with open(weights_path, "rb") as f:
                actual_sha = hashlib.sha256(f.read()).hexdigest()
                
            if expected_sha and actual_sha != expected_sha:
                raise ValueError(f"MODEL_ARTIFACT_INTEGRITY_ERROR: Mismatched weights. Expected {expected_sha}, got {actual_sha}")
                
            from transformers import AutoTokenizer
            tokenizer_origin = manifest.get("tokenizer_origin", "HuggingFaceTB/SmolLM-135M")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
            
            self.model = JayaLibrarianNativeV0(
                vocab_size=config["vocab_size"],
                d_model=config["d_model"],
                n_layers=config["n_layers"],
                n_heads=config["n_heads"]
            )
            
            from safetensors.torch import load_file
            state_dict = load_file(weights_path)
            self.model.load_state_dict(state_dict)
            
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model.to(self.device)
            self.model.eval()
            self._is_loaded = True
            
        def reason_and_respond(self, query: str, context_blocks: list) -> dict:
            if not self._is_loaded:
                raise RuntimeError("Model not loaded.")
                
            prompt = f"USER QUERY: {query}\n\nEVIDENCE:\n" + "\n".join(context_blocks) + "\n\nJSON:\n"
            input_ids = self.tokenizer(prompt, return_tensors="pt").input_ids.to(self.device)
            
            with torch.no_grad():
                generated_ids = self.model.generate(input_ids, max_new_tokens=256)
                
            # Extract generated part
            gen_part = generated_ids[0][input_ids.shape[1]:]
            output_text = self.tokenizer.decode(gen_part, skip_special_tokens=True)
            
            try:
                # Find JSON block
                start_idx = output_text.find('{')
                end_idx = output_text.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    json_str = output_text[start_idx:end_idx+1]
                    return json.loads(json_str)
            except Exception:
                pass
                
            return {
                "information_needs": ["Failed to parse model response"],
                "retrieval_required": False,
                "retrieval_queries": [],
                "answer": "Failed to parse model response",
                "evidence_refs": [],
                "confidence": 0.0
            }
else:
    class JayaLibrarianNativeV0:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch is required to initialize JayaLibrarianNativeV0.")
    class NativeJayaLibrarianRuntime:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch is required to initialize NativeJayaLibrarianRuntime.")
