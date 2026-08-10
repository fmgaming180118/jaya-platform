# 08 — Pembangunan Pilar 18: Zero Trust

- **ID pilar:** 18
- **Tahap:** 2 — Fondasi kedaulatan
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** SECURITY, RUNTIME

## Tujuan

Memverifikasi identitas, izin, integrity, freshness, dan scope pada setiap
boundary; tidak ada node, model, tool, artifact, atau request yang dipercaya
hanya karena berasal dari jaringan atau proses lokal.

## Dependensi

- [Pilar 11 — DNA Anchor](05-p11-dna-anchor.md)
- [Pilar 15 — Ethical Heart](06-p15-ethical-heart.md)
- [Pilar 20 — Sovereign Privacy](07-p20-sovereign-privacy.md)

## Kontrak dan integrasi

```text
Request/artifact → authenticate → authorize → validate → execute → audit
```

## Checklist implementasi

- [ ] Tetapkan trust boundary dan threat model setiap modul.
- [ ] Implementasikan short-lived credential, nonce, replay protection, dan ACL.
- [ ] Verifikasi signature serta digest artifact sebelum digunakan.
- [ ] Terapkan least privilege pada Core-Agent-OS dan puzzle packs.
- [ ] Uji replay, spoofed node, tampered artifact, duplicate, dan clock skew.
- [ ] Fail closed ketika verifier, clock, atau identity provider gagal.

## Exit criteria

Semua entry point dan capability call mempunyai authentication, authorization,
validation, timeout, audit receipt, dan tes penolakan nyata.

## Larangan

Localhost, nama proses, prefix signature, atau possession of file bukan bukti
kepercayaan.
