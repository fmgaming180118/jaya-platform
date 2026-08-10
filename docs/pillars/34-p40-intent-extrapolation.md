# 34 — Pembangunan Pilar 40: Intent Extrapolation

- **ID pilar:** 40
- **Tahap:** 9 — Ruang kendali
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** MODEL

## Tujuan

Memprediksi kebutuhan lanjutan secara terbatas dan transparan, lalu meminta
konfirmasi sebelum aksi yang mempunyai dampak eksternal atau risiko.

## Dependensi

- [Pilar 21 — Lingua Logica](02-p21-lingua-logica.md)
- [Pilar 4 — Multimodal Reflex](29-p04-multimodal-reflex.md)
- [Pilar 33 — Agentic RAG](30-p33-agentic-rag.md)
- [Pilar 38 — Meta Cognitive Planning](33-p38-meta-cognitive-planning.md)

## Kontrak dan integrasi

```text
Observed context → intent candidates + confidence → policy → suggest/confirm
```

## Checklist implementasi

- [ ] Definisikan intent candidate, confidence calibration, expiry, dan source.
- [ ] Bedakan explicit request, inference, dan prohibited assumption.
- [ ] Wajibkan consent untuk profiling serta proactive behavior.
- [ ] Jangan mengeksekusi side effect tanpa authority/confirmation.
- [ ] Uji wrong prediction, ambiguous user, stale context, privacy, dan opt-out.
- [ ] Evaluasi precision, false-positive cost, calibration, dan user correction.

## Exit criteria

JAYA menandai prediksi sebagai inference, mudah dikoreksi, mematuhi opt-out, dan
tidak pernah menyajikannya sebagai fakta atau perintah eksplisit.

## Larangan

Hardcoded suggestion, surveillance, atau menebak data sensitif dilarang.
