# Progres Tahap 3 — Selubung Keamanan

**Status kanonis:** INTEGRATED

**Progres sampai production:** 90%

**Checkpoint:** P13 90%; P14 85%; P16 95%; P12 90%
**Terakhir diperbarui:** 14 Agustus 2026

Seluruh implementasi lokal Tahap 3 sudah selesai dan terhubung ke runtime.
Persentase berasal dari gate berbobot `scripts/audit_security_envelope.py`,
bukan jumlah file. Sepuluh persen tersisa memerlukan hardware, review
independen, dan deployment persisten; bukti tersebut tidak boleh disimulasikan.

## Ringkasan

| Pilar | Status | Nilai | Bukti utama | Bukti eksternal tersisa |
|---|---|---:|---|---|
| P13 Cryptographic Skin | INTEGRATED | 90% | AES-256-GCM, DNA attestation, `.jayac`, backup, puzzle, mesh | anti-rollback dan production drill |
| P14 Hardware Locked | INTEGRATED | 85% | DPAPI machine scope, binding, migration, revocation, clone rejection | TPM/Secure Enclave dan production drill |
| P16 Quantum Resistant | VERIFIED | 95% | liboqs 0.16.0 ML-DSA-65, hybrid signature, lifecycle, capsule, benchmark | independent security review |
| P12 Immune System | INTEGRATED | 90% | integrity probe, encrypted quarantine, circuit breaker, telemetry, recovery | sustained production observation |
| **Tahap 3** | **INTEGRATED** | **90%** | **42 gate test dan 4 demo nyata** | **deployment/hardware eksternal** |

## Arsitektur aktual

```text
DNA Anchor
→ P14 authorizes brain_id + node_id and derives node-bound key context
→ P13 AES-256-GCM seals payload and signs envelope with DNA Ed25519
→ P16 hybrid Ed25519 + ML-DSA-65 signs the P13 envelope
→ one-file JAYA capsule (.jayac)
→ brain / SQLite backup / detachable puzzle / mesh batch
→ P12 integrity and dependency probes
→ quarantine or circuit open → runtime safe-stop
→ verified recovery probe → runtime ready
```

Private key ML-DSA tidak disimpan plaintext. Key tersebut disegel melalui P13
di SQLite, bertahan setelah restart, mendukung rotation lineage, dan revoked key
ditolak. Ed25519 tidak pernah dilabeli quantum-resistant ketika berjalan tanpa
ML-DSA.

## Checklist terukur

### P13 — 90%

- [x] Contract, AEAD, DNA authenticity, lifecycle key/nonce, failure path.
- [x] Runtime dan launcher wiring, restart, audit hash-chain, demo.
- [x] Format `.jayac` untuk brain, backup memory, puzzle, dan mesh.
- [ ] External anti-rollback/KMS evidence — 5%.
- [ ] Sustained production recovery/rotation/rollback drill — 5%.

### P14 — 85%

- [x] Brain/node/instance separation dan explicit enrollment.
- [x] DPAPI machine scope, authorized boot, clone/wrong-root rejection.
- [x] Migration/rewrap, revocation, audit, dan P13 key binding.
- [ ] TPM/Secure Enclave attestation — 10%.
- [ ] Sustained deployment migration/recovery drill — 5%.

DPAPI dilaporkan `hardware_backed: false`; ia bukan bukti TPM.

### P16 — 95%

- [x] Crypto-agility, threat horizon, asset lifetime, downgrade protection.
- [x] Provider nyata `liboqs-python 0.16.0` + `liboqs 0.16.0` ML-DSA-65.
- [x] Hybrid signature membutuhkan Ed25519 dan ML-DSA sekaligus.
- [x] Private-key persistence P13, restart, rotation, old-artifact continuity,
  dan revocation.
- [x] Integrasi launcher/runtime, `.jayac`, detachable puzzle, dan benchmark.
- [ ] Independent cryptographic security review — 5%.

Dependency reproducible tersedia di `JAYA_CORE/requirements-pq.txt`. Import
pertama membutuhkan instalasi liboqs atau toolchain C lokal sesuai dokumentasi
resmi Open Quantum Safe.

### P12 — 90%

- [x] DNA-attested integrity registry dan bounded probe.
- [x] P13 encrypted quarantine, persistent incident ledger, audit hash-chain.
- [x] Persistent dependency circuit breaker dan runtime safe-stop.
- [x] Restart, verified recovery, sanitized security metrics, serta demo.
- [ ] Sustained production telemetry/recovery drill — 10%.

## Bukti terbaru

```text
python scripts/audit_security_envelope.py --json-output temp/security_audit.json
42 passed, 0 failed, 0 skipped
P13 90% | P14 85% | P16 95% | P12 90% | Tahap 3 90%
```

Benchmark P16 aktual pada environment ini:

- public key ML-DSA-65: 1.952 byte;
- signature ML-DSA-65: 3.309 byte;
- capsule hybrid contoh: 8.250 byte;
- sign: 0,697 ms; verify: 0,414 ms pada salah satu demo aktual.

Angka benchmark bukan konstanta produk; jalankan ulang demo untuk environment
lain.

## Perintah verifikasi

```powershell
python -m pip install -r JAYA_CORE/requirements-pq.txt
python scripts/audit_security_envelope.py --json-output temp/security_audit.json
python scripts/demo_quantum_security.py --workspace temp/p16-demo
python scripts/validate_docs.py
python -m pytest JAYA_CORE/tests -q
```

## Batas klaim

Tahap 3 selesai pada tingkat **INTEGRATED** dan siap menjadi dependency tahap
berikutnya. Tahap ini belum `PRODUCTION`: tidak ada kode lokal yang dapat
menggantikan bukti TPM, security review independen, monitoring deployment,
backup operasional, atau rollback drill pada target produksi.
