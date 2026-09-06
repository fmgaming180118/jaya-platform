#!/usr/bin/env python3
"""Download and prepare fast datasets (Wikipedia samples, OpenAssistant, Alpaca).

This is a small helper to fetch and write compact JSONL datasets for downstream tokenization.
"""
import argparse
import json
import os
from pathlib import Path

def download_openassistant(out_path: str, sample: int | None = None):
    try:
        from datasets import load_dataset
    except Exception as exc:
        raise SystemExit("Please install 'datasets' (pip install datasets)") from exc

    ds = load_dataset('OpenAssistant/oasst1', split='train')
    total = len(ds)
    if sample:
        n = min(sample, total)
        ds = ds.select(range(n))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        for ex in ds:
            # best-effort mapping — datasets vary in schema
            prompt = ex.get('prompt') or ex.get('input') or ex.get('instruction') or ''
            answer = ex.get('response') or ex.get('output') or ex.get('assistant_response') or ''
            json.dump({'instruction': prompt, 'response': answer}, f, ensure_ascii=False)
            f.write('\n')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True, help='Output JSONL path')
    p.add_argument('--sample', type=int, default=100000)
    args = p.parse_args()
    download_openassistant(args.out, args.sample)

if __name__ == '__main__':
    main()
