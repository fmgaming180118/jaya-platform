# NVIDIA NIM Language Distillation (Ultra-Light Runtime)

Tujuan: mengajarkan gaya bahasa ke JAYA secara cepat tanpa chat manual berulang.

## Ringkas

- Distilasi berjalan sekali (offline build step).
- Runtime JAYA hanya memuat JSON template kecil.
- Tidak ada inferensi model besar saat shell berjalan normal.

## Cara Cepat (Tanpa Chat Terus)

1. Siapkan file contoh gaya bahasa (seed), bisa JSON atau TXT.
2. Jalankan distilasi sekali dengan NVIDIA NIM.
3. JAYA otomatis memakai hasilnya dari language policy override.

## Jalankan Distilasi

Otomatisasi CLI baru:

python JAYA_CORE/scripts/auto_improve_language_policy_from_nim.py

Tanpa seed file:

python JAYA_CORE/scripts/distill_language_policy_from_nim.py --model meta/llama3-70b-instruct

Dengan seed file (direkomendasikan):

python JAYA_CORE/scripts/distill_language_policy_from_nim.py --model meta/llama3-70b-instruct --seed-file JAYA_CORE/docs/language_distillation_seed.example.json

Output default:

- JAYA_CORE/docs/language_policy_overrides.json

## Cek Aktivasi Di Shell

Jalankan shell:

python JAYA_CORE/scripts/jaya_shell.py --offline

Lalu cek:

- status bahasa

## Format Seed File

Contoh format ada di:

- JAYA_CORE/docs/language_distillation_seed.example.json

Tips:

- Isi contoh sapaan, klarifikasi, no-memory, dan langkah prosedur.
- Gunakan kalimat pendek agar hasil template tetap ringan.
- Hindari data sensitif di seed file.

## Catatan Device RAM Rendah

- Distilasi dilakukan di mesin development yang lebih kuat.
- Device target cukup menerima file language_policy_overrides.json.
- Runtime di device target tetap ringan.
- Pastikan NVIDIA_API_KEY tersedia sebelum distilasi.
