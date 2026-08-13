# JAYA Core

JAYA Core adalah lapisan kognitif: intent, reasoning, planning, memory policy,
Lingua Logica/JayaIR, dan eksekusi. Pengetahuan riset mentah tetap dimiliki
JAYA Research dan hanya masuk melalui artefak yang lolos gate.

**Kematangan:** implemented untuk jalur utama Phase 1; belum dinyatakan
production secara keseluruhan.

Dokumentasi kanonis:

- [Arsitektur dan batas modul](../docs/ARCHITECTURE.md)
- [Status aktual](../docs/STATUS.md)
- [Gerbang promosi](../docs/GOVERNANCE.md)
- [Roadmap](../docs/ROADMAP.md)

## Verifikasi terarah

Dari root repository:

```powershell
python -m pytest JAYA_CORE\tests\test_phase1_jaya_ir.py -q
python JAYA_CORE\scripts\benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate
```

Benchmark hanya sah sebagai bukti jika command, commit, environment, dan output
aktualnya disimpan. JAYA Research tidak boleh menulis source Core secara
langsung.
