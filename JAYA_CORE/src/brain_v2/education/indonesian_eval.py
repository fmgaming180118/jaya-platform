"""
JAYA Indonesian Model Evaluator
Fase 3 — Mengukur kemampuan NanoModel setelah distilasi

Metrik:
  1. Token Accuracy  — seberapa sering model memprediksi token benar
  2. Perplexity      — ukuran seberapa baik model memahami bahasa
  3. Task Accuracy   — akurasi pada 40-Pillar command set JAYA
  4. Latency         — kecepatan inferensi

Semua evaluasi murni NumPy — bisa berjalan di smartwatch.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

logger = logging.getLogger("IndonesianEval")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from src.core_config import core_config

EVAL_RESULT_FILE = core_config.DATA_DIR / "eval_results.json"

# ── JAYA Command Set Evaluasi (berbasis 40 Pillar) ───────────────────────────
_COMMAND_EVAL_SET: List[Dict[str, Any]] = [
    # Format: input → expected token yang harus ada di top-5 prediksi
    {"input": "halo", "expected_contains": ["halo", "selamat", "pagi", "bos"]},
    {"input": "matikan", "expected_contains": ["matikan", "lampu", "sistem", "mode"]},
    {"input": "nyalakan", "expected_contains": ["nyalakan", "aktifkan", "hidupkan"]},
    {"input": "cari informasi", "expected_contains": ["cari", "informasi", "mencari", "tentang"]},
    {"input": "apa itu", "expected_contains": ["adalah", "merupakan", "kecerdasan", "sistem"]},
    {"input": "bagaimana cara", "expected_contains": ["cara", "langkah", "untuk", "proses"]},
    {"input": "tolong bantu", "expected_contains": ["bantu", "siap", "tentu", "membantu"]},
    {"input": "terima kasih", "expected_contains": ["sama", "senang", "bisa", "kembali"]},
    {"input": "simpan catatan", "expected_contains": ["simpan", "catatan", "disimpan", "memori"]},
    {"input": "tampilkan status", "expected_contains": ["status", "sistem", "aktif", "berjalan"]},
]


def _softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - logits.max())
    return e / (e.sum() + 1e-9)


def _perplexity(model: Any, token_ids: List[int]) -> float:
    """Hitung perplexity model pada urutan token."""
    if len(token_ids) < 2:
        return float("inf")
    x_ids = token_ids[:-1]
    y_ids = token_ids[1:]
    logits = model.forward(x_ids)  # (seq, vocab)
    probs  = np.array([
        _softmax(logits[i])[min(y_ids[i], logits.shape[1] - 1)]
        for i in range(len(y_ids))
    ])
    log_probs = np.log(probs + 1e-9)
    return float(np.exp(-log_probs.mean()))


def _top_k_tokens(logits_last: np.ndarray, k: int = 5) -> List[int]:
    """Ambil top-k token id dari logit posisi terakhir."""
    return np.argsort(logits_last)[::-1][:k].tolist()


class IndonesianEvaluator:
    """
    Evaluasi kemampuan NanoModel Bahasa Indonesia.
    Menghasilkan metrik komprehensif yang menunjukkan kesiapan deployment.
    """

    def __init__(self):
        self._results: Dict[str, Any] = {}

    def evaluate_all(
        self,
        model: Any,
        tokenizer: Any,
        dataset: List[Dict[str, str]],
        max_samples: int = 100,
    ) -> Dict[str, Any]:
        """
        Jalankan seluruh suite evaluasi.

        Returns dict berisi semua metrik.
        """
        logger.info("[Eval] Memulai evaluasi komprehensif...")
        results: Dict[str, Any] = {}

        # 1. Perplexity pada dataset validasi
        results["perplexity"] = self._eval_perplexity(model, tokenizer, dataset, max_samples)

        # 2. Token accuracy
        results["token_accuracy"] = self._eval_token_accuracy(model, tokenizer, dataset, max_samples)

        # 3. Command task accuracy (40-Pillar set)
        results["command_accuracy"] = self._eval_command_set(model, tokenizer)

        # 4. Inferensi latency
        results["latency"] = self._eval_latency(model, tokenizer)

        # Skor keseluruhan
        results["overall_score"] = self._compute_overall_score(results)
        results["verdict"] = self._verdict(results["overall_score"])
        results["smartwatch_ready"] = results["overall_score"] >= 0.4

        self._results = results
        logger.info("[Eval] Evaluasi selesai. Skor: %.2f — %s",
                    results["overall_score"], results["verdict"])
        return results

    def _eval_perplexity(
        self, model: Any, tokenizer: Any,
        dataset: List[Dict[str, str]], max_samples: int
    ) -> Dict[str, Any]:
        """Evaluasi perplexity pada subset dataset."""
        ppl_list = []
        for sample in dataset[:max_samples]:
            text   = sample.get("target", sample.get("input", ""))
            tokens = tokenizer.encode(text)
            if len(tokens) >= 3:
                ppl = _perplexity(model, tokens)
                if np.isfinite(ppl) and ppl < 10_000:
                    ppl_list.append(ppl)

        if not ppl_list:
            return {"mean": None, "median": None, "note": "Tidak cukup data"}

        return {
            "mean":   round(float(np.mean(ppl_list)), 2),
            "median": round(float(np.median(ppl_list)), 2),
            "min":    round(float(np.min(ppl_list)), 2),
            "max":    round(float(np.max(ppl_list)), 2),
            "n_samples": len(ppl_list),
            "note": "Semakin rendah semakin baik. Model yang baik: < 100",
        }

    def _eval_token_accuracy(
        self, model: Any, tokenizer: Any,
        dataset: List[Dict[str, str]], max_samples: int
    ) -> Dict[str, Any]:
        """Hitung token-level accuracy."""
        total, correct = 0, 0
        for sample in dataset[:max_samples]:
            text   = sample.get("target", "")
            tokens = tokenizer.encode(text)
            if len(tokens) < 3:
                continue
            x_ids = tokens[:-1]
            y_ids = tokens[1:]
            logits = model.forward(x_ids)
            preds  = np.argmax(logits, axis=-1)
            for pred, true in zip(preds, y_ids):
                total   += 1
                correct += (int(pred) == int(true))

        acc = correct / max(total, 1)
        return {
            "accuracy": round(acc, 4),
            "correct":  correct,
            "total":    total,
            "note": "Token accuracy — meningkat seiring training",
        }

    def _eval_command_set(self, model: Any, tokenizer: Any) -> Dict[str, Any]:
        """Evaluasi pada JAYA 40-Pillar command set."""
        hits, total = 0, 0
        details: List[Dict[str, Any]] = []

        for item in _COMMAND_EVAL_SET:
            total += 1
            tokens  = tokenizer.encode(item["input"])
            if not tokens:
                continue
            logits  = model.forward(tokens)
            top5_ids = _top_k_tokens(logits[-1], k=5)
            top5_toks = [tokenizer.id2token.get(tid, "<UNK>") for tid in top5_ids]

            hit = any(
                any(exp in tok for tok in top5_toks)
                for exp in item["expected_contains"]
            )
            if hit:
                hits += 1

            details.append({
                "input":    item["input"],
                "expected": item["expected_contains"],
                "top5":     top5_toks,
                "hit":      hit,
            })

        acc = hits / max(total, 1)
        return {
            "accuracy": round(acc, 4),
            "hits":     hits,
            "total":    total,
            "details":  details,
            "note": "Akurasi perintah JAYA. Target produksi: > 0.7",
        }

    def _eval_latency(self, model: Any, tokenizer: Any) -> Dict[str, Any]:
        """Benchmark latency inferensi."""
        tokens = tokenizer.encode("halo jaya, tolong aktifkan mode senyap")
        n_runs = 50

        t0 = time.perf_counter()
        for _ in range(n_runs):
            _ = model.forward(tokens)
        t1 = time.perf_counter()

        ms_per_run     = (t1 - t0) * 1000 / n_runs
        tokens_per_sec = len(tokens) / (ms_per_run / 1000)

        return {
            "ms_per_inference": round(ms_per_run, 2),
            "tokens_per_sec":   round(tokens_per_sec, 1),
            "seq_len":          len(tokens),
            "note": "Target smartwatch: < 200ms per inferensi",
        }

    def _compute_overall_score(self, results: Dict[str, Any]) -> float:
        """Hitung skor komposit 0-1."""
        score = 0.0
        weights: List[Tuple[str, float]] = [
            ("token_accuracy", 0.4),
            ("command_accuracy", 0.4),
            ("latency", 0.2),
        ]
        for key, w in weights:
            r = results.get(key, {})
            if key == "token_accuracy":
                score += w * float(r.get("accuracy", 0))
            elif key == "command_accuracy":
                score += w * float(r.get("accuracy", 0))
            elif key == "latency":
                ms = float(r.get("ms_per_inference", 9999))
                latency_score = max(0.0, 1.0 - ms / 200.0)
                score += w * latency_score
        return round(score, 4)

    def _verdict(self, score: float) -> str:
        if score >= 0.7:
            return "🌟 SANGAT BAIK — Siap production"
        elif score >= 0.5:
            return "✅ BAIK — Perlu beberapa epoch lagi"
        elif score >= 0.3:
            return "⚠️ CUKUP — Training masih perlu dilanjutkan"
        else:
            return "❌ AWAL — Model belum cukup terlatih (normal di awal)"

    def save(self, out_file: Path = EVAL_RESULT_FILE) -> None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(
            json.dumps(self._results, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )
        logger.info("[Eval] Hasil disimpan: %s", out_file)

    def print_summary(self) -> None:
        r = self._results
        print("\n" + "=" * 60)
        print("  JAYA INDONESIAN MODEL — EVALUATION REPORT")
        print("=" * 60)
        ta  = r.get("token_accuracy", {})
        ca  = r.get("command_accuracy", {})
        lat = r.get("latency", {})
        ppl = r.get("perplexity", {})
        print(f"  Token Accuracy   : {ta.get('accuracy', 0):.1%}  ({ta.get('correct', 0)}/{ta.get('total', 0)} token)")
        print(f"  Command Accuracy : {ca.get('accuracy', 0):.1%}  ({ca.get('hits', 0)}/{ca.get('total', 0)} perintah)")
        print(f"  Perplexity       : {ppl.get('mean', 'N/A')}")
        print(f"  Latency          : {lat.get('ms_per_inference', 0):.1f} ms  ({lat.get('tokens_per_sec', 0):.0f} tok/s)")
        print(f"\n  Overall Score    : {r.get('overall_score', 0):.2f} / 1.00")
        print(f"  Verdict          : {r.get('verdict', '')}")
        print(f"  Smartwatch Ready : {'✅ Ya' if r.get('smartwatch_ready') else '❌ Perlu training lebih'}")
        print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    from src.brain_v2.model.nano_inference           import NanoModel, INDONESIAN_CONFIG
    from src.brain_v2.education.indonesian_tokenizer import IndonesianTokenizer
    from src.brain_v2.education.distillation_dataset import DistillationDataset
    from src.brain_v2.education.distillation_trainer import DistillationTrainer, MODEL_OUT_FILE

    # Muat model
    model = NanoModel(config=INDONESIAN_CONFIG)
    weight_ok = DistillationTrainer.load_model_weights(model)
    if not weight_ok:
        print("[Eval] Bobot belum ada — evaluasi dengan random weights (skor rendah normal)")
        model.random_init()

    # Muat tokenizer
    if IndonesianTokenizer.exists():
        tok = IndonesianTokenizer.load()
    else:
        print("[Eval] Tokenizer belum dilatih. Jalankan: python indonesian_tokenizer.py --train")
        sys.exit(1)

    # Muat dataset
    ds = DistillationDataset().load()

    # Evaluasi
    ev = IndonesianEvaluator()
    ev.evaluate_all(model, tok, ds)
    ev.print_summary()
    ev.save()
