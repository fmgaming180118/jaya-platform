"""Pillar 40 — Intent Extrapolation (Mind Reader).  V18 UPGRADE.

Learns the user's intent patterns from conversation history and predicts
the most likely full command given a partial input.

V18 Architecture
----------------
* **N-gram layer** — bigram/trigram frequency counting for exact command completion.
* **TF-IDF layer** — cosine similarity between the partial input and all previously seen commands;
  provides semantic matching even when exact tokens differ.
* Combined score = 0.6 × n-gram_score + 0.4 × tfidf_score
* ``learn(command)`` updates both models simultaneously.
* ``predict_intent(partial)`` queries both, merges, re-ranks.
* Both models persist to JSON for cross-session memory with atomic durability.
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("IntentEngine")


def _tokenise(text: str) -> List[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return [t for t in text.split() if t]


class _TFIDFIndex:
    """Lightweight TF-IDF index for semantic intent matching.

    Stores seen commands as term-frequency vectors and supports
    cosine similarity search.  No external dependencies.
    """

    def __init__(self) -> None:
        self._docs: List[str] = []            # raw commands
        self._df: Dict[str, int] = {}         # document frequency per term
        self._tf_vecs: List[Dict[str, float]] = []  # TF vectors per doc

    def add(self, command: str) -> None:
        clean = " ".join(command.split())
        if clean in self._docs:
            return
        tokens = list(set(_tokenise(clean)))  # unique terms
        tf: Dict[str, float] = {}
        all_tokens = _tokenise(clean)
        total = max(1, len(all_tokens))
        for t in all_tokens:
            tf[t] = tf.get(t, 0) + 1.0 / total
        for t in tokens:
            self._df[t] = self._df.get(t, 0) + 1
        self._docs.append(clean)
        self._tf_vecs.append(tf)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        if not self._docs:
            return []
        q_tokens = _tokenise(query)
        if not q_tokens:
            return []
        n = len(self._docs)
        # Build query TF-IDF vector
        q_freq: Dict[str, float] = {}
        for t in q_tokens:
            q_freq[t] = q_freq.get(t, 0) + 1.0 / len(q_tokens)
        q_vec: Dict[str, float] = {}
        for t, tf_val in q_freq.items():
            df = self._df.get(t, 0)
            if df > 0:
                idf = math.log((n + 1) / (df + 1)) + 1.0  # smoothed IDF
                q_vec[t] = tf_val * idf

        # Cosine similarity with each doc
        results: List[Tuple[str, float]] = []
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0
        for i, tf_doc in enumerate(self._tf_vecs):
            dot = 0.0
            for t, q_val in q_vec.items():
                df = self._df.get(t, 0)
                if df > 0 and t in tf_doc:
                    idf = math.log((n + 1) / (df + 1)) + 1.0
                    dot += q_val * (tf_doc[t] * idf)
            doc_norm = math.sqrt(
                sum((tf_doc[t] * (math.log((n + 1) / (self._df.get(t, 1) + 1)) + 1.0)) ** 2
                    for t in tf_doc)
            ) or 1.0
            sim = dot / (q_norm * doc_norm)
            if sim > 0.05:
                results.append((self._docs[i], sim))

        results.sort(key=lambda x: -x[1])
        return results[:top_k]

    def serialize(self) -> Dict[str, Any]:
        return {"docs": self._docs, "df": self._df}

    def deserialize(self, data: Dict[str, Any]) -> None:
        self._docs = []
        self._df = {}
        self._tf_vecs = []
        for cmd in data.get("docs", []):
            if isinstance(cmd, str) and cmd:
                self.add(cmd)

    @property
    def doc_count(self) -> int:
        """Number of indexed documents."""
        return len(self._docs)


class IntentEngine:
    """N-gram and TF-IDF intent predictor for proactive command completion.

    Parameters
    ----------
    model_path:
        JSON file where the intent model is persisted.
    n:
        Maximum n-gram order (2 = bigrams, 3 = trigrams...).
    storage_path:
        Optional Path or str for persistence (overrides model_path).
    """

    def __init__(
        self,
        model_path: Optional[str | Path] = None,
        n: int = 3,
        storage_path: Optional[str | Path] = None,
    ):
        if storage_path is not None:
            self.storage_path = Path(storage_path).expanduser().resolve()
        elif model_path is not None:
            self.storage_path = Path(model_path).expanduser().resolve()
        else:
            from jaya_core.paths import core_data_dir
            self.storage_path = core_data_dir() / "intent_model.json"

        self.model_path = str(self.storage_path)
        self.n = max(2, int(n))
        # prefix -> {completion_word: count}
        self._model: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._total_learned: int = 0
        self.tfidf = _TFIDFIndex()
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def learn(self, command: str) -> bool:
        """Update the model with a new observed *command*."""
        clean = " ".join(str(command or "").strip().split())
        tokens = _tokenise(clean)
        if len(tokens) < 2:
            return False
        for i in range(len(tokens) - 1):
            for order in range(1, min(self.n, i + 2)):
                prefix_tokens = tokens[max(0, i - order + 1): i + 1]
                prefix = " ".join(prefix_tokens)
                self._model[prefix][tokens[i + 1]] += 1
        self._total_learned += 1
        self.tfidf.add(clean)
        self._save()
        return True

    def predict_intent(
        self,
        partial: str,
        top_k: int = 3,
    ) -> List[Tuple[str, float]]:
        """Return top-*k* (completion, confidence) pairs for *partial*."""
        clean = " ".join(str(partial or "").strip().split())
        tokens = _tokenise(clean)
        if not tokens:
            return []

        candidates: Dict[str, int] = defaultdict(int)
        for order in range(min(self.n, len(tokens)), 0, -1):
            prefix = " ".join(tokens[-order:])
            if prefix in self._model:
                for word, count in self._model[prefix].items():
                    candidates[word] += count * order

        # --- N-gram scores ---
        ngram_scores: Dict[str, float] = {}
        if candidates:
            total_ngram = sum(candidates.values())
            for word, count in candidates.items():
                completion = clean + " " + word
                ngram_scores[completion] = count / total_ngram

        # --- TF-IDF semantic scores ---
        tfidf_results: Dict[str, float] = {}
        for cmd, sim in self.tfidf.search(clean, top_k=top_k * 2):
            tfidf_results[cmd] = sim

        # --- Merge: 0.6 x ngram + 0.4 x tfidf ---
        all_keys: set[str] = set(ngram_scores) | set(tfidf_results)
        merged: Dict[str, float] = {}
        for key in all_keys:
            merged[key] = (
                0.6 * ngram_scores.get(key, 0.0)
                + 0.4 * tfidf_results.get(key, 0.0)
            )

        if not merged:
            return []

        ranked = sorted(merged.items(), key=lambda x: -x[1])[:top_k]
        return [(cmd, round(score, 4)) for cmd, score in ranked]

    def best_prediction(self, partial: str) -> Optional[str]:
        """Return the single most-likely full command, or None."""
        preds = self.predict_intent(partial, top_k=1)
        return preds[0][0] if preds else None

    def save(self) -> bool:
        """Manually persist the model to disk."""
        return self._save()

    def status(self) -> Dict[str, Any]:
        return {
            "available": True,
            "n": self.n,
            "prefixes": len(self._model),
            "tfidf_docs": self.tfidf.doc_count,
            "learned": self._total_learned,
            "model_path": str(self.storage_path),
            "persisted": self.storage_path.exists(),
        }

    # ------------------------------------------------------------------
    # Internal Persistence
    # ------------------------------------------------------------------

    def _save(self) -> bool:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            serialisable = {k: dict(v) for k, v in self._model.items()}
            payload = {
                "n": self.n,
                "learned": self._total_learned,
                "model": serialisable,
                "tfidf": self.tfidf.serialize(),
            }
            tmp_path = self.storage_path.with_suffix(f"{self.storage_path.suffix}.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, self.storage_path)
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("[IntentEngine] cannot save model to %s: %s", self.storage_path, exc)
            return False

    def _load(self) -> bool:
        if not self.storage_path.exists():
            return False
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            raw = data.get("model", {})
            if isinstance(raw, dict):
                for prefix, completions in raw.items():
                    if isinstance(completions, dict):
                        for word, count in completions.items():
                            self._model[prefix][word] = int(count)
            self._total_learned = int(data.get("learned", 0))
            if "tfidf" in data and isinstance(data["tfidf"], dict):
                self.tfidf.deserialize(data["tfidf"])
            logger.debug(
                "[IntentEngine] loaded %d prefixes, %d TF-IDF docs from %s",
                len(self._model), self.tfidf.doc_count, self.storage_path,
            )
            return True
        except Exception as exc:
            logger.warning("[IntentEngine] failed to load model from %s: %s", self.storage_path, exc)
            return False
