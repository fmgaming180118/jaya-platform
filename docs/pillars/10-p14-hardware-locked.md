# 10 — Pembangunan Pilar 14: Hardware Locked

- **ID pilar:** 14
- **Tahap:** 3 — Selubung keamanan
- **Status saat audit:** INTEGRATED — 85%
- **Pemilik:** SECURITY, RUNTIME

## Tujuan

Mengikat otorisasi node ke bukti perangkat tanpa menghilangkan kemampuan brain
untuk bermigrasi secara sah ke perangkat baru.

## Dependensi

- [Pilar 11 — DNA Anchor](05-p11-dna-anchor.md)
- [Pilar 13 — Cryptographic Skin](09-p13-cryptographic-skin.md)

## Kontrak dan integrasi

```text
Node attestation → node certificate → wrapped brain key → authorized boot
```

Brain identity portabel; node binding dapat di-rewrap melalui handoff owner.

## Checklist implementasi

- [x] Definisikan provider root sebagai adapter; Windows DPAPI machine scope aktif.
- [x] Bedakan stable `brain_id`, `node_id`, dan per-boot `instance_id`.
- [x] Implementasikan enrollment, rewrap, migration, revocation, dan recovery.
- [x] Persistensikan node-binding record yang ditandatangani DNA dan hash-chain.
- [x] Uji cloned DB, wrong node/root, revoked node, migration, restart, dan no-provider.
- [x] Tampilkan `hardware_backed: false`; DPAPI tidak diklaim sebagai TPM.
- [ ] Tambahkan TPM/Secure Enclave attestation pada target deployment.
- [ ] Jalankan migration/recovery drill dan observasi produksi persisten.

## Exit criteria

Salinan liar gagal memperoleh authority, sementara migrasi yang disetujui dapat
membuka brain yang sama pada node baru dan mencatat lineage.

## Bukti saat ini

`NodeBindingAuthority` mengikat secret node ke `brain_id` dan `node_id`, lalu
menurunkan konteks key yang dipakai P13. Launcher menolak boot sebelum enrollment
eksplisit. Auditor dan demo kanonis berada di `scripts/audit_security_envelope.py`
serta `scripts/demo_hardware_binding.py`.

## Larangan

Jangan mengunci data hanya dengan MAC address, hostname, disk serial, atau hash
yang tidak mempunyai root of trust.
