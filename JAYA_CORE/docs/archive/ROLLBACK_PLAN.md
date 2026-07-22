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
- Current candidate SHA: daebf67
- Previous stable SHA: d232d1a
- Rollback operator: JAYA System Administrator
- Rollback timestamp: 2026-07-22 22:16:00
- Incident reference: VERIFIED_NO_INCIDENT (Dry run & simulation pass)

## Validation After Rollback
- [x] Runtime awake.
- [x] Healthcheck passes.
- [x] Core intent path works.
- [x] Observability snapshots available.
