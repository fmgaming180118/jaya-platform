# 23 — Pembangunan Pilar 10: Affective Metabolism

- **ID pilar:** 10
- **Tahap:** 6 — Sistem regulasi
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** RUNTIME

## Tujuan

Mengatur urgency, caution, interaction tone, dan escalation sebagai state kontrol
yang transparan—bukan mengklaim JAYA mempunyai emosi manusia.

## Dependensi

- [Pilar 5 — Logical Homeostasis](04-p05-logical-homeostasis.md)
- [Pilar 15 — Ethical Heart](06-p15-ethical-heart.md)
- [Pilar 21 — Lingua Logica](02-p21-lingua-logica.md)

## Kontrak dan integrasi

```text
Task/user signals → bounded control state → planner/tone/escalation policy
```

## Checklist implementasi

- [ ] Definisikan state kontrol, sumber signal, range, decay, dan reset.
- [ ] Pisahkan inferred user state dari fakta dan minta konfirmasi bila penting.
- [ ] Batasi dampak state agar tidak melewati ethics/permission.
- [ ] Persistensikan hanya bila consent dan retention mengizinkan.
- [ ] Uji manipulation, extreme input, stale state, cross-user leak, dan reset.
- [ ] Evaluasi consistency dan false inference pada dataset representatif.

## Exit criteria

State memengaruhi strategi secara terbatas dan dapat dijelaskan, tetapi tidak
mengubah fakta, authority, atau safety decision.

## Larangan

Persona, emoji, sentiment label, atau angka mood hardcode bukan afek nyata.
