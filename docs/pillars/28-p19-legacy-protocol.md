# 28 — Pembangunan Pilar 19: Legacy Protocol

- **ID pilar:** 19
- **Tahap:** 7 — Perawatan gedung
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Memigrasikan brain capsule, identity, memory, dan policy dari versi lama ke
format baru secara eksplisit, aman, dan dapat di-rollback.

## Dependensi

- [Pilar 11 — DNA Anchor](05-p11-dna-anchor.md)
- [Pilar 13 — Cryptographic Skin](09-p13-cryptographic-skin.md)
- [Pilar 20 — Sovereign Privacy](07-p20-sovereign-privacy.md)
- [Pilar 25 — Digital Epigenetics](25-p25-digital-epigenetics.md)
- [Pilar 28 — Self Bootstrapping](27-p28-self-bootstrapping.md)

## Kontrak dan integrasi

```text
Legacy artifact → detect/verify → isolated migration → new `.jaya` → validate
```

## Checklist implementasi

- [ ] Inventaris seluruh magic/layout lama dan tentukan support window.
- [ ] Buat importer satu arah; jangan pertahankan dua runtime format aktif.
- [ ] Verifikasi input, mapping section, owner approval, dan output digest.
- [ ] Simpan migration receipt serta untouched source backup.
- [ ] Uji truncated file, unknown version, wrong key, duplicate, dan rollback.
- [ ] Demo migrasi setiap versi yang masih didukung.

## Exit criteria

Artifact lama dapat dikonversi tanpa kehilangan identity/memory yang didukung,
sedangkan format tidak dikenal ditolak tanpa merusak sumber.

## Larangan

Menebak layout, silently dropping section, atau membuka format lama langsung di
runtime production dilarang.
