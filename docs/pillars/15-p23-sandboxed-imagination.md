# 15 — Pembangunan Pilar 23: Sandboxed Imagination

- **ID pilar:** 23
- **Tahap:** 4 — Rangka mesin
- **Status saat audit:** PROTOTYPE
- **Pemilik:** SECURITY, RUNTIME

## Tujuan

Memungkinkan JAYA mencoba kode, tool, simulasi, atau rencana secara terisolasi
tanpa memberi akses langsung ke host, secret, network, atau data pemilik.

## Dependensi

- [Pilar 15 — Ethical Heart](06-p15-ethical-heart.md)
- [Pilar 18 — Zero Trust](08-p18-zero-trust.md)
- [Pilar 20 — Sovereign Privacy](07-p20-sovereign-privacy.md)
- [Pilar 21 — Lingua Logica](02-p21-lingua-logica.md)

## Kontrak dan integrasi

```text
Execution request → policy → sandbox → validated artifact/receipt → Core
```

## Checklist implementasi

- [ ] Allowlist executable, filesystem mount, network, env, dan syscall.
- [ ] Terapkan timeout, CPU/RAM/disk quota, cancellation, dan output limit.
- [ ] Isolasi working directory serta redaksi secret.
- [ ] Validasi artifact sebelum keluar dari sandbox.
- [ ] Uji escape, fork bomb, symlink, network denial, timeout, dan disk full.
- [ ] Demo menjalankan tool nyata dan menunjukkan failure path.

## Exit criteria

Eksekusi produksi tidak dapat mengakses resource di luar grant, dapat dibatalkan,
dan selalu menghasilkan audit receipt terstruktur.

## Larangan

`subprocess` terhadap input mentah atau Docker tanpa policy bukan sandbox aman.
