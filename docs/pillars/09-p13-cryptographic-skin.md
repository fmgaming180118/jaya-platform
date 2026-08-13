# 09 — Pembangunan Pilar 13: Cryptographic Skin

- **ID pilar:** 13
- **Tahap:** 3 — Selubung keamanan
- **Status saat audit:** INTEGRATED — 90%
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

- [x] Pilih primitive dari library kriptografi terawat; jangan membuat cipher.
- [x] Definisikan envelope versioned, associated data, key ID, nonce, dan expiry.
- [x] Integrasikan capsule satu-file `.jayac` ke brain, backup, mesh, dan puzzle
  pack melalui boundary runtime yang sama.
- [ ] Gunakan OS keystore/secret manager dan prosedur rotasi/revocation.
- [ ] Uji wrong key, nonce reuse, truncation, bit flip, rollback, dan corruption
  pada target lokal; seluruhnya kecuali anti-rollback eksternal sudah lulus.
- [x] Benchmark latency serta ukuran pada target node lokal.

Implementasi lokal memakai AES-256-GCM, Scrypt + HKDF, nonce registry persisten,
key rotation/revocation, Ed25519 DNA attestation, expiry, payload limit, serta
audit hash-chain. Launcher dan `JayaCoreRuntime` sudah memakai service P13 pada
jalur seal/open artifact. `JayaCapsuleCodec` memberi satu format biner dengan
purpose/subject/kind yang terikat dan dapat diberi signature hybrid P16. Nilai
executable saat ini 90%; rincian berada di
[dashboard Selubung Keamanan](../SECURITY_ENVELOPE_PROGRESS.md).

## Exit criteria

Artifact yang diubah satu bit ditolak, key dapat dirotasi tanpa kehilangan data,
dan tidak ada secret muncul di source, log, manifest publik, atau Git.

## Larangan

Base64, checksum, hash tanpa key, atau prefix `sig-*` bukan enkripsi/signature.
