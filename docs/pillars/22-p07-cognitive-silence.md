# 22 — Pembangunan Pilar 7: Cognitive Silence

- **ID pilar:** 7
- **Tahap:** 6 — Sistem regulasi
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Memberi mode hening ketika tidak ada tugas, resource tertekan, privacy boundary
aktif, atau owner meminta berhenti—tanpa background action tersembunyi.

## Dependensi

- [Pilar 2 — Resource Aware](03-p02-resource-aware.md)
- [Pilar 5 — Logical Homeostasis](04-p05-logical-homeostasis.md)
- [Pilar 21 — Lingua Logica](02-p21-lingua-logica.md)

## Kontrak dan integrasi

```text
Idle/stop/resource/privacy signal → silence mode → minimal allowed services
```

## Checklist implementasi

- [ ] Definisikan entry/exit condition, wake source, dan minimal service allowlist.
- [ ] Hentikan scheduler, model generation, network, dan tool yang tidak perlu.
- [ ] Persistensikan clean checkpoint sebelum sleep bila diperlukan.
- [ ] Hormati cancellation dan owner stop secara deterministik.
- [ ] Uji wake storm, stuck job, low battery, permission revoke, dan restart.
- [ ] Ukur CPU, RAM, network, dan energy saat silence.

## Exit criteria

Tidak ada aksi proaktif atau network call saat silence kecuali allowlist, dan
resource reduction dibuktikan dengan pengukuran aktual.

## Larangan

`sleep()` atau status string `IDLE` tanpa menghentikan pekerjaan bukan pilar ini.
