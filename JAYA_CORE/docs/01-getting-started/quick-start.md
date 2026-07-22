# Quick Start — JAYA_CORE (5 Menit)

## 1. Chat dengan Otak JAYA

```bash
cd JAYA_CORE
python scripts/jaya_chat_cli.py
```

Ketik pertanyaan, misal:
```
> apa kabar?
> jelaskan konsep intent engine
> buatkan rencana belajar python
```

Ketik `exit` atau `quit` untuk keluar.

---

## 2. Jalankan Test Kognitif (Phase 1)

```bash
# Test IR pipeline
python -m pytest tests/test_phase1_jaya_ir.py -v

# Test benchmark gate (ketat)
python scripts/benchmark_phase1_ir.py --rounds 10 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
```

---

## 3. Test Phase 3C: Intent → UI Pipeline

```bash
python -m pytest tests/test_phase3c_intent_to_ui.py -v
```

Output diharapkan:
```
test_intent_to_ui_pipeline PASSED
```

---

## 4. Generate Benchmark Snapshot

```bash
python scripts/benchmark_phase1_ir.py --rounds 80 --gate --json-out docs/phase1_benchmark_latest.json
```

Hasil: `docs/phase1_benchmark_latest.json` (bukti performa kognitif)

---

## 5. Mode Belajar Otonom

```bash
# Topik spesifik
python scripts/run_autonomous_curriculum.py --topics "Linguistik" "Fisika Quantum"

# Mode kontinu (background)
python scripts/run_autonomous_curriculum.py --continuous
```

---

## 🎯 Checklist "Done"

- [ ] `jaya_chat_cli.py` jalan & responsif
- [ ] `test_phase1_jaya_ir.py` pass
- [ ] Benchmark gate pass (p50 < 50ms, p95 < 100ms, hit-rate > 95%)
- [ ] `test_phase3c_intent_to_ui.py` pass
- [ ] Bisa generate benchmark JSON

---

## 🔗 Lanjutkan ke

- [Installation](installation.md) — Detail setup & troubleshooting
- [Configuration](configuration.md) — Env vars & config files
- [CLI Commands](cli-commands.md) — Semua script CLI
- [Architecture Overview](../02-architecture/overview.md) — Arsitektur Brain vs House