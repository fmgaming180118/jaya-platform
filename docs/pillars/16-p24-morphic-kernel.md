# 16 — Pembangunan Pilar 24: Morphic Kernel

- **ID pilar:** 24
- **Tahap:** 4 — Rangka mesin
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Memasang perubahan runtime secara transaksional dengan manifest, approval,
canary, rollback, dan compatibility gate; bukan self-modification liar.

## Dependensi

- [Pilar 12 — Immune System](12-p12-immune-system.md)
- [Pilar 15 — Ethical Heart](06-p15-ethical-heart.md)
- [Pilar 23 — Sandboxed Imagination](15-p23-sandboxed-imagination.md)

## Kontrak dan integrasi

```text
Signed candidate → verify → stage → canary → promote/rollback → audit ledger
```

## Checklist implementasi

- [ ] Definisikan immutable manifest, compatibility, approval, dan restore digest.
- [ ] Gunakan staging terisolasi dan atomic install.
- [ ] Wajibkan test serta benchmark yang terikat commit dan nonce.
- [ ] Implementasikan canary nyata, health observation, dan automatic rollback.
- [ ] Uji replay, revoked approval, crash mid-install, disk full, dan bad canary.
- [ ] Demo instalasi serta rollback artifact produksi.

## Exit criteria

Candidate yang gagal tidak memutasi Core aktif, restart aman setelah kegagalan,
dan seluruh keputusan promotion dapat direproduksi dari evidence ledger.

## Larangan

Menyalin file atau mengubah source langsung lalu menulis `success` bukan Morphic
Kernel.
