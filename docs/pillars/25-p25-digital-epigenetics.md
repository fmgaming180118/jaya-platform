# 25 — Pembangunan Pilar 25: Digital Epigenetics

- **ID pilar:** 25
- **Tahap:** 7 — Perawatan gedung
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Mencatat perubahan konfigurasi, policy, model, memory schema, dan capability
sebagai lineage yang dapat diaudit tanpa mengubah identitas inti JAYA.

## Dependensi

- [Pilar 11 — DNA Anchor](05-p11-dna-anchor.md)
- [Pilar 16 — Quantum Resistant](11-p16-quantum-resistant.md)
- [Pilar 20 — Sovereign Privacy](07-p20-sovereign-privacy.md)

## Kontrak dan integrasi

```text
Approved change → signed delta + evidence → new generation → lineage ledger
```

## Checklist implementasi

- [ ] Definisikan generation ID, parent digest, delta, evidence, dan approval.
- [ ] Pisahkan immutable identity dari mutable configuration/state.
- [ ] Simpan lineage append-only dan lindungi dari rollback attack.
- [ ] Integrasikan ke model update, policy, memory migration, dan puzzle pack.
- [ ] Uji forged parent, duplicate generation, branch, merge, revoke, dan restart.
- [ ] Demo menelusuri state aktif hingga genesis tanpa gap.

## Exit criteria

Setiap perubahan material mempunyai parent, bukti, approval, digest, dan rollback
target yang dapat diverifikasi.

## Larangan

Nomor versi yang dinaikkan manual atau timestamp saja bukan lineage epigenetik.
