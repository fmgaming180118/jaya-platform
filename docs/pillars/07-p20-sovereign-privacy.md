# 07 — Pembangunan Pilar 20: Sovereign Privacy

- **ID pilar:** 20
- **Tahap:** 2 — Fondasi kedaulatan
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** SECURITY, RUNTIME

## Tujuan

Memastikan memory, identity, prompt, artifact, dan telemetry hanya dipakai sesuai
izin pemilik, klasifikasi data, tujuan, serta masa retensinya.

## Dependensi

- [Pilar 11 — DNA Anchor](05-p11-dna-anchor.md)
- [Pilar 15 — Ethical Heart](06-p15-ethical-heart.md)

## Kontrak dan integrasi

```text
Data + owner + purpose → classification/consent gate → storage/provider/output
```

Kebijakan berlaku konsisten pada Core, Agent, OS, Research, dan puzzle pack.

## Checklist implementasi

- [ ] Definisikan kelas data, consent, retention, export, dan deletion policy.
- [ ] Terapkan encryption at rest/in transit dan log redaction.
- [ ] Pastikan model/provider tidak menerima data di luar izin.
- [ ] Tambahkan subject access, export, revoke, dan recoverable deletion flow.
- [ ] Uji cross-user access, log leak, backup, expired consent, dan provider fail.
- [ ] Audit dependency yang menyimpan atau mengirim data.

## Exit criteria

Tes membuktikan data privat tidak keluar dari boundary, dapat diekspor oleh owner,
dan deletion/retention berjalan pada storage serta backup yang didefinisikan.

## Larangan

Jangan menyimpan secret, prompt privat, atau memory mentah di log dan Git.
