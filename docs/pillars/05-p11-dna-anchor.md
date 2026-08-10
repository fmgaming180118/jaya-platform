# 05 — Pembangunan Pilar 11: DNA Anchor

- **ID pilar:** 11
- **Tahap:** 2 — Fondasi kedaulatan
- **Status saat audit:** INTEGRATED (90%)
- **Pemilik:** SECURITY, RUNTIME

## Tujuan

Memberikan `brain_id` dan identitas pemilik yang stabil ketika JAYA restart,
di-upgrade, atau berpindah node, tanpa mengikat permanen ke satu perangkat.

## Dependensi

- [Pilar 1 — Pure Logic](01-p01-pure-logic.md)
- [Pilar 5 — Logical Homeostasis](04-p05-logical-homeostasis.md)

## Kontrak dan integrasi

```text
Owner enrollment → keypair/brain_id → signed identity record → runtime boot
```

Pisahkan portable brain identity dari node certificate dan session instance ID.

## Checklist implementasi

- [x] Tetapkan schema `brain_id`, owner keys, lineage, rotation, dan revocation.
- [x] Simpan private material pada encrypted keystore dengan secret terinjeksi.
- [x] Implementasikan challenge-response, nonce, expiry, dan replay protection.
- [x] Persistensikan identity dan uji restart serta migration.
- [x] Uji cloning, tampering, revoked key, wrong owner, dan lost keystore.
- [x] Catat seluruh perubahan identity dalam signed audit ledger.
- [ ] Verifikasi OS-keystore/secret-manager dan deployment persisten.

## Exit criteria

Identitas yang sama dapat dibuktikan setelah restart dan migrasi resmi, sedangkan
salinan tanpa otorisasi gagal boot ke mode berotoritas.

## Larangan

Hash hardware, string `jaya-master`, atau owner hardcode bukan DNA Anchor.
