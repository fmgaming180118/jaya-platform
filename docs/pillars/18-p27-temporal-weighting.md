# 18 — Pembangunan Pilar 27: Temporal Weighting

- **ID pilar:** 27
- **Tahap:** 5 — Lantai memori
- **Status saat audit:** PROTOTYPE
- **Pemilik:** MODEL, RUNTIME

## Tujuan

Menilai relevansi memory berdasarkan waktu, validitas, sumber, penggunaan,
confidence, dan supersession tanpa menghapus sejarah secara diam-diam.

## Dependensi

- [Pilar 5 — Logical Homeostasis](04-p05-logical-homeostasis.md)
- [Pilar 26 — Semantic Bridge](17-p26-semantic-bridge.md)

## Kontrak dan integrasi

```text
Memory + timestamps + provenance → temporal policy → ranked active context
```

## Checklist implementasi

- [ ] Gunakan UTC, monotonic clock untuk durasi, dan clock-source metadata.
- [ ] Definisikan decay, expiry, supersession, retention, dan legal hold.
- [ ] Persistensikan event; jangan mutasi history tanpa audit trail.
- [ ] Hubungkan ranking ke retrieval dan context builder.
- [ ] Uji clock skew, future timestamp, stale fact, restart, dan timezone.
- [ ] Evaluasi ranking pada kasus perubahan fakta nyata.

## Exit criteria

Fakta lama tidak mengalahkan fakta baru yang tervalidasi, tetapi histori tetap
dapat diaudit dan direproduksi.

## Larangan

Timestamp hardcode atau sekadar mengurutkan `created_at` bukan Temporal Weighting.
