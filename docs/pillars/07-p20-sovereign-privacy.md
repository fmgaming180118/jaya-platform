# 07 — Pembangunan Pilar 20: Sovereign Privacy

- **ID pilar:** 20
- **Tahap:** 2 — Fondasi kedaulatan
- **Status saat audit:** INTEGRATED (95%, bukti lokal)
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

- [x] Definisikan kelas data, consent, retention, export, dan deletion policy.
- [x] Terapkan AES-GCM at rest dan log redaction berlapis.
- [x] Pastikan model/provider eksternal tidak menerima data tanpa consent sesuai scope.
- [x] Tambahkan owner access, export, consent revoke, dan tombstone deletion flow.
- [x] Uji log leak, ciphertext backup, wrong key, tamper, restart, consent scope, dan provider fallback.
- [ ] Audit dependency yang menyimpan atau mengirim data.

## Bukti aktual

- Runtime kanonis mengenkripsi payload episodik melalui reference vault dan
  memaksa model offline bila penggunaan provider eksternal tidak mempunyai
  consent bertanda tangan.
- `python scripts/demo_sovereign_privacy.py --workspace <dir>` membuktikan
  store, restart, ciphertext, deny/allow consent, export, delete, audit chain,
  latency, dan ukuran storage.
- Sisa 5% adalah key manager, scheduler retention, backup deletion, telemetry,
  serta recovery drill pada deployment persisten.

## Exit criteria

Tes membuktikan data privat tidak keluar dari boundary, dapat diekspor oleh owner,
dan deletion/retention berjalan pada storage serta backup yang didefinisikan.

## Larangan

Jangan menyimpan secret, prompt privat, atau memory mentah di log dan Git.
