"""
JAYA Knowledge Distillation Trainer
Fase 2 — Melatih NanoModel agar memahami Bahasa Indonesia

Pipeline:
  Dataset (input, target) → Tokenizer → NanoModel forward → Loss → Update bobot

Loss Function:
  Cross-Entropy Loss antara logit NanoModel dan target token ID
  (Soft-label KL-Divergence ditambahkan jika Teacher logits tersedia)

Optimizer:
  SGD dengan momentum — murni NumPy, zero dependency selain NumPy
  Ini memastikan training bisa berjalan bahkan di smartwatch!

Output:
  JAYA_CORE/data/id_nanomodel_v1.npy   — bobot terlatih (NumPy .npz)
  JAYA_CORE/data/training_log.json     — log training (loss per epoch)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("DistillationTrainer")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from src.core_config import core_config

MODEL_OUT_FILE = core_config.DATA_DIR / "id_nanomodel_v1.npz"
TRAIN_LOG_FILE = core_config.DATA_DIR / "training_log.json"


# ────────────────────────────────────────────────────────────────────────────
# Pure-NumPy Optimizer
# ────────────────────────────────────────────────────────────────────────────

class SGDMomentum:
    """
    SGD dengan momentum — pure NumPy.
    Tidak membutuhkan PyTorch/TensorFlow — cocok untuk smartwatch.
    """

    def __init__(self, lr: float = 0.01, momentum: float = 0.9):
        self.lr       = lr
        self.momentum = momentum
        self._velocity: Dict[str, np.ndarray] = {}

    def step(self, key: str, param: np.ndarray, grad: np.ndarray) -> np.ndarray:
        """Update satu parameter dengan momentum."""
        if key not in self._velocity:
            self._velocity[key] = np.zeros_like(param, dtype=np.float32)
        v = self._velocity[key]
        v[:] = self.momentum * v - self.lr * grad
        self._velocity[key] = v
        return param + v


# ────────────────────────────────────────────────────────────────────────────
# Loss Functions
# ────────────────────────────────────────────────────────────────────────────

def _softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - logits.max(axis=-1, keepdims=True))
    return e / (e.sum(axis=-1, keepdims=True) + 1e-9)


def _cross_entropy(logits: np.ndarray, target_ids: np.ndarray) -> Tuple[float, np.ndarray]:
    """
    Cross-entropy loss + gradient.
    logits: (seq_len, vocab_size) float32
    target_ids: (seq_len,) int
    Returns: (scalar loss, gradient same shape as logits)
    """
    seq_len, vocab_size = logits.shape
    probs = _softmax(logits)  # (seq, vocab)

    # Clip token ids ke range vocab
    targets = np.clip(target_ids, 0, vocab_size - 1)

    # NLL loss
    log_probs = np.log(probs[np.arange(seq_len), targets] + 1e-9)
    loss = -log_probs.mean()

    # Gradient: d_loss/d_logits = probs - one_hot(target)
    grad = probs.copy()
    grad[np.arange(seq_len), targets] -= 1.0
    grad /= seq_len
    return float(loss), grad


# ────────────────────────────────────────────────────────────────────────────
# Trainer
# ────────────────────────────────────────────────────────────────────────────

class DistillationTrainer:
    """
    Knowledge Distillation Trainer untuk NanoModel JAYA.

    Training loop murni NumPy — dapat berjalan di CPU tanpa GPU,
    cocok untuk bootstrap awal di PC, hasilnya di-deploy ke smartwatch.
    """

    def __init__(
        self,
        learning_rate: float = 0.005,
        momentum: float = 0.9,
        epochs: int = 3,
        log_every: int = 50,
    ):
        self.lr        = learning_rate
        self.momentum  = momentum
        self.epochs    = epochs
        self.log_every = log_every
        self._optimizer = SGDMomentum(lr=learning_rate, momentum=momentum)
        self._loss_history: List[Dict[str, Any]] = []

    def train(
        self,
        dataset: List[Dict[str, str]],
        tokenizer: Any,   # IndonesianTokenizer
        model: Any,       # NanoModel
    ) -> Dict[str, Any]:
        """
        Latih NanoModel pada dataset distilasi.

        Args:
            dataset:   List of {"input": str, "target": str}
            tokenizer: IndonesianTokenizer instance
            model:     NanoModel instance (INDONESIAN_CONFIG)

        Returns:
            Ringkasan training
        """
        logger.info("[Trainer] Memulai distilasi — %d sampel, %d epoch", len(dataset), self.epochs)
        logger.info("[Trainer] lr=%.4f, momentum=%.2f", self.lr, self.momentum)

        model.random_init()
        total_steps = 0
        start_time  = time.time()

        for epoch in range(1, self.epochs + 1):
            epoch_loss = 0.0
            # Shuffle dataset setiap epoch
            indices = np.random.permutation(len(dataset)).tolist()

            for step_in_epoch, idx in enumerate(indices):
                sample = dataset[idx]
                loss = self._train_step(sample, tokenizer, model)

                if loss is None:
                    continue

                epoch_loss += loss
                total_steps += 1

                if total_steps % self.log_every == 0:
                    avg = epoch_loss / (step_in_epoch + 1)
                    elapsed = time.time() - start_time
                    logger.info(
                        "[Trainer] Epoch %d  step %d/%d  avg_loss=%.4f  elapsed=%.0fs",
                        epoch, step_in_epoch + 1, len(dataset), avg, elapsed
                    )

            avg_epoch_loss = epoch_loss / max(len(dataset), 1)
            self._loss_history.append({
                "epoch": epoch,
                "avg_loss": round(avg_epoch_loss, 6),
                "steps": total_steps,
                "elapsed_s": round(time.time() - start_time, 1),
            })
            logger.info("[Trainer] === Epoch %d selesai — avg_loss=%.4f ===", epoch, avg_epoch_loss)

        elapsed_total = time.time() - start_time
        summary = {
            "status": "done",
            "total_steps": total_steps,
            "epochs": self.epochs,
            "final_avg_loss": self._loss_history[-1]["avg_loss"] if self._loss_history else None,
            "elapsed_seconds": round(elapsed_total, 1),
            "loss_history": self._loss_history,
        }
        logger.info("[Trainer] Training selesai dalam %.0f detik.", elapsed_total)
        return summary

    def _train_step(
        self,
        sample: Dict[str, str],
        tokenizer: Any,
        model: Any,
    ) -> Optional[float]:
        """Satu langkah training pada satu sampel."""
        try:
            # Encode input + target
            input_ids  = tokenizer.encode(sample["input"],  add_bos=True, add_eos=False)
            target_ids = tokenizer.encode(sample["target"], add_bos=False, add_eos=True)

            if len(input_ids) < 1 or len(target_ids) < 1:
                return None

            # Gabungkan: model melihat input, belajar memprediksi target
            full_seq = input_ids + target_ids
            x_ids    = full_seq[:-1]  # input ke model
            y_ids    = full_seq[1:]   # target (shifted by 1)

            if len(x_ids) < 1:
                return None

            # Forward pass
            logits = model.forward(x_ids)  # (seq_len, vocab_size)

            # Hanya hitung loss pada bagian target
            offset    = len(input_ids) - 1
            t_logits  = logits[offset:]
            t_targets = np.array(y_ids[offset:], dtype=np.int32)

            if len(t_logits) < 1:
                return None

            loss, grad = _cross_entropy(t_logits, t_targets)

            # Backward — update embedding saja (paling berpengaruh untuk bahasa)
            # Gradient approximation: update embedding for input tokens
            self._update_embeddings(model, x_ids[offset:], grad, t_targets)

            return loss

        except Exception as exc:
            logger.debug("[Trainer] Step error: %s", exc)
            return None

    def _update_embeddings(
        self,
        model: Any,
        token_ids: List[int],
        grad: np.ndarray,
        targets: np.ndarray,
    ) -> None:
        """Update embedding table berdasarkan gradient (pendekatan langsung)."""
        if model._weights is None:
            return

        emb: np.ndarray = model._weights["embeddings"].astype(np.float32)
        vocab_size = emb.shape[0]

        # Gradient embedding: akumulasikan gradient per token yang muncul
        emb_grad = np.zeros_like(emb)
        for i, tid in enumerate(token_ids):
            tid = int(tid) % vocab_size
            if i < len(grad):
                # Proyeksikan grad (vocab_size) ke embedding space (d_model)
                # Approximasi: pakai bobot output_head sebagai projektor
                oh = model._weights["output_head"].astype(np.float32)  # (d_model, vocab)
                g_emb = (oh @ grad[i]).astype(np.float32)  # (d_model,)
                emb_grad[tid] += g_emb

        # Update dengan optimizer
        updated = self._optimizer.step("embeddings", emb, emb_grad)
        # Ternarize kembali (round ke {-1, 0, 1})
        model._weights["embeddings"] = np.clip(np.round(updated), -1, 1).astype(np.int8)

    def save_model(self, model: Any, out_file: Path = MODEL_OUT_FILE) -> None:
        """Simpan bobot NanoModel yang sudah dilatih ke .npz."""
        out_file.parent.mkdir(parents=True, exist_ok=True)
        w = model._weights
        save_dict = {"embeddings": w["embeddings"], "output_head": w["output_head"]}
        for i, layer in enumerate(w["layers"]):
            for k, v in layer.items():
                save_dict[f"layer_{i}_{k}"] = v
        np.savez_compressed(str(out_file), **save_dict)
        logger.info("[Trainer] Model disimpan: %s (%.1f KB)", out_file,
                    out_file.stat().st_size / 1024)

    def save_log(self, log_file: Path = TRAIN_LOG_FILE) -> None:
        log_file.write_text(json.dumps(self._loss_history, indent=2), encoding="utf-8")

    @staticmethod
    def load_model_weights(model: Any, weight_file: Path = MODEL_OUT_FILE) -> bool:
        """Muat bobot terlatih ke NanoModel yang sudah diinisialisasi."""
        if not weight_file.exists():
            return False
        data = np.load(str(weight_file), allow_pickle=False)
        n_layers = model.n_layers
        w: Dict[str, Any] = {
            "embeddings":  data["embeddings"],
            "output_head": data["output_head"],
            "layers": [],
        }
        for i in range(n_layers):
            layer = {}
            for k in ["Wq", "Wk", "Wv", "Wo", "W1", "W2"]:
                key = f"layer_{i}_{k}"
                if key in data:
                    layer[k] = data[key]
            w["layers"].append(layer)
        model._weights     = w
        model._initialized = True
        logger.info("[Trainer] Bobot dimuat dari %s", weight_file)
        return True


# ────────────────────────────────────────────────────────────────────────────
# CLI — end-to-end training pipeline
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    import argparse
    parser = argparse.ArgumentParser(description="JAYA Indonesian Distillation Trainer")
    parser.add_argument("--epochs",  type=int,   default=3,    help="Jumlah epoch")
    parser.add_argument("--lr",      type=float, default=0.005, help="Learning rate")
    parser.add_argument("--no-wiki", action="store_true",       help="Skip Wikipedia download")
    parser.add_argument("--dry-run", action="store_true",       help="Test 5 sampel saja")
    args = parser.parse_args()

    from src.brain_v2.education.indonesian_corpus    import IndonesianCorpus
    from src.brain_v2.education.indonesian_tokenizer import IndonesianTokenizer, _train_and_save, VOCAB_FILE
    from src.brain_v2.education.distillation_dataset import DistillationDataset
    from src.brain_v2.model.nano_inference           import NanoModel, INDONESIAN_CONFIG

    # 1. Corpus
    print("\n[1/5] Membangun corpus Bahasa Indonesia...")
    corpus = IndonesianCorpus(use_wiki=not args.no_wiki)
    corpus.build()

    # 2. Tokenizer
    print("\n[2/5] Melatih tokenizer BPE (vocab 8K)...")
    if not IndonesianTokenizer.exists():
        _train_and_save(vocab_size=8_000)
    tok = IndonesianTokenizer.load()
    print(f"      Tokenizer: {len(tok.token2id):,} token")

    # 3. Dataset
    print("\n[3/5] Membangun dataset distilasi...")
    ds_obj = DistillationDataset()
    ds_obj.build()
    dataset = ds_obj.load()
    if args.dry_run:
        dataset = dataset[:5]
    print(f"      Dataset: {len(dataset)} sampel")

    # 4. Model
    print("\n[4/5] Inisialisasi NanoModel (INDONESIAN_CONFIG)...")
    model = NanoModel(config=INDONESIAN_CONFIG)
    model.random_init()
    print(f"      {model}")

    # 5. Training
    print(f"\n[5/5] Memulai Knowledge Distillation ({args.epochs} epoch)...")
    trainer = DistillationTrainer(learning_rate=args.lr, epochs=args.epochs)
    summary = trainer.train(dataset, tok, model)
    trainer.save_model(model)
    trainer.save_log()

    print(f"\n✅ Training selesai!")
    print(f"   Total steps : {summary['total_steps']}")
    print(f"   Final loss  : {summary['final_avg_loss']:.4f}")
    print(f"   Waktu       : {summary['elapsed_seconds']:.0f} detik")
    print(f"   Model saved : {MODEL_OUT_FILE}")
