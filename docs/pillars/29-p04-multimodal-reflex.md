# 29 — Pembangunan Pilar 4: Multimodal Reflex

- **ID pilar:** 4
- **Tahap:** 8 — Sensor dan laboratorium
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Menerima teks, audio, gambar, video, sensor, dan event sebagai input typed,
memilih provider nyata, lalu menghasilkan observation dengan provenance.

## Dependensi

- [Pilar 2 — Resource Aware](03-p02-resource-aware.md)
- [Pilar 18 — Zero Trust](08-p18-zero-trust.md)
- [Pilar 23 — Sandboxed Imagination](15-p23-sandboxed-imagination.md)
- [Pilar 26 — Semantic Bridge](17-p26-semantic-bridge.md)

## Kontrak dan integrasi

```text
Media/event → validate/authorize → modality adapter → observation → planner
```

## Checklist implementasi

- [ ] Definisikan media schema, size/duration limit, MIME, provenance, confidence.
- [ ] Integrasikan minimal satu provider production per modality yang diklaim.
- [ ] Lazy-load model besar dan sediakan health/readiness probe.
- [ ] Terapkan timeout, cancellation, content policy, dan secure temp storage.
- [ ] Uji malformed media, decompression bomb, provider fail, dan low resource.
- [ ] Ukur latency, RAM, serta kualitas pada corpus representatif.

## Exit criteria

Input nyata melewati adapter dan menghasilkan observation yang dapat ditelusuri;
modality tanpa provider berstatus `CAPABILITY_UNAVAILABLE`.

## Larangan

Intent multimodal, metadata dummy, atau respons “berhasil” bukan integrasi.
