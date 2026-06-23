# JAYA_CORE Rollback Plan

## Objective
Dokumen rollback minimal untuk release candidate JAYA_CORE.

## Rollback Trigger Examples
- Runtime healthcheck gagal setelah deployment.
- Readiness report menunjukkan blocker kritikal.
- Benchmark target environment gagal memenuhi threshold.
- Security reviewer menemukan blocker produksi.

## Rollback Steps
1. Identifikasi commit release candidate saat ini.
2. Tentukan previous stable commit SHA.
3. Redeploy artefak dari previous stable commit.
4. Jalankan smoke test `execute_intent()`.
5. Jalankan `healthcheck()` dan `readiness_report()`.
6. Catat insiden dan blocker yang memicu rollback.

## Required Metadata
- Current candidate SHA:
- Previous stable SHA:
- Rollback operator:
- Rollback timestamp:
- Incident reference:

## Validation After Rollback
- [ ] Runtime awake.
- [ ] Healthcheck passes.
- [ ] Core intent path works.
- [ ] Observability snapshots available.
