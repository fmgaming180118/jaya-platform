"""Pillar 40 — Intent Extrapolation (Mind Reader).

Learns the Boss's intent patterns from conversation history and predicts
the most likely full command given a partial input.  Uses n-gram frequency
counting — no LLM required, stays lightweight.

Architecture
------------
* ``IntentEngine`` maintains a bigram/trigram model over past commands.
* ``learn(command)`` updates the model with a new observed command.
* ``predict_intent(partial)`` returns the most-likely completion.
* Persists to a compact JSON file so patterns survive restarts.
"""

import json
import logging
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("IntentEngine")

_DEFAULT_PATH = os.path.join(
    os.path.dirname(__file__), "intent_model.json"
)


def _tokenise(text: str) -> List[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return [t for t in text.split() if t]


class IntentEngine:
    """N-gram intent predictor for proactive command completion.

    Parameters
    ----------
    model_path:
        JSON file where the n-gram model is persisted.
    n:
        Maximum n-gram order (2 = bigrams, 3 = trigrams…).
    """

    def __init__(self,
                 model_path: str = _DEFAULT_PATH,
                 n: int = 3):
        self.model_path = model_path
        self.n          = n
        # prefix → {completion_word: count}
        self._model: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._total_learned: int = 0
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def learn(self, command: str) -> None:
        """Update the model with a new observed *command*."""
        tokens = _tokenise(command)
        if len(tokens) < 2:
            return
        for i in range(len(tokens) - 1):
            for order in range(1, min(self.n, i + 2)):
                prefix_tokens = tokens[max(0, i - order + 1): i + 1]
                prefix = " ".join(prefix_tokens)
                self._model[prefix][tokens[i + 1]] += 1
        self._total_learned += 1
        if self._total_learned % 50 == 0:
            self._save()   # auto-save every 50 commands

    def predict_intent(self, partial: str,
                       top_k: int = 3) -> List[Tuple[str, float]]:
        """Return top-*k* (completion, confidence) pairs for *partial*.

        The completion string is appended to *partial* to form the full
        predicted command.
        """
        tokens = _tokenise(partial)
        if not tokens:
            return []

        candidates: Dict[str, int] = defaultdict(int)
        # Try progressively shorter prefixes (trigram → unigram)
        for order in range(min(self.n, len(tokens)), 0, -1):
            prefix = " ".join(tokens[-order:])
            if prefix in self._model:
                for word, count in self._model[prefix].items():
                    candidates[word] += count * order  # prefer longer match

        if not candidates:
            return []

        total = sum(candidates.values())
        ranked = sorted(candidates.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            (partial.strip() + " " + word, count / total)
            for word, count in ranked
        ]

    def best_prediction(self, partial: str) -> Optional[str]:
        """Return the single most-likely full command, or None."""
        preds = self.predict_intent(partial, top_k=1)
        return preds[0][0] if preds else None

    def save(self) -> None:
        """Manually persist the model to disk."""
        self._save()

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "n":              self.n,
            "prefixes":       len(self._model),
            "learned":        self._total_learned,
            "model_path":     self.model_path,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save(self) -> None:
        try:
            # Convert defaultdicts to plain dicts for JSON serialisation
            serialisable = {k: dict(v) for k, v in self._model.items()}
            with open(self.model_path, "w", encoding="utf-8") as f:
                json.dump({"n": self.n,
                           "learned": self._total_learned,
                           "model": serialisable}, f)
        except OSError as exc:
            logger.warning("[IntentEngine] cannot save model: %s", exc)

    def _load(self) -> None:
        if not os.path.exists(self.model_path):
            return
        try:
            with open(self.model_path, encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("model", {})
            for prefix, completions in raw.items():
                for word, count in completions.items():
                    self._model[prefix][word] = count
            self._total_learned = data.get("learned", 0)
            logger.debug("[IntentEngine] loaded %d prefixes from %s",
                         len(self._model), self.model_path)
        except Exception as exc:
            logger.warning("[IntentEngine] failed to load model: %s", exc)
