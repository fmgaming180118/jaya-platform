# JAYA_SOVEREIGN V18 — Arsitektur & Changelog

**Status**: COMPLETE ✅  
**Tanggal**: 2025  
**Tests**: 25/25 V18 | 83/86 total (2 gagal = pre-existing speaker_id, tidak terkait V18)

---

## Ringkasan Upgrade V18

V18 berfokus pada tiga tujuan utama:
1. **Ultra-light RAM** — model berjalan di bawah 1 MB raw, < 100 KB packed
2. **Self-evolution** — otak bisa berkembang sendiri tanpa input eksternal
3. **Device portability** — file `.jay` dapat dipindahkan dan re-bind ke hardware baru

---

## Arsitektur Baru

### 1. NanoModel (`src/brain_v2/model/nano_inference.py`)
Model inferensi murni NumPy — tanpa Numba, tanpa `.pyd`.

| Parameter    | Nilai         |
|-------------|---------------|
| d_model     | 64            |
| n_layers    | 2             |
| n_heads     | 4             |
| vocab_size  | 512           |
| RAM raw     | ~160 KB       |
| RAM packed  | ~40 KB (74.7% kompresi) |

**API utama:**
```python
model = NanoModel(NANO_CONFIG)
model.random_init()          # inisialisasi acak (unseeded)
logits = model.forward([1, 2, 3])  # shape: (seq_len, vocab_size)
tok = model.predict_token([1, 2, 3])  # int
bufs = model.get_weight_buffers()    # list[(key, ndarray)]
model.set_weight(key, array)
```

---

### 2. Packer 2-bit Ternary (`src/brain_v2/format/packer.py`)
Kompresi bobot `{-1, 0, +1}` ke 2 bit per nilai (4 nilai/byte).

```
Kode: 0b00 = -1, 0b01 = 0, 0b10 = +1
```

**API:**
```python
packed = pack_ternary(arr)        # ndarray → bytes
restored = unpack_ternary(packed, n)  # bytes, n → ndarray
state = pack_state_dict(buf_list)     # list[(k,arr)] → dict
buf_list = unpack_state_dict(state)   # dict → list[(k,arr)]
```

---

### 3. Live Evolver (`src/brain_v2/education/live_evolver.py`)
Algoritma (1+1)-ES: mutasi→evaluasi→terima/tolak secara online.

**Konfigurasi:**
```yaml
mutation_std: 0.05
eval_steps: 10
max_steps: 200
```

**API:**
```python
evolver = LiveEvolver(engine=runtime_instance)
result = evolver.run_evolution(steps=50)
# → {steps, accepted, delta_fitness, improved, duration_s}
```

Persists bobot terbaik ke section `IRON_BODY_PACKED` di file `.jay`.

---

### 4. Meta-Cognitive Planner (`src/brain_v2/engine/meta_cognitive.py`)
Pilar 38 — observasi dan perbaikan mandiri berbasis performa task.

```python
planner = MetaCognitivePlanner(
    reflect_interval=600,    # detik
    weak_threshold=0.45,
    watch_window=300,        # record terakhir untuk dianalisis
)
planner.tick(twin)           # panggil setiap siklus
planner.reflect(twin)        # trigger manual
```

Saat menemukan task dengan score < `weak_threshold`, planner:
- Patch melalui `MorphicKernel` jika tersedia
- Atau antri task `LiveEvolver` ke twin
- Template aksi: SEARCH→BM25, GREET→varied, QUERY_HOW→step-by-step

---

### 5. Self Bootstrap (`src/brain_v2/engine/self_bootstrap.py`)
Pilar 28 — kurikulum belajar mandiri saat idle.

```python
bootstrap = SelfBootstrap()
bootstrap.tick(twin)             # panggil setiap siklus
bootstrap.signal_activity()     # beri tahu sistem sedang aktif
```

Saat idle > threshold, auto-generate kurikulum dan antri task latihan.

---

### 6. Lingua Logica V18 (`src/brain_v2/soul/lingua_logica.py`)
Diperluas dari 17 → 200+ pola. Dukungan Bahasa Indonesia penuh.

**70+ aksi Bahasa Indonesia:** cari, hapus, buka, simpan, buat, kirim, hitung, terjemahkan, analisis, download, perbarui, dan lainnya.

**25+ query Bahasa Indonesia:** apa, bagaimana, siapa, kapan, di mana, kenapa, berapa, jelaskan.

Cache LRU 512 entries.

```python
ll = LinguaLogica()
expr = ll.encode("cari data penjualan")
# → ("ACTION", "SEARCH", "data penjualan")

expr = ll.encode("apa itu machine learning")
# → ("QUERY", "WHAT", "machine learning")
```

---

### 7. Intent Engine TF-IDF (`src/brain_v2/engine/intent_engine.py`)
Lapisan TF-IDF ditambahkan di atas n-gram.

**Skor gabungan:** `0.6 × ngram + 0.4 × tfidf`

```python
engine = IntentEngine()
engine.predict_intent("cari file dokumen")
status = engine.status()
# → includes "tfidf_docs": int
```

---

### 8. Legacy Protocol Migrate (`src/brain_v2/engine/legacy_protocol.py`)
Re-binding hardware UUID saat pemindahan perangkat.

```python
lp = LegacyProtocol(jay_path)
ok = lp.migrate(new_path, dst_hw_uuid="UUID-BARU-DEVICE")
```

Proses:
1. Copy file `.jay` ke lokasi baru
2. Patch header `hw_hash` + `dna_hash` dengan UUID tujuan
3. Re-enkripsi section SOUL dengan AES-GCM (jika `cryptography` tersedia)
4. Tambah UUID ke approved list

---

## Flags V18 di Format `.jay`

| Flag                | Bit   | Nilai Hex        |
|--------------------|-------|------------------|
| PACKED_WEIGHTS      | 42    | `0x400000000000` |
| NANO_PROFILE        | 43    | `0x800000000000` |
| SELF_EVOLVING       | 44    | `0x1000000000000` |

Total flags V18: `0x00001CFFFFFFFFFF` (semua 40 pilar + 3 flag baru)

---

## File `.jay` V18

| Property          | Nilai      |
|-------------------|-----------|
| File total        | ~52 KB    |
| Bobot packed      | ~40 KB    |
| Kompresi          | 74.7%     |
| Format            | JAYA_SOVEREIGN_V18.jay |
| Section baru      | `IRON_BODY_PACKED` (type 6), `LONG_TERM_MEMORY` (type 7) |

---

## Scripts

```bash
# Forge ulang V18.jay dari scratch
python scripts/forge_v18.py

# Atau dengan output custom
python scripts/forge_v18.py --out /path/ke/output.jay
```

---

## Test Coverage

```
tests/test_v18_nano.py — 25 tests
  TestPackUnpack         (5)  — packer 2-bit roundtrip
  TestNanoModelForward   (4)  — inferensi NanoModel
  TestNanoRam            (2)  — verifikasi ukuran RAM
  TestLiveEvolver        (2)  — evolusi (1+1)-ES
  TestMetaCognitive      (2)  — refleksi mandiri
  TestWeightPersistence  (2)  — simpan/load bobot
  TestMigrate            (3)  — legacy migrate re-bind
  TestLinguaBahasa       (1)  — 20 frasa Bahasa Indonesia
  TestIntentEngineTFIDF  (2)  — TF-IDF learn + predict
  TestForgeV18           (2)  — forge script end-to-end
```

**Hasil**: 25/25 ✅

---

## Runtime Integration

```python
# runtime.py (IronEngine.__init__)
self.NANO_MODE = False
self._nano_model = None          # NanoModel instance
self._meta_cognitive = None      # MetaCognitivePlanner
self._self_bootstrap = None      # SelfBootstrap
self._live_evolver = None        # LiveEvolver

# Auto-load dari .jay jika flag PACKED_WEIGHTS aktif
self._try_load_nano_model()

# Magnum cycle (tiap detik)
self._meta_cognitive.tick(twin)
self._self_bootstrap.tick(twin)
```

---

## Kompatibilitas

- Python 3.12+
- Dependensi: `numpy` saja (no Numba, no .pyd)
- Optional: `cryptography` (untuk AES-GCM re-encryption di migrate)
- Backward compatible: semua 40 pilar V17 tetap berfungsi
