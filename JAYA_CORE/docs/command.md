# command.md

Dokumen ini berisi perintah CLI untuk menjalankan JAYA dan memeriksa bahasa secara langsung.

## Perintah COPY-PASTE

### 1. Jalankan JAYA Shell

```bash
python JAYA_CORE/scripts/jaya_shell.py
```

### 2. Jalankan JAYA Shell offline

```bash
python JAYA_CORE/scripts/jaya_shell.py --offline
```

### 3. Tampilkan bantuan shell

```bash
python JAYA_CORE/scripts/jaya_shell.py --help
```

### 4. Validasi JSON policy override

```bash
python -m json.tool JAYA_CORE/docs/language_policy_overrides.json
```

### 5. Tampilkan policy Bahasa Indonesia yang aktif

```bash
python -c "from JAYA_CORE.src.brain_v2.soul.language_policy import get_policy; import json; print(json.dumps(get_policy('id'), indent=2, ensure_ascii=False))"
```

### 6. Jalankan otomatisasi distilasi bahasa dari NVIDIA NIM

```bash
python JAYA_CORE/scripts/auto_improve_language_policy_from_nim.py
```

Jika ingin pakai seed contoh dan model tertentu:

```bash
python JAYA_CORE/scripts/auto_improve_language_policy_from_nim.py --model meta/llama3-70b-instruct --seed-file JAYA_CORE/docs/language_distillation_seed.example.json --rounds 2
```

### 7. Tampilkan status IntentEngine

```bash
python -c "from JAYA_CORE.src.brain_v2.engine.intent_engine import IntentEngine; print(IntentEngine().status())"
```

### 8. Periksa apakah file override policy valid dan bisa dibuka

```bash
python -c "from pathlib import Path; p=Path('JAYA_CORE/docs/language_policy_overrides.json'); print(p.exists(), 'size=', p.stat().st_size)"
```

### 8. Buka file override policy di editor (Windows PowerShell)

```powershell
notepad JAYA_CORE/docs/language_policy_overrides.json
```

## Optimasi bahasa Indonesia tanpa training model besar

- `JAYA_CORE/docs/language_policy_overrides.json` adalah tempat utama untuk memperbaiki gaya bahasa Indonesia.
- Ubah frasa `greeting`, `clarify`, `no_memory`, `segment_*`, dan `portable` agar JAYA terdengar lebih natural.
- Setelah file diperbarui, jalankan ulang `python JAYA_CORE/scripts/jaya_shell.py`.

## Otomatisasi yang sudah berjalan

- `IntentEngine` menyimpan pola komando lokal secara otomatis.
- Semakin sering Anda berinteraksi, semakin baik JAYA mengenali gaya dan perintah Anda.
- Tidak perlu terus menambah frasa manual jika input pengguna sudah konsisten.
