# BUILD_JAY_LIGHT — Reproducible runbook for lightweight `.jay`

This document describes the minimal, reproducible pipeline to build a lightweight `.jay` student model suitable for devices with ~200 MB RAM and 1 GB storage. Follow the phases: D → A → C → B (docs, data, quantize/convert, distill).

## Overview
- Target: offline-first `.jay` that loads with `IronEngine` and uses `AgenticRAG` for knowledge.
- Device profile: 200 MB RAM, 1 GB storage.
- Priorities: accuracy > size; latency targets: warm ≤ 700 ms, cold ≤ 2000 ms.

## Dependencies
- Python 3.10+ (3.12 recommended) in a virtualenv
- Core packages (dev):
  - `datasets`, `transformers`, `accelerate`, `tokenizers`, `sentence-transformers`
  - `bitsandbytes` (for quantize/4-bit flows)
  - `faiss-cpu` or `annoy` (optional, for vector index)
  - `wikiextractor` (for Wikipedia dumps)

Quick install (example):
```bash
python -m venv .venv
.venv\Scripts\pip install -U pip
.venv\Scripts\pip install datasets transformers accelerate tokenizers sentence-transformers bitsandbytes faiss-cpu wikiextractor
```

Note: `bitsandbytes` may require CUDA drivers for GPU-based quantization; for CPU-only workflows use static conversion tools and ONNX TRT later.

## Phase D — Create reproducible documentation (this file)
- Keep this file under `JAYA_RESEARCH/docs/` and update with measured benchmarks and produced `.jay` filenames.

## Phase A — Fast dataset acquisition (Wikipedia + instruction datasets)

Recommended quick datasets to seed training:
- Wikipedia (extracted via `wikiextractor`) — broad factual coverage
- OpenAssistant (`OpenAssistant/oasst1`) — instruction-response pairs
- Alpaca / Dolly / FLAN derivatives (HuggingFace) — instruction templates

Quick commands:
```bash
# Download Wikipedia dump + extract (fast path: use pre-extracted mirror if available)
wget https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-pages-articles.xml.bz2
git clone https://github.com/attardi/wikiextractor.git
python wikiextractor/WikiExtractor.py -o extracted enwiki-latest-pages-articles.xml.bz2

# Download OpenAssistant via datasets (python snippet)
python - <<'PY'
from datasets import load_dataset
ds = load_dataset('OpenAssistant/oasst1', split='train')
ds.select(range(100000)).to_json('data/openassistant_sample.jsonl')
PY
```

Processing steps (recommended):
- Tokenize with your target tokenizer once and store tokenized shards
- Dedupe by hash; remove PII via regex rules; drop extremely short/noisy items
- Create `instruction-response` pairs for teacher-to-student distillation

## Phase C — Quantize & convert checkpoints to deployable arrays

Goal: convert student checkpoint (PyTorch) into quantized weights and/or NumPy buffers compatible with `nano_inference` and `pack_state_dict()`.

High-level:
- Use `bitsandbytes` for 4-bit weight conversion when GPU available
- For pure-CPU NanoModel, convert final float weights to NumPy arrays and use `pack_state_dict()` to produce packed bytes

Example flow (summary):
1. Train or obtain student checkpoint `student.ckpt` (PyTorch)
2. Run `quantize_convert.py --ckpt student.ckpt --out packed_weights.bin --bits 4`
3. Use `JAYA_CORE/src/brain_v2/format/packer.py` `pack_state_dict()` or `_write_nano_jay` writer to build `.jay`

## Phase B — Distillation (teacher → student)

Strategy (fast path):
- Use prebuilt datasets + synthetic generation: run teacher (cloud) to generate high-quality instruction-response pairs specifically for the user's domain and behavior.
- Distill in stages: first teach language/formatting (short-run), then factual grounding using RAG-augmented examples.

Verification and testing:
- Integration test: run `IronEngine(model_path='path/to/new.jay').ignite()` and `execute_intent()` smoke tests
- Unit tests: add a small test under `JAYA_CORE/tests/` to assert `.jay` loads and inference returns non-empty string
- Benchmarks: measure peak RAM and latency on target device and add results to this doc

## Packaging & release
- Name artifacts with semantic version and device hint: `JAYA_STUDENT_v1_device_TINY.jay`
- Add release notes describing training dataset, distillation steps, quantization bits, and measured metrics

## Runbook: quick commands

Build virtualenv and install deps:
```bash
python -m venv .venv
.venv\Scripts\pip install -r JAYA_RESEARCH/requirements-light.txt
```

Download small dataset sample and run tokenization script:
```bash
python JAYA_RESEARCH/scripts/download_datasets.py --sample 100000 --out data/combined.jsonl
python JAYA_RESEARCH/scripts/tokenize_shards.py --in data/combined.jsonl --out data/tokens/
```

Convert + pack student:
```bash
python JAYA_RESEARCH/scripts/quantize_convert.py --ckpt checkpoints/student.pt --bits 4 --out packed_weights.bin
python JAYA_CORE/src/brain_v2/genesis.py  # or call packer/unpack writer from a helper script
```

Run Engine smoke test:
```bash
python - <<'PY'
from src.brain_v2.engine.runtime import IronEngine
e = IronEngine(model_path='JAYA_RESEARCH/out/JAYA_STUDENT_v1.jay', password='x', enable_twin=False)
e.ignite()
print(e.execute_intent('Halo, siapa kamu?'))
PY
```

## Notes and next steps
- This runbook is a living document — record measured RAM/latency after first build and iterate. Prioritize RAG usage to keep the model small while preserving accuracy.
