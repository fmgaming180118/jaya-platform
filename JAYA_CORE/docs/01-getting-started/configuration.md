# Configuration — JAYA_CORE

## Environment Variables

| Variable | Default | Deskripsi |
|---|---|---|
| `JAYA_LOCAL_MODEL` | *(none)* | Path ke file `.gguf` untuk local LLM inference |
| `JAYA_OFFLINE_MODE` | `false` | `true` = 100% offline, no network calls |
| `JAYA_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `JAYA_BENCHMARK_ROUNDS` | `40` | Default rounds untuk benchmark gate |
| `JAYA_RESOURCE_CHECK_INTERVAL` | `5.0` | Detik antara resource monitor ticks |
| `JAYA_HIGH_CPU_THRESHOLD` | `85.0` | CPU% trigger `enter_silence()` |
| `JAYA_LOW_CPU_THRESHOLD` | `40.0` | CPU% trigger `exit_silence()` |

---

## Config Files

### `pyrightconfig.json`
Type checking config (Python 3.12 target). Jangan diubah kecuali upgrade Python version.

### `.env` (Optional)
Buat file `.env` di root `JAYA_CORE` untuk override env vars:

```env
JAYA_LOCAL_MODEL=models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
JAYA_OFFLINE_MODE=true
JAYA_LOG_LEVEL=DEBUG
```

Load otomatis via `python-dotenv` jika terinstall.

---

## Benchmark Gate Thresholds (Phase 1)

File: `scripts/benchmark_phase1_ir.py` — argumen CLI:

| Flag | Default | Deskripsi |
|---|---|---|
| `--rounds` | `40` | Jumlah iterasi benchmark |
| `--gate` | `false` | Aktifkan gate (fail jika threshold tidak terpenuhi) |
| `--fail-on-gate` | `false` | Exit code 1 jika gate gagal |
| `--max-warm-p50-ms` | `0.05` | Max p50 latency (ms) warm run |
| `--max-warm-p95-ms` | `0.10` | Max p95 latency (ms) warm run |
| `--min-hit-rate` | `0.95` | Minimal cache hit rate |
| `--json-out` | *(none)* | Path output JSON snapshot |

Contoh ketat:
```bash
python scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
```

---

## Resource Monitor Config (Pillar 2)

Di `src/brain_v2/organism/resource_monitor.py`:

```python
ResourceMonitor(
    check_interval=5.0,           # detik
    high_cpu_threshold=85.0,      # %
    low_cpu_threshold=40.0,       # %
    callbacks=[...]               # custom callbacks
)
```

Top-k ratio adjustment berdasarkan CPU:
| CPU% | topk_ratio |
|---|---|
| < 30% | 0.10 (full) |
| 30-60% | 0.07 |
| 60-80% | 0.04 |
| > 80% | 0.02 (minimal) |

---

## Intent Engine Config

Di `src/brain_v2/engine/intent_engine.py`:

```python
IntentEngine(
    tfidf_max_features=5000,    # vocab size
    tfidf_ngram_range=(1, 2),   # unigram + bigram
    min_confidence=0.3,         # threshold prediksi
    learning_enabled=True       # learn dari input user
)
```

---

## Feature Compiler Config

Di `src/os_kernel/feature_compiler.py`:

```python
FeatureCompiler(
    sandbox_timeout=30,         # detik timeout sandbox exec
    allowed_imports=[           # whitelist imports
        "json", "math", "datetime", "typing",
        "dataclasses", "enum", "collections"
    ],
    blocked_builtins=[          # diblokir di sandbox
        "__import__", "eval", "exec", "open", "compile"
    ]
)
```

---

## JayaBridge Config

Di `src/os_kernel/feature_bridge.py`:

```python
JayaBridge(
    features_dir="./features",  # direktori feature packages
    mount_timeout=10,           # detik timeout mount
    max_features=50             # max concurrent features
)
```

---

## DNA Anchor / Identity Config

File: `jaya.jay` (binary, encrypted) — **jangan edit manual**.

CLI untuk inspect:
```bash
python scripts/inspect_jaya_jay.py --path jaya.jay
```

---

## Logging Config

Default: `logging.basicConfig(level=INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")`

Override via `JAYA_LOG_LEVEL` atau di code:
```python
import logging
logging.getLogger("ResourceMonitor").setLevel(logging.DEBUG)
```

---

## Ringkasan File Config Penting

| File | Lokasi | Jenis |
|---|---|---|
| `pyrightconfig.json` | `JAYA_CORE/` | Type checking |
| `.env` | `JAYA_CORE/` (optional) | Env overrides |
| `jaya.jay` | Root repo | Binary identity (encrypted) |
| `rag_vault.db` | Root repo | SQLite RAG memory |
| `requirements.txt` | `JAYA_CORE/` (jika ada) | Python deps |