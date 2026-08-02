# AGENTS.md — REAL FEATURE IMPLEMENTATION RULES

## 1. Tujuan Dokumen

Dokumen ini wajib dipatuhi oleh setiap AI coding agent yang membaca, mengubah, menguji, atau menambahkan fitur pada repository ini.

Tujuan utama rules ini adalah memastikan agent menghasilkan:

* fitur yang benar-benar berfungsi;
* integrasi nyata dengan sistem;
* implementasi yang dapat digunakan;
* tes yang memeriksa perilaku sebenarnya;
* jalur kegagalan yang jelas;
* hasil yang dapat diverifikasi;
* kode yang tidak bergantung pada hardcode, mock, atau simulasi tersembunyi.

Agent tidak boleh menyebut sebuah fitur selesai hanya karena:

* file sudah dibuat;
* class sudah tersedia;
* endpoint sudah ditambahkan;
* UI sudah muncul;
* test mock berhasil;
* output contoh terlihat benar;
* dokumentasi sudah diperbarui;
* kode dapat di-import;
* fungsi mengembalikan nilai yang diharapkan secara hardcode.

---

# 2. Prinsip Utama

## 2.1 Implementasi Nyata Lebih Penting daripada Dokumentasi

Urutan kerja wajib:

```text
Pahami kebutuhan
→ baca kode existing
→ tentukan integration point
→ implementasikan fitur
→ hubungkan dengan runtime nyata
→ tambahkan test
→ jalankan test
→ jalankan demo nyata
→ ukur hasil
→ baru perbarui dokumentasi
```

Agent dilarang menjadikan perubahan dokumentasi sebagai hasil utama apabila pengguna meminta coding.

Dokumentasi tidak dihitung sebagai implementasi fitur.

---

## 2.2 Vertical Slice Wajib

Setiap fitur harus memiliki satu jalur end-to-end yang benar-benar bekerja.

Contoh:

```text
Request pengguna
→ API atau interface
→ business logic
→ service
→ storage/provider/tool
→ hasil
→ error handling
→ test
```

Fitur belum selesai apabila hanya salah satu lapisan yang dibuat.

Contoh yang tidak lengkap:

* UI dibuat tetapi backend belum ada.
* Endpoint dibuat tetapi hanya mengembalikan contoh JSON.
* Service dibuat tetapi tidak dipanggil runtime.
* Database repository dibuat tetapi tidak dipakai.
* Tool adapter dibuat tetapi tidak pernah dieksekusi.
* Planner membuat langkah tetapi Agent tidak dapat menjalankannya.
* Model contract dibuat tetapi model router tidak menggunakannya.

---

# 3. Larangan Prototype Tersembunyi

Agent dilarang menyebut fitur sebagai selesai apabila implementasi masih:

* prototype;
* proof of concept;
* mock;
* stub;
* placeholder;
* fake provider;
* simulated result;
* hardcoded response;
* in-memory only untuk data yang seharusnya persisten;
* selalu mengembalikan sukses;
* tidak terhubung ke sistem utama;
* hanya bekerja untuk satu input contoh;
* membutuhkan edit manual setelah agent selesai.

Jika memang hanya dapat membuat prototype, agent wajib menulis:

```text
STATUS: PROTOTYPE
BELUM PRODUCTION
BATASAN:
- ...
YANG MASIH HARUS DIIMPLEMENTASIKAN:
- ...
```

Agent dilarang menggunakan kata:

* selesai;
* implemented;
* production-ready;
* fully working;
* integrated;
* verified;

apabila kondisi tersebut belum terbukti melalui eksekusi nyata.

---

# 4. Larangan Hardcode

## 4.1 Hardcode yang Dilarang

Agent tidak boleh hardcode:

* nama pengguna;
* ID pengguna;
* path komputer tertentu;
* API key;
* token;
* credential;
* nama node;
* nama model;
* URL provider;
* port;
* direktori runtime;
* response AI;
* hasil penelitian;
* status sukses;
* nilai benchmark;
* daftar capability aktif;
* resource perangkat;
* hasil eksperimen;
* tanggal dan waktu hasil;
* konfigurasi lingkungan;
* daftar file pengguna;
* permission;
* data test di kode production.

Contoh yang dilarang:

```python
def research(topic: str) -> dict:
    return {
        "status": "success",
        "result": "Arc reactor dapat dibuat menggunakan palladium."
    }
```

Contoh yang dilarang:

```python
if prompt == "buat desain 3d":
    return "Desain berhasil dibuat"
```

Contoh yang dilarang:

```python
API_KEY = "sk-123456"
```

Contoh yang dilarang:

```python
MODEL_PATH = "C:/Users/Fahri/model.gguf"
```

---

## 4.2 Konfigurasi yang Benar

Nilai yang berbeda antar-environment harus berasal dari:

* environment variable;
* configuration file tervalidasi;
* dependency injection;
* database;
* runtime discovery;
* capability registry;
* command-line argument;
* secret manager.

Contoh:

```python
@dataclass(frozen=True)
class RuntimeConfig:
    model_path: Path
    data_dir: Path
    provider_url: str
    request_timeout_seconds: float
```

Semua konfigurasi wajib divalidasi saat startup.

Konfigurasi yang tidak tersedia harus menyebabkan error terstruktur, bukan fallback palsu.

---

# 5. Larangan Mock pada Jalur Production

Mock hanya boleh digunakan di dalam test.

Kode production dilarang menggunakan:

* fake provider;
* dummy model;
* sample response;
* generated random success;
* static experiment result;
* mock database;
* mock tool output.

Jika dependency nyata tidak tersedia, runtime harus mengembalikan status seperti:

```text
PROVIDER_UNAVAILABLE
MODEL_NOT_CONFIGURED
CAPABILITY_UNAVAILABLE
HARDWARE_NOT_AVAILABLE
NETWORK_REQUIRED
PERMISSION_DENIED
BLOCKED_EXTERNAL
```

Runtime tidak boleh mengganti kegagalan dependency dengan hasil buatan.

---

# 6. Implementasi Harus Menggunakan Dependency Nyata

Ketika sebuah fitur membutuhkan dependency, agent wajib:

1. menentukan dependency sebenarnya;
2. memeriksa apakah dependency sudah ada;
3. membuat adapter yang jelas;
4. menghubungkan adapter ke runtime;
5. menangani dependency unavailable;
6. menambahkan health check;
7. menambahkan timeout;
8. menambahkan test untuk jalur gagal;
9. membuat satu demo dengan dependency nyata apabila tersedia.

Contoh untuk desain 3D:

```text
JAYA Core
→ capability negotiation
→ JAYA Agent
→ CAD adapter
→ Blender/FreeCAD/OpenUSD/Omniverse
→ file atau scene nyata
→ hasil diverifikasi
```

Agent tidak boleh menganggap fitur desain 3D selesai hanya karena:

* intent `CREATE_3D_DESIGN` tersedia;
* class `CADCapability` tersedia;
* JSON rencana telah dibuat;
* output menyebut file berhasil dibuat.

Minimal harus ada file geometri nyata atau perubahan scene nyata dari tool yang digunakan.

---

# 7. Definition of Real Feature

Sebuah fitur dianggap nyata hanya jika seluruh kondisi berikut terpenuhi.

## 7.1 Input Nyata

Fitur menerima input melalui jalur resmi:

* API;
* CLI;
* UI;
* event;
* message queue;
* file;
* tool protocol.

Input harus divalidasi.

---

## 7.2 Logic Nyata

Fitur memiliki logic yang:

* memproses input;
* menangani beberapa variasi input;
* tidak bergantung pada satu contoh;
* tidak mengembalikan hasil statis;
* mempunyai error handling;
* mempunyai batas resource;
* mempunyai timeout jika memanggil dependency.

---

## 7.3 Integration Nyata

Fitur digunakan oleh runtime utama.

Agent wajib menunjukkan:

```text
File pemanggil
→ fungsi yang dipanggil
→ dependency
→ hasil
```

Class yang tidak pernah dipakai tidak dihitung sebagai fitur.

---

## 7.4 Output Nyata

Output harus berasal dari proses yang benar-benar terjadi.

Contoh:

* data benar-benar tersimpan di database;
* file benar-benar dibuat;
* model benar-benar dipanggil;
* scene benar-benar diperbarui;
* tool benar-benar dijalankan;
* event benar-benar masuk event log;
* hasil benar-benar dapat dibuka kembali.

---

## 7.5 Persistence Nyata

Data yang harus bertahan setelah restart wajib menggunakan storage persisten.

Agent dilarang memakai dictionary global untuk:

* job;
* session;
* user memory;
* artifact;
* experiment;
* task;
* state penting.

In-memory storage hanya boleh untuk:

* cache;
* working memory;
* test;
* data sementara yang secara eksplisit boleh hilang.

Test wajib membuktikan data tetap tersedia setelah runtime dibuat ulang.

---

## 7.6 Error Nyata

Fitur harus diuji pada kondisi:

* input salah;
* file tidak ditemukan;
* provider tidak tersedia;
* timeout;
* permission ditolak;
* storage penuh;
* dependency gagal;
* response invalid;
* duplikasi request;
* restart;
* resource rendah.

Fitur yang hanya mempunyai happy path belum selesai.

---

# 8. Aturan Repository Existing

Agent wajib menggunakan kode yang sudah ada terlebih dahulu.

Sebelum membuat modul baru, cari:

* class dengan fungsi serupa;
* interface yang sudah ada;
* schema existing;
* service existing;
* repository existing;
* adapter existing;
* test existing;
* configuration existing.

Agent dilarang membuat:

```text
new_core
core_v2
core_v3
final_core
better_core
new_runtime
runtime_fixed
```

hanya untuk menghindari refactor kode lama.

Jika implementasi lama salah, refactor implementasi tersebut secara aman.

Tidak boleh ada dua sumber kebenaran untuk fitur yang sama.

---

# 9. Aturan Scope dan Arsitektur

Sebelum coding, agent wajib menentukan:

```text
Pemilik fitur:
Integration point:
Input:
Output:
Dependency:
Persistence:
Error model:
Security boundary:
Acceptance criteria:
```

Agent tidak boleh menempatkan logika hanya karena file tersebut mudah diubah.

Contoh ownership:

```text
JAYA Core
→ memahami, merencanakan, memilih capability.

JAYA Agent
→ mengeksekusi tool.

JAYA OS
→ izin, sandbox, resource, audit.

JAYA Research
→ evidence, hipotesis, eksperimen, artifact.

Capability Adapter
→ integrasi domain seperti CAD, solver, robotika.
```

JAYA Core tidak boleh mengandung implementasi Blender, Omniverse, OCR, atau device driver secara langsung.

---

# 10. Aturan Interface dan Implementasi

Membuat interface saja tidak cukup.

Setiap interface baru wajib memiliki:

1. minimal satu implementasi production;
2. minimal satu test implementation;
3. wiring ke runtime;
4. health check;
5. failure behavior.

Contoh:

```python
class CADProvider(Protocol):
    def create_scene(self, request: CADRequest) -> CADResult:
        ...
```

Belum dianggap selesai sampai terdapat implementasi seperti:

```python
class OpenUSDProvider:
    ...
```

atau provider nyata lain yang benar-benar dapat menghasilkan scene/file.

Jika provider production belum tersedia, status fitur harus tetap `PROTOTYPE`.

---

# 11. Aturan Todo dan Placeholder

Agent dilarang meninggalkan:

* `TODO`;
* `FIXME`;
* `pass`;
* `NotImplementedError`;
* fungsi kosong;
* return sementara;
* komentar “implement later”;

pada jalur fitur yang disebut selesai.

Pengecualian hanya diperbolehkan untuk scope yang secara eksplisit dinyatakan belum dikerjakan.

Setiap placeholder yang tersisa harus dilaporkan pada hasil akhir.

---

# 12. Aturan Database dan Storage

Agent wajib:

* menggunakan transaction;
* mencegah SQL injection;
* menggunakan migration atau schema version;
* menangani duplicate;
* menangani corruption;
* menutup connection;
* mempunyai indeks yang relevan;
* tidak menyimpan secret;
* tidak menggunakan pickle untuk data tidak tepercaya.

Repository harus mempunyai test:

```text
create
read
update
delete jika diizinkan
duplicate
restart
migration
invalid payload
```

---

# 13. Aturan API

Endpoint baru wajib:

* menggunakan schema input;
* menolak unknown field;
* membatasi ukuran input;
* menggunakan authentication jika diperlukan;
* melakukan authorization;
* mempunyai timeout;
* mengembalikan error code stabil;
* tidak membocorkan stack trace;
* mempunyai idempotency jika operasi dapat diulang;
* mempunyai test API.

Endpoint berikut dilarang:

```python
@app.post("/research")
def research():
    return {"status": "success"}
```

Endpoint harus benar-benar memanggil service atau runtime terkait.

---

# 14. Aturan UI

UI belum dianggap selesai apabila hanya:

* halaman tampil;
* tombol tersedia;
* data dummy muncul;
* loading animation bekerja.

UI dianggap terintegrasi hanya jika:

* mengirim request ke API nyata;
* menampilkan progress nyata;
* menampilkan error nyata;
* dapat membatalkan job bila didukung;
* menampilkan hasil dari backend;
* dapat membuka artifact;
* tidak menampilkan sukses ketika backend gagal.

Agent dilarang menambahkan fake loading yang berakhir dengan hasil statis.

---

# 15. Aturan Model AI

Agent dilarang menyebut rule-based system sebagai model AI.

Agent wajib membedakan:

```text
RULE_BASED
LOCAL_MODEL
REMOTE_MODEL
SIMULATION
MOCK
EMPIRICAL
```

Jika model belum tersedia:

* jangan membuat jawaban palsu;
* jangan hardcode hasil;
* kembalikan status model unavailable;
* gunakan rule-based fallback hanya untuk capability yang memang didukung;
* jelaskan keterbatasannya.

Model harus dimuat secara lazy.

Import package tidak boleh otomatis memuat model besar.

---

# 16. Aturan Penelitian dan Simulasi

JAYA Research tidak boleh menyatakan penemuan hanya berdasarkan:

* output LLM;
* visualisasi 3D;
* simulasi random;
* persona ahli;
* self-score;
* satu solver run;
* data sintetis.

Label wajib:

```text
HYPOTHESIS
SIMULATION
EMPIRICAL
REPRODUCED
REJECTED
UNVERIFIED
```

Simulasi 3D bukan bukti bahwa desain dapat dibuat secara fisik.

Visualisasi Omniverse bukan bukti bahwa hukum fisik terpenuhi.

Hasil solver wajib menyimpan:

* solver;
* solver version;
* input;
* geometry hash;
* mesh;
* boundary condition;
* material;
* environment;
* configuration;
* output;
* convergence status;
* warning;
* uncertainty.

---

# 17. Aturan Test

## 17.1 Test Wajib

Setiap fitur baru wajib memiliki:

* unit test;
* integration test;
* failure-path test;
* persistence test jika menggunakan storage;
* API test jika memiliki endpoint;
* contract test jika lintas modul;
* end-to-end smoke test.

---

## 17.2 Test Tidak Boleh Memalsukan Fitur

Agent dilarang:

* menguji hanya mock;
* menguji return hardcode;
* mengubah expected result agar bug dianggap benar;
* menonaktifkan test lama;
* menambah skip tanpa alasan eksternal;
* menghapus assertion penting;
* menangkap semua exception agar test lulus.

Minimal satu integration test harus menggunakan implementasi production.

Jika dependency eksternal tidak tersedia, integration test dapat diberi status:

```text
BLOCKED_EXTERNAL
```

Tetapi fitur tidak boleh disebut integrated.

---

## 17.3 Test Harus Dijalankan

Agent wajib menjalankan test, bukan hanya menuliskannya.

Laporan harus mencantumkan:

```text
Command:
Exit code:
Passed:
Failed:
Skipped:
Duration:
```

Agent dilarang mengatakan test berhasil tanpa output aktual.

---

# 18. Aturan Demo

Setiap fitur besar harus memiliki demo yang dapat dijalankan.

Demo harus:

* menggunakan runtime production;
* tidak menggunakan response statis;
* menerima input;
* menghasilkan output;
* menunjukkan failure path;
* dapat dijalankan dari repository;
* tidak membutuhkan perubahan manual pada source.

Contoh:

```bash
python scripts/demo_feature.py
```

Demo bukan pengganti test, tetapi menjadi bukti jalur fitur dapat digunakan.

---

# 19. Aturan Benchmark

Fitur yang berkaitan dengan performa wajib diukur.

Dilarang hardcode angka benchmark.

Ukur minimal:

* latency;
* RAM;
* CPU;
* storage;
* waktu startup;
* ukuran artifact;
* jumlah request;
* error rate jika relevan.

Hasil benchmark harus mencantumkan environment.

Klaim seperti:

* ringan;
* cepat;
* hemat RAM;
* berjalan di edge;
* di bawah 200 MB;

dilarang tanpa pengukuran nyata.

---

# 20. Aturan Security

Agent dilarang:

* menonaktifkan authentication;
* menonaktifkan authorization;
* menonaktifkan validation;
* mengizinkan wildcard CORS tanpa alasan;
* menjalankan command shell dari input mentah;
* membuka seluruh filesystem;
* memasukkan secret ke source;
* menyimpan API key di log;
* melewati approval;
* menambah permission secara otomatis.

Fitur yang mengeksekusi tool wajib memiliki:

* allowlist;
* timeout;
* resource limit;
* working directory terbatas;
* audit log;
* cancellation;
* result validation.

---

# 21. Aturan Dependency

Dependency baru hanya boleh ditambahkan jika:

* benar-benar dibutuhkan;
* tidak ada implementasi existing;
* lisensinya sesuai;
* ukurannya diketahui;
* dampak resource diketahui;
* dimasukkan pada layer yang benar;
* tidak membuat base Core menjadi berat.

Dependency domain seperti:

* Omniverse;
* OpenUSD;
* Blender;
* FreeCAD;
* CFD;
* FEA;
* OCR;
* voice;
* CUDA;

harus bersifat optional capability.

---

# 22. Aturan Perubahan Besar

Untuk perubahan besar, agent wajib:

1. membuat branch terpisah jika tool tersedia;
2. memeriksa Git status;
3. tidak menimpa perubahan pengguna;
4. membuat perubahan bertahap;
5. menjalankan test setiap tahap penting;
6. tidak melakukan merge atau push tanpa instruksi eksplisit.

Agent dilarang melakukan refactor seluruh repository tanpa kebutuhan fitur.

---

# 23. Mandatory Implementation Checklist

Sebelum menyatakan fitur selesai, agent wajib menjawab `YA` pada seluruh pertanyaan berikut.

```text
[ ] Apakah ada source code production yang berubah?
[ ] Apakah fitur dipanggil oleh runtime utama?
[ ] Apakah input divalidasi?
[ ] Apakah output berasal dari proses nyata?
[ ] Apakah tidak ada response hardcode?
[ ] Apakah dependency nyata digunakan?
[ ] Apakah dependency failure ditangani?
[ ] Apakah data penting persisten?
[ ] Apakah restart telah diuji?
[ ] Apakah error path diuji?
[ ] Apakah permission diuji?
[ ] Apakah timeout tersedia?
[ ] Apakah unit test berjalan?
[ ] Apakah integration test berjalan?
[ ] Apakah demo berjalan?
[ ] Apakah hasil aktual diperiksa?
[ ] Apakah dokumentasi sesuai implementasi?
[ ] Apakah tidak ada TODO pada jalur utama?
[ ] Apakah tidak ada mock dalam production?
[ ] Apakah status fitur tidak dibesar-besarkan?
```

Satu jawaban `TIDAK` berarti fitur belum selesai.

---

# 24. Mandatory Stop Conditions

Agent harus berhenti dan melaporkan masalah apabila menemukan:

* secret aktif;
* data pengguna masuk Git;
* perubahan pengguna akan tertimpa;
* direct mutation ke Core;
* auto-deployment;
* migration destruktif tanpa backup;
* permission escalation;
* mock digunakan di production;
* benchmark palsu;
* test palsu;
* hasil simulasi diberi label empirical;
* dependency tidak legal;
* fitur tidak mungkin diimplementasikan tanpa dependency eksternal.

Berhenti tidak berarti menghapus fitur.

Agent harus menjelaskan:

```text
Masalah:
Dampak:
Bagian yang berhasil:
Bagian yang belum berhasil:
Dependency yang dibutuhkan:
Langkah aman berikutnya:
```

---

# 25. Status Fitur yang Diperbolehkan

Gunakan salah satu status:

```text
IDEA
PLANNED
PROTOTYPE
IMPLEMENTED_LOCAL
INTEGRATED
VERIFIED
PRODUCTION
BLOCKED_EXTERNAL
FAILED
```

Definisi:

## IDEA

Belum ada implementasi.

## PLANNED

Sudah ada desain tetapi belum ada kode bekerja.

## PROTOTYPE

Ada kode percobaan tetapi belum terintegrasi atau masih memakai mock/simulasi.

## IMPLEMENTED_LOCAL

Fitur bekerja lokal dengan dependency yang tersedia dan memiliki test.

## INTEGRATED

Fitur terhubung end-to-end dengan dependency nyata.

## VERIFIED

Fitur telah diuji pada environment representatif dan batas utamanya diketahui.

## PRODUCTION

Fitur telah deployed, termonitor, aman, mempunyai backup dan rollback.

Agent tidak boleh langsung menaikkan status dari PROTOTYPE ke PRODUCTION.

---

# 26. Definition of Done

Fitur dianggap selesai hanya jika:

1. implementasi production tersedia;
2. tidak ada response hardcode;
3. tidak ada mock pada jalur production;
4. runtime benar-benar memanggil implementasi;
5. dependency nyata terhubung;
6. input dan output tervalidasi;
7. error handling tersedia;
8. data penting persisten;
9. test relevan lulus;
10. demo berjalan;
11. hasil aktual diperiksa;
12. resource diukur jika relevan;
13. security boundary tidak diturunkan;
14. dokumentasi mencerminkan kondisi aktual;
15. rollback tersedia untuk perubahan berisiko;
16. seluruh keterbatasan dilaporkan.

---

# 27. Format Laporan Akhir Agent

Agent wajib memberikan laporan berikut.

## A. Implementasi Nyata

```text
File | Class/Function | Perilaku nyata
```

## B. Integrasi

```text
Input
→ Runtime
→ Service
→ Dependency
→ Output
```

## C. Hardcode dan Prototype yang Dihapus

```text
File | Masalah lama | Perbaikan
```

## D. Test

```text
Command | Status | Passed | Failed | Skipped
```

## E. Demo

```text
Command:
Input:
Output aktual:
Artifact yang dihasilkan:
```

## F. Dependency Nyata

```text
Dependency | Versi | Fungsi | Status koneksi
```

## G. Hal yang Belum Selesai

Gunakan status:

```text
PROTOTYPE
BLOCKED_EXTERNAL
NOT IMPLEMENTED
```

## H. Risiko

Urutkan:

```text
P0
P1
P2
```

## I. Kesimpulan Jujur

Agent wajib menyatakan salah satu:

```text
FITUR BELUM SELESAI
FITUR IMPLEMENTED_LOCAL
FITUR INTEGRATED
FITUR VERIFIED
```

Agent dilarang memberikan kesimpulan yang lebih tinggi daripada bukti aktual.

---

# 28. Instruksi Penutup

Ketika pengguna meminta fitur:

* jangan hanya menulis dokumentasi;
* jangan hanya membuat class;
* jangan hanya membuat endpoint;
* jangan hanya membuat mock;
* jangan hanya membuat JSON contoh;
* jangan hanya membuat test yang memalsukan dependency;
* jangan berhenti setelah audit;
* jangan meminta pengguna menyelesaikan coding secara manual.

Lakukan coding nyata sejauh environment dan dependency memungkinkan.

Prinsip utama:

> Sebuah fitur belum ada sampai input nyata melewati sistem nyata, menggunakan implementasi nyata, menghasilkan output nyata, bertahan terhadap kegagalan, dan dibuktikan melalui test serta demo yang benar-benar dijalankan.
