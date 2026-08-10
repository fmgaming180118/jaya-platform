# 01 — Pembangunan Pilar 1: Pure Logic

- **ID pilar:** 1
- **Tahap:** 1 — Pondasi
- **Status saat audit:** VERIFIED (95%)
- **Pemilik:** MODEL

## Tujuan

Menyediakan mesin inferensi deterministik untuk fakta, aturan, kontradiksi, dan
ketidakpastian. Pilar ini menjadi pondasi agar keputusan JAYA dapat dijelaskan
dan tidak bergantung pada keluaran model bahasa saja.

## Dependensi

Tidak ada pilar sebelumnya. Dependency teknis harus berupa parser aturan,
representasi fakta, dan solver nyata yang dipilih melalui konfigurasi.

## Kontrak dan integrasi

```text
Fakta + aturan tervalidasi → LogicService → solver → kesimpulan + proof trace
```

Output wajib membedakan `PROVED`, `DISPROVED`, `UNKNOWN`, dan `CONFLICT`.
Proof trace harus persisten bila dipakai oleh keputusan atau penelitian.

## Checklist implementasi

- [x] Tetapkan schema fakta, aturan, query, proof, dan contradiction report.
- [x] Integrasikan minimal satu solver production dan health check-nya.
- [x] Hubungkan LogicService ke JayaIR sebagai puzzle Core tanpa opcode palsu.
- [x] Batasi ukuran teori, waktu solver, RSS proses, dan iterasi inferensi.
- [x] Uji fakta salah, konflik, timeout, input besar, dan resource tidak cukup.
- [x] Demo membuktikan hasil dari solver, bukan jawaban statis.

Seluruh gate implementasi lokal telah lulus. Lima persen terakhir adalah bukti
observasi deployment berkelanjutan; detail terukur berada di
[dashboard Pondasi Logika](../LOGICAL_FOUNDATION_PROGRESS.md).

## Exit criteria

Minimal dua variasi teori dapat dibuktikan, kontradiksi terdeteksi, restart tidak
menghilangkan proof penting, dan [Pilar 21](02-p21-lingua-logica.md) dapat
mengonsumsi kontrak logika ini.

## Larangan

Jangan menyebut prompt LLM, pencocokan string, atau `if input == contoh` sebagai
Pure Logic.
