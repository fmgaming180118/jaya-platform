# 12 — Pembangunan Pilar 12: Immune System

- **ID pilar:** 12
- **Tahap:** 3 — Selubung keamanan
- **Status saat audit:** INTEGRATED — 90%
- **Pemilik:** SECURITY, RUNTIME

## Tujuan

Mendeteksi, mengisolasi, dan memulihkan corruption, policy violation, dependency
abuse, model anomaly, serta perubahan tidak sah pada state JAYA.

## Dependensi

- [Pilar 13 — Cryptographic Skin](09-p13-cryptographic-skin.md)
- [Pilar 18 — Zero Trust](08-p18-zero-trust.md)

## Kontrak dan integrasi

```text
Signals + integrity probes → detection → quarantine/safe-stop → recovery receipt
```

## Checklist implementasi

- [x] Definisikan kelas insiden, severity, source, dan failure code stabil.
- [x] Tambahkan registry/probe integritas untuk artifact Core yang didaftarkan.
- [x] Implementasikan karantina P13, circuit breaker, safe-stop, dan recovery.
- [x] Persistensikan incident ledger dan audit hash-chain tanpa secret.
- [x] Uji corruption, path escape, batas resource, repeated failure, dan restart.
- [x] Demo menunjukkan isolasi serta pemulihan artifact nyata.
- [x] Publikasikan telemetry lokal untuk kelas/severity/state insiden, circuit
  breaker, dan jumlah audit event.
- [ ] Hubungkan feed policy dan exporter telemetry deployment nyata.
- [ ] Jalankan recovery drill serta observasi produksi persisten.

## Exit criteria

Gangguan tidak menyebar ke Core, dependency bermasalah diisolasi, dan sistem
tidak mengaku sehat sebelum recovery probe benar-benar lulus.

## Larangan

Exception handler umum, antivirus branding, atau selalu mengembalikan aman bukan
Immune System.

## Alur nyata saat ini

```text
Artifact terdaftar + DNA attestation
→ probe SHA-256
→ insiden persisten
→ envelope P13 terenkripsi + hapus sumber tidak aman
→ runtime safe-stop
→ artifact approved dipulihkan
→ probe recovery lulus → insiden resolved
```

Dependency yang gagal berulang membuka circuit breaker persisten. Runtime tidak
kembali ready sebelum health probe benar-benar mengembalikan sehat.
