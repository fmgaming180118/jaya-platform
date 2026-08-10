# 31 — Pembangunan Pilar 3: Active Dreaming

- **ID pilar:** 3
- **Tahap:** 8 — Sensor dan laboratorium
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** MODEL

## Tujuan

Mensimulasikan hipotesis dan skenario di ruang kerja terisolasi untuk menghasilkan
kandidat, bukan fakta atau penemuan otomatis.

## Dependensi

- [Pilar 15 — Ethical Heart](06-p15-ethical-heart.md)
- [Pilar 23 — Sandboxed Imagination](15-p23-sandboxed-imagination.md)
- [Pilar 8 — Holographic Memory](19-p08-holographic-memory.md)
- [Pilar 33 — Agentic RAG](30-p33-agentic-rag.md)

## Kontrak dan integrasi

```text
Goal + evidence → sandboxed hypotheses/simulations → evaluation → candidate only
```

## Checklist implementasi

- [ ] Definisikan `HYPOTHESIS`, `SIMULATION`, `REJECTED`, dan `UNVERIFIED`.
- [ ] Simpan model/solver, input, seed, config, output, warning, uncertainty.
- [ ] Batasi compute, time, iteration, dan tool access.
- [ ] Pisahkan memory eksperimen dari verified knowledge.
- [ ] Uji no evidence, unsafe scenario, non-convergence, timeout, dan replay.
- [ ] Demo menghasilkan artifact simulasi dengan label yang benar.

## Exit criteria

Candidate reproducible tersedia, tidak dipromosikan sebagai empirical tanpa
eksperimen nyata, dan seluruh provenance tersimpan.

## Larangan

Visualisasi, output model, atau random simulation bukan bukti penemuan.
