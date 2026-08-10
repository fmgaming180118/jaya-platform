# 30 — Pembangunan Pilar 33: Agentic RAG

- **ID pilar:** 33
- **Tahap:** 8 — Sensor dan laboratorium
- **Status saat audit:** PROTOTYPE
- **Pemilik:** MODEL, RUNTIME

## Tujuan

Mendeteksi kebutuhan informasi, mencari katalog nyata, mengevaluasi kecukupan
bukti, mengulang retrieval secara terbatas, dan menjawab dengan citation valid.

## Dependensi

- [Pilar 18 — Zero Trust](08-p18-zero-trust.md)
- [Pilar 20 — Sovereign Privacy](07-p20-sovereign-privacy.md)
- [Pilar 8 — Holographic Memory](19-p08-holographic-memory.md)
- [Pilar 26 — Semantic Bridge](17-p26-semantic-bridge.md)
- [Pilar 4 — Multimodal Reflex](29-p04-multimodal-reflex.md)

## Kontrak dan integrasi

```text
Question → need detection → retrieval loop → evidence gate → cited answer
```

## Checklist implementasi

- [ ] Perbaiki checkpoint native sampai load dan inference probe lulus.
- [ ] Validasi query, evidence ID, citation span, confidence, dan round limit.
- [ ] Gunakan persistent library serta provider production.
- [ ] Tolak citation yang tidak ada dan jawaban tanpa evidence saat diwajibkan.
- [ ] Uji unseen source, conflicting evidence, empty retrieval, timeout, restart.
- [ ] Evaluasi groundedness, citation precision/recall, latency, dan RAM.

## Exit criteria

Model nyata dapat menjawab sumber yang belum pernah dilatih, seluruh citation
terverifikasi, dan jalur production dipanggil oleh Core runtime.

## Larangan

Mock model, contoh buku hardcode, atau output LLM tanpa evidence bukan Agentic RAG.
