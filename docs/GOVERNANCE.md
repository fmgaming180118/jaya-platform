# Tata Kelola JAYA

## Tujuan

Tata kelola memastikan dokumentasi tidak kembali bercabang, klaim kemampuan
dapat dibuktikan, dan proses otonom tidak mengambil otoritas dari manusia.

## Sumber kebenaran

- Dokumentasi aktif hanya berada di `docs/`.
- README root adalah pintu masuk; README modul hanya ringkasan dan tautan.
- `docs/archive/` menyimpan riwayat dan tidak menentukan perilaku saat ini.
- `docs/references/` berisi bahan eksternal dan tidak otomatis menjadi requirement.
- Ketika terjadi konflik, urutan kebenaran di [README.md](README.md) berlaku.

Setiap dokumen aktif memiliki tujuan tunggal:

| Dokumen | Memiliki keputusan tentang |
|---|---|
| PRODUCT | masalah, pengguna, scope, non-goal, ukuran sukses |
| ARCHITECTURE | ownership dan batas teknis |
| DECISIONS | keputusan arsitektur aktif dan penggantinya |
| WORKFLOWS | state dan urutan operasi |
| STATUS | bukti kondisi aktual dan risiko |
| ROADMAP | prioritas, dependency, exit criteria |
| GOVERNANCE | aturan perubahan, keamanan, dan persetujuan |
| DEVELOPMENT | cara menjalankan, menguji, dan berkontribusi |

## Aturan status dan bukti

Klaim `VERIFIED` atau `PRODUCTION` harus mencantumkan:

- commit/version yang diuji;
- command, environment, dan dataset;
- output tes serta benchmark aktual;
- cakupan happy path dan failure path;
- risiko yang diterima;
- reviewer/approver dan tanggal;
- cara rollback.

File, endpoint, atau test mock yang tersedia hanya membuktikan implementasi
awal. Boolean seperti `tests_passed=true` dari caller bukan bukti tes. Benchmark
harus berasal dari runner yang benar-benar dieksekusi.

## Perubahan dokumentasi

Perubahan dianggap lengkap jika:

1. Dokumen pemilik konsep diperbarui.
2. `STATUS.md` mencerminkan fakta terbaru.
3. `ROADMAP.md` mencerminkan pekerjaan/exit criteria.
4. `CHANGELOG.md` mencatat perubahan penting.
5. Tautan dan struktur lulus `python scripts/validate_docs.py`.
6. Klaim implementasi memiliki bukti yang dapat diulang.

Dokumen lama dipindahkan ke arsip dengan alasan dan tanggal. Jangan membuat
roadmap baru di module directory.

## Gerbang promosi Research → ekosistem

Promosi kemampuan harus melalui seluruh gate berikut:

| Urutan | Gate | Kondisi lulus |
|---|---|---|
| 1 | Evidence | Sumber, metode, data, hasil, dan batasan lengkap |
| 2 | Reproducibility | Run independen menghasilkan hasil dalam tolerance |
| 3 | Artifact validation | Schema, versi, hash, dependency, dan license valid |
| 4 | Sandbox | Payload tidak mendapat akses di luar izin |
| 5 | Tests | Test runner aktual lulus, termasuk negative/failure cases |
| 6 | Benchmark | Tidak melanggar batas kualitas, latency, memory, dan safety |
| 7 | Security review | Tidak ada secret leak, unsafe permission, atau supply-chain issue |
| 8 | Human approval | Maintainer menyetujui bukti dan dampak |
| 9 | Signature/install | Artefak ditandatangani dan dipasang lewat adapter publik |
| 10 | Observe/rollback | Canary termonitor dan rollback sudah diuji |

Kegagalan satu gate menghentikan promosi. Research tidak boleh menulis file
source Core, Agent, OS, atau Android secara langsung.

## Kebijakan otonomi

Proses otonom memerlukan:

- aktivasi eksplisit pengguna;
- scope, budget waktu/biaya/resource, dan jumlah iterasi;
- izin tool minimum;
- progress dan audit log;
- cancel/kill switch yang selalu tersedia;
- checkpoint dan recovery;
- status `SIMULATION` untuk hasil sintetis;
- review manusia sebelum aksi berdampak lintas modul.

Loop tanpa batas, startup otomatis yang tersembunyi, auto-promotion, dan
auto-deployment perubahan kognitif/policy dilarang.

## Data, privasi, dan secret

- Secret hanya melalui environment/secret store; tidak di source atau dokumen.
- Upload, database, vector store, log, model, dan eksperimen diabaikan Git.
- Data keluar perangkat hanya bila diperlukan dan diketahui pengguna.
- Provider, tujuan, jenis data, retention, dan cara opt-out harus terdokumentasi.
- Dataset training/evaluation memiliki provenance, license, consent, dan versi.
- Log tidak menyimpan key, token, isi dokumen sensitif, atau PII tanpa kebutuhan.

## Keamanan eksekusi

- Semua path eksternal dicanonicalize dan dicegah keluar workspace/sandbox.
- Upload diverifikasi MIME, ukuran, checksum, dan parser timeout.
- Network/tool execution memakai allowlist, quota, timeout, dan circuit breaker.
- Artefak pihak ketiga diverifikasi integrity dan license.
- Perubahan destructive membutuhkan target spesifik dan mekanisme pemulihan.

## Ownership dan review

Perubahan lintas batas memerlukan minimal maintainer modul sumber dan tujuan.
Perubahan Core reasoning, OS policy, Agent permission, model registry, atau
security gate memerlukan review eksplisit. Jika owner formal belum ditetapkan,
maintainer root bertindak sebagai approver sementara dan dicatat di changelog.

## Penanganan konflik dan insiden

1. Bekukan deployment/promosi terkait.
2. Catat fakta di `STATUS.md`, termasuk dampak dan scope.
3. Kembalikan ke artefak/version terakhir yang diketahui aman.
4. Simpan log/bukti tanpa mengekspos data sensitif.
5. Perbaiki code, test, dokumen, dan gate yang gagal.
6. Aktifkan kembali hanya setelah review serta bukti regresi.
