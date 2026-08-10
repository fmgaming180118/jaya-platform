# 21 — Pembangunan Pilar 17: Socratic Mirror

- **ID pilar:** 17
- **Tahap:** 6 — Sistem regulasi
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Menguji asumsi, evidence, risiko, kontradiksi, dan alternatif sebelum keputusan
berdampak tinggi diteruskan ke execution.

## Dependensi

- [Pilar 1 — Pure Logic](01-p01-pure-logic.md)
- [Pilar 15 — Ethical Heart](06-p15-ethical-heart.md)
- [Pilar 20 — Sovereign Privacy](07-p20-sovereign-privacy.md)

## Kontrak dan integrasi

```text
Candidate decision → critique questions/proofs → revised or blocked decision
```

## Checklist implementasi

- [ ] Definisikan trigger berbasis risk, uncertainty, novelty, dan impact.
- [ ] Gunakan evidence validator dan logic proof, bukan self-score saja.
- [ ] Batasi round, token, latency, dan escalation ke manusia.
- [ ] Simpan critique serta perubahan keputusan sebagai audit evidence.
- [ ] Uji unsupported claim, confirmation bias, timeout, dan circular reasoning.
- [ ] Evaluasi apakah critique memperbaiki error pada benchmark nyata.

## Exit criteria

Keputusan berisiko tidak dapat lolos tanpa evidence atau approval yang diwajibkan,
dan manfaat refleksi terukur terhadap baseline.

## Larangan

Prompt “pikirkan lagi” atau dua jawaban model yang saling setuju bukan proof.
