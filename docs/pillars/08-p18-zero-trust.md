# 08 — Pembangunan Pilar 18: Zero Trust

- **ID pilar:** 18
- **Tahap:** 2 — Fondasi kedaulatan
- **Status saat audit:** INTEGRATED (95%, bukti lokal)
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

- [x] Tetapkan trust boundary untuk invocation puzzle kanonis.
- [x] Implementasikan short-lived envelope, nonce, replay protection, dan ACL.
- [x] Verifikasi DNA attestation, payload digest, dan puzzle artifact digest.
- [x] Terapkan least privilege pada Core dan puzzle registry.
- [x] Uji replay, spoofed node, tampered payload/artifact, expiry, dan revocation.
- [x] Fail closed ketika identity/authority tidak tersedia pada mode wajib.

## Bukti aktual

- Registry hanya menjalankan puzzle setelah receipt Ethical Heart valid dan
  envelope Zero Trust baru terikat brain, node, capability, payload, expiry,
  nonce, serta DNA attestation.
- `python scripts/demo_zero_trust.py --workspace <dir>` membuktikan allow,
  replay deny, payload-tamper deny, restart persistence, audit chain, latency,
  dan ukuran storage.
- Sisa 5% adalah CA/key rotation, distributed clock, revocation propagation,
  telemetry, dan recovery drill pada deployment live.

## Exit criteria

Semua entry point dan capability call mempunyai authentication, authorization,
validation, timeout, audit receipt, dan tes penolakan nyata.

## Larangan

Localhost, nama proses, prefix signature, atau possession of file bukan bukti
kepercayaan.
