# QLoRA Hybrid Pipeline (Heavy Teaching, Lightweight Runtime)

Tujuan: pengajaran boleh memakai resource besar, tetapi saat JAYA dijalankan tetap ringan dan 40 pilar tetap utuh.

## Inti Arsitektur

1. Teacher local: Ollama `qwen3:4b` (GGUF) dipakai untuk membangun dataset bahasa.
2. Training: QLoRA adapter dilatih pada base model Hugging Face yang sekeluarga.
3. Deployment runtime JAYA: jangan jalankan model besar; deploy hasil distilasi policy kecil.

## Klarifikasi Penting Tentang GGUF

- Model GGUF Ollama tidak dipakai langsung sebagai objek training QLoRA.
- QLoRA melatih model Hugging Face (4-bit quantized via bitsandbytes).
- Jadi peran Ollama di pipeline ini adalah teacher/data generator.

## Step 1 - Install Dependency Training Saja

python -m pip install -r JAYA_RESEARCH/requirements-qlora.txt

### Windows (recommended one-time CUDA setup)

Jalankan script berikut agar environment QLoRA otomatis dibuat dengan Python 3.12 + PyTorch CUDA:

JAYA_RESEARCH\scripts\setup_qlora_cuda_env.cmd

Setelah sukses, loop CMD akan otomatis memakai `JAYA_RESEARCH/.venv312/Scripts/python.exe`.
Jika ingin override interpreter manual, set env var `QLORA_PYTHON` sebelum menjalankan loop.

## Step 2 - Generate Dataset Dari Ollama qwen3:4b

python JAYA_RESEARCH/src/training/build_qlora_dataset_from_ollama.py --model qwen3:4b --variants-per-key 8 --out JAYA_RESEARCH/data/qlora/language_policy_qlora_dataset.jsonl

Opsional style seed:

python JAYA_RESEARCH/src/training/build_qlora_dataset_from_ollama.py --model qwen3:4b --seed-file JAYA_CORE/docs/language_distillation_seed.example.json --variants-per-key 10

## Step 3 - Train Adapter QLoRA

python JAYA_RESEARCH/src/training/train_qlora_language_adapter.py --base-model Qwen/Qwen3-4B-Instruct-2507 --dataset JAYA_RESEARCH/data/qlora/language_policy_qlora_dataset.jsonl --output-dir JAYA_RESEARCH/data/qlora/adapter-qwen3-4b-language --epochs 2 --batch-size 1 --grad-accum 16 --max-seq-length 768

Dry-run dulu untuk cek stack:

python JAYA_RESEARCH/src/training/train_qlora_language_adapter.py --dry-run

## Step 4 - Evaluasi Kecil (Base vs Adapter)

Dry-run evaluator:

python JAYA_RESEARCH/src/training/evaluate_qlora_language_adapter.py --dry-run

Evaluasi base dan adapter pada sampel dataset:

python JAYA_RESEARCH/src/training/evaluate_qlora_language_adapter.py --base-model Qwen/Qwen3-4B-Instruct-2507 --adapter-dir JAYA_RESEARCH/data/qlora/adapter-qwen3-4b-language --dataset JAYA_RESEARCH/data/qlora/language_policy_qlora_dataset.jsonl --sample-count 32 --out JAYA_RESEARCH/data/qlora/eval_report.json

Mode gate ketat (contoh: adapter harus lebih baik minimal +0.03 pada weighted score):

python JAYA_RESEARCH/src/training/evaluate_qlora_language_adapter.py --base-model Qwen/Qwen3-4B-Instruct-2507 --adapter-dir JAYA_RESEARCH/data/qlora/adapter-qwen3-4b-language --dataset JAYA_RESEARCH/data/qlora/language_policy_qlora_dataset.jsonl --sample-count 32 --gate-metric avg_weighted_score --min-delta 0.03 --fail-on-gate --out JAYA_RESEARCH/data/qlora/eval_report.json

Output evaluator:

- JAYA_RESEARCH/data/qlora/eval_report.json
- Exit code evaluator: `0` (ok), `2` (gate fail saat `--fail-on-gate` aktif)

## Step 5 - Tetap Deploy Runtime Ringan

- Adapter QLoRA dipakai di jalur pengajaran/eksperimen.
- Runtime harian JAYA tetap gunakan policy override ringan di `JAYA_CORE/docs/language_policy_overrides.json`.
- Ini menjaga jejak memori kecil dan kompatibel dengan constraint low-resource saat run.

## Rekomendasi Untuk Laptop 20GB RAM / 6GB VRAM

- Gunakan `--batch-size 1` dan `--grad-accum 16` atau lebih.
- Mulai dengan `--max-seq-length 512` jika VRAM mepet.
- Aktifkan training singkat dulu (`--epochs 1`) lalu evaluasi.

## 40 Pilar Tetap Aman

- Pipeline ini berada di domain research/training.
- Tidak mengubah struktur inti 40 pilar di runtime JAYA_CORE.
- Output runtime yang didorong ke core tetap artefak kecil dan terkontrol.
