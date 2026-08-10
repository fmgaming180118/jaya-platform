# 38 — Pembangunan Pilar 35: Activation Sparsity

- **ID pilar:** 35
- **Tahap:** 10 — Kompleks terdistribusi
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Mengurangi compute dengan mengaktifkan jalur/neuron penting saja menggunakan
kernel nyata sambil menjaga kualitas dan determinisme yang dibutuhkan.

## Dependensi

- [Pilar 2 — Resource Aware](03-p02-resource-aware.md)
- [Pilar 5 — Logical Homeostasis](04-p05-logical-homeostasis.md)
- [Pilar 34 — Dynamic Sparsity MoE](37-p34-dynamic-sparsity-moe.md)

## Kontrak dan integrasi

```text
Activation state + threshold/policy → sparse kernel → output + sparsity metrics
```

## Checklist implementasi

- [ ] Definisikan threshold, calibration, kernel support, dan quality budget.
- [ ] Implementasikan runtime sparse kernel atau adapter production.
- [ ] Gunakan capability probe dan dense fallback yang jujur.
- [ ] Ukur achieved sparsity, latency, memory, energy, serta accuracy.
- [ ] Uji threshold ekstrem, unsupported hardware, NaN, dan fallback.
- [ ] Simpan benchmark environment dan model digest.

## Exit criteria

Sparsity aktual terukur pada inference production dan quality regression berada
dalam acceptance threshold yang disetujui.

## Larangan

Menghitung nol pada tensor tanpa kernel yang memanfaatkan sparsity bukan fitur.
