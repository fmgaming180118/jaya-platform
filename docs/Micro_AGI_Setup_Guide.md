# Micro-AGI: Setup & Architecture Guide

## 1. Filosofi: "Neural Compiler"
Proyek ini bukan membuat Chatbot. Proyek ini membuat **AI yang memprogram dirinya sendiri** (Neural Compiler).
Tujuannya adalah efisiensi ekstrem (1GB VRAM) dengan cara mengubah logika tingkat tinggi menjadi kode mesin (LLVM IR / Assembly).

## 2. Struktur Project
```
jaya-research/
├── config.yaml          # Jantung konfigurasi (Model, VRAM, API Keys)
├── docs/                # Dokumentasi Riset
├── models/              # Tempat menaruh model .safetensors / .gguf
├── src/
│   ├── main.py          # Bootloader
│   ├── engine.py        # Wrapper tinygrad
│   └── teacher.py       # Wrapper NVIDIA NIM
└── requirements.txt
```

## 3. Konfigurasi (config.yaml)
Kami menolak hardcoding. Semua pengaturan teknis diatur di `config.yaml`.

```yaml
system:
  vram_limit_mb: 1024       # Batas keras memori GPU
  use_gpu: true             # Gunakan GPU jika ada, fall back ke CPU
  log_level: "INFO"

teacher:
  provider: "nvidia_nim"
  model: "meta/llama3-70b-instruct"
  # api_key: diambil dari env var NVIDIA_API_KEY

student:
  framework: "tinygrad"
  model_path: "models/micro_agi_v1.safetensors"
  context_window: 2048
```

## 4. Cara Penggunaan
1.  **Install Dependencies:** `pip install tinygrad pyyaml`
2.  **Set API Key:** `export NVIDIA_API_KEY=ur_key_here`
3.  **Jalankan Bootloader:** `python src/main.py`

## 5. Next Step: "The Seed"
Langkah selanjutnya adalah melatih "Bibit" model kecil untuk memahami instruksi dasar CPU.
