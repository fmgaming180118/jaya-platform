# Installation Guide — JAYA_OS

## Prasyarat Sistem

| Komponen | Versi Minimum | Catatan |
|---|---|---|
| **Python** | 3.12 | Lihat `pyrightconfig.json` di JAYA_CORE |
| **OS** | Windows 10/11, Linux, macOS | Cross-platform |
| **RAM** | 4 GB+ | 8 GB+ recommended untuk local LLM |
| **Disk** | 2 GB free | Models, cache, logs |

---

## 1. Clone Repository

```bash
git clone https://github.com/fmgaming180118/jaya-research.git
cd jaya-research/JAYA_OS
```

---

## 2. Setup Virtual Environment

### Windows (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

### Linux / macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note**: Jika `requirements.txt` tidak ada di root `JAYA_OS`, install dependencies minimal:
> ```bash
> pip install numpy pydantic pytest pytest-asyncio psutil
> ```

---

## 3. Verifikasi Instalasi

```bash
# Jalankan test runtime (Phase 3C)
python -m pytest tests/test_phase3c_intent_to_ui.py -v

# Harus output: 1 passed
```

---

## 4. Opsional: Install Local LLM (untuk chat offline)

Jika ingin menjalankan `jaya_chat_cli.py` dengan model lokal:

```bash
# Install llama.cpp Python bindings
pip install llama-cpp-python

# Download model GGUF (contoh: TinyLlama 1.1B Q4_K_M)
mkdir -p models
cd models
wget https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
```

Lalu set environment variable:
```bash
# Windows
$env:JAYA_LOCAL_MODEL = "models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

# Linux/macOS
export JAYA_LOCAL_MODEL="models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
```

---

## 5. Struktur Direktori Penting

```
JAYA_OS/
├── src/
│   ├── os_kernel/          # Home Layer (Body)
│   │   ├── feature_compiler.py
│   │   ├── feature_registry.py
│   │   ├── feature_bridge.py
│   │   ├── intent_to_ui.py
│   │   ├── ui_spec.py
│   │   ├── ipc.py
│   │   └── window_manager.py
│   └── jaya_language/      # Shared Language Layer
├── tests/                  # Test cases
├── scripts/                # CLI tools
├── docs/                   # Dokumentasi (folder ini)
└── pyrightconfig.json      # Python 3.12 config
```

---

## 6. Troubleshooting Umum

| Masalah | Solusi |
|---|---|
| `ModuleNotFoundError: src.os_kernel` | Jalankan dari root `JAYA_OS` atau set `PYTHONPATH=.` |
| `pytest` tidak ditemukan | `pip install pytest pytest-asyncio` |
| `psutil` error di Windows | `pip install psutil` (biasanya OK) |
| Benchmark gagal p50/p95 | Pastikan tidak ada proses berat lain; jalankan `--rounds 10` dulu untuk smoke test |

---

## 7. Langkah Selanjutnya

- [Quick Start](quick-start.md) — Jalankan JAYA_OS dalam 5 menit
- [Configuration](configuration.md) — Penjelasan config & env vars
- [CLI Commands](cli-commands.md) — Referensi lengkap script CLI