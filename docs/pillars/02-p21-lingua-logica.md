# 02 — Pembangunan Pilar 21: Lingua Logica

- **ID pilar:** 21
- **Tahap:** 1 — Pondasi
- **Status saat audit:** VERIFIED (95%)
- **Pemilik:** MODEL

## Tujuan

Menerjemahkan bahasa alami menjadi representasi formal yang immutable,
tervalidasi, dan dapat dieksekusi secara aman melalui JayaIR.

## Dependensi

- [Pilar 1 — Pure Logic](01-p01-pure-logic.md)

## Kontrak dan integrasi

```text
Teks → intent/schema validation → Lingua Logica → JayaIR Core
→ registry puzzle → capability atau failure code
```

JayaIR schema, validator, integrity, control flow, permission, dan discovery
tetap berada di Core. Model/domain/provider menjadi puzzle opsional dengan
manifest dan digest artefak. Agent/OS tidak menjadi dependency wajib.

## Checklist implementasi

- [x] Bekukan versi grammar, AST, JayaIR, dan aturan kompatibilitas.
- [x] Tolak unknown opcode/field dan payload melebihi batas.
- [x] Ganti `CALL_STUB` dengan typed `CALL_CAPABILITY` yang fail-closed.
- [x] Sediakan permission gate, health check, timeout, dan receipt di Core.
- [x] Uji malformed graph, capability hilang, izin ditolak, dan artefak rusak.
- [x] Demo/test menjalankan puzzle eksternal nyata end-to-end.
- [ ] Buktikan telemetry capability pada deployment yang hidup berkelanjutan.

## Exit criteria

Pilar telah `VERIFIED` karena teks menghasilkan JayaIR valid, melewati
permission Core, menjalankan puzzle nyata, dan mengembalikan audit receipt.
`PRODUCTION` memerlukan observasi deployment berkelanjutan.

## Larangan

Descriptor seperti `{action: open}` bukan bukti aksi telah dijalankan.

Pure Logic kini dikonsumsi sebagai puzzle bawaan `core.logic.evaluate` melalui
`CALL_CAPABILITY`. Puzzle eksternal ditemukan otomatis dari direktori tepercaya;
lihat [dashboard Pondasi Logika](../LOGICAL_FOUNDATION_PROGRESS.md).
