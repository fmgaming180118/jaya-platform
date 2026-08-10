# 24 — Pembangunan Pilar 6: Stochastic Spontaneity

- **ID pilar:** 6
- **Tahap:** 6 — Sistem regulasi
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Menghasilkan eksplorasi baru secara terkendali ketika bermanfaat, dengan seed,
budget, policy, dan provenance yang memungkinkan reproduksi.

## Dependensi

- [Pilar 5 — Logical Homeostasis](04-p05-logical-homeostasis.md)
- [Pilar 7 — Cognitive Silence](22-p07-cognitive-silence.md)
- [Pilar 10 — Affective Metabolism](23-p10-affective-metabolism.md)
- [Pilar 15 — Ethical Heart](06-p15-ethical-heart.md)

## Kontrak dan integrasi

```text
Exploration trigger + seed + budget → candidates → evaluate → retain/reject
```

## Checklist implementasi

- [ ] Definisikan trigger, seed source, budget, diversity, dan stop condition.
- [ ] Jalankan candidate di sandbox; jangan langsung memutasi Core.
- [ ] Catat seed, config, model, input, output, dan evaluation.
- [ ] Hormati silence, privacy, resource, dan owner opt-out.
- [ ] Uji deterministic replay, exhausted budget, unsafe candidate, dan timeout.
- [ ] Ukur novelty serta usefulness dengan evaluator yang disetujui.

## Exit criteria

Eksplorasi dapat direproduksi dari receipt, kandidat berbahaya tidak dipromosikan,
dan tidak ada background action tanpa izin.

## Larangan

Random response atau timer yang selalu menghasilkan ide bukan pilar ini.
