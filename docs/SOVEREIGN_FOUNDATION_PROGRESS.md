# Progres Tahap 2 — Fondasi Kedaulatan

**Status kanonis:** IMPLEMENTED_LOCAL

**Progres tahap:** 92,5%

**Fokus aktif:** validasi deployment Fondasi Kedaulatan

**Checkpoint:** P11 90%; P15 90%; P20 95%; P18 95%

**Terakhir diperbarui:** 14 Agustus 2026

Dokumen ini wajib diperbarui pada setiap sesi pengerjaan Tahap 2. Persentase
hanya berasal dari gate berbobot yang mempunyai test, demo, atau receipt aktual.
Jika pekerjaan berhenti, lanjutkan dari bagian **Checkpoint lanjutan** tanpa
mengandalkan riwayat percakapan.

## Urutan pembangunan

| Urutan | Pilar | Status | Persentase | Dependency |
|---:|---|---|---:|---|
| 1 | P11 DNA Anchor | INTEGRATED | 90% | Pondasi Logika VERIFIED |
| 2 | P15 Ethical Heart | INTEGRATED | 90% | P11 minimal INTEGRATED |
| 3 | P20 Sovereign Privacy | INTEGRATED | 95% | P11 + P15 minimal INTEGRATED |
| 4 | P18 Zero Trust | INTEGRATED | 95% | P11 + P15 + P20 minimal INTEGRATED |
|  | **Tahap 2** | **IMPLEMENTED_LOCAL** | **92,5%** | rata-rata empat pilar |

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

## P20 Sovereign Privacy — gate berbobot 100

- [x] **5% — Kontrak dibekukan:** classification, owner, subject, purpose,
  destination, retention, consent, export, deletion, dan failure code.
- [x] **10% — Consent integrity:** consent Ed25519 terikat owner, subject,
  purpose, provider, data class, expiry, policy version, dan nonce.
- [x] **15% — Purpose/provider gate:** data tidak dapat dipakai untuk purpose
  atau provider di luar izin; default external sharing adalah deny.
- [x] **15% — Encryption at rest:** memory/vault privat memakai AES-GCM dengan
  secret yang diinjeksi dan plaintext tidak tersimpan di SQLite/backup.
- [x] **10% — Retention/deletion:** expiry, revoke, owner deletion, dan tombstone
  receipt bertahan setelah restart.
- [x] **10% — Subject access/export:** hanya owner berotoritas dapat membaca dan
  mengekspor data dengan manifest integrity.
- [x] **10% — Redaction:** structured field, nested value, message, exception,
  telemetry, dan provider error tidak membocorkan secret/data privat.
- [x] **10% — Runtime integration:** episodic memory dan model/provider routing
  melewati privacy gate pada launcher kanonis.
- [x] **5% — Failure/security:** cross-owner, revoked/scoped consent, tamper,
  wrong key, missing provider, backup, dan restart diuji fail-closed.
- [x] **5% — Demo/measurement:** store → restart → access/export → revoke/
  delete menghasilkan receipt aktual serta latency/storage terukur.
- [ ] **5% — Observasi production:** key manager, retention scheduler, telemetry,
  backup deletion, dan recovery drill terbukti pada deployment persisten.

### Threat model P20

- Prompt, memory, artifact, receipt, telemetry, log, backup, dan provider input
  dianggap data sampai classification serta purpose-nya terbukti.
- Keyword seperti `password` bukan classifier dan tidak dapat memberi jaminan
  privacy; data privat tanpa keyword tetap harus terlindungi.
- Enkripsi tidak menggantikan authorization, retention, deletion, atau consent.
- Provider lokal maupun cloud tidak dipercaya hanya dari nama model/provider.
- Backup wajib mempertahankan ciphertext dan deletion semantics yang terukur.

## P18 Zero Trust — gate berbobot 100

- [x] **5% — Kontrak dibekukan:** principal, node, role, capability ACL,
  signed envelope, payload binding, issued/expiry, nonce, dan receipt.
- [x] **10% — Principal registry:** enrollment/revocation persisten dan
  tidak ada trusted source default atau mutable allowlist tanpa authority.
- [x] **15% — Authentication/freshness:** DNA attestation, short-lived envelope,
  clock skew, nonce, signature, serta replay diverifikasi fail-closed.
- [x] **15% — Authorization/least privilege:** actor, node, capability, payload,
  ACL, dan policy receipt harus cocok sebelum invocation.
- [x] **10% — Artifact integrity:** puzzle artifact digest diverifikasi sebelum
  load; artifact yang berubah ditolak sebelum import.
- [x] **15% — Runtime boundary:** `CALL_CAPABILITY` dan direct registry pada
  launcher kanonis melewati Ethical Heart lalu Zero Trust sebelum puzzle.
- [x] **10% — Persistent audit:** keputusan membentuk integrity chain dan
  corrupt/restart/provider failure menghentikan authority.
- [x] **10% — Failure/security:** spoofed node, replay, expired,
  tamper, duplicate, clock failure/skew, dan privilege escalation diuji.
- [x] **5% — Demo/measurement:** signed request → allow/deny/replay/tamper
  menghasilkan receipt aktual serta latency/storage terukur.
- [ ] **5% — Observasi production:** CA/key rotation, distributed clock,
  revocation propagation, telemetry, dan recovery drill terbukti live.

### Threat model P18

- `localhost`, nama proses, source label, possession of file, atau lolos regex
  bukan bukti identitas maupun authority.
- Setiap request dan artifact dianggap hostile sampai signature, freshness,
  scope, payload digest, serta ACL terverifikasi.
- Ethical decision P15 dan privacy decision P20 wajib ada tetapi tidak
  menggantikan authentication P18.

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

**P20 selesai lokal:** auditor gabungan `60 passed`; P20 `95% / INTEGRATED`;
consent Ed25519, purpose/provider default-deny, vault dan memori AES-GCM,
restart, export/delete, redaction, runtime model gate, serta demo terukur lulus.

**P18 selesai lokal:** auditor gabungan `60 passed`; P18 `95% / INTEGRATED`;
principal registry persisten, DNA-bound short-lived envelope, capability ACL,
replay, expiry, node spoof, payload tamper, dual gate runtime, dan demo lulus.

**Tindakan berikutnya:** 7,5% tersisa hanya gate deployment eksternal: secret
manager/HSM, key rotation, retention scheduler, distributed clock, revocation
propagation, telemetry persisten, backup deletion, dan recovery drill. Jangan
menaikkan status menjadi `VERIFIED` atau `PRODUCTION` sebelum bukti itu ada.

### Regression repository keseluruhan

Perintah `python -m pytest -c NUL JAYA_CORE/tests -q` pada 14 Agustus 2026
dijalankan dua kali dari proses baru. Keduanya menghasilkan `652 passed`,
`0 failed`, dan `10 skipped`, masing-masing dalam 293,14 dan 287,75 detik.
Batas memori runtime sekarang memakai RSS baseline + headroom tugas sehingga
tidak bergantung pada posisi tes dalam suite. Verifier deployment memakai
secret privasi ephemeral yang terisolasi untuk child process; ini membuktikan
wiring lokal, bukan integrasi secret manager produksi. Repository lokal green,
tetapi bukti deployment production tetap belum tersedia.

## Hubungan dengan sisa 5% Pondasi Logika

Observasi produksi Pondasi Logika menunggu Tahap 2 dan Tahap 3 karena host
production memerlukan identity, policy, privacy, zero-trust, keystore, dan
artifact authenticity. Ini bukan kekurangan algoritma Pure Logic dan tidak
menghalangi pembangunan pilar berikutnya.
