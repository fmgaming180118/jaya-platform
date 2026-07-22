# CLI Reference & Fitur Otomatisasi (Autonomous)

Dokumen ini mencatat seluruh **Command Line Interface (CLI)** dan **fitur otomatisasi/autonomous** yang dimiliki oleh JAYA Research untuk menjalankan berbagai engine riset otonom, watchdog launcher, dan pipeline training.

---

## 1. CLI Pengoperasian Utama (Main Launcher CLI)

Proyek ini menyediakan dua cara utama untuk meluncurkan backend dan frontend React.

### A. JAYA Autorun (Watchdog Launcher)
Launcher satu-klik dengan pemantauan otomatis (watchdog), pembebasan port otomatis (jika server lama menggantung), dan tampilan status real-time terpusat.

* **Perintah:**
  ```bash
  # Windows
  JAYA_AUTORUN.bat

  # Manual Python
  python jaya_autorun.py
  ```
* **Fitur Otomatis:**
  - Melacak status backend FastAPI dan frontend Vite secara real-time.
  - Melakukan restart otomatis jika salah satu service crash.
  - Membaca "Conscious Mind" JAYA secara langsung dari data evolusi compiler untuk menampilkan status suasana pikiran model.

### B. OpenJay CLI
CLI minimalis untuk meluncurkan backend API atau dashboard UI secara individual.

* **Perintah:**
  ```bash
  # Menjalankan Backend API
  openjay run
  # (Memicu: python src/network/research_api.py)

  # Menjalankan Dashboard UI
  openjay dashboard
  # (Memicu: npm run dev di folder ui/)
  ```

---

## 2. Fitur & CLI Riset Otomatis (Autonomous Agents)

JAYA Research dirancang dengan engine agen AI yang dapat bekerja secara mandiri tanpa intervensi konstan dari manusia.

### A. Autonomous & Recursive Research Agent
Melakukan pengumpulan paper, ekstraksi data, sintesis, evaluasi, hingga penulisan draf laporan riset akhir secara mandiri.

* **Melalui API:**
  - Single-Pass: `POST /research/autonomous`
  - Deep Recursive: `POST /research/recursive`
* **Alur Kerja Otomatis:**
  - **Plan:** LLM memecah topik riset menjadi sub-pertanyaan ilmiah secara otomatis.
  - **Search:** Mengambil data paralel dari ArXiv, Semantic Scholar, dan vector store internal secara otonom.
  - **Synthesis:** Menggabungkan seluruh data mentah menjadi draf laporan riset komprehensif berformat Markdown.

### B. Research-Guided Digital Twin Evolution
Menjalankan evolusi bahasa pemrograman buatan (`.jaya` spec) dan referensi compiler (`compiler.py`) untuk menemukan optimasi compiler tingkat tinggi di CPU.

* **Perintah:**
  ```bash
  # Evolusi JIT Compiler otonom
  python src/digital_twin_compiler.py --forever
  ```
* **Fitur Otomatis:**
  - **Mutasi Otomatis:** Model Teacher (NVIDIA NIM) melakukan modifikasi grammar bahasa dan kode compiler generasi ke generasi.
  - **Strict Evolution:** Sistem otomatis membandingkan benchmark forward/backward pass runtime. Hasil modifikasi hanya disimpan jika skor efisiensi meningkat secara signifikan dibandingkan generasi terbaik sebelumnya.

### C. Research Twin (Stagnation Research Loop)
Loop tingkat lanjut yang mengawasi jalannya Digital Twin.

* **Perintah:**
  ```bash
  python src/research/research_twin.py
  ```
* **Fitur Otomatis:**
  - **Deteksi Stagnasi:** Jika skor optimasi evolusi compiler tidak meningkat dalam beberapa generasi, sistem mendeteksi "kemandekan riset".
  - **Autonomous Literature Search:** Memulai pencarian paper riset terbaru tentang optimasi compiler di ArXiv + Scholar.
  - **Feedback Loop:** Membaca paper tersebut, mengekstrak teknik optimasi baru, lalu menyuapnya sebagai context panduan ke mutator evolusi compiler berikutnya untuk mendobrak batas optimasi.

---

## 3. CLI Logic Compression & compiler (Edison Loop)

Riset untuk membakar (JIT compile) logika Autograd mentah menjadi instruksi tingkat rendah (LLVM IR via Numba).

```bash
# Terminal 1: Loop Kompresi Logika
python src/discovery.py --forever

# Terminal 2: Loop Kompilasi/Ascension Bahasa
python src/jit_discovery.py --forever
```

---

## 4. CLI Pipeline QLoRA Dataset & Training

CLI untuk melatih model adapter lokal (`LoRA`) menggunakan model teacher eksternal untuk melokalisasi gaya bahasa JAYA.

### A. Build Dataset
```bash
python src/training/build_qlora_dataset_from_ollama.py \
  --model qwen3:4b \
  --variants-per-key 8 \
  --out data/qlora/language_policy_qlora_dataset.jsonl
```

### B. Train QLoRA Adapter
```bash
python src/training/train_qlora_language_adapter.py \
  --base-model Qwen/Qwen3-4B-Instruct-2507 \
  --dataset data/qlora/language_policy_qlora_dataset.jsonl \
  --output-dir data/qlora/adapter-qwen3-4b-language \
  --epochs 2
```

### C. Evaluate Adapter
```bash
python src/training/evaluate_qlora_language_adapter.py \
  --adapter-dir data/qlora/adapter-qwen3-4b-language
```
