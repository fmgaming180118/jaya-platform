# JAYA_CORE Deployment Validation Checklist

## Objective
Checklist validasi deployment pada environment target sebelum JAYA_CORE dinyatakan layak produksi penuh.

## Environment Metadata
- Hostname:
- OS Version:
- Python Version:
- CPU / RAM:
- Deployment Date:
- Operator:

## Pre-Deployment Checks
- [ ] Python runtime tersedia dan sesuai baseline.
- [ ] Artefak `.jay` target tersedia.
- [ ] Environment variables yang diperlukan tersedia.
- [ ] Folder data/runtime writable.

## Runtime Validation
- [ ] Jalankan `python JAYA_CORE/scripts/validate_target_runtime.py` pada mesin target.
- [ ] `IronEngine.healthcheck()` returns `ok=true`.
- [ ] `IronEngine.readiness_report()` returns `stage=production_candidate`.
- [ ] `execute_intent()` smoke test berhasil.
- [ ] `status()` menampilkan observability snapshot lengkap.
- [ ] Zero Trust path menolak source yang tidak trusted.

## Performance Validation
- [ ] Benchmark strict gate dijalankan pada mesin target.
- [ ] Warm p50 memenuhi threshold.
- [ ] Warm p95 memenuhi threshold.
- [ ] Hit rate memenuhi threshold.

## Failure Mode Validation
- [ ] Missing model path degrades cleanly (no silent crash).
- [ ] Missing optional subsystem tetap menghasilkan status terstruktur.
- [ ] Resource monitor silence path dapat dipantau.
- [ ] Runtime rollback/degraded mode terdokumentasi.

## Final Decision
- [ ] ACCEPT deployment target
- [ ] REJECT deployment target

Notes:
