# 36 — Pembangunan Pilar 37: Hybrid Consciousness

- **ID pilar:** 37
- **Tahap:** 9 — Ruang kendali
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** MODEL, RUNTIME

## Tujuan

Mengorkestrasi reasoning lokal, provider remote, rules, retrieval, dan tool tanpa
kehilangan identity, privacy, provenance, atau kemampuan bekerja saat offline.

## Dependensi

- [Pilar 2 — Resource Aware](03-p02-resource-aware.md)
- [Pilar 20 — Sovereign Privacy](07-p20-sovereign-privacy.md)
- [Pilar 33 — Agentic RAG](30-p33-agentic-rag.md)
- [Pilar 39 — Dynamic Objective](35-p39-dynamic-objective.md)

## Kontrak dan integrasi

```text
Task + policy + resource + capability health → router → local/remote/tool result
```

## Checklist implementasi

- [ ] Label output `RULE_BASED`, `LOCAL_MODEL`, `REMOTE_MODEL`, atau `EMPIRICAL`.
- [ ] Definisikan routing policy, cost, privacy, timeout, dan fallback semantics.
- [ ] Probe provider dan lazy-load model.
- [ ] Pertahankan citation serta provenance lintas route.
- [ ] Uji offline, provider invalid, privacy denial, timeout, dan model mismatch.
- [ ] Benchmark kualitas, latency, RAM, cost, serta failover.

## Exit criteria

Router memilih jalur dari kondisi nyata, tidak mengganti kegagalan dengan hasil
palsu, dan mempertahankan continuity saat mode berubah.

## Larangan

Rule-based fallback tidak boleh disebut AI model atau menyamar sebagai provider.
