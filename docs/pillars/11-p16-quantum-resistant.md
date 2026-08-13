# 11 — Pembangunan Pilar 16: Quantum Resistant

- **ID pilar:** 16
- **Tahap:** 3 — Selubung keamanan
- **Status saat audit:** VERIFIED — 95%
- **Pemilik:** SECURITY, RUNTIME

## Tujuan

Menyediakan crypto agility dan jalur migrasi post-quantum untuk signature serta
key establishment tanpa membuat klaim keamanan yang belum diverifikasi.

## Dependensi

- [Pilar 13 — Cryptographic Skin](09-p13-cryptographic-skin.md)
- [Pilar 18 — Zero Trust](08-p18-zero-trust.md)

## Kontrak dan integrasi

```text
Algorithm policy → classical/PQ or hybrid suite → versioned signed envelope
```

## Checklist implementasi

- [x] Tetapkan threat horizon, asset lifetime, dan algorithm-agility contract.
- [x] Sediakan adapter `liboqs` ML-DSA-65 yang gagal tertutup bila unavailable.
- [x] Dukung hybrid migration serta downgrade protection pada kontrak.
- [x] Ukur ukuran key/signature, latency, dan compatibility pada node audit.
- [x] Uji unsupported algorithm, invalid signature, dan downgrade.
- [x] Implementasikan keystore persisten, rotation lineage, revocation, restart,
  dan verifikasi artifact lama.
- [x] Integrasikan ML-DSA-65 nyata ke capsule P13, termasuk puzzle pack.
- [ ] Minta security review sebelum menaikkan status `VERIFIED`.

## Exit criteria

Brain capsule dan puzzle pack dapat diverifikasi dengan suite versioned, tidak
menerima downgrade, dan mempunyai prosedur rotasi yang diuji.

## Larangan

Nama algoritma, dependency opsional, atau key random tanpa integrasi tidak boleh
disebut quantum resistant.

## Batas bukti

Ed25519 lama tetap dilabeli `ED25519_CLASSICAL_NOT_PQ` dan
`quantum_resistant=false`. Audit memakai `liboqs-python`/`liboqs` 0.16.0 dengan
ML-DSA-65 nyata; private key disegel P13 di SQLite, rotation/restart/revocation
serta capsule hybrid diuji. Lima persen tersisa adalah security review
independen dan observasi deployment; tidak ada fallback palsu.
