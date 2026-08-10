# 39 — Pembangunan Pilar 30: Twin Protocol

- **ID pilar:** 30
- **Tahap:** 10 — Kompleks terdistribusi
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Memindahkan atau mereplikasi state yang diizinkan antar-node dengan identity,
attestation, conflict resolution, encryption, dan migration lineage nyata.

## Dependensi

- [Pilar 11 — DNA Anchor](05-p11-dna-anchor.md)
- [Pilar 13 — Cryptographic Skin](09-p13-cryptographic-skin.md)
- [Pilar 20 — Sovereign Privacy](07-p20-sovereign-privacy.md)
- [Pilar 25 — Digital Epigenetics](25-p25-digital-epigenetics.md)
- [Pilar 19 — Legacy Protocol](28-p19-legacy-protocol.md)
- [Pilar 37 — Hybrid Consciousness](36-p37-hybrid-consciousness.md)

## Kontrak dan integrasi

```text
Source attestation → owner-approved handoff → encrypted transfer → target verify
```

## Checklist implementasi

- [ ] Definisikan node certificate, handoff nonce, authority, lease, dan revocation.
- [ ] Implementasikan transport authenticated-encrypted dan resumable transfer.
- [ ] Rewrap brain key untuk target; jangan menyalin node secret.
- [ ] Persistensikan cursor, conflict, migration ledger, dan completion receipt.
- [ ] Uji replay, split brain, interrupted transfer, revoked target, dan clock skew.
- [ ] Demo migrasi dua node nyata dengan continuity dan rollback.

## Exit criteria

JAYA mempertahankan `brain_id`, mengetahui node aktif, mencegah authority ganda,
dan dapat membuktikan seluruh lineage perpindahannya.

## Larangan

Menyalin file, in-memory event sync, atau prefix signature bukan Twin Protocol.
