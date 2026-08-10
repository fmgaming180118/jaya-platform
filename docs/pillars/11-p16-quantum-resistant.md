# 11 — Pembangunan Pilar 16: Quantum Resistant

- **ID pilar:** 16
- **Tahap:** 3 — Selubung keamanan
- **Status saat audit:** NOT_IMPLEMENTED
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

- [ ] Tetapkan threat horizon, asset lifetime, dan algorithm-agility contract.
- [ ] Pilih implementasi standar dari provider terawat dan catat versinya.
- [ ] Dukung hybrid migration serta downgrade protection.
- [ ] Ukur ukuran key/signature, latency, RAM, dan compatibility.
- [ ] Uji unsupported algorithm, invalid signature, rotation, dan old artifact.
- [ ] Minta security review sebelum menaikkan status `VERIFIED`.

## Exit criteria

Brain capsule dan puzzle pack dapat diverifikasi dengan suite versioned, tidak
menerima downgrade, dan mempunyai prosedur rotasi yang diuji.

## Larangan

Nama algoritma, dependency opsional, atau key random tanpa integrasi tidak boleh
disebut quantum resistant.
