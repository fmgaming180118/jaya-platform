# Progres Tahap 2 — Fondasi Kedaulatan

**Status kanonis:** IN_PROGRESS  
**Progres tahap:** 45%  
**Fokus aktif:** P20 Sovereign Privacy (P11 dan P15 sudah INTEGRATED)  
**Checkpoint:** P11 90%; P15 90%; lanjutkan dari threat model P20  
**Terakhir diperbarui:** 10 Agustus 2026

Dokumen ini wajib diperbarui pada setiap sesi pengerjaan Tahap 2. Persentase
hanya berasal dari gate berbobot yang mempunyai test, demo, atau receipt aktual.
Jika pekerjaan berhenti, lanjutkan dari bagian **Checkpoint lanjutan** tanpa
mengandalkan riwayat percakapan.

## Urutan pembangunan

| Urutan | Pilar | Status | Persentase | Dependency |
|---:|---|---|---:|---|
| 1 | P11 DNA Anchor | INTEGRATED | 90% | Pondasi Logika VERIFIED |
| 2 | P15 Ethical Heart | INTEGRATED | 90% | P11 minimal INTEGRATED |
| 3 | P20 Sovereign Privacy | NOT_IMPLEMENTED | 0% | P11 + P15 minimal INTEGRATED |
| 4 | P18 Zero Trust | NOT_IMPLEMENTED | 0% | P11 + P15 + P20 minimal INTEGRATED |
|  | **Tahap 2** | **IN_PROGRESS** | **45%** | rata-rata empat pilar |

## P11 DNA Anchor — gate berbobot 100

- [x] **10% — Kontrak:** schema versioned untuk `brain_id`, owner public key,
  lineage, node binding, rotation, revocation, dan failure code.
- [x] **10% — Enrollment:** owner membuat identitas baru melalui input resmi,
  tanpa owner ID, secret, path, atau hardware fingerprint hardcode.
- [x] **10% — Portabilitas:** `brain_id` tetap sama ketika dipindahkan secara
  resmi, sedangkan `node_id` dan session ID tetap terpisah.
- [x] **10% — Keystore terenkripsi:** private key Ed25519 disimpan AES-GCM,
  secret diinjeksikan, dan private material tidak masuk log/database.
- [ ] **5% — Secret manager production:** uji provider OS-keystore/secret
  manager pada target deployment.
- [x] **15% — Challenge-response:** signature, nonce, purpose, expiry, dan
  replay protection diverifikasi secara konstan/fail-closed.
- [x] **10% — Rotation/revocation:** key baru memiliki lineage; key lama yang
  dicabut tidak dapat memperoleh authority.
- [x] **10% — Runtime boot:** runtime utama memuat identity tervalidasi dan
  menolak mode berotoritas bila identity/keystore rusak atau hilang.
- [x] **5% — Persistence/migration:** restart dan migrasi resmi mempertahankan
  identitas; clone tanpa keystore gagal.
- [x] **5% — Failure/security test:** tamper, wrong owner, replay, expired
  challenge, revoked key, lost keystore, dan duplicate enrollment.
- [x] **5% — Demo/measurement:** enrollment → restart → challenge → migration
  menghasilkan receipt aktual dan ukuran/latency dicatat.
- [ ] **5% — Observasi production:** telemetry identity dari deployment
  persisten dan recovery drill dengan secret manager.

## P15 Ethical Heart — gate berbobot 100

- [x] **5% — Kontrak dibekukan:** `PolicyRequest`, `PolicyDecision`, kelas
  risiko, versi policy, approval satu-kali, dan failure code bersifat
  terstruktur; teks prompt bukan input otorisasi.
- [x] **10% — Policy integrity/versioning:** policy immutable disimpan dengan
  digest; perubahan rule wajib menaikkan versi dan konflik gagal tertutup.
- [x] **15% — Keputusan deterministic:** rule yang sama menghasilkan
  `ALLOW`, `DENY`, atau `REQUIRE_APPROVAL` yang sama dan mempunyai reason code.
- [x] **15% — Gate runtime:** planner dan setiap `CALL_CAPABILITY` melewati Ethical Heart
  setelah manifest ditemukan dan sebelum adapter menerima payload.
- [x] **10% — Human approval:** signature Ed25519, actor, policy, capability,
  hash payload, expiry, nonce, serta replay diverifikasi; Core tidak
  menerbitkan approval untuk dirinya sendiri.
- [x] **10% — Decision receipt:** keputusan dipersistensikan sebagai hash-chain
  dan ditandatangani DNA Anchor bila runtime beridentitas.
- [x] **10% — Restart/tamper:** policy dan receipt bertahan setelah restart;
  corrupt database atau policy digest yang berubah menghentikan eksekusi.
- [x] **10% — Failure/security:** policy unavailable, unknown capability,
  privilege escalation, stale/wrong approval, replay, dan payload injection
  diuji fail-closed.
- [x] **5% — Demo/measurement:** allow, deny, approval-required, approval sah,
  serta latency/storage menghasilkan output aktual.
- [ ] **5% — Konfigurasi deployment:** trust key pemilik berasal dari secret
  manager/keystore target dan prosedur rotasi/appeal diuji.
- [ ] **5% — Observasi production:** telemetry policy berkelanjutan, alarm
  bypass/tamper, dan recovery drill telah dibuktikan pada deployment.

### Threat model P15

- Puzzle dan payload dianggap tidak tepercaya; deklarasi `READ_ONLY` dari
  puzzle eksternal tidak otomatis memperoleh izin.
- Prompt injection tidak boleh memodifikasi rule, actor, risk class, policy
  version, atau approval.
- Approval hanya sah untuk satu actor, satu capability, satu hash payload, dan
  satu versi policy dalam jendela waktu terbatas.
- Policy hilang, rusak, conflict, atau tidak terpasang berarti capability tidak
  dijalankan.
- Receipt keputusan membuktikan apa yang diputuskan Core; signature receipt
  bukan pengganti approval manusia.
- Gate P15 tidak menggantikan permission sandbox P18 maupun minimisasi data
  P20; seluruh gate harus lulus secara berurutan.

## Temuan legacy yang harus dihapus dari jalur runtime

- Hardware fingerprint dijadikan identitas otak sehingga otak tidak portabel.
- Kunci enkripsi diturunkan dari fingerprint yang bukan secret.
- Kegagalan decrypt/tamper membuat identitas baru secara diam-diam.
- Token memuat timestamp baru ketika diverifikasi sehingga kontraknya rusak.
- Default storage memakai home directory global dan global singleton.
- `JayaCoreRuntime` memakai `jaya-master` dan `owner` hardcode.
- `created_at`/`registered_at` identity menggunakan tanggal statis.

## Checklist sesi kerja

Sebelum coding:

- [x] Baca dokumen P11, P15, P20, dan P18.
- [x] Cari implementasi identity/DNA existing dan integration point runtime.
- [x] Catat konflik keamanan dan compatibility.
- [x] Bekukan kontrak dan acceptance test P11.

Sesudah setiap vertical slice:

- [x] Jalankan unit, integration, failure-path, persistence, dan restart test.
- [x] Jalankan demo nyata tanpa mock production.
- [x] Perbarui persentase berdasarkan gate yang benar-benar lulus.
- [x] Sinkronkan status kontrak 40 pilar, matriks, index pilar, STATUS, dan
  changelog bila status berubah.
- [x] Catat perintah, jumlah passed/failed/skipped, serta keterbatasan.

## Checkpoint lanjutan

**P11 selesai lokal:** auditor `11 passed`; P11 `90% / INTEGRATED`; demo
enrollment, challenge, rotation, restart, migrasi, signed audit receipt lulus.

**P15 selesai lokal:** auditor `18 passed`; P15 `90% / INTEGRATED`; demo
menunjukkan allow, deny, approval-required, approval sah, adapter hanya dipanggil
setelah izin, dan signed receipt chain valid.

**Tindakan berikutnya:** bekukan data-classification, purpose limitation,
retention, redaction, encryption-at-rest, dan acceptance test P20 Sovereign
Privacy. P20 harus memakai identity serta policy receipt P11/P15 dan tidak boleh
menyamarkan penyimpanan plaintext sebagai privacy.

## Hubungan dengan sisa 5% Pondasi Logika

Observasi produksi Pondasi Logika menunggu Tahap 2 dan Tahap 3 karena host
production memerlukan identity, policy, privacy, zero-trust, keystore, dan
artifact authenticity. Ini bukan kekurangan algoritma Pure Logic dan tidak
menghalangi pembangunan pilar berikutnya.
