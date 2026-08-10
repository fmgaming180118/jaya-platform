# 09 — Pembangunan Pilar 13: Cryptographic Skin

- **ID pilar:** 13
- **Tahap:** 3 — Selubung keamanan
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** SECURITY, RUNTIME

## Tujuan

Melindungi confidentiality, integrity, dan authenticity brain capsule, memory,
event, model artifact, serta komunikasi lintas boundary.

## Dependensi

- [Pilar 11 — DNA Anchor](05-p11-dna-anchor.md)
- [Pilar 18 — Zero Trust](08-p18-zero-trust.md)
- [Pilar 20 — Sovereign Privacy](07-p20-sovereign-privacy.md)

## Kontrak dan integrasi

```text
Plain payload + policy → AEAD/signature → sealed envelope → verified consumer
```

Key derivation, rotation, version, nonce, dan algorithm suite harus eksplisit.

## Checklist implementasi

- [ ] Pilih primitive dari library kriptografi terawat; jangan membuat cipher.
- [ ] Definisikan envelope versioned, associated data, key ID, nonce, dan expiry.
- [ ] Integrasikan ke `.jaya`, memory, backup, mesh, dan puzzle pack.
- [ ] Gunakan OS keystore/secret manager dan prosedur rotasi/revocation.
- [ ] Uji wrong key, nonce reuse, truncation, bit flip, rollback, dan corruption.
- [ ] Benchmark latency serta ukuran pada target node.

## Exit criteria

Artifact yang diubah satu bit ditolak, key dapat dirotasi tanpa kehilangan data,
dan tidak ada secret muncul di source, log, manifest publik, atau Git.

## Larangan

Base64, checksum, hash tanpa key, atau prefix `sig-*` bukan enkripsi/signature.
