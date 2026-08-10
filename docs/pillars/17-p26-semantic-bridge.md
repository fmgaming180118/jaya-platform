# 17 — Pembangunan Pilar 26: Semantic Bridge

- **ID pilar:** 26
- **Tahap:** 5 — Lantai memori
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** MODEL

## Tujuan

Menyatukan makna lintas teks, kode, dokumen, event, memory, dan capability ke
dalam referensi semantik yang typed serta mempunyai provenance.

## Dependensi

- [Pilar 1 — Pure Logic](01-p01-pure-logic.md)
- [Pilar 21 — Lingua Logica](02-p21-lingua-logica.md)
- [Pilar 23 — Sandboxed Imagination](15-p23-sandboxed-imagination.md)

## Kontrak dan integrasi

```text
Source artifact → parser/encoder → semantic entity + relation + provenance
```

## Checklist implementasi

- [ ] Definisikan entity, relation, namespace, source ID, dan schema version.
- [ ] Integrasikan parser/embedding/provider nyata melalui adapter.
- [ ] Pertahankan citation span dan digest sumber.
- [ ] Hubungkan output ke memory, retrieval, planner, dan JayaIR.
- [ ] Uji ambiguous term, duplicate entity, corrupt source, dan model unavailable.
- [ ] Evaluasi retrieval/semantic matching pada dataset representatif.

## Exit criteria

Entitas lintas sumber dapat ditautkan dan ditelusuri kembali ke bukti asli,
serta ketidakpastian tidak diubah menjadi fakta pasti.

## Larangan

Embedding similarity saja tanpa provenance dan schema tidak cukup.
