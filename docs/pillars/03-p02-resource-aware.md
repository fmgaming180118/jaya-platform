# 03 — Pembangunan Pilar 2: Resource Aware

- **ID pilar:** 2
- **Tahap:** 1 — Pondasi
- **Status saat audit:** VERIFIED (95%)
- **Pemilik:** MODEL, RUNTIME

## Tujuan

Membuat JAYA mengetahui resource aktual tempat ia hidup dan memilih model,
budget, serta capability sesuai kondisi node tanpa angka fallback palsu.

## Dependensi

- [Pilar 1 — Pure Logic](01-p01-pure-logic.md)
- [Pilar 21 — Lingua Logica](02-p21-lingua-logica.md)

## Kontrak dan integrasi

```text
OS metrics + capability probe → ResourceProfile → Budget → Model/plan selection
```

Metric yang tidak dapat dibaca wajib berstatus `UNKNOWN`, bukan nilai perkiraan.

## Checklist implementasi

- [x] Definisikan schema CPU, RAM, storage, accelerator, network, thermal, power.
- [x] Implementasikan probe lintas platform dan provider test terpisah.
- [x] Simpan waktu, unit semantik, sumber metric, dan nilai unknown apa adanya.
- [x] Hubungkan profile ke budget, mode, homeostasis, dan metrics Core.
- [x] Uji metric hilang, resource rendah, perubahan thermal/power, dan disk rendah.
- [x] Benchmark overhead profiler pada perangkat lokal.

Probe memakai data OS/`psutil` dan `nvidia-smi` bila tersedia, tanpa fallback
palsu. Consumer di luar Core tetap puzzle opsional. Lima persen terakhir adalah
observasi deployment berkelanjutan; lihat
[dashboard Pondasi Logika](../LOGICAL_FOUNDATION_PROGRESS.md).

## Exit criteria

Keputusan mode berubah berdasarkan metric nyata dan dapat diaudit; restart,
provider gagal, serta nilai `UNKNOWN` tidak menghasilkan klaim resource palsu.

## Larangan

Tidak boleh hardcode RAM, storage, network availability, atau kelas node.
