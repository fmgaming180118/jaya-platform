# 12 — Pembangunan Pilar 12: Immune System

- **ID pilar:** 12
- **Tahap:** 3 — Selubung keamanan
- **Status saat audit:** NOT_IMPLEMENTED
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

- [ ] Definisikan kelas insiden, severity, signal source, dan response policy.
- [ ] Tambahkan integrity monitor untuk brain, model, memory, dan puzzle pack.
- [ ] Implementasikan quarantine, circuit breaker, safe-stop, dan recovery.
- [ ] Persistensikan incident ledger tanpa menyimpan secret.
- [ ] Uji corruption, malicious pack, repeated failure, false positive, dan restart.
- [ ] Demo menunjukkan isolasi serta rollback artifact nyata.

## Exit criteria

Gangguan tidak menyebar ke Core, dependency bermasalah diisolasi, dan sistem
tidak mengaku sehat sebelum recovery probe benar-benar lulus.

## Larangan

Exception handler umum, antivirus branding, atau selalu mengembalikan aman bukan
Immune System.
