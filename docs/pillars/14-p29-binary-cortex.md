# 14 — Pembangunan Pilar 29: Binary Cortex

- **ID pilar:** 29
- **Tahap:** 4 — Rangka mesin
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Mengoptimalkan bagian terpilih dari inferensi dengan representasi biner dan
kernel perangkat nyata tanpa mengorbankan jalur fallback yang benar.

## Dependensi

- [Pilar 2 — Resource Aware](03-p02-resource-aware.md)
- [Pilar 13 — Cryptographic Skin](09-p13-cryptographic-skin.md)
- [Pilar 21 — Lingua Logica](02-p21-lingua-logica.md)

## Kontrak dan integrasi

```text
Hardware profile + binary artifact → compatible kernel → inference + metrics
```

## Checklist implementasi

- [ ] Tentukan operasi yang aman dibinarisasi dan baseline kualitasnya.
- [ ] Implementasikan kernel production atau adapter library nyata.
- [ ] Tambahkan runtime dispatch berdasarkan capability probe.
- [ ] Verifikasi artifact, alignment, shape, dan CPU instruction support.
- [ ] Uji unsupported hardware, corrupt weight, fallback, dan timeout.
- [ ] Benchmark terhadap floating/ternary baseline pada target node.

## Exit criteria

Runtime memilih kernel berdasarkan bukti hardware dan hasil benchmark aktual,
bukan flag; fallback tidak mengubah jawaban menjadi sukses palsu.

## Larangan

Bit flag `BINARY_CORTEX` atau file packed tanpa eksekusi kernel tidak dihitung.
