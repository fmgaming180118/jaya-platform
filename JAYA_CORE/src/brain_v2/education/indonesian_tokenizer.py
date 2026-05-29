"""
JAYA Indonesian Tokenizer — Byte-Pair Encoding (BPE)
Fase 1 — Fondasi Bahasa

Membangun tokenizer BPE murni Python dari corpus Bahasa Indonesia.
Target vocab: 8.000 subword token (sweet spot untuk BI sehari-hari)

Output:
  JAYA_CORE/data/id_vocab.json     — mapping token → id
  JAYA_CORE/data/id_merges.json    — daftar BPE merge rules (untuk encode)
  JAYA_CORE/data/id_tokenizer.json — metadata lengkap

Kenapa BPE?
  - Terbukti di BERT, GPT-2, LLaMA
  - Subword seperti "mem-" + "bantu" → "membantu"
  - Cocok untuk bahasa aglutinatif Indonesia (me-, di-, -kan, -lah)
  - Kompresi vocab efisien: satu token bisa merepresentasikan morfem utuh
"""
from __future__ import annotations

import json
import logging
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger("IndonesianTokenizer")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))
from src.core_config import core_config

DATA_DIR       = core_config.DATA_DIR
VOCAB_FILE     = DATA_DIR / "id_vocab.json"
MERGES_FILE    = DATA_DIR / "id_merges.json"
TOKENIZER_FILE = DATA_DIR / "id_tokenizer.json"

# Token khusus — harus ada di semua vocab JAYA
SPECIAL_TOKENS = [
    "<PAD>",   # padding
    "<UNK>",   # unknown token
    "<BOS>",   # beginning of sequence
    "<EOS>",   # end of sequence
    "<SEP>",   # separator
    "<MASK>",  # masked token (untuk MLM jika dibutuhkan)
    "<SYS>",   # system message JAYA
    "<USR>",   # user message
    "<CMD>",   # perintah JAYA
    "<RSP>",   # respons JAYA
]

DEFAULT_VOCAB_SIZE = 8_000


# ────────────────────────────────────────────────────────────────────────────
# BPE Trainer (Pure Python — zero external dependency)
# ────────────────────────────────────────────────────────────────────────────

def _tokenize_chars(text: str) -> List[str]:
    """Pisahkan teks menjadi karakter dengan marker akhir kata (</w>)."""
    words = re.findall(r"\b\w+\b", text.lower())
    return words


def _word_to_chars(word: str) -> Tuple[str, ...]:
    """Ubah kata menjadi tuple karakter dengan end-of-word marker."""
    return tuple(list(word) + ["</w>"])


def _get_vocab(corpus: List[str]) -> Dict[Tuple[str, ...], int]:
    """Hitung frekuensi setiap kata (sebagai tuple karakter) dalam corpus."""
    vocab: Counter[Tuple[str, ...]] = Counter()
    for line in corpus:
        for word in _tokenize_chars(line):
            vocab[_word_to_chars(word)] += 1
    return dict(vocab)


def _get_pairs(vocab: Dict[Tuple[str, ...], int]) -> Counter:
    """Hitung frekuensi setiap pasangan simbol yang berdekatan."""
    pairs: Counter = Counter()
    for word, freq in vocab.items():
        for i in range(len(word) - 1):
            pairs[(word[i], word[i + 1])] += freq
    return pairs


def _merge_vocab(pair: Tuple[str, str], vocab: Dict[Tuple[str, ...], int]) -> Dict[Tuple[str, ...], int]:
    """Merge semua kemunculan 'pair' dalam vocab menjadi satu simbol baru."""
    new_vocab: Dict[Tuple[str, ...], int] = {}
    bigram_re = re.compile(
        r"(?<!\S)" + re.escape(" ".join(pair)) + r"(?!\S)"
    )
    for word_tuple, freq in vocab.items():
        word_str = " ".join(word_tuple)
        new_word_str = bigram_re.sub("".join(pair), word_str)
        new_vocab[tuple(new_word_str.split())] = freq
    return new_vocab


def train_bpe(
    corpus: List[str],
    vocab_size: int = DEFAULT_VOCAB_SIZE,
    min_frequency: int = 2,
    log_every: int = 500,
) -> Tuple[Dict[str, int], List[Tuple[str, str]]]:
    """
    Latih BPE dari corpus dan kembalikan:
      - token2id: Dict[str, int]
      - merges: List[Tuple[str, str]]  — dalam urutan merge
    """
    logger.info("[BPE] Membangun vocab awal dari karakter...")
    word_vocab = _get_vocab(corpus)

    # Karakter awal = semua karakter unik + special tokens
    char_set: set = set()
    for word_tuple in word_vocab:
        char_set.update(word_tuple)

    # token2id dimulai dari special tokens
    token2id: Dict[str, int] = {tok: i for i, tok in enumerate(SPECIAL_TOKENS)}
    for ch in sorted(char_set):
        if ch not in token2id:
            token2id[ch] = len(token2id)

    logger.info("[BPE] Vocab awal: %d token (char level). Target: %d", len(token2id), vocab_size)

    merges: List[Tuple[str, str]] = []
    n_merges_needed = vocab_size - len(token2id)

    for step in range(n_merges_needed):
        pairs = _get_pairs(word_vocab)
        if not pairs:
            break

        # Pilih pasangan paling sering
        best_pair = max(pairs, key=lambda p: pairs[p])
        if pairs[best_pair] < min_frequency:
            break

        # Merge
        new_token = "".join(best_pair)
        merges.append(best_pair)
        if new_token not in token2id:
            token2id[new_token] = len(token2id)

        word_vocab = _merge_vocab(best_pair, word_vocab)

        if (step + 1) % log_every == 0:
            logger.info("[BPE] Step %d/%d — vocab: %d token, best: %r (freq=%d)",
                        step + 1, n_merges_needed, len(token2id),
                        best_pair, pairs[best_pair])

        if len(token2id) >= vocab_size:
            break

    logger.info("[BPE] Training selesai: %d token, %d merge rules", len(token2id), len(merges))
    return token2id, merges


# ────────────────────────────────────────────────────────────────────────────
# Tokenizer class
# ────────────────────────────────────────────────────────────────────────────

class IndonesianTokenizer:
    """
    Tokenizer BPE Bahasa Indonesia untuk NanoModel JAYA.

    Usage:
        tok = IndonesianTokenizer.load()  # muat dari disk
        ids = tok.encode("halo jaya, matikan lampu")
        text = tok.decode(ids)
    """

    PAD_ID  = 0
    UNK_ID  = 1
    BOS_ID  = 2
    EOS_ID  = 3
    SEP_ID  = 4
    SYS_ID  = 6
    USR_ID  = 7
    CMD_ID  = 8
    RSP_ID  = 9

    def __init__(
        self,
        token2id: Dict[str, int],
        merges: List[Tuple[str, str]],
        vocab_size: int = DEFAULT_VOCAB_SIZE,
    ):
        self.token2id  = token2id
        self.id2token  = {v: k for k, v in token2id.items()}
        self.merges    = merges
        self._merge_set: Dict[Tuple[str, str], int] = {
            pair: i for i, pair in enumerate(merges)
        }
        self.vocab_size = vocab_size

    # ── Encode ──────────────────────────────────────────────────────────────

    def encode(self, text: str, add_bos: bool = True, add_eos: bool = True) -> List[int]:
        """Teks → list[int] token IDs."""
        ids: List[int] = []
        if add_bos:
            ids.append(self.BOS_ID)

        words = re.findall(r"\b\w+\b|[^\w\s]", text.lower())
        for word in words:
            ids.extend(self._encode_word(word))

        if add_eos:
            ids.append(self.EOS_ID)
        return ids

    def _encode_word(self, word: str) -> List[int]:
        """Encode satu kata menggunakan merge rules."""
        chars = list(word) + ["</w>"]
        # Apply merges greedily
        for pair in self.merges:
            i = 0
            new_chars = []
            while i < len(chars):
                if i < len(chars) - 1 and (chars[i], chars[i + 1]) == pair:
                    new_chars.append("".join(pair))
                    i += 2
                else:
                    new_chars.append(chars[i])
                    i += 1
            chars = new_chars

        return [self.token2id.get(c, self.UNK_ID) for c in chars]

    # ── Decode ──────────────────────────────────────────────────────────────

    def decode(self, ids: List[int], skip_special: bool = True) -> str:
        """List[int] → teks."""
        tokens = []
        for tid in ids:
            tok = self.id2token.get(tid, "<UNK>")
            if skip_special and tok in SPECIAL_TOKENS:
                continue
            tokens.append(tok)

        text = "".join(tokens).replace("</w>", " ").strip()
        return text

    # ── Persistence ─────────────────────────────────────────────────────────

    def save(
        self,
        vocab_file: Path = VOCAB_FILE,
        merges_file: Path = MERGES_FILE,
        meta_file: Path = TOKENIZER_FILE,
    ) -> None:
        vocab_file.parent.mkdir(parents=True, exist_ok=True)
        vocab_file.write_text(json.dumps(self.token2id, ensure_ascii=False, indent=2), encoding="utf-8")
        merges_file.write_text(json.dumps(self.merges, ensure_ascii=False), encoding="utf-8")
        meta = {
            "vocab_size": self.vocab_size,
            "actual_vocab": len(self.token2id),
            "n_merges": len(self.merges),
            "special_tokens": SPECIAL_TOKENS,
            "language": "id",
            "version": "1.0",
            "model_target": "JAYA NanoModel Indonesian",
        }
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[Tokenizer] Disimpan: %d token, %d merges → %s", len(self.token2id), len(self.merges), vocab_file.parent)

    @classmethod
    def load(
        cls,
        vocab_file: Path = VOCAB_FILE,
        merges_file: Path = MERGES_FILE,
    ) -> "IndonesianTokenizer":
        if not vocab_file.exists():
            raise FileNotFoundError(
                f"Vocab belum ada di {vocab_file}. "
                "Jalankan: python indonesian_tokenizer.py --train"
            )
        token2id = json.loads(vocab_file.read_text(encoding="utf-8"))
        merges_raw = json.loads(merges_file.read_text(encoding="utf-8"))
        merges = [tuple(m) for m in merges_raw]  # type: ignore[assignment]
        return cls(token2id=token2id, merges=merges, vocab_size=len(token2id))  # type: ignore[arg-type]

    @classmethod
    def exists(cls) -> bool:
        return VOCAB_FILE.exists() and MERGES_FILE.exists()

    def status(self) -> dict:
        return {
            "vocab_size": len(self.token2id),
            "n_merges": len(self.merges),
            "special_tokens": len(SPECIAL_TOKENS),
            "language": "id",
            "vocab_file": str(VOCAB_FILE),
        }


# ────────────────────────────────────────────────────────────────────────────
# CLI — jalankan langsung untuk melatih
# ────────────────────────────────────────────────────────────────────────────

def _train_and_save(vocab_size: int = DEFAULT_VOCAB_SIZE) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    from src.brain_v2.education.indonesian_corpus import IndonesianCorpus

    corpus_obj = IndonesianCorpus()
    if not corpus_obj.out_file.exists():
        logger.info("[Tokenizer] Corpus belum ada. Membangun dari seed...")
        corpus_obj.build()

    corpus = corpus_obj.load()
    logger.info("[Tokenizer] Melatih BPE pada %d kalimat (target vocab: %d)...", len(corpus), vocab_size)

    token2id, merges = train_bpe(corpus, vocab_size=vocab_size)
    tok = IndonesianTokenizer(token2id=token2id, merges=merges, vocab_size=vocab_size)
    tok.save()

    # Quick smoke test
    test = "halo jaya, tolong matikan lampu dan aktifkan mode senyap"
    encoded = tok.encode(test)
    decoded = tok.decode(encoded)
    print(f"\n✅ Tokenizer selesai: {len(token2id):,} token, {len(merges):,} merge rules")
    print(f"   Smoke test encode: {test!r}")
    print(f"   Token IDs ({len(encoded)}): {encoded[:20]}...")
    print(f"   Decoded: {decoded!r}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="JAYA Indonesian BPE Tokenizer")
    parser.add_argument("--train", action="store_true", help="Latih tokenizer baru")
    parser.add_argument("--vocab-size", type=int, default=DEFAULT_VOCAB_SIZE)
    parser.add_argument("--test", type=str, default="", help="Test encode teks")
    args = parser.parse_args()

    if args.train:
        _train_and_save(args.vocab_size)
    elif args.test:
        tok = IndonesianTokenizer.load()
        ids = tok.encode(args.test)
        print(f"Input  : {args.test!r}")
        print(f"IDs    : {ids}")
        print(f"Decoded: {tok.decode(ids)!r}")
    else:
        parser.print_help()
