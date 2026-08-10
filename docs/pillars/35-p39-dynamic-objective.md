# 35 — Pembangunan Pilar 39: Dynamic Objective

- **ID pilar:** 39
- **Tahap:** 9 — Ruang kendali
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** MODEL, RUNTIME

## Tujuan

Menyesuaikan prioritas subtujuan terhadap kondisi, risiko, resource, dan
feedback tanpa mengubah tujuan pemilik atau safety invariant.

## Dependensi

- [Pilar 5 — Logical Homeostasis](04-p05-logical-homeostasis.md)
- [Pilar 6 — Stochastic Spontaneity](24-p06-stochastic-spontaneity.md)
- [Pilar 15 — Ethical Heart](06-p15-ethical-heart.md)
- [Pilar 38 — Meta Cognitive Planning](33-p38-meta-cognitive-planning.md)
- [Pilar 40 — Intent Extrapolation](34-p40-intent-extrapolation.md)

## Kontrak dan integrasi

```text
Owner goal + invariants + observations → bounded objective weights → planner
```

## Checklist implementasi

- [ ] Definisikan immutable owner goal, invariant, subgoal, weight, dan bounds.
- [ ] Tautkan perubahan ke evidence, policy decision, dan expiry.
- [ ] Minta approval untuk perubahan scope atau dampak material.
- [ ] Persistensikan objective history serta rollback.
- [ ] Uji goal hijack, reward hacking, conflict, oscillation, dan stale evidence.
- [ ] Demo reprioritization aman pada resource/tool failure nyata.

## Exit criteria

Subgoal dapat berubah dalam batas yang dibuktikan, tetapi owner goal, privacy,
ethics, dan authority tidak dapat ditimpa model.

## Larangan

Model tidak boleh menciptakan tujuan utama baru atau menaikkan authority sendiri.
