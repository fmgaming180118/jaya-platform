"""Patch intent_engine.py with TF-IDF semantic similarity on top of n-gram."""
import pathlib

p = pathlib.Path(
    r"d:\Kampus\coba-coba\jaya-research\JAYA_CORE\src\brain_v2\engine\intent_engine.py"
)
content = p.read_text(encoding="utf-8")

# 1. Update docstring
NEW_DOCSTRING = '''"""Pillar 40 — Intent Extrapolation (Mind Reader).  V18 UPGRADE.

Learns the user\'s intent patterns from conversation history and predicts
the most likely full command given a partial input.

V18 Architecture
----------------
* **N-gram layer** (unchanged) — bigram/trigram frequency counting for
  exact command completion.
* **TF-IDF layer** (NEW) — cosine similarity between the partial input
  and all previously seen commands; provides semantic matching even when
  exact tokens differ.
* Combined score = 0.6 × n-gram_score + 0.4 × tfidf_score
* ``learn(command)`` updates both models simultaneously.
* ``predict_intent(partial)`` queries both, merges, re-ranks.
* Both models persist to JSON for cross-session memory.
"""'''

OLD_DOCSTRING = '''"""Pillar 40 — Intent Extrapolation (Mind Reader).

Learns the Boss\'s intent patterns from conversation history and predicts
the most likely full command given a partial input.  Uses n-gram frequency
counting — no LLM required, stays lightweight.

Architecture
------------
* ``IntentEngine`` maintains a bigram/trigram model over past commands.
* ``learn(command)`` updates the model with a new observed command.
* ``predict_intent(partial)`` returns the most-likely completion.
* Persists to a compact JSON file so patterns survive restarts.
"""'''

assert OLD_DOCSTRING in content, "OLD docstring not found"
content = content.replace(OLD_DOCSTRING, NEW_DOCSTRING)

# 2. Add numpy import
content = content.replace(
    "import json\nimport logging\nimport os\nimport re",
    "import json\nimport logging\nimport math\nimport os\nimport re"
)

# 3. Add TF-IDF class before IntentEngine class
TFIDF_CLASS = '''
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
        tokens = list(set(_tokenise(command)))  # unique terms
        n = len(self._docs)
        tf: Dict[str, float] = {}
        all_tokens = _tokenise(command)
        total = max(1, len(all_tokens))
        for t in all_tokens:
            tf[t] = tf.get(t, 0) + 1.0 / total
        for t in tokens:
            self._df[t] = self._df.get(t, 0) + 1
        self._docs.append(command)
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
        self._docs = data.get("docs", [])
        self._df = data.get("df", {})
        # Rebuild TF vectors
        self._tf_vecs = []
        for cmd in self._docs:
            tf: Dict[str, float] = {}
            tokens = _tokenise(cmd)
            total = max(1, len(tokens))
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1.0 / total
            self._tf_vecs.append(tf)


'''

# Insert before class IntentEngine
INSERT_BEFORE = "\nclass IntentEngine:"
assert INSERT_BEFORE in content, "IntentEngine class not found"
content = content.replace(INSERT_BEFORE, TFIDF_CLASS + "\nclass IntentEngine:", 1)

# 4. Add _tfidf attribute to __init__
OLD_INIT = "        self._total_learned: int = 0\n        self._load()"
NEW_INIT = "        self._total_learned: int = 0\n        self._tfidf = _TFIDFIndex()\n        self._load()"
assert OLD_INIT in content, "OLD_INIT not found"
content = content.replace(OLD_INIT, NEW_INIT, 1)

# 5. Update learn() to also train TF-IDF
OLD_LEARN = "        self._total_learned += 1\n        if self._total_learned % 50 == 0:\n            self._save()   # auto-save every 50 commands"
NEW_LEARN = "        self._total_learned += 1\n        self._tfidf.add(command)  # V18: also train TF-IDF index\n        if self._total_learned % 50 == 0:\n            self._save()   # auto-save every 50 commands"
assert OLD_LEARN in content, "OLD_LEARN not found"
content = content.replace(OLD_LEARN, NEW_LEARN, 1)

# 6. Upgrade predict_intent to combine n-gram + TF-IDF
OLD_PREDICT_END = """        if not candidates:
            return []

        total = sum(candidates.values())
        ranked = sorted(candidates.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            (partial.strip() + " " + word, count / total)
            for word, count in ranked
        ]"""

NEW_PREDICT_END = """        # --- N-gram scores ---
        ngram_scores: Dict[str, float] = {}
        if candidates:
            total_ngram = sum(candidates.values())
            for word, count in candidates.items():
                completion = partial.strip() + " " + word
                ngram_scores[completion] = count / total_ngram

        # --- TF-IDF semantic scores (V18) ---
        tfidf_results: Dict[str, float] = {}
        for cmd, sim in self._tfidf.search(partial, top_k=top_k * 2):
            tfidf_results[cmd] = sim

        # --- Merge: 0.6 × ngram + 0.4 × tfidf ---
        all_keys: set = set(ngram_scores) | set(tfidf_results)
        merged: Dict[str, float] = {}
        for key in all_keys:
            merged[key] = (
                0.6 * ngram_scores.get(key, 0.0)
                + 0.4 * tfidf_results.get(key, 0.0)
            )

        if not merged:
            return []

        ranked = sorted(merged.items(), key=lambda x: -x[1])[:top_k]
        return [(cmd, score) for cmd, score in ranked]"""

assert OLD_PREDICT_END in content, "OLD_PREDICT_END not found"
content = content.replace(OLD_PREDICT_END, NEW_PREDICT_END, 1)

# 7. Update _save to include tfidf data
OLD_SAVE = '                json.dump({"n": self.n,\n                           "learned": self._total_learned,\n                           "model": serialisable}, f)'
NEW_SAVE = '                json.dump({"n": self.n,\n                           "learned": self._total_learned,\n                           "model": serialisable,\n                           "tfidf": self._tfidf.serialize()}, f)'
assert OLD_SAVE in content, "OLD_SAVE not found"
content = content.replace(OLD_SAVE, NEW_SAVE, 1)

# 8. Update _load to restore tfidf
OLD_LOAD_END = '            self._total_learned = data.get("learned", 0)\n            logger.debug("[IntentEngine] loaded %d prefixes from %s",\n                         len(self._model), self.model_path)'
NEW_LOAD_END = '            self._total_learned = data.get("learned", 0)\n            if "tfidf" in data:\n                self._tfidf.deserialize(data["tfidf"])  # V18: restore TF-IDF index\n            logger.debug("[IntentEngine] loaded %d prefixes, %d TF-IDF docs from %s",\n                         len(self._model), len(self._tfidf._docs), self.model_path)'
assert OLD_LOAD_END in content, "OLD_LOAD_END not found"
content = content.replace(OLD_LOAD_END, NEW_LOAD_END, 1)

# 9. Update status() to include tfidf info
OLD_STATUS = '        return {\n            "n":              self.n,\n            "prefixes":       len(self._model),\n            "learned":        self._total_learned,\n            "model_path":     self.model_path,\n        }'
NEW_STATUS = '        return {\n            "n":              self.n,\n            "prefixes":       len(self._model),\n            "tfidf_docs":     len(self._tfidf._docs),\n            "learned":        self._total_learned,\n            "model_path":     self.model_path,\n        }'
assert OLD_STATUS in content, "OLD_STATUS not found"
content = content.replace(OLD_STATUS, NEW_STATUS, 1)

p.write_text(content, encoding="utf-8")
print("intent_engine.py updated OK")
print(f"File size: {len(content)} bytes")
