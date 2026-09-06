from jaya_research.config import config

import json
import os

class CharTokenizer:
    def __init__(self):
        self.chars = sorted(list(set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~\n\t"
        )))
        self.vocab_size = len(self.chars) + 1 # +1 for padding/unknown
        self.char_to_idx = {ch: i+1 for i, ch in enumerate(self.chars)}
        self.idx_to_char = {i+1: ch for i, ch in enumerate(self.chars)}
        self.pad_token = 0

    def encode(self, text, max_len=None):
        ids = [self.char_to_idx.get(ch, 0) for ch in text]
        if max_len:
            if len(ids) > max_len:
                ids = ids[:max_len]
            else:
                ids += [self.pad_token] * (max_len - len(ids))
        return ids

    def decode(self, ids):
        chars = []
        for i in ids:
            if i == self.pad_token: continue
            chars.append(self.idx_to_char.get(i, ''))
        return "".join(chars)

    def save(self, path=config.TOKENIZER_PATH):
        with open(path, "w") as f:
            json.dump({"chars": self.chars}, f)

    def load(self, path=config.TOKENIZER_PATH):
        with open(path, "r") as f:
            data = json.load(f)
            self.chars = data["chars"]
            self.vocab_size = len(self.chars) + 1
            self.char_to_idx = {ch: i+1 for i, ch in enumerate(self.chars)}
            self.idx_to_char = {i+1: ch for i, ch in enumerate(self.chars)}

if __name__ == "__main__":
    t = CharTokenizer()
    print(f"Vocab Size: {t.vocab_size}")
    enc = t.encode("def add(a, b): return a + b", max_len=50)
    print(f"Encoded: {enc}")
    dec = t.decode(enc)
    print(f"Decoded: {dec}")
