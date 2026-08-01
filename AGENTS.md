# AGENTS.md — Mandatory Rules for JAYA Agents

## 1. Purpose

Semua agent yang membaca, menulis, menguji, merancang, atau meninjau repository JAYA wajib mengikuti dokumen ini.

Tujuan akhir JAYA adalah membangun asisten AI pribadi berdaulat dengan kemampuan fungsional menuju JARVIS.

JAYA Research merupakan laboratorium evolusi kognitif, bukan aplikasi tugas akhir.

Analisis tugas akhir adalah domain adapter dan testbed.

---

## 2. Instruction Priority

Agent mengikuti urutan berikut:

1. kebijakan keselamatan dan keamanan platform;
2. instruksi eksplisit pemilik repository;
3. `AGENTS.md`;
4. `docs/GOVERNANCE.md`;
5. `docs/PRODUCT.md`;
6. `docs/ARCHITECTURE.md`;
7. `docs/DECISIONS.md`;
8. `docs/WORKFLOWS.md`;
9. `docs/STATUS.md`;
10. `docs/ROADMAP.md`;
11. komentar kode dan dokumentasi legacy.

Apabila dua dokumen bertentangan, agent harus mengikuti dokumen dengan prioritas lebih tinggi dan mencatat konflik tersebut.

---

## 3. Mission Preservation

Setiap fitur atau perubahan harus menjawab:

1. Kemampuan JARVIS apa yang didukung?
2. Modul mana yang seharusnya memiliki kemampuan tersebut?
3. Apakah ini kemampuan umum atau domain adapter?
4. Bukti apa yang diperlukan?
5. Bagaimana cara rollback?
6. Apa dampaknya terhadap keamanan, resource, dan privasi?

Perubahan tidak boleh diteruskan apabila tidak memiliki jawaban yang masuk akal.

Agent dilarang mengubah tujuan JAYA menjadi:

* aplikasi tugas akhir;
* chatbot PDF;
* generator karya akademik;
* mesin pencari jurnal;
* aplikasi voice assistant sederhana;
* satu produk domain-spesifik.

Semua fungsi tersebut hanya dapat menjadi bagian dari ekosistem JAYA.

---

## 4. Module Ownership

### JAYA Research

Boleh:

* memperoleh evidence;
* mengelola provenance;
* membangun knowledge store riset;
* mendeteksi gap;
* membentuk hipotesis;
* menjalankan eksperimen;
* melakukan evaluasi;
* menghasilkan candidate artifact;
* menerbitkan kandidat ke outbox.

Dilarang:

* menulis source Core;
* mengubah database aktif Core;
* mengaktifkan kemampuan Core;
* mengubah policy OS;
* memperluas izin Agent;
* memasang model aktif;
* mengirim release Android;
* melakukan auto-promotion.

### JAYA Core

Memiliki:

* reasoning;
* planning;
* cognitive memory;
* model runtime;
* intent;
* cognitive policy;
* candidate readiness check;
* controlled installation interface;
* rollback.

Core tidak boleh mengambil output Research mentah sebagai kebenaran.

### JAYA Agent

Memiliki:

* task orchestration;
* tool routing;
* permission request;
* progress;
* retry;
* cancellation.

Agent tidak memiliki kewenangan mengubah permission miliknya sendiri.

### JAYA OS

Memiliki:

* sandbox;
* filesystem policy;
* network policy;
* process policy;
* resource policy;
* hardware access;
* audit;
* kill switch.

### Interfaces

UI, Android, CLI, dan voice hanya menjadi interface. Interface tidak boleh menjadi sumber kebenaran atau melewati policy backend.

---

## 5. Candidate-Only Rule

Semua hasil keterbaruan memiliki status awal:

```text
CANDIDATE
```

Default wajib:

```text
executable = false
auto_install = false
auto_promote = false
human_review_required = true
```

Istilah berikut dilarang untuk kandidat yang belum dipromosikan:

* applied;
* deployed;
* installed;
* activated;
* learned permanently;
* production-ready;
* verified;
* proven.

Gunakan istilah:

* candidate created;
* indexed in Research;
* awaiting validation;
* awaiting benchmark;
* awaiting approval;
* rejected;
* staged;
* canary;
* rolled back.

---

## 6. Evidence Rules

Output LLM bukan evidence.

Ringkasan bukan pengganti sumber.

Persona ahli bukan reviewer manusia.

Self-score bukan benchmark.

File JSON yang dibuat caller bukan bukti eksekusi.

Fixture sintetis bukan dataset representatif.

Agent wajib membedakan:

* `SOURCE_EVIDENCE`
* `INFERENCE`
* `HYPOTHESIS`
* `SIMULATION`
* `EMPIRICAL_RESULT`
* `HUMAN_REVIEW`
* `VERIFIED_ARTIFACT`

Klaim tanpa evidence harus menghasilkan abstention, limitation, atau status unverified.

---

## 7. Novelty Rules

Agent tidak boleh menyatakan sesuatu baru secara absolut.

Klaim novelty harus menyebut:

* corpus;
* periode pencarian;
* metode;
* query;
* domain;
* sumber yang tidak tersedia;
* confidence;
* keterbatasan.

Novelty yang dihasilkan hanya oleh model memiliki status:

```text
NOVELTY_HYPOTHESIS
```

Bukan:

```text
VERIFIED_NOVELTY
```

---

## 8. Experiment Rules

Eksperimen harus mencatat:

* hypothesis ID;
* dataset dan hash;
* source hashes;
* environment;
* dependency versions;
* seed;
* configuration;
* budget;
* stop rule;
* raw results;
* failed runs;
* uncertainty;
* effect size bila relevan;
* analysis method;
* reproduction status.

Data sintetis harus berlabel `SIMULATION`.

Simulasi tidak boleh dipromosikan menjadi kemampuan aktif.

---

## 9. Promotion Rules

Promotion wajib melalui:

1. evidence validation;
2. provenance validation;
3. license validation;
4. schema validation;
5. integrity validation;
6. sandbox;
7. tests;
8. benchmark;
9. security review;
10. human approval;
11. signature;
12. canary installation;
13. observation;
14. promotion atau rollback.

Kegagalan satu gate menghentikan proses.

Tidak ada emergency bypass untuk perubahan kognitif tanpa keputusan eksplisit pemilik dan catatan audit.

---

## 10. Autonomy Rules

Semua proses otonom membutuhkan:

* consent eksplisit;
* tujuan;
* scope;
* daftar tool;
* resource budget;
* biaya maksimum;
* timeout;
* iteration limit;
* progress;
* audit log;
* cancel;
* kill switch;
* checkpoint;
* recovery.

Loop tanpa batas dilarang.

Startup loop tersembunyi dilarang.

Agent tidak boleh memperpanjang budget atau izin dirinya sendiri.

Agent tidak boleh melakukan aksi destruktif tanpa target spesifik, preview dampak, konfirmasi, dan recovery plan.

---

## 11. Domain Adapter Rules

Fitur khusus domain harus berada di adapter atau boundary yang jelas.

Contoh:

```text
adapters/thesis
adapters/academic
adapters/software_engineering
adapters/home_automation
```

Adapter tidak boleh:

* menambahkan asumsi domain ke generic Core;
* mengubah schema global tanpa kebutuhan umum;
* menjadi dependency wajib bagi Research Core;
* mengubah planner umum menjadi planner domain;
* mengubah proactive engine menjadi domain-specific engine.

Adapter harus dapat dinonaktifkan tanpa menghentikan fungsi inti.

---

## 12. Code Modification Rules

Sebelum mengubah kode, agent wajib:

1. membaca file pemilik konsep;
2. membaca test terkait;
3. memeriksa status Git;
4. mendeteksi perubahan pengguna;
5. menentukan scope;
6. menuliskan acceptance criteria;
7. memahami dependency dan boundary.

Agent dilarang:

* menimpa perubahan pengguna;
* menghapus kode yang tidak dipahami;
* melakukan refactor besar di luar scope;
* membuat duplicate implementation;
* menambahkan fallback yang menyembunyikan error;
* memakai `except Exception: pass`;
* menonaktifkan security check;
* hardcode secret;
* memasukkan data pengguna ke Git;
* mengubah test agar bug terlihat benar;
* mengklaim implementasi selesai hanya karena file tersedia.

---

## 13. Dependency Rules

Dependency baru harus memiliki:

* alasan;
* pemilik;
* lisensi;
* ukuran;
* risiko supply chain;
* kebutuhan network;
* kebutuhan hardware;
* alternatif yang telah dipertimbangkan.

Dependency berat tidak boleh masuk base installation apabila hanya dibutuhkan adapter tertentu.

Gunakan dependency opsional untuk:

* NVIDIA;
* voice;
* OCR berat;
* video;
* Android;
* training;
* model besar.

Target footprint harus diperlakukan sebagai target yang diukur, bukan klaim.

---

## 14. Security and Privacy Rules

Agent tidak boleh commit:

* API key;
* token;
* `.env`;
* private key;
* database runtime;
* PDF pengguna;
* dataset tanpa izin;
* model berlisensi terbatas;
* log sensitif;
* PII;
* credential contoh yang masih aktif.

Data eksternal dianggap tidak tepercaya.

Validasi wajib mencakup:

* path;
* MIME;
* size;
* checksum;
* parser timeout;
* archive traversal;
* symlink;
* network destination;
* license;
* content provenance.

---

## 15. Test Rules

Setiap perubahan perilaku membutuhkan test.

Test harus mencakup:

* happy path;
* invalid input;
* missing dependency;
* timeout;
* permission denial;
* empty evidence;
* conflicting evidence;
* restart;
* duplicate request;
* rollback;
* cross-module violation.

Agent dilarang mengatakan `PASS` ketika test belum dijalankan.

Status laporan yang diperbolehkan:

* `PASS`
* `FAIL`
* `NOT RUN`
* `BLOCKED_EXTERNAL`
* `SMOKE_ONLY`

`PASS_LOCAL` tidak berarti production-ready.

---

## 16. Documentation Rules

Perubahan selesai hanya jika dokumen terkait diselaraskan:

* `PRODUCT.md` untuk tujuan dan scope;
* `ARCHITECTURE.md` untuk ownership;
* `DECISIONS.md` untuk keputusan;
* `WORKFLOWS.md` untuk alur;
* `STATUS.md` untuk fakta;
* `ROADMAP.md` untuk pekerjaan berikutnya;
* `CHANGELOG.md` untuk perubahan penting;
* `DEVELOPMENT.md` untuk command dan setup.

Dokumentasi tidak boleh mengklaim kemampuan yang belum dibuktikan.

Dokumentasi archive tidak menentukan perilaku aktif.

---

## 17. Git Rules

Agent harus bekerja pada branch terpisah apabila perubahan besar dan environment mendukung.

Agent dilarang:

* force push;
* menghapus branch pengguna;
* mengubah history;
* merge ke branch utama;
* membuat release;
* push ke remote;
* menutup issue;
* menghapus tag;

tanpa instruksi eksplisit pemilik.

Commit harus:

* memiliki scope jelas;
* tidak mencampur perubahan tidak terkait;
* tidak menyertakan secret;
* menyebut test yang dijalankan;
* tidak memakai klaim berlebihan.

---

## 18. Reporting Rules

Laporan agent wajib memisahkan:

### Facts

Hal yang benar-benar ditemukan atau dijalankan.

### Inferences

Kesimpulan berdasarkan fakta.

### Proposed Changes

Perubahan yang belum dilakukan.

### Completed Changes

Perubahan yang benar-benar diterapkan.

### Verification

Command dan hasil nyata.

### Remaining Risks

Risiko, dependency, dan bukti yang belum tersedia.

Agent tidak boleh menyembunyikan kegagalan.

Agent tidak boleh mengganti status gagal menjadi warning tanpa alasan teknis yang sah.

---

## 19. Mandatory Stop Conditions

Agent harus berhenti sebelum menjalankan tindakan terkait apabila menemukan:

* secret aktif;
* data pengguna di Git;
* direct Core mutation;
* auto-deployment kognitif;
* permission escalation;
* destructive migration tanpa backup;
* test yang menulis source production;
* benchmark palsu;
* hasil simulasi dilabeli empiris;
* lisensi tidak jelas;
* perubahan user yang berpotensi tertimpa;
* scope yang dapat menyebabkan kehilangan data.

Agent kemudian melaporkan temuan, dampak, serta tindakan aman yang dibutuhkan.

---

## 20. Definition of Done

Pekerjaan hanya selesai ketika:

* misi JAYA tetap terjaga;
* ownership modul benar;
* perubahan modular;
* candidate boundary tidak dilanggar;
* security tidak diturunkan;
* test relevan dijalankan;
* dokumentasi diperbarui;
* status dilaporkan jujur;
* rollback tersedia;
* tidak ada perubahan pengguna yang tertimpa;
* tidak ada klaim melebihi bukti.

Prinsip penutup:

> JAYA boleh meneliti secara otonom, tetapi tidak boleh mempercayai, mengubah, atau memasang hasil penelitiannya secara otonom tanpa bukti, gate, dan otoritas manusia.
