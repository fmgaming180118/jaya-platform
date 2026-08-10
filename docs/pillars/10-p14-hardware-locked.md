# 10 — Pembangunan Pilar 14: Hardware Locked

- **ID pilar:** 14
- **Tahap:** 3 — Selubung keamanan
- **Status saat audit:** PROTOTYPE
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

- [ ] Definisikan provider TPM/Secure Enclave/OS keystore sebagai optional adapter.
- [ ] Bedakan stable `brain_id`, `node_id`, dan per-boot `instance_id`.
- [ ] Implementasikan enrollment, rewrap, migration, revocation, dan recovery.
- [ ] Simpan signed node-binding record di brain capsule.
- [ ] Uji cloned disk, replaced hardware, revoked node, migration, dan no-TPM.
- [ ] Tampilkan `UNKNOWN/UNAVAILABLE`, bukan hardware fingerprint buatan.

## Exit criteria

Salinan liar gagal memperoleh authority, sementara migrasi yang disetujui dapat
membuka brain yang sama pada node baru dan mencatat lineage.

## Larangan

Jangan mengunci data hanya dengan MAC address, hostname, disk serial, atau hash
yang tidak mempunyai root of trust.
