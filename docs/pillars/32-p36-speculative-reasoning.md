# 32 — Pembangunan Pilar 36: Speculative Reasoning

- **ID pilar:** 36
- **Tahap:** 8 — Sensor dan laboratorium
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** MODEL

## Tujuan

Membangun beberapa jalur solusi, memverifikasi masing-masing dengan evidence dan
constraint, lalu memilih atau menolak kandidat berdasarkan evaluator nyata.

## Dependensi

- [Pilar 1 — Pure Logic](01-p01-pure-logic.md)
- [Pilar 5 — Logical Homeostasis](04-p05-logical-homeostasis.md)
- [Pilar 15 — Ethical Heart](06-p15-ethical-heart.md)
- [Pilar 23 — Sandboxed Imagination](15-p23-sandboxed-imagination.md)
- [Pilar 3 — Active Dreaming](31-p03-active-dreaming.md)

## Kontrak dan integrasi

```text
Problem → bounded candidates → verify/evaluate → select/reject + rationale
```

## Checklist implementasi

- [ ] Definisikan candidate graph, budget, evaluator, confidence, dan stop rule.
- [ ] Gunakan independent checks untuk logika, citation, test, atau solver.
- [ ] Jalankan kandidat berisiko di sandbox.
- [ ] Simpan candidate yang ditolak beserta alasan tanpa memenuhi context aktif.
- [ ] Uji evaluator disagreement, no valid candidate, timeout, dan resource limit.
- [ ] Benchmark accuracy/latency terhadap single-path baseline.

## Exit criteria

Pemilihan kandidat meningkatkan metrik yang ditetapkan dan dapat direproduksi;
tidak ada jalur valid menghasilkan status gagal terstruktur.

## Larangan

Mengambil jawaban dengan self-score tertinggi tanpa verifier bukan pilar ini.
