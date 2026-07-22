# QLoRA Hybrid Pipeline

Pipeline untuk fine-tuning model kecil menggunakan teacher model besar — tanpa butuh GPU besar saat runtime.

**Prinsip:** Pengajaran boleh pakai resource besar, tapi JAYA saat dijalankan tetap ringan.

---

## Arsitektur Pipeline

```
Ollama (qwen3:4b lokal)         ← Teacher: generate dataset bahasa
        │
        ▼ (JSONL dataset)
QLoRA Training (HuggingFace)    ← Fine-tune base model dengan adapter
        │
        ▼ (LoRA adapter weights)
Deploy: base model + adapter     ← Runtime JAYA yang ringan
```

---

## Prasyarat

```bash
# Windows — setup CUDA environment otomatis
JAYA_RESEARCH\scripts\setup_qlora_cuda_env.cmd

# Manual
pip install -r requirements-qlora.txt

# Install Ollama + model teacher
# Download: https://ollama.ai
ollama pull qwen3:4b
```

> [!NOTE]
> QLoRA membutuhkan GPU dengan minimal 8GB VRAM untuk training. Runtime setelah training tidak butuh GPU.

---

## Step 1: Generate Dataset dari Ollama

```bash
python JAYA_RESEARCH/src/training/build_qlora_dataset_from_ollama.py \
  --model qwen3:4b \
  --variants-per-key 8 \
  --out JAYA_RESEARCH/data/qlora/language_policy_qlora_dataset.jsonl
```

**Opsi:**
- `--variants-per-key` — berapa variasi per key (lebih banyak = dataset lebih kaya)
- `--seed-file` — JSON berisi seed examples untuk mengarahkan gaya bahasa

---

## Step 2: Training QLoRA Adapter

```bash
# Dry-run dulu untuk cek environment
python src/training/train_qlora_language_adapter.py --dry-run

# Training sesungguhnya
python src/training/train_qlora_language_adapter.py \
  --base-model Qwen/Qwen3-4B-Instruct-2507 \
  --dataset data/qlora/language_policy_qlora_dataset.jsonl \
  --output-dir data/qlora/adapter-qwen3-4b-language \
  --epochs 2 \
  --batch-size 1 \
  --grad-accum 16 \
  --max-seq-length 768
```

**Parameter penting:**
- `--grad-accum 16` — effective batch size = 16 (hemat VRAM)
- `--max-seq-length 768` — sesuaikan dengan panjang contoh dalam dataset
- `--epochs 2` — cukup untuk adapter, lebih banyak bisa overfit

---

## Step 3: Evaluasi

```bash
# Evaluasi dry-run
python src/training/evaluate_qlora_language_adapter.py --dry-run

# Evaluasi penuh (base vs adapter)
python src/training/evaluate_qlora_language_adapter.py \
  --adapter-dir data/qlora/adapter-qwen3-4b-language
```

---

## Klarifikasi Teknis

| Konsep | Penjelasan |
|---|---|
| **GGUF (Ollama)** | Format model terkompresi untuk inference lokal — dipakai sebagai **teacher** |
| **HuggingFace model** | Base model untuk QLoRA training (bukan GGUF) |
| **LoRA adapter** | Delta weights kecil yang ditambah ke base model saat inference |
| **Deployment** | `base_model + adapter` — jauh lebih ringan dari model monolitik |

> [!IMPORTANT]
> Model GGUF Ollama **tidak bisa** ditraining langsung dengan QLoRA. Ollama hanya dipakai sebagai data generator (teacher).

---

## Output

Adapter disimpan di `data/qlora/adapter-*/` (dikecualikan dari git — berisi model weights).

Untuk deploy, load adapter di atas base model:
```python
from peft import PeftModel
from transformers import AutoModelForCausalLM

base_model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-4B-Instruct-2507")
model = PeftModel.from_pretrained(base_model, "data/qlora/adapter-qwen3-4b-language")
```
