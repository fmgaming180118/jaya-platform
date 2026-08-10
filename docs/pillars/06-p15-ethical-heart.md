# 06 — Pembangunan Pilar 15: Ethical Heart

- **ID pilar:** 15
- **Tahap:** 2 — Fondasi kedaulatan
- **Status saat audit:** INTEGRATED (90%)
- **Pemilik:** SECURITY, RUNTIME

## Tujuan

Menegakkan kebijakan keselamatan, tujuan pemilik, batas hukum, dan kewajiban
human approval sebelum planner atau tool menjalankan aksi berisiko.

## Dependensi

- [Pilar 1 — Pure Logic](01-p01-pure-logic.md)
- [Pilar 11 — DNA Anchor](05-p11-dna-anchor.md)

## Kontrak dan integrasi

```text
DNA actor + capability manifest + payload hash + policy version
→ PolicyDecision
→ allow / deny / require_approval
→ permission sandbox
→ capability adapter
```

Keputusan harus versioned, explainable, signed, dan fail-closed.

Policy tidak menilai izin dari kata atau kalimat di prompt. Approval manusia
harus ditandatangani key pemilik yang terpisah, terikat pada actor, capability,
hash payload, versi policy, expiry, dan nonce satu-kali. Signature receipt oleh
DNA Anchor hanya membuktikan keputusan Core dan tidak boleh dianggap sebagai
approval manusia.

## Checklist implementasi

- [x] Definisikan policy schema, risk class, approval, expiry, dan failure code.
- [x] Implementasikan policy engine deterministic tanpa keyword authorization.
- [x] Tempatkan gate sebelum planner handoff dan setiap `CALL_CAPABILITY`.
- [x] Uji prompt injection, missing policy, stale/wrong approval, replay,
  version conflict, restart, serta tamper.
- [x] Persistensikan policy version dan signed decision receipt hash-chain.
- [x] Demo menunjukkan allow, deny, approval-required, dan approval sah pada
  adapter nyata.
- [ ] Uji trust key melalui HSM/secret manager target, rotasi/appeal, telemetry,
  alarm bypass, dan recovery drill pada deployment persisten.

## Exit criteria

Tidak ada jalur eksekusi yang dapat melewati policy gate, dan policy failure
menghentikan aksi dengan error terstruktur.

Untuk scope lokal yang telah diuji, jalur resmi planner dan `CALL_CAPABILITY`
memenuhi kriteria ini. Status belum `VERIFIED/PRODUCTION` karena pengelolaan
trust key serta observasi deployment masih belum tersedia.

## Larangan

System prompt, daftar kata terlarang, atau self-score model tidak cukup sebagai
Ethical Heart.
