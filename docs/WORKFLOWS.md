# Alur Sistem JAYA

Dokumen ini mendefinisikan alur operasional. Kondisi implementasi aktual tetap
merujuk ke [STATUS.md](STATUS.md), sedangkan urutan pengerjaan merujuk ke
[ROADMAP.md](ROADMAP.md).

---

## 1. Alur Utama — Cognitive Evolution Pipeline

**Ini adalah workflow inti JAYA Research sebagai Cognitive Evolution Laboratory.**

Seluruh fitur lain adalah sub-proses atau domain adapter dari pipeline ini.

```mermaid
flowchart TD
    GAP["Cognitive gap atau kebutuhan JAYA"] --> ACQUIRE["Evidence acquisition\n(sumber, jurnal, dataset)"]
    ACQUIRE --> PROVENANCE["Validasi provenance,\nlisensi, kualitas, konflik"]
    PROVENANCE --> SYNTHESIS["Sintesis & pembentukan\nhipotesis terukur"]
    SYNTHESIS --> EXPERIMENT["Desain eksperimen\n+ acceptance criteria"]
    EXPERIMENT --> SAFETYGATE{Safety &\nresource gate}
    SAFETYGATE -->|gagal| REJECT_EXP["Ditolak + alasan"]
    SAFETYGATE -->|lulus| EXECUTE["Eksekusi terisolasi\n(seed, config, env)"]
    EXECUTE --> ANALYSIS["Analisis hasil\n+ uncertainty"]
    ANALYSIS --> REPRO{Reproduksi\nindependen}
    REPRO -->|gagal| REVISE["Revisi hipotesis"]
    REVISE --> EXPERIMENT
    REPRO -->|lulus| ARTIFACT["Candidate Cognitive Artifact\n(status: CANDIDATE, executable: false)"]
    ARTIFACT --> VALIDATE["Schema, hash, provenance,\nlicense, security validation"]
    VALIDATE --> BENCHMARK["Benchmark terhadap\nbaseline aktif"]
    BENCHMARK --> HUMAN["Persetujuan manusia\n(human_review_required: true)"]
    HUMAN -->|ditolak| REJECTED["REJECTED — dengan alasan"]
    HUMAN -->|disetujui| CANARY["Canary installation\n(via adapter publik modul)"]
    CANARY --> OBSERVE["Observasi regresi"]
    OBSERVE -->|regresi| ROLLBACK["Rollback"]
    OBSERVE -->|aman| PROMOTE["Promote ke Core"]
```

Aturan:
- Tidak ada tahap yang boleh dilewati.
- Simulasi tidak boleh dipromosikan.
- Output LLM bukan evidence.
- Human approval wajib ada sebelum canary.

---

## 2. Ingestion dan RAG

1. Pengguna mengunggah atau menautkan sumber.
2. Sistem memvalidasi izin, ukuran, tipe, checksum, dan duplikasi.
3. Parser mengekstrak teks serta struktur sambil menyimpan provenance.
4. Teks dinormalisasi, di-chunk, dan diperkaya metadata.
5. Embedding/index dan relasi graph diperbarui secara atomik.
6. Query pengguna diubah menjadi rencana retrieval.
7. Candidate diambil, direrank, lalu difilter berdasarkan relevansi.
8. Model menyusun jawaban hanya dari konteks yang dapat ditelusuri.
9. Respons menyertakan citation, confidence, dan peringatan jika bukti kurang.
10. Feedback masuk ke evaluasi; bukan langsung menjadi kebenaran baru.

Kondisi gagal harus membedakan kesalahan input, parsing, provider, quota,
retrieval kosong, dan internal error. Data parsial tidak boleh ditandai berhasil.

---

## 3. Deep/Recursive Research

1. Ubah pertanyaan menjadi scope, sub-pertanyaan, dan kriteria selesai.
2. Bentuk rencana pencarian dengan batas waktu, sumber, dan jumlah iterasi.
3. Cari sumber, deduplikasi, dan nilai kualitasnya.
4. Ekstrak bukti pro/kontra dan catat ketidakpastian.
5. Identifikasi gap; lakukan iterasi baru hanya jika memberi informasi tambahan.
6. Hentikan ketika kriteria tercapai, budget habis, atau pengguna membatalkan.
7. Susun sintesis, daftar sumber, konflik bukti, dan pertanyaan terbuka.

Recursive research tidak berarti loop tanpa batas. Setiap run memiliki budget,
timeout, indikator progres, dan *kill switch*.

---

## 4. Promosi Kemampuan ke Ekosistem

Promosi selalu berupa artefak, bukan penulisan source lintas modul:

1. Research menghasilkan paket artefak versioned.
2. Validator memeriksa schema, hash, provenance, license, dan kelengkapan.
3. Sandbox memasang artefak pada kandidat environment yang terisolasi.
4. Test aktual dijalankan; hasil tidak boleh berupa flag buatan.
5. Benchmark sebelum/sesudah dijalankan pada dataset tetap.
6. Security review menilai akses, data leak, supply chain, dan rollback.
7. Maintainer meninjau bukti dan menyetujui atau menolak.
8. Artefak ditandatangani lalu dipasang melalui adapter publik modul tujuan.
9. Observability memantau regresi; pelanggaran gate memicu rollback.

Tidak ada jalur cepat yang melewati persetujuan manusia untuk perubahan Core,
policy OS, izin Agent, atau distribusi Android.

---

## 5. Alur Pengguna — Pilih Pekerjaan

```mermaid
flowchart TD
    START["Buat / pilih workspace"] --> INPUT["Tambahkan sumber atau pertanyaan"]
    INPUT --> MODE{"Pilih pekerjaan"}
    MODE -->|Chat| RAG["Retrieval + jawaban bercitation"]
    MODE -->|Deep research| DEEP["Rencana pencarian bertahap"]
    MODE -->|Discovery| DISC["Hipotesis + eksperimen"]
    MODE -->|Domain Adapter| ADAPTER["Pilih adapter (thesis, academic, dll.)"]
    RAG --> REVIEW["Tinjau sumber, confidence, dan batasan"]
    DEEP --> REVIEW
    DISC --> REVIEW
    ADAPTER --> REVIEW
    REVIEW --> EXPORT["Simpan / ekspor artefak"]
```

Setiap pekerjaan memiliki `job_id`, state, progress, timestamp, error yang dapat
ditindaklanjuti, dan tautan ke artefak. Target state machine:

```text
QUEUED -> RUNNING -> WAITING_REVIEW -> SUCCEEDED
                    \-> FAILED
QUEUED/RUNNING/WAITING_REVIEW -> CANCELED
FAILED -> RETRYING -> RUNNING
```

Pekerjaan panjang harus persisten dan idempotent. Restart API tidak boleh
menghapus sesi atau membuat artefak ganda.

---

## 6. Domain Adapter: Thesis Analysis

Analisis tesis adalah domain adapter opsional — bukan workflow utama JAYA.
Fitur ini dapat dinonaktifkan tanpa menghentikan fungsi Research Core.

```mermaid
flowchart LR
    PDF["PDF tesis"] --> EXTRACT["Ekstraksi teks + metadata"]
    EXTRACT --> TOPIC["Topik, tujuan, metode, kontribusi"]
    TOPIC --> LIT["Pencarian literatur pembanding"]
    LIT --> NOV["Novelty dan gap"]
    TOPIC --> CRIT["Review metodologi dan argumen"]
    NOV --> DEF["Pertanyaan sidang"]
    CRIT --> DEF
    NOV --> REV["Saran revisi"]
    CRIT --> REV
    DEF --> REPORT["Laporan bercitation"]
    REV --> REPORT
```

Aturan kualitas adapter thesis:

- Bedakan kutipan dari sumber, inferensi model, dan saran.
- Jangan menyatakan novelty absolut; nyatakan cakupan sumber dan waktu pencarian.
- Pengguna dapat membuka bukti yang mendukung setiap klaim.
- Revisi tidak mengganti naskah asli tanpa preview dan persetujuan.
- Sesi dan tahap analisis disimpan persisten.
- Fitur ini tidak boleh mengubah planner generik Core menjadi domain-spesifik tesis.

---

## 7. Alur Kesalahan dan Pemulihan

- Error memiliki kode stabil, pesan pengguna, detail teknis terlog, dan
  `correlation_id`.
- Retry hanya untuk operasi idempotent dan memakai backoff.
- Circuit breaker mencegah kegagalan provider menyebar.
- Artefak parsial diberi status jelas dan dapat dibersihkan.
- Pengguna dapat membatalkan job dan melihat tahap terakhir yang berhasil.
- Insiden keamanan atau integritas membekukan promosi sampai review selesai.
