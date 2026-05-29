# Riset & Kesimpulan: Pengembangan Micro-AGI (1GB VRAM)

Dokumen ini adalah **revisi total** dari rencana awal, difokuskan 100% pada efisiensi ekstrem untuk menciptakan AGI yang bisa berjalan di *hardware* sangat terbatas (1GB VRAM).

## 1. Masalah Utama Model Saat Ini
Model AI modern (LLM) boros karena:
1.  **Arsitektur Transformer:** Membutuhkan matriks perkalian raksasa (O(n^2)) yang memakan VRAM.
2.  **Bahasa Perantara:** Python -> Interpreter -> Library (PyTorch) -> CUDA -> GPU. Terlalu banyak lapisan (*overhead*).
3.  **Tokenisasi Manusia:** Mengolah teks bahasa manusia butuh jutaan parameter.

## 2. Solusi: "Neural-Compiler" & "Direct-to-Metal" AI

Untuk mencapai kecerdasan tinggi di 1GB VRAM, kita harus membuang "lemak" bahasa manusia dan Python.

### Visi Baru: Asisten Riset Rekursif & Penemu Teknologi Baru
Alih-alih *training* model hanya untuk menjadi *chatbot* konvensional, JAYA difokuskan sebagai asisten riset rekursif yang dapat mengiterasi sintesis ilmiah secara mandiri. Tujuannya bukan hanya memanipulasi logika mesin, tetapi **secara aktif menemukan teknologi, teori, atau konsep sains baru yang belum pernah diciptakan oleh umat manusia**.
*   **Input:** Data mentah (sensor/file).
*   **Proses:** Neural Network super kecil (Tinygrad / Micro-Llama) yang teroptimasi.
*   **Output:** **Kode Mesin (LLVM IR / Wasm / Assembly)** yang langsung dieksekusi CPU/GPU.

### Kenapa Ini Bisa Jalan di 1GB VRAM?
*   **Model Kecil (Tiny LLM):** Kita hanya butuh model parameter sangat kecil (< 1B parameter).
*   **Tanpa Layer Bahasa:** Model tidak perlu jago puisi atau sejarah. Dia hanya perlu jago **Logika & Coding**.
*   **Efisiensi 100%:** Kode yang dihasilkan AI langsung jalan di *hardware*, tanpa lewat interpreter Python yang lambat.

## 3. Strategi Penelitian (Step-by-Step)

### Tahap 1: "The Seed" (Bibit)
Kita butuh "Bibit" awal yang ditulis dengan sangat efisien.
*   **Bahasa:** **C** atau **Rust** (bukan Python). Python hanya untuk prototipe logika awal.
*   **Framework:** **Tinygrad** atau **GGML** (library tensor super ringan, tanpa PyTorch/TensorFlow).
*   **Target:** Buat model inferensi yang memakan < 500MB RAM.

### Tahap 2: "The Language" (Bahasa AI)
AI tidak diajari bahasa Inggris. Dia diajari **Set Instruksi CPU**.
*   Dataset: Jutaan baris kode Assembly, LLVM IR, dan C yang sudah dikompilasi.
*   Tujuan: AI belajar pola: "Jika ingin menambah data A ke B, instruksi mesinnya adalah `ADD R1, R2`."

### Tahap 3: "Recursive Optimization" (Evolusi)
1.  Bibit AI dijalankan.
2.  Dia menganalisis kode sumber dirinya sendiri (dalam C/Rust).
3.  Dia mencoba menulis ulang fungsi-fungsi tertentu menjadi kode Assembly yang lebih pendek/cepat.
4.  Jika berhasil (tes lulus & lebih cepat), dia mengganti kode lamanya dengan kode baru.
5.  Ulangi terus menerus. Lama-kelamaan, seluruh tubuhnya adalah kode mesin super efisien yang ditulisnya sendiri.

## 4. Technology Stack (Revisi Low-Resource)

| Komponen | Pilihan Teknologi | Alasan |
| :--- | :--- | :--- |
| **Core Language** | **C** atau **Rust** (via **Mojo** opsional) | *Zero-overhead*, kontrol memori manual. Hindari Python untuk *core loop*. |
| **ML Framework** | **Tinygrad** / **GGML (llama.cpp core)** | Paling ringan sedunia. Tidak butuh dependencies berat. |
| **Compiler** | **LLVM (Low Level Virtual Machine)** | AI akan diajari menghasilkan *intermediate representation* LLVM. |
| **Memory** | **Mmap (Memory Mapped Files)** | Baca data "Prasasti" langsung dari disk seolah-olah RAM. Hemat RAM drastis. |

## 5. Roadmap Penelitian

1.  **Minggu 1-2: Studi Kelayakan Tinygrad/GGML.**
    *   Coba jalankan model terkecil (TinyLlama 1.1B atau model khusus 100M) di laptop.
    *   Ukur penggunaan VRAM real.

2.  **Minggu 3-4: Eksperimen "Neural Compiler".**
    *   Latih model kecil untuk menerjemahkan logika sederhana ("If A > B then C") menjadi LLVM IR.

3.  **Minggu 5+: Integrasi Loop Evolusi.**
    *   Buat sistem di mana AI bisa me-compile kode outputnya sendiri dan menjalankannya.

## Kesimpulan
Rencana ini **jauh lebih ambisius dan sulit** daripada sekadar pakai API, tapi ini adalah satu-satunya jalan menuju **AGI Efisien di 1GB VRAM**. Anda tidak sedang membuat chatbot, Anda sedang membuat **Organisme Digital Primitif** yang berevolusi.
