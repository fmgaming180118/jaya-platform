# Digital Twin — Language Evolution & Compiler Research

## Konsep

Digital Twin adalah modul eksperimental yang mensimulasikan evolusi bahasa pemrograman dan compiler.

AI berperan sebagai:
1. **Language Architect** — merancang syntax baru (`.jaya` spec)
2. **Compiler Engineer** — menulis compiler untuk syntax tersebut
3. **Evaluator** — mengukur efisiensi, hanya simpan jika lebih baik dari generasi sebelumnya

Tujuan akhir: menemukan bahasa yang mendekati batas teoritis efisiensi hardware — kemudian "diajarkan" ke model AI lewat fine-tuning.

---

## Menjalankan Evolution Loop

```bash
# 5 generasi (default)
python src/digital_twin_compiler.py

# Loop terus-menerus sampai dihentikan manual
python src/digital_twin_compiler.py --forever

# Loop terbatas dengan kondisi stop
python src/digital_twin_compiler.py --max-gen 20 --target-score 0.95
```

**Aturan evolusi:**
- Versi baru hanya disimpan jika Optimization Score > versi terbaik sebelumnya
- Setiap generasi menghasilkan: `.jaya` spec + `compiler.py` + score report

---

## Menghasilkan Dataset Fine-Tuning

Setelah evolusi, "bekukan" bahasa terbaik ke dalam dataset training:

```bash
python src/generate_training_data.py
```

Output: `data/finetune_dataset.jsonl` — bisa diupload ke Unsloth, TogetherAI, atau fine-tuning platform lain.

---

## Artefak yang Dihasilkan

Semua output disimpan di `data/language_evolution/` (dikecualikan dari git):

| File | Deskripsi |
|---|---|
| `jaya_vX_TIMESTAMP.spec` | Grammar/syntax specification generasi X |
| `compiler_vX_TIMESTAMP.py` | Reference compiler untuk generasi X |
| `evolution_log.json` | Riwayat semua generasi + score |

---

## Research Twin (Gabungan Research + Evolution)

`research_twin.py` menggabungkan autonomous research dengan evolution loop:

```bash
python src/research/research_twin.py
```

**Alur:**
1. Jalankan evolution loop normal
2. Jika skor stagnan (tidak ada perbaikan dalam N generasi) → **trigger research**
3. JAYA mencari teknik optimasi compiler terbaru di ArXiv + Scholar
4. Temuan dimasukkan sebagai context ke mutasi generasi berikutnya
5. Lanjutkan evolution

Ini menciptakan loop: *Evolve → Stagnate → Research → Innovate → Evolve*

---

## Catatan Teknis

- Evolution berjalan di CPU — tidak butuh GPU
- Setiap generasi membutuhkan 1–3 API call ke NIM (Teacher model)
- Token budget: ~8000 token per generasi (bisa disesuaikan)
- Progress disimpan ke `data/evolution/` — aman jika proses terhenti

---

> [!NOTE]
> Digital Twin adalah riset eksploratori — bukan fitur produksi. Jangan integrasikan langsung ke backend utama tanpa validasi menyeluruh.
